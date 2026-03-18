from __future__ import annotations

from sqlmodel import select

from app.models import Account, Contact
from app.services.importer import import_contacts


def test_imports_and_dedupes_contacts(session, fixtures_dir):
    first = (fixtures_dir / "cognism_sample.csv").read_bytes()
    second = (fixtures_dir / "salesforce_sample.csv").read_bytes()

    first_summary = import_contacts(session, "cognism_sample.csv", first)
    second_summary = import_contacts(session, "salesforce_sample.csv", second)
    session.commit()

    contacts = session.exec(select(Contact)).all()
    accounts = session.exec(select(Account)).all()

    assert first_summary.created_contacts == 2
    assert second_summary.updated_contacts >= 1
    assert len(contacts) == 3
    assert len(accounts) == 2

    jane = session.exec(select(Contact).where(Contact.email == "jane@acme.io")).first()
    assert jane is not None
    assert jane.source_system == "Salesforce"
    assert "High intent from webinar list" in jane.provenance_notes

