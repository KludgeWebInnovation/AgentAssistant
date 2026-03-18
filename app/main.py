from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import get_session, init_db
from app.models import (
    Account,
    AgencyProfile,
    ApprovalTask,
    AuditEvent,
    ComplianceSettings,
    Contact,
    ICPProfile,
    LeadSource,
    LeadState,
    OfferProfile,
    ReplyEvent,
    ResearchBrief,
    Sequence,
    SequenceStep,
    SequenceTemplate,
    StepStatus,
    utcnow,
)
from app.services.ai import OpenAIService
from app.services.importer import ImportSummary, import_contacts
from app.services.replies import handle_reply
from app.services.sequences import approve_step, generate_research_brief, generate_sequence, pause_contact, record_manual_send

settings = get_settings()
templates = Jinja2Templates(directory=str(settings.base_dir / "app" / "templates"))
ai_service = OpenAIService()


class NotAuthenticated(Exception):
    pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")
app.mount("/static", StaticFiles(directory=str(settings.base_dir / "app" / "static")), name="static")


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, _: NotAuthenticated) -> RedirectResponse:
    set_flash(request, "Please sign in first.", "warning")
    return RedirectResponse("/login", status_code=303)


def require_auth(request: Request) -> str:
    if request.session.get("user") != settings.admin_username:
        raise NotAuthenticated()
    return settings.admin_username


def is_hx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def set_flash(request: Request, message: str, level: str = "info") -> None:
    request.session["flash"] = {"message": message, "level": level}


def pop_flash(request: Request) -> dict[str, str] | None:
    return request.session.pop("flash", None)


def base_context(request: Request, **extra):
    return {
        "request": request,
        "app_name": settings.app_name,
        "flash": pop_flash(request),
        "current_user": request.session.get("user"),
        "today": date.today(),
        **extra,
    }


def get_singletons(session: Session):
    agency = session.exec(select(AgencyProfile)).first()
    offer = session.exec(select(OfferProfile)).first()
    icp = session.exec(select(ICPProfile)).first()
    template = session.exec(select(SequenceTemplate)).first()
    compliance = session.exec(select(ComplianceSettings)).first()
    return agency, offer, icp, template, compliance


def load_contact_detail(session: Session, contact_id: int):
    contact = session.get(Contact, contact_id)
    if contact is None:
        return None
    account = session.get(Account, contact.account_id)
    research = session.exec(select(ResearchBrief).where(ResearchBrief.contact_id == contact.id)).first()
    sequence = session.exec(
        select(Sequence).where(Sequence.contact_id == contact.id).order_by(Sequence.generated_at.desc())
    ).first()
    steps = []
    if sequence:
        steps = session.exec(
            select(SequenceStep).where(SequenceStep.sequence_id == sequence.id).order_by(SequenceStep.step_order)
        ).all()
    replies = session.exec(
        select(ReplyEvent).where(ReplyEvent.contact_id == contact.id).order_by(ReplyEvent.created_at.desc())
    ).all()
    tasks = session.exec(
        select(ApprovalTask).where(ApprovalTask.contact_id == contact.id).order_by(ApprovalTask.created_at.desc())
    ).all()
    return {
        "contact": contact,
        "account": account,
        "research": research,
        "sequence": sequence,
        "steps": steps,
        "replies": replies,
        "tasks": tasks,
    }


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user") == settings.admin_username:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", base_context(request))


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == settings.admin_username and password == settings.admin_password:
        request.session["user"] = settings.admin_username
        set_flash(request, "Signed in.", "success")
        return RedirectResponse("/", status_code=303)
    set_flash(request, "Invalid credentials.", "danger")
    return RedirectResponse("/login", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    contacts = session.exec(select(Contact).order_by(Contact.last_activity_at.desc())).all()
    due_steps = session.exec(
        select(SequenceStep)
        .where(
            SequenceStep.status.in_([StepStatus.PENDING, StepStatus.APPROVED]),
            SequenceStep.due_date <= date.today(),
        )
        .order_by(SequenceStep.due_date, SequenceStep.step_order)
    ).all()
    counts = {
        "contacts": len(contacts),
        "due_steps": len(due_steps),
        "meetings": len([contact for contact in contacts if contact.lead_state == LeadState.MEETING_BOOKED]),
        "suppressed": len([contact for contact in contacts if contact.do_not_contact]),
    }
    return templates.TemplateResponse(
        "dashboard.html",
        base_context(
            request,
            counts=counts,
            due_steps=due_steps[:10],
            recent_contacts=contacts[:8],
        ),
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    agency, offer, icp, template, compliance = get_singletons(session)
    return templates.TemplateResponse(
        "settings.html",
        base_context(
            request,
            agency=agency,
            offer=offer,
            icp=icp,
            template=template,
            compliance=compliance,
        ),
    )


@app.post("/settings")
async def update_settings(
    request: Request,
    agency_name: str = Form(...),
    website: str = Form(""),
    positioning: str = Form(""),
    value_proposition: str = Form(""),
    target_region: str = Form("Europe/UK"),
    service_name: str = Form(...),
    offer_summary: str = Form(""),
    differentiators: str = Form(""),
    call_to_action: str = Form(""),
    industries: str = Form(""),
    company_sizes: str = Form(""),
    personas: str = Form(""),
    pain_points: str = Form(""),
    exclusions: str = Form(""),
    template_name: str = Form(...),
    channels: str = Form(...),
    delay_days: str = Form(...),
    step_labels: str = Form(...),
    booking_link: str = Form(""),
    opt_out_text: str = Form(""),
    region: str = Form("Europe/UK"),
    manual_review_required: bool = Form(False),
    provenance_required: bool = Form(False),
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    agency, offer, icp, template, compliance = get_singletons(session)

    agency.agency_name = agency_name
    agency.website = website
    agency.positioning = positioning
    agency.value_proposition = value_proposition
    agency.target_region = target_region
    agency.updated_at = utcnow()

    offer.service_name = service_name
    offer.offer_summary = offer_summary
    offer.differentiators = differentiators
    offer.call_to_action = call_to_action
    offer.updated_at = utcnow()

    icp.industries = industries
    icp.company_sizes = company_sizes
    icp.personas = personas
    icp.pain_points = pain_points
    icp.exclusions = exclusions
    icp.updated_at = utcnow()

    template.name = template_name
    template.channels = channels
    template.delay_days = delay_days
    template.step_labels = step_labels
    template.updated_at = utcnow()

    compliance.booking_link = booking_link
    compliance.opt_out_text = opt_out_text
    compliance.region = region
    compliance.manual_review_required = manual_review_required
    compliance.provenance_required = provenance_required
    compliance.updated_at = utcnow()

    session.add(AuditEvent(event_type="settings_updated", detail="Core configuration updated."))
    session.commit()
    set_flash(request, "Settings updated.", "success")
    return RedirectResponse("/settings", status_code=303)


@app.get("/imports", response_class=HTMLResponse)
def imports_page(
    request: Request,
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    history = session.exec(select(LeadSource).order_by(LeadSource.imported_at.desc())).all()
    return templates.TemplateResponse("imports.html", base_context(request, history=history))


@app.post("/imports")
async def upload_import(
    request: Request,
    file: UploadFile = File(...),
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    content = await file.read()
    summary: ImportSummary = import_contacts(session, file.filename or "upload.csv", content)
    session.commit()
    message = (
        f"Imported {summary.created_contacts} new contacts, updated {summary.updated_contacts}, "
        f"and skipped {summary.skipped_rows} rows."
    )
    if summary.errors:
        message = f"{message} First issue: {summary.errors[0]}"
    set_flash(request, message, "success")
    return RedirectResponse("/imports", status_code=303)


@app.get("/contacts", response_class=HTMLResponse)
def contacts_page(
    request: Request,
    q: str = "",
    state: str = "",
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    contacts = session.exec(select(Contact).order_by(Contact.last_activity_at.desc())).all()
    accounts = {account.id: account for account in session.exec(select(Account)).all()}
    if q:
        query = q.lower()
        contacts = [
            contact
            for contact in contacts
            if query in contact.display_name.lower()
            or query in contact.email.lower()
            or query in accounts.get(contact.account_id, Account(company_name="")).company_name.lower()
        ]
    if state:
        contacts = [contact for contact in contacts if contact.lead_state.value == state]
    return templates.TemplateResponse(
        "contacts.html",
        base_context(
            request,
            contacts=contacts,
            accounts=accounts,
            query=q,
            state=state,
            states=[item.value for item in LeadState],
        ),
    )


@app.get("/contacts/{contact_id}", response_class=HTMLResponse)
def contact_detail(
    request: Request,
    contact_id: int,
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    detail = load_contact_detail(session, contact_id)
    if detail is None:
        set_flash(request, "Contact not found.", "danger")
        return RedirectResponse("/contacts", status_code=303)
    return templates.TemplateResponse("contact_detail.html", base_context(request, **detail))


@app.post("/contacts/{contact_id}/generate")
def generate_contact_assets(
    request: Request,
    contact_id: int,
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    detail = load_contact_detail(session, contact_id)
    if detail is None:
        set_flash(request, "Contact not found.", "danger")
        return RedirectResponse("/contacts", status_code=303)
    agency, offer, icp, template, compliance = get_singletons(session)
    package = ai_service.generate_research_package(
        account_name=detail["account"].company_name,
        company_website=detail["account"].company_website,
        contact=detail["contact"],
        agency=agency,
        offer=offer,
        icp=icp,
        compliance=compliance,
        template=template,
    )
    generate_research_brief(session, detail["contact"], package)
    generate_sequence(session, detail["contact"], template, package)
    session.commit()
    set_flash(request, "Research brief and sequence regenerated.", "success")
    return RedirectResponse(f"/contacts/{contact_id}", status_code=303)


@app.post("/steps/{step_id}/approve", response_class=HTMLResponse)
def approve_sequence_step(
    request: Request,
    step_id: int,
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    step = session.get(SequenceStep, step_id)
    if step is None:
        return HTMLResponse("Step not found", status_code=404)
    sequence = session.get(Sequence, step.sequence_id)
    contact = session.get(Contact, sequence.contact_id) if sequence else None
    if contact is None:
        return HTMLResponse("Contact not found", status_code=404)
    approve_step(session, contact, step)
    session.commit()
    if is_hx(request):
        detail = load_contact_detail(session, contact.id)
        return templates.TemplateResponse("partials/sequence_panel.html", base_context(request, **detail))
    return RedirectResponse(f"/contacts/{contact.id}", status_code=303)


@app.post("/steps/{step_id}/record-send", response_class=HTMLResponse)
def record_step_send(
    request: Request,
    step_id: int,
    audit_note: str = Form(""),
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    step = session.get(SequenceStep, step_id)
    if step is None:
        return HTMLResponse("Step not found", status_code=404)
    sequence = session.get(Sequence, step.sequence_id)
    contact = session.get(Contact, sequence.contact_id) if sequence else None
    if contact is None:
        return HTMLResponse("Contact not found", status_code=404)
    record_manual_send(session, contact, step, audit_note)
    session.commit()
    if is_hx(request):
        detail = load_contact_detail(session, contact.id)
        return templates.TemplateResponse("partials/sequence_panel.html", base_context(request, **detail))
    return RedirectResponse(f"/contacts/{contact.id}", status_code=303)


@app.post("/contacts/{contact_id}/reply", response_class=HTMLResponse)
async def reply_assistant(
    request: Request,
    contact_id: int,
    reply_text: str = Form(...),
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    detail = load_contact_detail(session, contact_id)
    if detail is None:
        return HTMLResponse("Contact not found", status_code=404)
    _, offer, _, _, compliance = get_singletons(session)
    handle_reply(
        session=session,
        ai_service=ai_service,
        account_name=detail["account"].company_name,
        contact=detail["contact"],
        reply_text=reply_text,
        offer=offer,
        compliance=compliance,
    )
    session.commit()
    if is_hx(request):
        detail = load_contact_detail(session, contact_id)
        return templates.TemplateResponse("partials/reply_panel.html", base_context(request, **detail))
    return RedirectResponse(f"/contacts/{contact_id}", status_code=303)


@app.post("/contacts/{contact_id}/status")
def update_contact_status(
    request: Request,
    contact_id: int,
    status: str = Form(...),
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    detail = load_contact_detail(session, contact_id)
    if detail is None:
        return RedirectResponse("/contacts", status_code=303)
    contact = detail["contact"]
    if status == LeadState.MEETING_BOOKED.value:
        pause_contact(session, contact, "Meeting booked.", LeadState.MEETING_BOOKED)
    elif status == LeadState.DO_NOT_CONTACT.value:
        pause_contact(session, contact, "Manually suppressed.", LeadState.DO_NOT_CONTACT)
    elif status == LeadState.DISQUALIFIED.value:
        pause_contact(session, contact, "Marked disqualified.", LeadState.DISQUALIFIED)
    else:
        contact.lead_state = LeadState(status)
        contact.last_activity_at = utcnow()
        session.add(AuditEvent(contact_id=contact.id, event_type="status_updated", detail=status))
    session.commit()
    return RedirectResponse(f"/contacts/{contact_id}", status_code=303)


@app.get("/discovery", response_class=HTMLResponse)
def discovery_page(
    request: Request,
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    _, offer, icp, _, _ = get_singletons(session)
    return templates.TemplateResponse(
        "discovery.html",
        base_context(request, offer=offer, icp=icp, suggestions=[]),
    )


@app.post("/discovery/generate", response_class=HTMLResponse)
def discovery_generate(
    request: Request,
    count: int = Form(5),
    _: str = Depends(require_auth),
    session: Session = Depends(get_session),
):
    _, offer, icp, _, _ = get_singletons(session)
    suggestions = ai_service.generate_discovery_suggestions(offer, icp, count=max(1, min(count, 10)))
    if is_hx(request):
        return templates.TemplateResponse("partials/discovery_results.html", base_context(request, suggestions=suggestions))
    return templates.TemplateResponse("discovery.html", base_context(request, offer=offer, icp=icp, suggestions=suggestions))

