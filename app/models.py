from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LeadState(str, Enum):
    NEW = "new"
    RESEARCH_READY = "research_ready"
    DRAFT_READY = "draft_ready"
    APPROVED = "approved"
    SENT_MANUALLY = "sent_manually"
    WAITING = "waiting"
    REPLIED = "replied"
    MEETING_BOOKED = "meeting_booked"
    DISQUALIFIED = "disqualified"
    DO_NOT_CONTACT = "do_not_contact"


class StepStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SENT_MANUALLY = "sent_manually"
    SKIPPED = "skipped"
    CANCELED = "canceled"


class ReplyIntent(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    OPT_OUT = "opt_out"


class AgencyProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    agency_name: str = Field(default="Your Agency")
    website: str = Field(default="")
    positioning: str = Field(default="")
    value_proposition: str = Field(default="")
    target_region: str = Field(default="Europe/UK")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class OfferProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    service_name: str = Field(default="Managed outbound SDR")
    offer_summary: str = Field(default="")
    differentiators: str = Field(default="")
    call_to_action: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ICPProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    industries: str = Field(default="")
    company_sizes: str = Field(default="")
    personas: str = Field(default="")
    pain_points: str = Field(default="")
    exclusions: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SequenceTemplate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="Default 4-touch sequence")
    channels: str = Field(default="email,linkedin,email,email")
    delay_days: str = Field(default="0,2,3,4")
    step_labels: str = Field(default="Intro email,LinkedIn touch,Follow-up email,Final email")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ComplianceSettings(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    region: str = Field(default="Europe/UK")
    booking_link: str = Field(default="")
    opt_out_text: str = Field(default="")
    manual_review_required: bool = Field(default=True)
    provenance_required: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SalesPlaybook(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    positioning_summary: str = Field(default="")
    icp_summary: str = Field(default="")
    persona_guidance: str = Field(default="")
    objection_handling: str = Field(default="")
    proof_points_summary: str = Field(default="")
    compliance_guardrails: str = Field(default="")
    tone_rules: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class MessagingExample(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(default="email", index=True)
    label: str = Field(default="")
    audience: str = Field(default="")
    content: str = Field(default="")
    outcome_hint: str = Field(default="")
    is_winning: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ObjectionRule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    objection: str = Field(default="", index=True)
    response_guidance: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProofPoint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(default="", index=True)
    detail: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LeadSource(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    source_type: str = Field(default="csv")
    description: str = Field(default="")
    row_count: int = Field(default=0)
    imported_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_name: str = Field(index=True)
    company_website: str = Field(default="")
    country: str = Field(default="")
    notes: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Contact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    first_name: str = Field(default="")
    last_name: str = Field(default="")
    job_title: str = Field(default="")
    email: str = Field(default="", index=True)
    linkedin_url: str = Field(default="", index=True)
    country: str = Field(default="")
    source_system: str = Field(default="")
    source_list: str = Field(default="")
    provenance_notes: str = Field(default="")
    import_date: date = Field(default_factory=date.today)
    lead_state: LeadState = Field(default=LeadState.NEW, index=True)
    do_not_contact: bool = Field(default=False, index=True)
    suppressed_reason: str = Field(default="")
    last_activity_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def display_name(self) -> str:
        full_name = " ".join(part for part in [self.first_name, self.last_name] if part).strip()
        return full_name or self.email or self.linkedin_url or f"Contact {self.id}"


class ResearchBrief(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    summary: str = Field(default="")
    pain_hypothesis: str = Field(default="")
    personalization_notes: str = Field(default="")
    provenance_summary: str = Field(default="")
    raw_model_output: str = Field(default="")
    generated_at: datetime = Field(default_factory=utcnow)


class CompanyResearchBrief(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    summary: str = Field(default="")
    icp_fit: str = Field(default="")
    growth_stage_region: str = Field(default="")
    service_relevance: str = Field(default="")
    trigger_signals: str = Field(default="")
    source_summary: str = Field(default="")
    generated_at: datetime = Field(default_factory=utcnow)


class ContactResearchBrief(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    role_summary: str = Field(default="")
    persona_fit: str = Field(default="")
    personalization_angles: str = Field(default="")
    buying_pains: str = Field(default="")
    source_summary: str = Field(default="")
    generated_at: datetime = Field(default_factory=utcnow)


class ResearchSource(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int | None = Field(default=None, foreign_key="account.id", index=True)
    contact_id: int | None = Field(default=None, foreign_key="contact.id", index=True)
    source_kind: str = Field(default="internal", index=True)
    title: str = Field(default="")
    url: str = Field(default="")
    snippet: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class EvidenceSnippet(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_research_brief_id: int | None = Field(default=None, foreign_key="companyresearchbrief.id", index=True)
    contact_research_brief_id: int | None = Field(default=None, foreign_key="contactresearchbrief.id", index=True)
    research_source_id: int | None = Field(default=None, foreign_key="researchsource.id", index=True)
    evidence_type: str = Field(default="fact", index=True)
    snippet_text: str = Field(default="")
    note: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class Sequence(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    template_name: str = Field(default="")
    status: str = Field(default="active", index=True)
    generated_at: datetime = Field(default_factory=utcnow)
    last_generated_at: datetime = Field(default_factory=utcnow)


class SequenceStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sequence_id: int = Field(foreign_key="sequence.id", index=True)
    step_order: int = Field(index=True)
    channel: str = Field(default="email")
    label: str = Field(default="")
    delay_days: int = Field(default=0)
    subject: str = Field(default="")
    body: str = Field(default="")
    due_date: date | None = Field(default=None, index=True)
    status: StepStatus = Field(default=StepStatus.PENDING, index=True)
    approved_at: datetime | None = Field(default=None)
    sent_at: datetime | None = Field(default=None)
    skipped_at: datetime | None = Field(default=None)
    audit_note: str = Field(default="")


class ApprovalTask(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    sequence_step_id: int = Field(foreign_key="sequencestep.id", index=True)
    task_type: str = Field(default="review_send")
    status: str = Field(default="open", index=True)
    note: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = Field(default=None)


class ReplyEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    sequence_step_id: int | None = Field(default=None, foreign_key="sequencestep.id")
    reply_text: str = Field(default="")
    reply_intent: ReplyIntent = Field(default=ReplyIntent.NEUTRAL)
    suggested_response: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class DraftFeedbackEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    sequence_step_id: int | None = Field(default=None, foreign_key="sequencestep.id", index=True)
    feedback_type: str = Field(default="draft_edit", index=True)
    note: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class ApprovedExample(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int | None = Field(default=None, foreign_key="contact.id", index=True)
    sequence_step_id: int | None = Field(default=None, foreign_key="sequencestep.id", index=True)
    channel: str = Field(default="email", index=True)
    label: str = Field(default="")
    subject: str = Field(default="")
    body: str = Field(default="")
    rationale: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contact_id: int | None = Field(default=None, foreign_key="contact.id", index=True)
    event_type: str = Field(index=True)
    actor: str = Field(default="system")
    detail: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
