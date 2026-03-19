from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import get_settings
from app.models import (
    AgencyProfile,
    ApprovedExample,
    CompanyResearchBrief,
    ComplianceSettings,
    Contact,
    ContactResearchBrief,
    EvidenceSnippet,
    ICPProfile,
    MessagingExample,
    ObjectionRule,
    OfferProfile,
    ProofPoint,
    ReplyIntent,
    SalesPlaybook,
    SequenceTemplate,
)

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
        playbook: SalesPlaybook | None = None,
        messaging_examples: list[MessagingExample] | None = None,
        objection_rules: list[ObjectionRule] | None = None,
        proof_points: list[ProofPoint] | None = None,
        approved_examples: list[ApprovedExample] | None = None,
        company_research: CompanyResearchBrief | None = None,
        contact_research: ContactResearchBrief | None = None,
        evidence_snippets: list[EvidenceSnippet] | None = None,
    ) -> ResearchPackage:
        messaging_examples = messaging_examples or []
        objection_rules = objection_rules or []
        proof_points = proof_points or []
        approved_examples = approved_examples or []
        evidence_snippets = evidence_snippets or []

        fallback = self._fallback_research(
            account_name=account_name,
            company_website=company_website,
            contact=contact,
            agency=agency,
            offer=offer,
            icp=icp,
            compliance=compliance,
            template=template,
            playbook=playbook,
            messaging_examples=messaging_examples,
            objection_rules=objection_rules,
            proof_points=proof_points,
            approved_examples=approved_examples,
            company_research=company_research,
            contact_research=contact_research,
            evidence_snippets=evidence_snippets,
        )
        if self._client is None:
            return fallback

        system = (
            "You are an expert outbound SDR strategist for a services business. "
            "Use the internal playbook, examples, proof points, and sourced research context. "
            "Return valid JSON with keys summary, pain_hypothesis, personalization_notes, provenance_summary, and steps. "
            "Steps must be an array of objects with channel, label, subject, and body. "
            "Do not invent facts that are not supported by research evidence or imported data."
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
            "playbook": self._serialize_playbook(playbook),
            "messaging_examples": self._serialize_examples(messaging_examples),
            "approved_examples": self._serialize_approved_examples(approved_examples),
            "objection_rules": self._serialize_objections(objection_rules),
            "proof_points": self._serialize_proof_points(proof_points),
            "company_research": self._serialize_company_research(company_research),
            "contact_research": self._serialize_contact_research(contact_research),
            "research_evidence": self._serialize_evidence(evidence_snippets),
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
        playbook: SalesPlaybook | None = None,
        objection_rules: list[ObjectionRule] | None = None,
    ) -> ReplySuggestion:
        objection_rules = objection_rules or []
        fallback = self._fallback_reply(account_name, contact, reply_text, offer, compliance, playbook, objection_rules)
        if self._client is None:
            return fallback

        system = (
            "Classify the outbound reply intent and return valid JSON with keys intent and suggested_response. "
            "Intent must be one of positive, neutral, negative, or opt_out. "
            "Use the playbook and objection guidance when proposing the next response."
        )
        prompt = {
            "account_name": account_name,
            "contact_name": contact.display_name,
            "reply_text": reply_text,
            "booking_link": compliance.booking_link,
            "offer_summary": offer.offer_summary,
            "playbook": self._serialize_playbook(playbook),
            "objection_rules": self._serialize_objections(objection_rules),
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
        playbook: SalesPlaybook | None = None,
        proof_points: list[ProofPoint] | None = None,
    ) -> list[DiscoverySuggestion]:
        proof_points = proof_points or []
        fallback = self._fallback_discovery(offer, icp, count, playbook, proof_points)
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
            "playbook": self._serialize_playbook(playbook),
            "proof_points": self._serialize_proof_points(proof_points),
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
        playbook: SalesPlaybook | None,
        messaging_examples: list[MessagingExample],
        objection_rules: list[ObjectionRule],
        proof_points: list[ProofPoint],
        approved_examples: list[ApprovedExample],
        company_research: CompanyResearchBrief | None,
        contact_research: ContactResearchBrief | None,
        evidence_snippets: list[EvidenceSnippet],
    ) -> ResearchPackage:
        labels = [label.strip() for label in template.step_labels.split(",") if label.strip()]
        channels = [channel.strip() for channel in template.channels.split(",") if channel.strip()]
        role = contact.job_title or "commercial leader"
        website_hint = f" Website: {company_website}." if company_website else ""

        company_summary = company_research.summary if company_research and company_research.summary else ""
        company_fit = company_research.icp_fit if company_research and company_research.icp_fit else ""
        trigger_signals = company_research.trigger_signals if company_research and company_research.trigger_signals else ""
        contact_angles = (
            contact_research.personalization_angles if contact_research and contact_research.personalization_angles else ""
        )
        persona_fit = contact_research.persona_fit if contact_research and contact_research.persona_fit else role
        buying_pains = contact_research.buying_pains if contact_research and contact_research.buying_pains else ""

        proof_hint = ""
        if proof_points:
            proof_hint = f"Proof point: {proof_points[0].title} - {proof_points[0].detail}"
        elif playbook and playbook.proof_points_summary:
            proof_hint = playbook.proof_points_summary
        else:
            proof_hint = offer.differentiators

        objection_hint = objection_rules[0].response_guidance if objection_rules else ""
        example_hint = ""
        if approved_examples:
            example_hint = approved_examples[0].body
        elif messaging_examples:
            example_hint = messaging_examples[0].content

        source_facts = [item.snippet_text for item in evidence_snippets if item.evidence_type == "fact"]
        source_fact_line = "; ".join(source_facts[:3])

        pain_hypothesis = buying_pains or (
            f"{contact.display_name} likely cares about pipeline consistency and converting targeted outbound into meetings "
            f"without adding heavy internal SDR headcount."
        )
        summary = (
            company_summary
            or f"{account_name} appears aligned with {offer.service_name} based on the ICP focus on "
            f"{icp.industries.lower()} and {icp.company_sizes.lower()}.{website_hint}"
        )
        if company_fit:
            summary = f"{summary} {company_fit}".strip()

        playbook_angle = playbook.positioning_summary if playbook and playbook.positioning_summary else agency.value_proposition
        personalization_notes = (
            f"Reference {contact.display_name}'s role as {role}, use persona fit '{persona_fit}', "
            f"connect to {playbook_angle.lower()}, and personalize with: {contact_angles or trigger_signals or source_fact_line or 'imported source context'}."
        )
        provenance_summary = (
            f"Source system: {contact.source_system or 'manual import'}. "
            f"Source list: {contact.source_list or 'unlabeled'}. "
            f"Imported on {contact.import_date.isoformat()}. "
            f"Research drivers: {source_fact_line or (company_research.source_summary if company_research else 'import record only')}."
        )

        opt_out = compliance.opt_out_text.strip()
        tone_rules = playbook.tone_rules if playbook and playbook.tone_rules else "Keep the draft concise, commercially specific, and low-friction."
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
                            f"{contact_angles or trigger_signals or 'I thought your current commercial focus might make this relevant.'} "
                            f"If useful, I can share how {agency.agency_name} approaches research-led prospecting for {account_name}."
                        ),
                    )
                )
                continue

            subject_prefix = account_name if index == 0 else f"Follow-up for {account_name}"
            subject = [
                f"Idea for {subject_prefix}",
                f"Following up on outbound at {account_name}",
                f"Quick follow-up for {account_name}",
                f"Close the loop on outbound support",
            ][index]

            if index == 0:
                opener = example_hint or f"I help SMB B2B teams turn tightly researched prospect lists into more booked meetings."
                body = (
                    f"Hi {contact.first_name or contact.display_name},\n\n"
                    f"{opener} {offer.offer_summary}.\n\n"
                    f"I thought this may be relevant to {account_name} because {company_summary.lower() if company_summary else pain_hypothesis.lower()} "
                    f"{contact_angles or ''}\n\n"
                    f"{proof_hint}\n\n"
                    f"{offer.call_to_action}\n\n"
                    f"{opt_out}"
                ).strip()
            elif index == 1:
                body = (
                    f"Hi {contact.first_name or contact.display_name},\n\n"
                    f"Following up in case the earlier note was relevant. "
                    f"{company_fit or 'The fit looks strongest where outbound capacity and message quality both matter.'}\n\n"
                    f"{proof_hint}\n\n"
                    f"{offer.call_to_action}\n\n"
                    f"{opt_out}"
                ).strip()
            elif index == 2:
                objection_line = objection_hint or "We normally keep the first step lightweight and focused on relevance."
                body = (
                    f"Hi {contact.first_name or contact.display_name},\n\n"
                    f"One more angle from my side: {pain_hypothesis} "
                    f"{objection_line}\n\n"
                    f"{proof_hint}\n\n"
                    f"{offer.call_to_action}\n\n"
                    f"{opt_out}"
                ).strip()
            else:
                body = (
                    f"Hi {contact.first_name or contact.display_name},\n\n"
                    f"I'll close the loop after this note. "
                    f"{tone_rules} "
                    f"If a short conversation around {offer.service_name.lower()} would be useful for {account_name}, "
                    f"I can share a concise outline.\n\n"
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

        raw_fallback = {
            "source": "fallback",
            "account_name": account_name,
            "company_research": self._serialize_company_research(company_research),
            "contact_research": self._serialize_contact_research(contact_research),
            "proof_points": self._serialize_proof_points(proof_points),
            "objection_rules": self._serialize_objections(objection_rules),
        }
        return ResearchPackage(
            summary=summary,
            pain_hypothesis=pain_hypothesis,
            personalization_notes=personalization_notes,
            provenance_summary=provenance_summary,
            raw_model_output=json.dumps(raw_fallback),
            steps=steps,
        )

    def _fallback_reply(
        self,
        account_name: str,
        contact: Contact,
        reply_text: str,
        offer: OfferProfile,
        compliance: ComplianceSettings,
        playbook: SalesPlaybook | None,
        objection_rules: list[ObjectionRule],
    ) -> ReplySuggestion:
        text = reply_text.lower()
        objection_hint = objection_rules[0].response_guidance if objection_rules else ""
        tone_hint = playbook.tone_rules if playbook and playbook.tone_rules else ""
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
            response = "Understood. Thanks for the reply, and I will close this out on my side for now."
            if objection_hint:
                response = f"Understood. {objection_hint} If priorities change, I can revisit this later."
            return ReplySuggestion(intent=ReplyIntent.NEGATIVE, suggested_response=response)
        response = (
            f"Thanks for the reply. If useful, I can share a short outline of how {offer.service_name} "
            f"could support outbound for {account_name}."
        )
        if tone_hint:
            response = f"{response} {tone_hint}"
        return ReplySuggestion(intent=ReplyIntent.NEUTRAL, suggested_response=response)

    def _fallback_discovery(
        self,
        offer: OfferProfile,
        icp: ICPProfile,
        count: int,
        playbook: SalesPlaybook | None,
        proof_points: list[ProofPoint],
    ) -> list[DiscoverySuggestion]:
        industries = [segment.strip() for segment in icp.industries.split(",") if segment.strip()] or ["B2B services"]
        personas = [segment.strip() for segment in icp.personas.split(",") if segment.strip()] or ["Founder"]
        pains = [segment.strip() for segment in icp.pain_points.split(",") if segment.strip()] or ["pipeline inconsistency"]
        proof_hint = proof_points[0].title if proof_points else (playbook.proof_points_summary if playbook else "")
        suggestions = []
        for index in range(count):
            industry = industries[index % len(industries)]
            persona = personas[index % len(personas)]
            pain = pains[index % len(pains)]
            rationale = f"{offer.service_name} is relevant when {persona} is dealing with {pain.lower()}."
            if proof_hint:
                rationale = f"{rationale} Lead with proof around {proof_hint.lower()}."
            suggestions.append(
                DiscoverySuggestion(
                    segment=f"{industry} companies in Europe/UK with {icp.company_sizes.lower()}",
                    persona=persona,
                    rationale=rationale,
                    search_hint=f"Use Cognism or LinkedIn to find {persona} profiles in {industry} firms mentioning growth, pipeline, or outbound hiring.",
                )
            )
        return suggestions

    def _serialize_playbook(self, playbook: SalesPlaybook | None) -> dict[str, str]:
        if playbook is None:
            return {}
        return {
            "positioning_summary": playbook.positioning_summary,
            "icp_summary": playbook.icp_summary,
            "persona_guidance": playbook.persona_guidance,
            "objection_handling": playbook.objection_handling,
            "proof_points_summary": playbook.proof_points_summary,
            "compliance_guardrails": playbook.compliance_guardrails,
            "tone_rules": playbook.tone_rules,
        }

    def _serialize_examples(self, examples: list[MessagingExample]) -> list[dict[str, str | bool]]:
        return [
            {
                "channel": example.channel,
                "label": example.label,
                "audience": example.audience,
                "content": example.content,
                "outcome_hint": example.outcome_hint,
                "is_winning": example.is_winning,
            }
            for example in examples[:5]
        ]

    def _serialize_approved_examples(self, examples: list[ApprovedExample]) -> list[dict[str, str]]:
        return [
            {
                "channel": example.channel,
                "label": example.label,
                "subject": example.subject,
                "body": example.body,
                "rationale": example.rationale,
            }
            for example in examples[:5]
        ]

    def _serialize_objections(self, rules: list[ObjectionRule]) -> list[dict[str, str]]:
        return [
            {"objection": rule.objection, "response_guidance": rule.response_guidance}
            for rule in rules[:5]
        ]

    def _serialize_proof_points(self, proof_points: list[ProofPoint]) -> list[dict[str, str]]:
        return [{"title": proof.title, "detail": proof.detail} for proof in proof_points[:5]]

    def _serialize_company_research(self, brief: CompanyResearchBrief | None) -> dict[str, str]:
        if brief is None:
            return {}
        return {
            "summary": brief.summary,
            "icp_fit": brief.icp_fit,
            "growth_stage_region": brief.growth_stage_region,
            "service_relevance": brief.service_relevance,
            "trigger_signals": brief.trigger_signals,
            "source_summary": brief.source_summary,
        }

    def _serialize_contact_research(self, brief: ContactResearchBrief | None) -> dict[str, str]:
        if brief is None:
            return {}
        return {
            "role_summary": brief.role_summary,
            "persona_fit": brief.persona_fit,
            "personalization_angles": brief.personalization_angles,
            "buying_pains": brief.buying_pains,
            "source_summary": brief.source_summary,
        }

    def _serialize_evidence(self, snippets: list[EvidenceSnippet]) -> list[dict[str, str]]:
        return [
            {
                "evidence_type": snippet.evidence_type,
                "snippet_text": snippet.snippet_text,
                "note": snippet.note,
            }
            for snippet in snippets[:8]
        ]
