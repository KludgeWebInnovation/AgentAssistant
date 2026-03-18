from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import get_settings
from app.models import AgencyProfile, ComplianceSettings, Contact, ICPProfile, OfferProfile, ReplyIntent, SequenceTemplate

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency at runtime
    OpenAI = None


@dataclass
class SequenceDraftStep:
    channel: str
    label: str
    subject: str
    body: str


@dataclass
class ResearchPackage:
    summary: str
    pain_hypothesis: str
    personalization_notes: str
    provenance_summary: str
    raw_model_output: str
    steps: list[SequenceDraftStep]


@dataclass
class ReplySuggestion:
    intent: ReplyIntent
    suggested_response: str


@dataclass
class DiscoverySuggestion:
    segment: str
    persona: str
    rationale: str
    search_hint: str


class OpenAIService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key and OpenAI else None

    def generate_research_package(
        self,
        account_name: str,
        company_website: str,
        contact: Contact,
        agency: AgencyProfile,
        offer: OfferProfile,
        icp: ICPProfile,
        compliance: ComplianceSettings,
        template: SequenceTemplate,
    ) -> ResearchPackage:
        fallback = self._fallback_research(
            account_name=account_name,
            company_website=company_website,
            contact=contact,
            agency=agency,
            offer=offer,
            icp=icp,
            compliance=compliance,
            template=template,
        )
        if self._client is None:
            return fallback

        system = (
            "You are an expert outbound SDR strategist for a services business. "
            "Return valid JSON with keys summary, pain_hypothesis, personalization_notes, "
            "provenance_summary, and steps. Steps must be an array of objects with channel, label, subject, and body."
        )
        prompt = {
            "account_name": account_name,
            "company_website": company_website,
            "contact_name": contact.display_name,
            "job_title": contact.job_title,
            "source_system": contact.source_system,
            "source_list": contact.source_list,
            "agency": {
                "name": agency.agency_name,
                "positioning": agency.positioning,
                "value_proposition": agency.value_proposition,
            },
            "offer": {
                "service_name": offer.service_name,
                "offer_summary": offer.offer_summary,
                "differentiators": offer.differentiators,
                "cta": offer.call_to_action,
            },
            "icp": {
                "industries": icp.industries,
                "company_sizes": icp.company_sizes,
                "personas": icp.personas,
                "pain_points": icp.pain_points,
            },
            "compliance": {
                "region": compliance.region,
                "opt_out_text": compliance.opt_out_text,
            },
            "sequence_template": {
                "channels": template.channels,
                "labels": template.step_labels,
            },
        }
        try:
            completion = self._client.chat.completions.create(
                model=self.settings.openai_research_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
            )
            raw = completion.choices[0].message.content or "{}"
            payload = json.loads(raw)
            steps = []
            for index, fallback_step in enumerate(fallback.steps):
                source = payload.get("steps", [])[index] if index < len(payload.get("steps", [])) else {}
                steps.append(
                    SequenceDraftStep(
                        channel=str(source.get("channel", fallback_step.channel)),
                        label=str(source.get("label", fallback_step.label)),
                        subject=str(source.get("subject", fallback_step.subject)),
                        body=str(source.get("body", fallback_step.body)),
                    )
                )
            return ResearchPackage(
                summary=str(payload.get("summary", fallback.summary)),
                pain_hypothesis=str(payload.get("pain_hypothesis", fallback.pain_hypothesis)),
                personalization_notes=str(payload.get("personalization_notes", fallback.personalization_notes)),
                provenance_summary=str(payload.get("provenance_summary", fallback.provenance_summary)),
                raw_model_output=raw,
                steps=steps,
            )
        except Exception:
            return fallback

    def suggest_reply(
        self,
        account_name: str,
        contact: Contact,
        reply_text: str,
        offer: OfferProfile,
        compliance: ComplianceSettings,
    ) -> ReplySuggestion:
        fallback = self._fallback_reply(account_name, contact, reply_text, offer, compliance)
        if self._client is None:
            return fallback

        system = (
            "Classify the outbound reply intent and return valid JSON with keys intent and suggested_response. "
            "Intent must be one of positive, neutral, negative, or opt_out."
        )
        prompt = {
            "account_name": account_name,
            "contact_name": contact.display_name,
            "reply_text": reply_text,
            "booking_link": compliance.booking_link,
            "offer_summary": offer.offer_summary,
        }
        try:
            completion = self._client.chat.completions.create(
                model=self.settings.openai_classify_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            raw = completion.choices[0].message.content or "{}"
            payload = json.loads(raw)
            intent_value = str(payload.get("intent", fallback.intent.value))
            intent = ReplyIntent(intent_value) if intent_value in ReplyIntent._value2member_map_ else fallback.intent
            suggested_response = str(payload.get("suggested_response", fallback.suggested_response))
            return ReplySuggestion(intent=intent, suggested_response=suggested_response)
        except Exception:
            return fallback

    def generate_discovery_suggestions(
        self,
        offer: OfferProfile,
        icp: ICPProfile,
        count: int = 5,
    ) -> list[DiscoverySuggestion]:
        fallback = self._fallback_discovery(offer, icp, count)
        if self._client is None:
            return fallback

        system = (
            "Generate account-hunting suggestions for an SDR. "
            "Return valid JSON with a suggestions array. Each item must include segment, persona, rationale, and search_hint."
        )
        prompt = {
            "offer_summary": offer.offer_summary,
            "industries": icp.industries,
            "company_sizes": icp.company_sizes,
            "personas": icp.personas,
            "pain_points": icp.pain_points,
            "count": count,
        }
        try:
            completion = self._client.chat.completions.create(
                model=self.settings.openai_classify_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            raw = completion.choices[0].message.content or "{}"
            payload = json.loads(raw)
            suggestions = []
            for item in payload.get("suggestions", [])[:count]:
                suggestions.append(
                    DiscoverySuggestion(
                        segment=str(item.get("segment", "")),
                        persona=str(item.get("persona", "")),
                        rationale=str(item.get("rationale", "")),
                        search_hint=str(item.get("search_hint", "")),
                    )
                )
            return suggestions or fallback
        except Exception:
            return fallback

    def _fallback_research(
        self,
        account_name: str,
        company_website: str,
        contact: Contact,
        agency: AgencyProfile,
        offer: OfferProfile,
        icp: ICPProfile,
        compliance: ComplianceSettings,
        template: SequenceTemplate,
    ) -> ResearchPackage:
        labels = [label.strip() for label in template.step_labels.split(",") if label.strip()]
        channels = [channel.strip() for channel in template.channels.split(",") if channel.strip()]
        role = contact.job_title or "commercial leader"
        website_hint = f" Website: {company_website}." if company_website else ""
        pain_hypothesis = (
            f"{contact.display_name} likely cares about pipeline consistency and converting targeted outbound into meetings "
            f"without adding heavy internal SDR headcount."
        )
        summary = (
            f"{account_name} appears aligned with {offer.service_name} based on the ICP focus on "
            f"{icp.industries.lower()} and {icp.company_sizes.lower()}.{website_hint}"
        )
        personalization_notes = (
            f"Reference {contact.display_name}'s role as {role}, connect to {agency.value_proposition.lower()}, "
            f"and keep the message concise for {compliance.region} prospects."
        )
        provenance_summary = (
            f"Source system: {contact.source_system or 'manual import'}. "
            f"Source list: {contact.source_list or 'unlabeled'}. "
            f"Imported on {contact.import_date.isoformat()}."
        )
        opt_out = compliance.opt_out_text.strip()
        steps: list[SequenceDraftStep] = []
        for index, channel in enumerate(channels):
            label = labels[index] if index < len(labels) else f"Step {index + 1}"
            if channel == "linkedin":
                steps.append(
                    SequenceDraftStep(
                        channel=channel,
                        label=label,
                        subject="",
                        body=(
                            f"Hi {contact.first_name or contact.display_name}, I work with teams that want more consistent outbound meetings. "
                            f"If useful, I can share how {agency.agency_name} approaches research-led prospecting for {account_name}."
                        ),
                    )
                )
                continue
            subject = [
                f"Idea for {account_name}",
                f"Following up on outbound at {account_name}",
                f"Quick follow-up for {account_name}",
                f"Close the loop on outbound support",
            ][index]
            body = (
                f"Hi {contact.first_name or contact.display_name},\n\n"
                f"I help SMB B2B teams turn tightly researched prospect lists into more booked meetings. "
                f"{offer.offer_summary}.\n\n"
                f"I thought this may be relevant to {account_name} because {pain_hypothesis.lower()} "
                f"{offer.differentiators}\n\n"
                f"{offer.call_to_action}\n\n"
                f"{opt_out}"
            ).strip()
            steps.append(
                SequenceDraftStep(
                    channel=channel,
                    label=label,
                    subject=subject,
                    body=body,
                )
            )
        return ResearchPackage(
            summary=summary,
            pain_hypothesis=pain_hypothesis,
            personalization_notes=personalization_notes,
            provenance_summary=provenance_summary,
            raw_model_output=json.dumps({"source": "fallback", "account_name": account_name}),
            steps=steps,
        )

    def _fallback_reply(
        self,
        account_name: str,
        contact: Contact,
        reply_text: str,
        offer: OfferProfile,
        compliance: ComplianceSettings,
    ) -> ReplySuggestion:
        text = reply_text.lower()
        if any(token in text for token in ["unsubscribe", "remove me", "stop", "not interested"]):
            return ReplySuggestion(
                intent=ReplyIntent.OPT_OUT,
                suggested_response="Acknowledged. I will not follow up again.",
            )
        if any(token in text for token in ["sounds good", "interested", "let's talk", "book", "meeting", "call"]):
            return ReplySuggestion(
                intent=ReplyIntent.POSITIVE,
                suggested_response=(
                    f"Thanks {contact.first_name or contact.display_name}, happy to. "
                    f"You can pick a time here: {compliance.booking_link}"
                ),
            )
        if any(token in text for token in ["no budget", "not now", "already covered"]):
            return ReplySuggestion(
                intent=ReplyIntent.NEGATIVE,
                suggested_response="Understood. Thanks for the reply, and I will close this out on my side for now.",
            )
        return ReplySuggestion(
            intent=ReplyIntent.NEUTRAL,
            suggested_response=(
                f"Thanks for the reply. If useful, I can share a short outline of how {offer.service_name} "
                f"could support outbound for {account_name}."
            ),
        )

    def _fallback_discovery(self, offer: OfferProfile, icp: ICPProfile, count: int) -> list[DiscoverySuggestion]:
        industries = [segment.strip() for segment in icp.industries.split(",") if segment.strip()] or ["B2B services"]
        personas = [segment.strip() for segment in icp.personas.split(",") if segment.strip()] or ["Founder"]
        pains = [segment.strip() for segment in icp.pain_points.split(",") if segment.strip()] or ["pipeline inconsistency"]
        suggestions = []
        for index in range(count):
            industry = industries[index % len(industries)]
            persona = personas[index % len(personas)]
            pain = pains[index % len(pains)]
            suggestions.append(
                DiscoverySuggestion(
                    segment=f"{industry} companies in Europe/UK with {icp.company_sizes.lower()}",
                    persona=persona,
                    rationale=f"{offer.service_name} is relevant when {persona} is dealing with {pain.lower()}.",
                    search_hint=f"Use Cognism or LinkedIn to find {persona} profiles in {industry} firms mentioning growth, pipeline, or outbound hiring.",
                )
            )
        return suggestions

