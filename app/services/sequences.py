from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import (
    ApprovedExample,
    ApprovalTask,
    AuditEvent,
    Contact,
    DraftFeedbackEvent,
    LeadState,
    ResearchBrief,
    Sequence,
    SequenceStep,
    SequenceTemplate,
    StepStatus,
    utcnow,
)
from app.services.ai import ResearchPackage


def generate_research_brief(
    session: Session,
    contact: Contact,
    package: ResearchPackage,
) -> ResearchBrief:
    existing = session.exec(select(ResearchBrief).where(ResearchBrief.contact_id == contact.id)).first()
    if existing is None:
        existing = ResearchBrief(contact_id=contact.id)
        session.add(existing)
    existing.summary = package.summary
    existing.pain_hypothesis = package.pain_hypothesis
    existing.personalization_notes = package.personalization_notes
    existing.provenance_summary = package.provenance_summary
    existing.raw_model_output = package.raw_model_output
    existing.generated_at = utcnow()
    contact.lead_state = LeadState.RESEARCH_READY
    contact.last_activity_at = utcnow()
    session.add(AuditEvent(contact_id=contact.id, event_type="research_generated", detail="Research brief refreshed."))
    session.flush()
    return existing


def generate_sequence(
    session: Session,
    contact: Contact,
    template: SequenceTemplate,
    package: ResearchPackage,
) -> Sequence:
    for sequence in session.exec(select(Sequence).where(Sequence.contact_id == contact.id)).all():
        if sequence.status in {"active", "paused"}:
            sequence.status = "superseded"
    for step in _contact_steps(session, contact.id):
        if step.status in {StepStatus.PENDING, StepStatus.APPROVED}:
            step.status = StepStatus.CANCELED
    for task in session.exec(select(ApprovalTask).where(ApprovalTask.contact_id == contact.id, ApprovalTask.status == "open")).all():
        task.status = "canceled"
        task.resolved_at = utcnow()

    sequence = Sequence(contact_id=contact.id, template_name=template.name, status="active")
    session.add(sequence)
    session.flush()

    delays = _parse_int_csv(template.delay_days, default=[0, 2, 3, 4])
    due_cursor = date.today()
    for index, draft in enumerate(package.steps):
        delay_days = delays[index] if index < len(delays) else 2
        if index == 0:
            due_cursor = date.today() + timedelta(days=delay_days)
        else:
            due_cursor = due_cursor + timedelta(days=delay_days)
        step = SequenceStep(
            sequence_id=sequence.id,
            step_order=index + 1,
            channel=draft.channel,
            label=draft.label,
            delay_days=delay_days,
            subject=draft.subject,
            body=draft.body,
            due_date=due_cursor,
            status=StepStatus.PENDING,
        )
        session.add(step)
        session.flush()
        session.add(ApprovalTask(contact_id=contact.id, sequence_step_id=step.id, note=f"Review {draft.label}"))

    contact.lead_state = LeadState.DRAFT_READY
    contact.last_activity_at = utcnow()
    session.add(AuditEvent(contact_id=contact.id, event_type="sequence_generated", detail=f"Sequence created from template {template.name}."))  # noqa: E501
    session.flush()
    return sequence


def approve_step(session: Session, contact: Contact, step: SequenceStep) -> None:
    step.status = StepStatus.APPROVED
    step.approved_at = utcnow()
    contact.lead_state = LeadState.APPROVED
    contact.last_activity_at = utcnow()
    _resolve_task(session, step.id)
    session.add(
        DraftFeedbackEvent(
            contact_id=contact.id,
            sequence_step_id=step.id,
            feedback_type="approved",
            note=f"Approved step {step.step_order}.",
        )
    )
    session.add(AuditEvent(contact_id=contact.id, event_type="step_approved", detail=f"Approved step {step.step_order}."))  # noqa: E501


def record_manual_send(session: Session, contact: Contact, step: SequenceStep, audit_note: str = "") -> None:
    step.status = StepStatus.SENT_MANUALLY
    step.sent_at = utcnow()
    step.audit_note = audit_note
    contact.lead_state = LeadState.WAITING
    contact.last_activity_at = utcnow()

    next_step = _next_step(session, step.sequence_id, step.step_order)
    if next_step is None:
        sequence = session.get(Sequence, step.sequence_id)
        if sequence:
            sequence.status = "completed"
        contact.lead_state = LeadState.SENT_MANUALLY
    else:
        next_step.due_date = step.sent_at.date() + timedelta(days=next_step.delay_days)

    session.add(
        DraftFeedbackEvent(
            contact_id=contact.id,
            sequence_step_id=step.id,
            feedback_type="sent_manually",
            note=audit_note or f"Recorded manual send for step {step.step_order}.",
        )
    )
    session.add(AuditEvent(contact_id=contact.id, event_type="step_sent", detail=f"Recorded manual send for step {step.step_order}."))  # noqa: E501


def pause_contact(session: Session, contact: Contact, reason: str, terminal_state: LeadState) -> None:
    for sequence in session.exec(select(Sequence).where(Sequence.contact_id == contact.id, Sequence.status.in_(["active", "paused"]))).all():  # noqa: E501
        sequence.status = "paused"
    for step in _contact_steps(session, contact.id):
        if step.status in {StepStatus.PENDING, StepStatus.APPROVED}:
            step.status = StepStatus.CANCELED
            step.audit_note = reason
    for task in session.exec(select(ApprovalTask).where(ApprovalTask.contact_id == contact.id, ApprovalTask.status == "open")).all():
        task.status = "resolved"
        task.note = reason
        task.resolved_at = utcnow()
    contact.lead_state = terminal_state
    if terminal_state == LeadState.DO_NOT_CONTACT:
        contact.do_not_contact = True
        contact.suppressed_reason = reason
    contact.last_activity_at = utcnow()
    session.add(AuditEvent(contact_id=contact.id, event_type="contact_paused", detail=reason))


def save_step_feedback(
    session: Session,
    contact: Contact,
    step: SequenceStep,
    subject: str,
    body: str,
    feedback_note: str = "",
    save_as_example: bool = False,
) -> None:
    step.subject = subject
    step.body = body
    contact.last_activity_at = utcnow()

    note = feedback_note.strip() or f"Draft updated for step {step.step_order}."
    session.add(
        DraftFeedbackEvent(
            contact_id=contact.id,
            sequence_step_id=step.id,
            feedback_type="draft_edit",
            note=note,
        )
    )
    session.add(AuditEvent(contact_id=contact.id, event_type="draft_updated", detail=note))

    if save_as_example:
        session.add(
            ApprovedExample(
                contact_id=contact.id,
                sequence_step_id=step.id,
                channel=step.channel,
                label=step.label,
                subject=step.subject,
                body=step.body,
                rationale=note,
            )
        )
        session.add(
            DraftFeedbackEvent(
                contact_id=contact.id,
                sequence_step_id=step.id,
                feedback_type="approved_example",
                note="Saved as reusable approved example.",
            )
        )


def _contact_steps(session: Session, contact_id: int) -> list[SequenceStep]:
    sequences = session.exec(select(Sequence).where(Sequence.contact_id == contact_id)).all()
    if not sequences:
        return []
    sequence_ids = [sequence.id for sequence in sequences if sequence.id is not None]
    return session.exec(
        select(SequenceStep).where(SequenceStep.sequence_id.in_(sequence_ids)).order_by(SequenceStep.step_order)
    ).all()


def _next_step(session: Session, sequence_id: int, current_order: int) -> SequenceStep | None:
    return session.exec(
        select(SequenceStep).where(SequenceStep.sequence_id == sequence_id, SequenceStep.step_order == current_order + 1)
    ).first()


def _resolve_task(session: Session, step_id: int) -> None:
    task = session.exec(
        select(ApprovalTask).where(ApprovalTask.sequence_step_id == step_id, ApprovalTask.status == "open")
    ).first()
    if task:
        task.status = "resolved"
        task.resolved_at = utcnow()


def _parse_int_csv(raw_value: str, default: list[int]) -> list[int]:
    try:
        values = [int(part.strip()) for part in raw_value.split(",") if part.strip()]
    except ValueError:
        return default
    return values or default
