# AISDR

AISDR is a Python-first internal Sales Development Representative pilot for services teams. It ingests exported lead data, generates research and multi-step outreach drafts, tracks manual-send execution, and helps convert replies into meetings while keeping a full audit trail.

## What it does

- Imports Cognism, Salesforce, or manual CSV lists into a single prospect workspace.
- Stores configurable agency, offer, ICP, sequence, and compliance settings.
- Generates research briefs and a default 4-step email/LinkedIn sequence for each contact.
- Requires human approval before any step is marked ready to send.
- Tracks manual send outcomes, reply handling, suppression, and meeting-booked states.
- Produces discovery suggestions for where to prospect next.

## Stack

- FastAPI
- Jinja2 + HTMX
- SQLModel / SQLAlchemy
- SQLite for local development
- Postgres-ready via `DATABASE_URL`
- Optional OpenAI integration with deterministic fallbacks when no API key is configured

## Local setup

1. Create a virtual environment.
2. Install the project:

```bash
python -m pip install -e .[dev]
```

3. Copy `.env.example` to `.env` and update the admin credentials and session secret.
4. Run the app:

```bash
uvicorn app.main:app --reload
```

5. Open `http://127.0.0.1:8000`.

## CSV contract

Required:

- `company_name`
- At least one of `email` or `linkedin_url`

Optional:

- `first_name`
- `last_name`
- `job_title`
- `company_website`
- `country`
- `source_system`
- `source_list`
- `notes`

## Testing

```bash
pytest
```

## Railway deployment

The repo includes a `Dockerfile` suitable for Railway. Set these environment variables in Railway:

- `DATABASE_URL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `SESSION_SECRET`
- `OPENAI_API_KEY` if you want live model calls

## GitHub next steps

This workspace does not currently have `git` on the shell path, so connect it after installing Git for Windows.

Recommended flow for your existing remote repository:

```bash
git init
git remote add origin https://github.com/<owner>/<repo>.git
git add .
git commit -m "Initial AISDR MVP scaffold"
git branch -M main
git push -u origin main
```

After that, GitHub Actions will run the included CI workflow on push.

