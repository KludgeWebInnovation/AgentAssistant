from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import AgencyProfile, ComplianceSettings, ICPProfile, OfferProfile, SequenceTemplate


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            AgencyProfile(
                agency_name="Signal Ops",
                positioning="Outbound execution partner",
                value_proposition="High-context outbound for B2B teams",
                target_region="Europe/UK",
            )
        )
        session.add(
            OfferProfile(
                service_name="Managed SDR",
                offer_summary="Research and execute outbound sequences",
                differentiators="Human-reviewed personalization",
                call_to_action="Open to a short intro next week?",
            )
        )
        session.add(
            ICPProfile(
                industries="B2B SaaS, agencies",
                company_sizes="10-200 employees",
                personas="Founder, Head of Sales",
                pain_points="Pipeline inconsistency, weak reply rates",
                exclusions="Consumer brands",
            )
        )
        session.add(
            SequenceTemplate(
                name="Default 4-touch sequence",
                channels="email,linkedin,email,email",
                delay_days="0,2,3,4",
                step_labels="Intro email,LinkedIn touch,Follow-up email,Final email",
            )
        )
        session.add(
            ComplianceSettings(
                region="Europe/UK",
                booking_link="https://cal.com/signal-ops/intro",
                opt_out_text="Reply and I will not follow up again.",
                manual_review_required=True,
                provenance_required=True,
            )
        )
        session.commit()
        yield session


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"

