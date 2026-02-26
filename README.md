# Fiarrd

A personal job search pipeline manager built on SQLite, with a Click CLI, a local Flask dashboard, and Claude AI for fit scoring, outreach drafting, interview prep, and resume generation.

---

## Features

- **Pipeline tracking** — 8-stage funnel (Prospect → Closed) with tier priorities and job family labels
- **AI fit scoring** — Claude evaluates your resume against a JD and returns a 1–10 score, strengths, gaps, and ATS keywords
- **Tailored resume generation** — Claude rewrites your full resume optimized for a specific role and JD; persisted per opportunity
- **Outreach drafting** — generates a LinkedIn connection note, InMail, and email for each contact
- **Email sending** — sends outreach and thank-you emails via a local SMTP relay; tracks Day 0/3/7 follow-up cadence
- **Thank-you drafting** — AI writes post-interview thank-you emails personalized by key moment and fit point
- **Resume bullet tailoring** — rewrites individual bullets to mirror JD language without changing any metrics (CLI)
- **Interview prep** — behavioral and technical questions, company briefing, and questions to ask
- **Follow-up queue** — surfaces contacts due for Day 3 and Day 7 follow-ups
- **Daily digest** — AI-generated briefing: today's priorities, follow-up alerts, and pipeline health
- **RSS/Atom job feed** — polls configured job board feeds, deduplicates by URL, and auto-adds new postings as Prospects
- **Background scheduler** — runs digest, stale-record check, and feed poll automatically each day at a configurable time
- **Metrics dashboard** — stage funnel, fit-score distribution, source and tier breakdowns, outreach response rates
- **Local web dashboard** — filterable opportunity list, contact tracking, activity log, stage management
- **CSV export** — one click (or command) dumps the full pipeline to a dated CSV

---

## Setup

**Requirements:** Python 3.10+

```bash
pip install -r requirements.txt
```

Copy `.env.template` to `.env` and fill in your values:

```bash
cp .env.template .env
```

```
ANTHROPIC_API_KEY=your_key_here
DB_PATH=jobsearch.db              # optional, defaults to jobsearch.db
RESUME_CACHE_PATH=.resume_cache.txt  # optional

# SMTP relay (defaults shown — override if your relay differs)
SMTP_HOST=192.168.1.24
SMTP_PORT=25
SMTP_FROM=noreply@example.com
SENDER_NAME=Your Name
```

The database is created automatically on first run. App settings (scheduler time, feed URLs, SMTP overrides) are persisted to `app_settings.json` via the Settings page.

---

## CLI Usage

```bash
python main.py <command> [args]
```

| Command | What it does |
|---|---|
| `add-job` | Ingest a job posting (URL or pasted text), parse with AI, add to pipeline |
| `score-fit <opp_id>` | Score resume fit against a JD (1–10 with rationale) |
| `add-contact <opp_id>` | Attach a contact (HM, recruiter, peer, etc.) to an opportunity |
| `send-outreach <contact_id>` | Draft AI outreach, confirm, and log Day 0 |
| `follow-up` | Show contacts due for Day 3 / Day 7 follow-up and mark as sent |
| `advance <opp_id> <stage>` | Move an opportunity to a new pipeline stage |
| `prep <opp_id>` | Generate interview prep materials |
| `tailor <opp_id>` | Rewrite resume bullets to match JD keywords |
| `digest` | Print and log a daily AI-generated briefing |
| `dashboard` | Launch the local web UI at http://127.0.0.1:5001 |
| `list [--stage STAGE]` | List all open opportunities in a table |
| `export` | Export all opportunities to a dated CSV |

### Typical workflow for a new opportunity

```bash
# 1. Add the job
python main.py add-job

# 2. Score fit against your resume
python main.py score-fit 1

# 3. Add a contact and draft outreach
python main.py add-contact 1
python main.py send-outreach 1

# 4. Check follow-ups each morning
python main.py follow-up

# 5. Advance stage after a recruiter call
python main.py advance 1 "Recruiter Screen"

# 6. Prep for interviews
python main.py prep 1
```

---

## Web Dashboard

```bash
python main.py dashboard
# Opens at http://127.0.0.1:5001
```

The dashboard is local-only (binds to 127.0.0.1) with no authentication. The background scheduler starts automatically when the dashboard runs.

| Route | What it does |
|---|---|
| `/` | Today's queue, pipeline stage counts, stale opportunity alerts |
| `/opportunities` | Full opportunity list with stage/tier/job-family filters |
| `/opportunity/<id>` | Detail view: JD keywords, fit summary, contacts, activity log, stage management, AI scoring, interview prep, tailored resume |
| `/add-job` | Two-step form — paste a URL or JD text → AI extracts fields → confirm and save |
| `/contacts` | All contacts with response-status color coding and follow-up highlights |
| `/metrics` | Pipeline funnel, fit-score distribution, source/tier breakdowns, outreach response rates |
| `/settings` | Edit resume, set daily digest time, configure SMTP relay, manage RSS feed URLs and keyword filters |
| `/export` | Download full pipeline as a CSV file |

### Opportunity detail actions (AJAX)

- **Score Fit** — runs AI fit analysis against the cached resume and updates the score in-page
- **Generate Tailored Resume** — rewrites your full resume for this specific role; result is saved and shown on future page loads
- **Interview Prep** — generates prep materials (displayed inline, not stored)
- **Draft Outreach** — writes LinkedIn note + email copy for a contact
- **Send Email** — sends outreach or thank-you via SMTP relay, logs Day 0
- **Draft Thank You** — AI writes a post-interview thank-you (provide key moment + fit point)
- **Mark as Sent** — logs outreach without sending (for messages sent outside the app)

---

## Pipeline Stages

```
Prospect → Warm Lead → Applied → Recruiter Screen → HM Interview → Loop → Offer Pending → Closed
```

Each stage transition recalculates `next_action_date` and logs to the activity trail. The **Change Stage** card on the opportunity detail page allows movement in either direction. When closing an opportunity, a **Close Reason** field appears (Accepted / Declined / Rejected / Ghosted / Withdrew).

---

## Job Families

| Code | Label |
|---|---|
| A | Analytics Manager |
| B | Data Manager |
| C | BI Manager |
| D | Decision Science |
| E | Director Stretch |

---

## RSS Job Feeds

Configure feed URLs and keyword filters in **Settings → Job Feeds**. On each scheduled poll (and via the dashboard's manual "Poll Now" button), the system:

1. Fetches each RSS/Atom feed URL
2. Filters titles against your keyword list (blank = import everything)
3. Deduplicates by posting URL — existing entries are never re-imported
4. Creates new Prospect opportunities with source set to `Other`

No AI calls are made during ingestion. Run Score Fit or Generate Tailored Resume from the opportunity page once you decide a posting is worth pursuing.

---

## Project Structure

```
├── main.py              CLI entry point (Click commands)
├── config.py            Environment config, constants, owner context
├── requirements.txt
├── .env.template
│
├── models/              Data models and CRUD
│   ├── opportunity.py
│   ├── contact.py
│   └── activity.py
│
├── modules/             Business logic
│   ├── ai_engine.py     All Anthropic API calls (score, outreach, prep, tailor, digest, thank-you, resume)
│   ├── workflow.py      Stage transitions, follow-up queue, stale alerts
│   ├── ingester.py      JD parsing from URL or pasted text
│   ├── digest.py        Daily digest generation
│   ├── mailer.py        SMTP email sending
│   ├── job_feed.py      RSS/Atom feed polling and deduplication
│   └── scheduler.py     Background thread: daily digest, stale check, feed poll
│
├── db/
│   ├── database.py      SQLite connection, query wrapper, and schema migrations
│   └── schema.sql       Tables, triggers, and views
│
├── web/
│   ├── app.py           Flask app initialization + scheduler startup
│   └── routes.py        Dashboard route handlers
│
├── templates/           Jinja2 HTML templates
│   ├── base.html
│   ├── dashboard.html
│   ├── opportunities.html
│   ├── opportunity.html
│   ├── contacts.html
│   ├── add_job.html
│   ├── metrics.html
│   └── settings.html
│
└── tests/
    ├── test_ai_engine.py
    └── test_workflow.py
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests use a mocked Anthropic client and an in-memory SQLite database — no tokens burned, no files written.

---

## Data & Privacy

- Resume text is cached locally in `.resume_cache.txt` and never written to the database
- Tailored resumes are stored per-opportunity in the local SQLite database
- The Anthropic API key is loaded from `.env` and never logged or committed
- The database is a local SQLite file (`jobsearch.db` by default)
- App settings (digest time, feed URLs, SMTP config) are stored in `app_settings.json`
- `.resume_cache.txt`, `.env`, and `app_settings.json` should be added to `.gitignore` if you version-control this directory
