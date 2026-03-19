from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlparse

import httpx
from sqlmodel import Session, select

from app.models import (
    Account,
    CompanyResearchBrief,
    Contact,
    ContactResearchBrief,
    EvidenceSnippet,
    ICPProfile,
    ResearchSource,
    SalesPlaybook,
    utcnow,
)


@dataclass
class ResearchSourceDraft:
    source_kind: str
    title: str
    url: str
    snippet: str
    account_scope: bool = False
    contact_scope: bool = False


@dataclass
class EvidenceDraft:
    scope: str
    evidence_type: str
    snippet_text: str
    note: str
    source_index: int | None = None


@dataclass
class ResearchBundle:
    company_summary: str
    company_icp_fit: str
    company_growth_stage_region: str
    company_service_relevance: str
    company_trigger_signals: str
    company_source_summary: str
    contact_role_summary: str
    contact_persona_fit: str
    contact_personalization_angles: str
    contact_buying_pains: str
    contact_source_summary: str
    sources: list[ResearchSourceDraft]
    company_evidence: list[EvidenceDraft]
    contact_evidence: list[EvidenceDraft]


class ResearchService:
    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=5.0,
            follow_redirects=True,
            headers={
                "User-Agent": "AISDR Research Bot/0.1 (+https://github.com/KludgeWebInnovation/AgentAssistant)"
            },
        )

    def collect_bundle(
        self,
        account: Account,
        contact: Contact,
        icp: ICPProfile,
        playbook: SalesPlaybook | None,
    ) -> ResearchBundle:
        sources: list[ResearchSourceDraft] = []
        company_evidence: list[EvidenceDraft] = []
        contact_evidence: list[EvidenceDraft] = []

        internal_source = self._build_internal_source(account, contact)
        sources.append(internal_source)
        company_evidence.append(
            EvidenceDraft(
                scope="company",
                evidence_type="fact",
                snippet_text=f"Imported account: {account.company_name}",
                note="Account name from imported source data.",
                source_index=0,
            )
        )
        if account.country:
            company_evidence.append(
                EvidenceDraft(
                    scope="company",
                    evidence_type="fact",
                    snippet_text=f"Country: {account.country}",
                    note="Account country from imported data.",
                    source_index=0,
                )
            )
        if contact.source_system or contact.source_list:
            company_evidence.append(
                EvidenceDraft(
                    scope="company",
                    evidence_type="fact",
                    snippet_text=f"Lead source: {contact.source_system or 'manual'} / {contact.source_list or 'unlabeled'}",
                    note="Provenance recorded at import time.",
                    source_index=0,
                )
            )
        if contact.job_title:
            contact_evidence.append(
                EvidenceDraft(
                    scope="contact",
                    evidence_type="fact",
                    snippet_text=f"Role: {contact.job_title}",
                    note="Role title from imported contact data.",
                    source_index=0,
                )
            )
        if contact.provenance_notes:
            contact_evidence.append(
                EvidenceDraft(
                    scope="contact",
                    evidence_type="fact",
                    snippet_text=contact.provenance_notes,
                    note="Imported notes or provenance comments.",
                    source_index=0,
                )
            )

        website_url = self._guess_company_url(account, contact)
        if website_url:
            website_source = self._fetch_public_page(website_url, "company_website", account_scope=True)
            if website_source:
                sources.append(website_source)
                company_evidence.append(
                    EvidenceDraft(
                        scope="company",
                        evidence_type="fact",
                        snippet_text=website_source.snippet,
                        note="Public website summary.",
                        source_index=len(sources) - 1,
                    )
                )
        if contact.linkedin_url:
            linkedin_source = self._fetch_public_page(contact.linkedin_url, "contact_profile", contact_scope=True)
            if linkedin_source:
                sources.append(linkedin_source)
                contact_evidence.append(
                    EvidenceDraft(
                        scope="contact",
                        evidence_type="fact",
                        snippet_text=linkedin_source.snippet,
                        note="Public contact page summary.",
                        source_index=len(sources) - 1,
                    )
                )

        persona_match = self._match_persona(contact.job_title, icp.personas)
        company_text = " ".join(source.snippet for source in sources if source.account_scope or not source.contact_scope).strip()
        contact_text = " ".join(source.snippet for source in sources if source.contact_scope).strip()
        playbook_hint = playbook.positioning_summary if playbook else ""

        company_summary = self._compose_company_summary(account, company_text, playbook_hint)
        company_icp_fit = self._compose_icp_fit(account, icp, company_text)
        growth_stage_region = self._compose_growth_stage_region(account, icp, company_text)
        service_relevance = self._compose_service_relevance(icp, playbook, company_text)
        trigger_signals = self._compose_trigger_signals(contact, account, company_text)
        company_source_summary = self._build_source_summary([source for source in sources if source.account_scope or not source.contact_scope])

        role_summary = self._compose_role_summary(contact, contact_text)
        contact_persona_fit = persona_match
        personalization_angles = self._compose_personalization_angles(contact, account, contact_text, company_text)
        buying_pains = self._compose_buying_pains(icp, contact)
        contact_source_summary = self._build_source_summary([source for source in sources if source.contact_scope or not source.account_scope])

        company_evidence.extend(
            [
                EvidenceDraft(
                    scope="company",
                    evidence_type="inference",
                    snippet_text=company_icp_fit,
                    note="ICP fit inferred from imported fields and public account context.",
                ),
                EvidenceDraft(
                    scope="company",
                    evidence_type="inference",
                    snippet_text=service_relevance,
                    note="Service relevance inferred from the current offer and account context.",
                ),
            ]
        )
        contact_evidence.extend(
            [
                EvidenceDraft(
                    scope="contact",
                    evidence_type="inference",
                    snippet_text=contact_persona_fit,
                    note="Persona fit inferred from the contact's title and ICP personas.",
                ),
                EvidenceDraft(
                    scope="contact",
                    evidence_type="inference",
                    snippet_text=buying_pains,
                    note="Likely buying pains inferred from persona and ICP pain points.",
                ),
            ]
        )

        return ResearchBundle(
            company_summary=company_summary,
            company_icp_fit=company_icp_fit,
            company_growth_stage_region=growth_stage_region,
            company_service_relevance=service_relevance,
            company_trigger_signals=trigger_signals,
            company_source_summary=company_source_summary,
            contact_role_summary=role_summary,
            contact_persona_fit=contact_persona_fit,
            contact_personalization_angles=personalization_angles,
            contact_buying_pains=buying_pains,
            contact_source_summary=contact_source_summary,
            sources=sources,
            company_evidence=company_evidence,
            contact_evidence=contact_evidence,
        )

    def persist_bundle(self, session: Session, account: Account, contact: Contact, bundle: ResearchBundle) -> tuple[CompanyResearchBrief, ContactResearchBrief]:
        company_brief = session.exec(
            select(CompanyResearchBrief).where(CompanyResearchBrief.account_id == account.id)
        ).first()
        if company_brief is None:
            company_brief = CompanyResearchBrief(account_id=account.id)
            session.add(company_brief)
            session.flush()

        contact_brief = session.exec(
            select(ContactResearchBrief).where(ContactResearchBrief.contact_id == contact.id)
        ).first()
        if contact_brief is None:
            contact_brief = ContactResearchBrief(contact_id=contact.id)
            session.add(contact_brief)
            session.flush()

        company_brief.summary = bundle.company_summary
        company_brief.icp_fit = bundle.company_icp_fit
        company_brief.growth_stage_region = bundle.company_growth_stage_region
        company_brief.service_relevance = bundle.company_service_relevance
        company_brief.trigger_signals = bundle.company_trigger_signals
        company_brief.source_summary = bundle.company_source_summary
        company_brief.generated_at = utcnow()

        contact_brief.role_summary = bundle.contact_role_summary
        contact_brief.persona_fit = bundle.contact_persona_fit
        contact_brief.personalization_angles = bundle.contact_personalization_angles
        contact_brief.buying_pains = bundle.contact_buying_pains
        contact_brief.source_summary = bundle.contact_source_summary
        contact_brief.generated_at = utcnow()

        existing_sources = session.exec(
            select(ResearchSource).where(
                (ResearchSource.account_id == account.id) | (ResearchSource.contact_id == contact.id)
            )
        ).all()
        source_ids = [source.id for source in existing_sources if source.id is not None]
        if source_ids:
            for evidence in session.exec(
                select(EvidenceSnippet).where(EvidenceSnippet.research_source_id.in_(source_ids))
            ).all():
                session.delete(evidence)
        for evidence in session.exec(
            select(EvidenceSnippet).where(
                (EvidenceSnippet.company_research_brief_id == company_brief.id)
                | (EvidenceSnippet.contact_research_brief_id == contact_brief.id)
            )
        ).all():
            session.delete(evidence)
        for source in existing_sources:
            session.delete(source)
        session.flush()

        stored_sources: list[ResearchSource] = []
        for source in bundle.sources:
            stored = ResearchSource(
                account_id=account.id if source.account_scope else None,
                contact_id=contact.id if source.contact_scope else None,
                source_kind=source.source_kind,
                title=source.title,
                url=source.url,
                snippet=source.snippet,
            )
            session.add(stored)
            session.flush()
            stored_sources.append(stored)

        for evidence in bundle.company_evidence:
            session.add(
                EvidenceSnippet(
                    company_research_brief_id=company_brief.id,
                    research_source_id=stored_sources[evidence.source_index].id
                    if evidence.source_index is not None and evidence.source_index < len(stored_sources)
                    else None,
                    evidence_type=evidence.evidence_type,
                    snippet_text=evidence.snippet_text,
                    note=evidence.note,
                )
            )
        for evidence in bundle.contact_evidence:
            session.add(
                EvidenceSnippet(
                    contact_research_brief_id=contact_brief.id,
                    research_source_id=stored_sources[evidence.source_index].id
                    if evidence.source_index is not None and evidence.source_index < len(stored_sources)
                    else None,
                    evidence_type=evidence.evidence_type,
                    snippet_text=evidence.snippet_text,
                    note=evidence.note,
                )
            )
        session.flush()
        return company_brief, contact_brief

    def _build_internal_source(self, account: Account, contact: Contact) -> ResearchSourceDraft:
        notes = contact.provenance_notes or account.notes or "No additional notes recorded."
        snippet = (
            f"Company {account.company_name}. "
            f"Website {account.company_website or 'not provided'}. "
            f"Contact {contact.display_name} ({contact.job_title or 'role not provided'}). "
            f"Notes: {notes}"
        )
        return ResearchSourceDraft(
            source_kind="import_record",
            title="Imported CRM / list data",
            url="",
            snippet=snippet,
            account_scope=True,
            contact_scope=True,
        )

    def _guess_company_url(self, account: Account, contact: Contact) -> str:
        if account.company_website:
            return self._normalize_url(account.company_website)
        email_domain = contact.email.split("@", 1)[1].strip().lower() if "@" in contact.email else ""
        if not email_domain or email_domain in {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com"}:
            return ""
        return f"https://{email_domain}"

    def _fetch_public_page(self, url: str, source_kind: str, account_scope: bool = False, contact_scope: bool = False) -> ResearchSourceDraft | None:
        try:
            response = self._client.get(self._normalize_url(url))
            response.raise_for_status()
        except Exception:
            return None
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return None
        title = self._extract_title(response.text) or self._safe_domain(url)
        snippet = self._extract_description(response.text) or self._extract_visible_text(response.text)
        if not snippet:
            return None
        return ResearchSourceDraft(
            source_kind=source_kind,
            title=title[:140],
            url=str(response.url),
            snippet=snippet[:600],
            account_scope=account_scope,
            contact_scope=contact_scope,
        )

    def _compose_company_summary(self, account: Account, company_text: str, playbook_hint: str) -> str:
        if company_text:
            return f"{account.company_name} appears to be {company_text[:220].rstrip('. ')}."
        if playbook_hint:
            return f"{account.company_name} is being evaluated against the current playbook positioning: {playbook_hint}"
        return f"{account.company_name} is a candidate account being evaluated for outbound relevance."

    def _compose_icp_fit(self, account: Account, icp: ICPProfile, company_text: str) -> str:
        industries = [item.strip() for item in icp.industries.split(",") if item.strip()]
        matched = next((industry for industry in industries if industry.lower() in company_text.lower()), None)
        if matched:
            return f"Strong ICP signal: public context aligns with the {matched} segment."
        return f"Baseline ICP fit is inferred from imported targeting against {icp.industries.lower()}."

    def _compose_growth_stage_region(self, account: Account, icp: ICPProfile, company_text: str) -> str:
        region = account.country or "Europe/UK target region not yet confirmed"
        size_hint = icp.company_sizes or "SMB range"
        if any(token in company_text.lower() for token in ["platform", "software", "agency", "services", "growth"]):
            return f"Likely aligned with the {size_hint} range and region context of {region}."
        return f"Growth stage is inferred conservatively from the target size band {size_hint}; region context: {region}."

    def _compose_service_relevance(self, icp: ICPProfile, playbook: SalesPlaybook | None, company_text: str) -> str:
        playbook_hint = playbook.positioning_summary if playbook and playbook.positioning_summary else "research-led outbound support"
        pain = next((item.strip() for item in icp.pain_points.split(",") if item.strip()), "pipeline inconsistency")
        if company_text:
            return f"The account may be relevant because public context can support a {playbook_hint.lower()} angle around {pain.lower()}."
        return f"The account is relevant if it is facing {pain.lower()} and needs {playbook_hint.lower()}."

    def _compose_trigger_signals(self, contact: Contact, account: Account, company_text: str) -> str:
        signals = []
        if contact.source_list:
            signals.append(f"listed in {contact.source_list}")
        if account.company_website:
            signals.append("has a public website available for context")
        if company_text:
            signals.append("public copy provides positioning cues")
        return ", ".join(signals) if signals else "No strong trigger signals beyond imported targeting criteria."

    def _compose_role_summary(self, contact: Contact, contact_text: str) -> str:
        role = contact.job_title or "Commercial stakeholder"
        if contact_text:
            return f"{contact.display_name} appears to operate as {role}. Public context adds extra role cues for personalization."
        return f"{contact.display_name} is being treated as {role} based on imported contact data."

    def _compose_personalization_angles(self, contact: Contact, account: Account, contact_text: str, company_text: str) -> str:
        role_reference = contact.job_title or "commercial leadership"
        if contact_text:
            return f"Lead with {contact.display_name}'s {role_reference} remit and tie it to {account.company_name}'s public positioning."
        if company_text:
            return f"Connect {role_reference} priorities to the company's current market focus and keep the ask lightweight."
        return f"Personalize around the {role_reference} role, existing provenance notes, and why the account was targeted."

    def _compose_buying_pains(self, icp: ICPProfile, contact: Contact) -> str:
        pains = [item.strip() for item in icp.pain_points.split(",") if item.strip()]
        if contact.job_title:
            return f"For a {contact.job_title}, likely pains include {', '.join(pains[:2]).lower()}."
        return f"Likely pains include {', '.join(pains[:2]).lower()}."

    def _build_source_summary(self, sources: list[ResearchSourceDraft]) -> str:
        if not sources:
            return "No sources captured."
        labels = [source.title for source in sources[:3]]
        extra = len(sources) - len(labels)
        summary = ", ".join(labels)
        if extra > 0:
            summary = f"{summary}, plus {extra} more"
        return summary

    def _match_persona(self, job_title: str, personas: str) -> str:
        persona_list = [item.strip() for item in personas.split(",") if item.strip()]
        lowered_title = job_title.lower()
        for persona in persona_list:
            if persona.lower() in lowered_title:
                return f"Direct persona match: {persona}"
        return f"Closest persona fit: {persona_list[0]}" if persona_list else "Persona fit not yet classified"

    def _normalize_url(self, raw_url: str) -> str:
        url = raw_url.strip()
        if not url:
            return ""
        if "://" not in url:
            return f"https://{url}"
        return url

    def _safe_domain(self, raw_url: str) -> str:
        parsed = urlparse(self._normalize_url(raw_url))
        return parsed.netloc or raw_url

    def _extract_title(self, html: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        return self._clean_text(match.group(1)) if match else ""

    def _extract_description(self, html: str) -> str:
        patterns = [
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return self._clean_text(match.group(1))
        return ""

    def _extract_visible_text(self, html: str) -> str:
        without_scripts = re.sub(r"<script.*?>.*?</script>|<style.*?>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", without_scripts)
        return self._clean_text(text)[:400]

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", unescape(value)).strip()
