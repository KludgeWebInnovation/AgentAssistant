from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings
from app.models import (
    AgencyProfile,
    ComplianceSettings,
    ICPProfile,
    MessagingExample,
    ObjectionRule,
    OfferProfile,
    ProofPoint,
    SalesPlaybook,
    SequenceTemplate,
)

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(settings.database_url)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.exec(select(AgencyProfile)).first() is None:
            session.add(
                AgencyProfile(
                    agency_name="Your Agency",
                    website="",
                    positioning="Outbound growth partner for SMB B2B teams.",
                    value_proposition="We turn targeted prospect lists into booked meetings with tightly personalized outreach.",
                    target_region="Europe/UK",
                )
            )
        if session.exec(select(OfferProfile)).first() is None:
            session.add(
                OfferProfile(
                    service_name="Managed outbound SDR",
                    offer_summary="Research-led outbound prospecting and meeting booking.",
                    differentiators="Human-reviewed personalization, compliance-first workflow, and ICP-specific messaging.",
                    call_to_action="Would a short intro call next week be useful?",
                )
            )
        if session.exec(select(ICPProfile)).first() is None:
            session.add(
                ICPProfile(
                    industries="B2B SaaS, agencies, professional services",
                    company_sizes="10-200 employees",
                    personas="Founder, CEO, CRO, Head of Sales, Marketing Director",
                    pain_points="Inconsistent pipeline, low reply rates, limited SDR capacity",
                    exclusions="Consumer brands, companies outside Europe/UK, non-English outreach",
                )
            )
        if session.exec(select(SequenceTemplate)).first() is None:
            session.add(
                SequenceTemplate(
                    name="Default 4-touch sequence",
                    channels="email,linkedin,email,email",
                    delay_days="0,2,3,4",
                    step_labels="Intro email,LinkedIn touch,Follow-up email,Final email",
                )
            )
        if session.exec(select(ComplianceSettings)).first() is None:
            session.add(
                ComplianceSettings(
                    region="Europe/UK",
                    booking_link="https://cal.com/your-team/intro",
                    opt_out_text="If this is not relevant, reply and I will not follow up again.",
                    manual_review_required=True,
                    provenance_required=True,
                )
            )
        if session.exec(select(SalesPlaybook)).first() is None:
            session.add(
                SalesPlaybook(
                    positioning_summary="We act as a research-led SDR partner for SMB B2B teams that need more qualified conversations without building a large internal SDR function.",
                    icp_summary="Best-fit accounts are Europe/UK B2B firms with a clear commercial owner, a defined offer, and inconsistent outbound pipeline generation.",
                    persona_guidance="Speak to founders and revenue leaders as owners of pipeline quality, reply rates, and sales capacity. Keep the tone direct, commercially aware, and concise.",
                    objection_handling="Address concerns around relevance, bandwidth, and risk by emphasizing research quality, human review, and low-friction next steps.",
                    proof_points_summary="Use proof anchored in improved meeting creation, tighter personalization, and lower operator burden.",
                    compliance_guardrails="Do not overclaim results. Keep messaging compliant, specific, and easy to opt out from.",
                    tone_rules="Write like an experienced outbound operator: concise, informed, respectful, and commercially specific.",
                )
            )
        if session.exec(select(MessagingExample)).first() is None:
            session.add(
                MessagingExample(
                    channel="email",
                    label="Founder intro",
                    audience="Founder / CEO",
                    content="We help lean commercial teams turn better-fit prospect research into more booked meetings without adding heavy SDR overhead.",
                    outcome_hint="Use as a concise opening value proposition.",
                    is_winning=True,
                )
            )
        if session.exec(select(ObjectionRule)).first() is None:
            session.add(
                ObjectionRule(
                    objection="We already do outbound internally.",
                    response_guidance="Position the service as a way to improve research quality, message sharpness, and operator capacity rather than replacing the internal team.",
                )
            )
        if session.exec(select(ProofPoint)).first() is None:
            session.add(
                ProofPoint(
                    title="Human-reviewed personalization",
                    detail="Every outbound touch is reviewed before it is sent, which keeps messaging relevant and compliance-safe.",
                )
            )
        session.commit()
