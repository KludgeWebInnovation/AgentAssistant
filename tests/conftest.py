from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session as runtime_get_session
from app.main import app
from app.models import AgencyProfile, ComplianceSettings, ICPProfile, OfferProfile, SequenceTemplate
from app.models import MessagingExample, ObjectionRule, ProofPoint, SalesPlaybook


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
        session.add(
            SalesPlaybook(
                positioning_summary="Signal Ops helps B2B teams run research-led outbound without heavy internal SDR hiring.",
                icp_summary="Focus on Europe/UK B2B service and software teams with inconsistent pipeline creation.",
                persona_guidance="Write for founders and heads of sales who own pipeline quality.",
                objection_handling="Reduce perceived risk with specificity and low-friction next steps.",
                proof_points_summary="Use proof anchored in booked meetings and better-fit personalization.",
                compliance_guardrails="Avoid overclaiming and keep opt-out language intact.",
                tone_rules="Keep it concise, grounded, and commercially clear.",
            )
        )
        session.add(
            MessagingExample(
                channel="email",
                label="Founder opener",
                audience="Founder",
                content="We help lean B2B teams improve outbound quality without building a large SDR team.",
                outcome_hint="Use as the first sentence in an intro email.",
                is_winning=True,
            )
        )
        session.add(
            ObjectionRule(
                objection="We already do outbound in-house.",
                response_guidance="Position the service as a quality and capacity layer for the existing team.",
            )
        )
        session.add(
            ProofPoint(
                title="Booked meetings from tighter research",
                detail="Teams use the workflow to ground outreach in better-fit account context before sending.",
            )
        )
        session.commit()
        yield session


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def client(session):
    def override_get_session():
        yield session

    app.dependency_overrides[runtime_get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
