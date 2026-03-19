from __future__ import annotations

from datetime import timedelta

from sqlmodel import select

from app.models import (
    Account,
    AgencyProfile,
    ApprovedExample,
    CompanyResearchBrief,
    ComplianceSettings,
    Contact,
    ContactResearchBrief,
    DraftFeedbackEvent,
    ICPProfile,
    LeadState,
    MessagingExample,
    ObjectionRule,
    OfferProfile,
    ProofPoint,
    ResearchSource,
    SalesPlaybook,
    Sequence,
    SequenceStep,
    SequenceTemplate,
    StepStatus,
)
from app.services.ai import OpenAIService
from app.services.importer import import_contacts
from app.services.replies import handle_reply
from app.services.research import ResearchService, ResearchSourceDraft
from app.services.sequences import (
    approve_step,
    generate_research_brief,
    generate_sequence,
    record_manual_send,
    save_step_feedback,
)


def seed_contact(session, fixtures_dir):
    import_contacts(session, "cognism_sample.csv", (fixtures_dir / "cognism_sample.csv").read_bytes())
    session.commit()
    contact = session.exec(select(Contact).where(Contact.email == "jane@acme.io")).first()
    account = session.get(Account, contact.account_id)
    return contact, account


def _load_generation_context(session):
    return (
        session.exec(select(AgencyProfile)).first(),
        session.exec(select(OfferProfile)).first(),
        session.exec(select(ICPProfile)).first(),
        session.exec(select(SequenceTemplate)).first(),
        session.exec(select(ComplianceSettings)).first(),
        session.exec(select(SalesPlaybook)).first(),
        session.exec(select(MessagingExample)).all(),
        session.exec(select(ObjectionRule)).all(),
        session.exec(select(ProofPoint)).all(),
        session.exec(select(ApprovedExample)).all(),
    )


def test_generates_research_and_default_sequence(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency, offer, icp, template, compliance, playbook, examples, objections, proof_points, approved_examples = _load_generation_context(session)

    ai = OpenAIService()
    package = ai.generate_research_package(
        account.company_name,
        account.company_website,
        contact,
        agency,
        offer,
        icp,
        compliance,
        template,
        playbook=playbook,
        messaging_examples=examples,
        objection_rules=objections,
        proof_points=proof_points,
        approved_examples=approved_examples,
    )
    brief = generate_research_brief(session, contact, package)
    sequence = generate_sequence(session, contact, template, package)
    session.commit()

    steps = session.exec(select(SequenceStep).where(SequenceStep.sequence_id == sequence.id).order_by(SequenceStep.step_order)).all()

    assert brief.summary
    assert len(steps) == 4
    assert steps[0].channel == "email"
    assert steps[1].channel == "linkedin"
    assert contact.lead_state == LeadState.DRAFT_READY
    assert "Booked meetings" in steps[0].body or "booked meetings" in steps[0].body.lower()


def test_approving_and_sending_updates_next_due_date(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency, offer, icp, template, compliance, *_ = _load_generation_context(session)

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
    feedback = session.exec(select(DraftFeedbackEvent).where(DraftFeedbackEvent.sequence_step_id == first_step.id)).all()
    assert {item.feedback_type for item in feedback} >= {"approved", "sent_manually"}


def test_positive_reply_pauses_sequence_and_includes_booking_link(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency, offer, icp, template, compliance, *_ = _load_generation_context(session)

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
    agency, offer, icp, template, compliance, *_ = _load_generation_context(session)

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
    playbook = session.exec(select(SalesPlaybook)).first()
    proof_points = session.exec(select(ProofPoint)).all()

    suggestions = OpenAIService().generate_discovery_suggestions(offer, icp, count=3, playbook=playbook, proof_points=proof_points)

    assert len(suggestions) == 3
    assert all(item.segment for item in suggestions)
    assert all(item.search_hint for item in suggestions)


def test_research_service_persists_company_and_contact_briefs(session, fixtures_dir, monkeypatch):
    contact, account = seed_contact(session, fixtures_dir)
    icp = session.exec(select(ICPProfile)).first()
    playbook = session.exec(select(SalesPlaybook)).first()
    service = ResearchService()

    def fake_fetch(url, source_kind, account_scope=False, contact_scope=False):
        return ResearchSourceDraft(
            source_kind=source_kind,
            title="Public page",
            url=url,
            snippet="Acme AI helps revenue teams qualify and prioritize outbound opportunities across Europe.",
            account_scope=account_scope,
            contact_scope=contact_scope,
        )

    monkeypatch.setattr(service, "_fetch_public_page", fake_fetch)
    bundle = service.collect_bundle(account, contact, icp, playbook)
    company_brief, contact_brief = service.persist_bundle(session, account, contact, bundle)
    session.commit()

    stored_sources = session.exec(select(ResearchSource)).all()
    stored_company = session.exec(select(CompanyResearchBrief).where(CompanyResearchBrief.account_id == account.id)).first()
    stored_contact = session.exec(select(ContactResearchBrief).where(ContactResearchBrief.contact_id == contact.id)).first()

    assert company_brief.summary
    assert contact_brief.role_summary
    assert stored_company is not None
    assert stored_contact is not None
    assert len(stored_sources) >= 2


def test_feedback_edits_can_create_approved_examples(session, fixtures_dir):
    contact, account = seed_contact(session, fixtures_dir)
    agency, offer, icp, template, compliance, *_ = _load_generation_context(session)

    package = OpenAIService().generate_research_package(account.company_name, account.company_website, contact, agency, offer, icp, compliance, template)
    generate_research_brief(session, contact, package)
    sequence = generate_sequence(session, contact, template, package)
    session.flush()

    first_step = session.exec(
        select(SequenceStep).where(SequenceStep.sequence_id == sequence.id, SequenceStep.step_order == 1)
    ).first()
    save_step_feedback(
        session,
        contact,
        first_step,
        subject="Sharper founder intro",
        body="Updated body with clearer value proposition and proof.",
        feedback_note="Tightened the opener and made the proof more specific.",
        save_as_example=True,
    )
    session.commit()

    approved = session.exec(select(ApprovedExample).where(ApprovedExample.sequence_step_id == first_step.id)).first()
    feedback = session.exec(select(DraftFeedbackEvent).where(DraftFeedbackEvent.sequence_step_id == first_step.id)).all()

    assert approved is not None
    assert approved.subject == "Sharper founder intro"
    assert {item.feedback_type for item in feedback} >= {"draft_edit", "approved_example"}


def test_authenticated_contact_page_has_explicit_home_navigation(client, session, fixtures_dir):
    contact, _ = seed_contact(session, fixtures_dir)

    login_response = client.post("/login", data={"username": "admin", "password": "change-me"})
    assert login_response.status_code in {200, 303}

    response = client.get(f"/contacts/{contact.id}")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Playbook" in response.text
    assert "Back to contacts" in response.text
