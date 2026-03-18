from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.models import Account, AuditEvent, Contact, LeadSource, LeadState, utcnow


@dataclass
class ImportSummary:
    created_accounts: int = 0
    created_contacts: int = 0
    updated_contacts: int = 0
    skipped_rows: int = 0
    errors: list[str] = field(default_factory=list)


def import_contacts(session: Session, filename: str, content: bytes) -> ImportSummary:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    summary = ImportSummary()
    lead_source = LeadSource(
        name=filename,
        source_type="csv",
        description=f"Imported from {filename}",
        row_count=0,
    )
    session.add(lead_source)
    session.flush()

    for line_number, raw_row in enumerate(reader, start=2):
        row = {key.strip().lower(): (value or "").strip() for key, value in raw_row.items() if key}
        company_name = row.get("company_name", "")
        email = row.get("email", "").lower()
        linkedin_url = row.get("linkedin_url", "")

        if not company_name:
            summary.skipped_rows += 1
            summary.errors.append(f"Line {line_number}: missing company_name.")
            continue
        if not email and not linkedin_url:
            summary.skipped_rows += 1
            summary.errors.append(f"Line {line_number}: at least one of email or linkedin_url is required.")
            continue

        account = _find_account(session, company_name, row.get("company_website", ""))
        if account is None:
            account = Account(
                company_name=company_name,
                company_website=row.get("company_website", ""),
                country=row.get("country", ""),
                notes=row.get("notes", ""),
            )
            session.add(account)
            session.flush()
            summary.created_accounts += 1
        else:
            if row.get("company_website") and not account.company_website:
                account.company_website = row["company_website"]
            if row.get("country") and not account.country:
                account.country = row["country"]
            if row.get("notes"):
                account.notes = _join_notes(account.notes, row["notes"])
            account.updated_at = utcnow()

        contact = _find_contact(
            session=session,
            email=email,
            linkedin_url=linkedin_url,
            account_id=account.id,
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
        )
        if contact is None:
            contact = Contact(
                account_id=account.id,
                first_name=row.get("first_name", ""),
                last_name=row.get("last_name", ""),
                job_title=row.get("job_title", ""),
                email=email,
                linkedin_url=linkedin_url,
                country=row.get("country", ""),
                source_system=row.get("source_system", ""),
                source_list=row.get("source_list", ""),
                provenance_notes=row.get("notes", ""),
                import_date=date.today(),
                lead_state=LeadState.NEW,
            )
            session.add(contact)
            session.flush()
            summary.created_contacts += 1
            _log_event(session, contact.id, "contact_imported", f"Created from {filename}.")
        else:
            _merge_contact(contact, row)
            contact.updated_at = utcnow()
            contact.last_activity_at = utcnow()
            summary.updated_contacts += 1
            _log_event(session, contact.id, "contact_imported", f"Updated from {filename}.")

    lead_source.row_count = summary.created_contacts + summary.updated_contacts
    session.flush()
    return summary


def _find_account(session: Session, company_name: str, company_website: str) -> Account | None:
    statement = select(Account).where(func.lower(Account.company_name) == company_name.lower())
    if company_website:
        statement = statement.where(
            or_(
                func.lower(Account.company_website) == company_website.lower(),
                Account.company_website == "",
            )
        )
    return session.exec(statement).first()


def _find_contact(
    session: Session,
    email: str,
    linkedin_url: str,
    account_id: int | None,
    first_name: str,
    last_name: str,
) -> Contact | None:
    if email:
        contact = session.exec(select(Contact).where(func.lower(Contact.email) == email.lower())).first()
        if contact:
            return contact
    if linkedin_url:
        contact = session.exec(select(Contact).where(func.lower(Contact.linkedin_url) == linkedin_url.lower())).first()
        if contact:
            return contact
    if account_id and (first_name or last_name):
        return session.exec(
            select(Contact).where(
                Contact.account_id == account_id,
                func.lower(Contact.first_name) == first_name.lower(),
                func.lower(Contact.last_name) == last_name.lower(),
            )
        ).first()
    return None


def _merge_contact(contact: Contact, row: dict[str, str]) -> None:
    contact.first_name = contact.first_name or row.get("first_name", "")
    contact.last_name = contact.last_name or row.get("last_name", "")
    contact.job_title = contact.job_title or row.get("job_title", "")
    contact.email = contact.email or row.get("email", "").lower()
    contact.linkedin_url = contact.linkedin_url or row.get("linkedin_url", "")
    contact.country = contact.country or row.get("country", "")
    contact.source_system = row.get("source_system", "") or contact.source_system
    contact.source_list = row.get("source_list", "") or contact.source_list
    if row.get("notes"):
        contact.provenance_notes = _join_notes(contact.provenance_notes, row["notes"])


def _join_notes(existing: str, incoming: str) -> str:
    if not existing:
        return incoming
    if incoming in existing:
        return existing
    return f"{existing}\n{incoming}"


def _log_event(session: Session, contact_id: int, event_type: str, detail: str) -> None:
    session.add(AuditEvent(contact_id=contact_id, event_type=event_type, detail=detail))

