# AISDR Demo Runbook

Use this for the March 19 strat session. The goal is to show product direction and a credible operator workflow, not production readiness.

## Before the session

1. Confirm your `.env` values are correct.
2. If you want more relevant output, open the app once and update Settings with your agency name, positioning, offer, ICP, and booking link.
3. Make sure the local database already contains the prepared sample workflow.
4. Close any old AISDR server windows so port `8000` is free.

## Launch the demo

From the repo root, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1
```

What this does:

- copies your current local database to `data/aisdr-demo.db`
- starts AISDR on `http://127.0.0.1:8000`
- opens the login page in your browser

The launcher uses a demo snapshot, so clicks during the meeting do not affect your working database.

## Suggested 5-10 minute walkthrough

1. `Dashboard`
   Explain the operator model: imported leads, due work, and current pipeline status.
2. `Settings`
   Show how agency positioning, ICP, sequence, and compliance settings shape the generated output.
3. `Imports`
   Explain that Cognism and Salesforce data come in as CSV exports.
4. `Contacts`
   Open the prepared contact record.
5. `Contact detail`
   Show the research brief, the generated 4-step sequence, the approval step, manual-send tracking, and the logged reply with the suggested next response.
6. `Discovery`
   End by showing how the app can suggest new target accounts to pursue next.

## Demo talking points

- Human approval is required before outbound actions.
- Outreach is draft-first and execution-safe for a v1 pilot.
- Contact provenance, suppression, and audit history are built into the workflow.
- The same foundation can later connect to richer enrichment, email, calendar, or CRM systems.

## Fallbacks

- If the browser does not open, go to `http://127.0.0.1:8000/login`.
- If the launcher says port `8000` is busy, close the old server window and rerun it.
- If you need to start manually, run:

```powershell
$env:DATABASE_URL="sqlite:///./data/aisdr-demo.db"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- If the demo data looks stale, rerun `.\scripts\start-demo.ps1` to refresh the snapshot from your working database.
