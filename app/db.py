from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings
from app.models import AgencyProfile, ComplianceSettings, ICPProfile, OfferProfile, SequenceTemplate

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
        session.commit()
