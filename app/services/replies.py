from __future__ import annotations

from sqlmodel import Session

from app.models import AuditEvent, Contact, LeadState, ReplyEvent, SequenceStep, utcnow
from app.services.ai import OpenAIService
from app.services.sequences import pause_contact


def handle_reply(
    session: Session,
    ai_service: OpenAIService,
    account_name: str,
    contact: Contact,
    reply_text: str,
    offer,
    compliance,
    step: SequenceStep | None = None,
) -> ReplyEvent:
    suggestion = ai_service.suggest_reply(account_name, contact, reply_text, offer, compliance)
    event = ReplyEvent(
        contact_id=contact.id,
        sequence_step_id=step.id if step else None,
        reply_text=reply_text,
        reply_intent=suggestion.intent,
        suggested_response=suggestion.suggested_response,
    )
    session.add(event)
    if suggestion.intent.value == "opt_out":
        pause_contact(session, contact, "Prospect opted out.", LeadState.DO_NOT_CONTACT)
    elif suggestion.intent.value == "positive":
        pause_contact(session, contact, "Positive reply received.", LeadState.REPLIED)
    elif suggestion.intent.value == "negative":
        pause_contact(session, contact, "Negative reply received.", LeadState.DISQUALIFIED)
    else:
        pause_contact(session, contact, "Reply received; sequence paused for review.", LeadState.REPLIED)
    contact.last_activity_at = utcnow()
    session.add(AuditEvent(contact_id=contact.id, event_type="reply_logged", detail=suggestion.intent.value))
    session.flush()
    return event

