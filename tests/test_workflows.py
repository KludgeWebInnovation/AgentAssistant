from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import select

from app.models import (
    Account,
    AgencyProfile,
    ComplianceSettings,
    Contact,
    ICPProfile,
    LeadState,
    OfferProfile,
    Sequence,
    SequenceStep,
    SequenceTemplate,
    StepStatus,
)
from app.services.ai import OpenAIService
from app.services.importer import import_contacts
from app.services.replies import handle_reply
from app.services.sequences import approve_step, generate_research_brief, generate_sequence, record_manual_send


def seed_contact(session, fixtures_dir):
    import_contacts(session, "cognism_sample.csv", (fixtures_dir / "cognism_sample.csv").read_bytes())
    session.commit()
    contact = session.exec(select(Contact).where(Contact.email == "jane@acme.io")).first()
    account = session.get(Account, contact.account_id)
    return contact, account


def test_generates_research_and_default_sequence(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency = session.exec(select(AgencyProfile)).first()
    offer = session.exec(select(OfferProfile)).first()
    icp = session.exec(select(ICPProfile)).first()
    template = session.exec(select(SequenceTemplate)).first()
    compliance = session.exec(select(ComplianceSettings)).first()

    ai = OpenAIService()
    package = ai.generate_research_package(account.company_name, account.company_website, contact, agency, offer, icp, compliance, template)
    brief = generate_research_brief(session, contact, package)
    sequence = generate_sequence(session, contact, template, package)
    session.commit()

    steps = session.exec(select(SequenceStep).where(SequenceStep.sequence_id == sequence.id).order_by(SequenceStep.step_order)).all()

    assert brief.summary
    assert len(steps) == 4
    assert steps[0].channel == "email"
    assert steps[1].channel == "linkedin"
    assert contact.lead_state == LeadState.DRAFT_READY


def test_approving_and_sending_updates_next_due_date(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency = session.exec(select(AgencyProfile)).first()
    offer = session.exec(select(OfferProfile)).first()
    icp = session.exec(select(ICPProfile)).first()
    template = session.exec(select(SequenceTemplate)).first()
    compliance = session.exec(select(ComplianceSettings)).first()

    package = OpenAIService().generate_research_package(account.company_name, account.company_website, contact, agency, offer, icp, compliance, template)
    generate_research_brief(session, contact, package)
    sequence = generate_sequence(session, contact, template, package)
    session.flush()

    steps = session.exec(select(SequenceStep).where(SequenceStep.sequence_id == sequence.id).order_by(SequenceStep.step_order)).all()
    first_step, second_step = steps[0], steps[1]

    approve_step(session, contact, first_step)
    assert first_step.status == StepStatus.APPROVED
    assert contact.lead_state == LeadState.APPROVED

    record_manual_send(session, contact, first_step, "Sent via Gmail manually.")
    session.commit()

    assert first_step.status == StepStatus.SENT_MANUALLY
    assert second_step.due_date == first_step.sent_at.date() + timedelta(days=second_step.delay_days)
    assert contact.lead_state == LeadState.WAITING


def test_positive_reply_pauses_sequence_and_includes_booking_link(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency = session.exec(select(AgencyProfile)).first()
    offer = session.exec(select(OfferProfile)).first()
    icp = session.exec(select(ICPProfile)).first()
    template = session.exec(select(SequenceTemplate)).first()
    compliance = session.exec(select(ComplianceSettings)).first()

    package = OpenAIService().generate_research_package(account.company_name, account.company_website, contact, agency, offer, icp, compliance, template)
    generate_research_brief(session, contact, package)
    sequence = generate_sequence(session, contact, template, package)
    session.flush()

    event = handle_reply(
        session=session,
        ai_service=OpenAIService(),
        account_name=account.company_name,
        contact=contact,
        reply_text="This sounds good. Happy to book a call.",
        offer=offer,
        compliance=compliance,
    )
    session.commit()

    steps = session.exec(select(SequenceStep).where(SequenceStep.sequence_id == sequence.id)).all()
    db_sequence = session.get(Sequence, sequence.id)

    assert contact.lead_state == LeadState.REPLIED
    assert compliance.booking_link in event.suggested_response
    assert db_sequence.status == "paused"
    assert all(step.status in {StepStatus.CANCELED, StepStatus.PENDING} or step.status == StepStatus.SENT_MANUALLY for step in steps)
    assert not any(step.status in {StepStatus.PENDING, StepStatus.APPROVED} for step in steps)


def test_opt_out_marks_contact_do_not_contact(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency = session.exec(select(AgencyProfile)).first()
    offer = session.exec(select(OfferProfile)).first()
    icp = session.exec(select(ICPProfile)).first()
    template = session.exec(select(SequenceTemplate)).first()
    compliance = session.exec(select(ComplianceSettings)).first()

    package = OpenAIService().generate_research_package(account.company_name, account.company_website, contact, agency, offer, icp, compliance, template)
    generate_research_brief(session, contact, package)
    sequence = generate_sequence(session, contact, template, package)
    session.flush()

    event = handle_reply(
        session=session,
        ai_service=OpenAIService(),
        account_name=account.company_name,
        contact=contact,
        reply_text="Please remove me from your outreach.",
        offer=offer,
        compliance=compliance,
    )
    session.commit()

    open_steps = session.exec(
        select(SequenceStep)
        .where(SequenceStep.sequence_id == sequence.id, SequenceStep.status.in_([StepStatus.PENDING, StepStatus.APPROVED]))
    ).all()

    assert event.reply_intent.value == "opt_out"
    assert contact.lead_state == LeadState.DO_NOT_CONTACT
    assert contact.do_not_contact is True
    assert open_steps == []


def test_discovery_suggestions_are_generated(session):
    offer = session.exec(select(OfferProfile)).first()
    icp = session.exec(select(ICPProfile)).first()

    suggestions = OpenAIService().generate_discovery_suggestions(offer, icp, count=3)

    assert len(suggestions) == 3
    assert all(item.segment for item in suggestions)
    assert all(item.search_hint for item in suggestions)

