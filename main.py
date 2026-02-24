#!/usr/bin/env python3
"""
main.py — Job Search Ops CLI
Usage: python main.py <command> [args]
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import date

import click

# Ensure project root is always on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def _load_resume() -> str:
    """Load resume text from cache file, prompting if not present."""
    from config import RESUME_CACHE_PATH
    cache = Path(RESUME_CACHE_PATH)
    if cache.exists() and cache.stat().st_size > 100:
        return cache.read_text()
    click.echo("\n📄 No resume cache found. Paste your resume text below.")
    click.echo("(Paste all text, then press Enter, then type END on a new line and press Enter)\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    resume_text = "\n".join(lines)
    cache.write_text(resume_text)
    click.echo(f"✓ Resume saved to {RESUME_CACHE_PATH}")
    return resume_text


def _pick_job_family() -> str:
    from config import JOB_FAMILIES
    click.echo("\nJob Family:")
    for k, v in JOB_FAMILIES.items():
        click.echo(f"  {k}) {v}")
    choice = click.prompt("Select", type=click.Choice(list(JOB_FAMILIES.keys())), default="A")
    return choice


@click.group()
def cli():
    """Job Search Ops — manage your pipeline from the command line."""
    pass


@cli.command("add-job")
def add_job():
    """Ingest a job posting (paste text or URL) and add to pipeline."""
    from modules.ingester import ingest_jd
    from models.opportunity import create_opportunity
    from models.activity import log_activity
    from modules.workflow import calculate_next_action

    click.echo("\n🔍 Add Job Opportunity")
    click.echo("─" * 40)

    source_type = click.prompt(
        "Source type",
        type=click.Choice(["url", "text"]),
        default="text"
    )

    if source_type == "url":
        source = click.prompt("Job posting URL")
    else:
        click.echo("Paste job description (type END on a new line when done):\n")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "END":
                break
            lines.append(line)
        source = "\n".join(lines)

    click.echo("\n⏳ Parsing job description with AI...")
    try:
        structured = ingest_jd(source)
    except Exception as e:
        click.echo(f"❌ Failed to parse JD: {e}", err=True)
        sys.exit(1)

    # Show what AI extracted, allow overrides
    click.echo(f"\n✓ Extracted:")
    click.echo(f"  Company:    {structured.get('company', '—')}")
    click.echo(f"  Role:       {structured.get('role_title', '—')}")
    click.echo(f"  Family:     {structured.get('job_family_guess', '—')}")
    click.echo(f"  Salary:     {structured.get('salary_range', '—')}")
    click.echo(f"  Remote:     {structured.get('remote_ok', '—')}")
    click.echo(f"  Keywords:   {', '.join(structured.get('keywords', []))}")

    company = click.prompt("\nCompany", default=structured.get("company") or "")
    role_title = click.prompt("Role title", default=structured.get("role_title") or "")
    job_family = _pick_job_family()
    tier = click.prompt("Tier (1=top priority, 3=low)", type=click.IntRange(1, 3), default=2)
    source_label = click.prompt(
        "Source",
        type=click.Choice(["LinkedIn", "Referral", "Job Board", "Outbound", "Other"]),
        default="LinkedIn"
    )
    salary = click.prompt("Salary range", default=structured.get("salary_range") or "", show_default=False)

    keywords_list = structured.get("keywords", [])
    keywords_json = json.dumps(keywords_list)
    next_action_text, days_out = calculate_next_action("Prospect")
    next_action_date = (date.today() - __import__("datetime").timedelta(days=0) + __import__("datetime").timedelta(days=days_out)).isoformat()

    opp_id = create_opportunity(
        company=company,
        role_title=role_title,
        job_family=job_family,
        tier=tier,
        stage="Prospect",
        source=source_label,
        salary_range=salary or None,
        jd_url=structured.get("source_url"),
        jd_raw=structured.get("raw_text"),
        jd_keywords=keywords_json,
        next_action=next_action_text,
        next_action_date=next_action_date,
    )

    log_activity(
        activity_type="Note Added",
        description=f"Opportunity created via add-job CLI",
        opportunity_id=opp_id,
    )

    click.echo(f"\n✅ Added opportunity ID {opp_id}: {company} — {role_title}")
    click.echo(f"   Next action: {next_action_text} (by {next_action_date})")
    click.echo(f"\n   Run fit score: python main.py score-fit {opp_id}")
    click.echo(f"   Add contact:   python main.py add-contact {opp_id}")


@cli.command("score-fit")
@click.argument("opp_id", type=int)
def score_fit(opp_id):
    """Run AI fit score for an opportunity."""
    from models.opportunity import get_opportunity, update_opportunity
    from modules.ai_engine import score_fit as ai_score_fit

    opp = get_opportunity(opp_id)
    if not opp:
        click.echo(f"❌ Opportunity {opp_id} not found.", err=True)
        sys.exit(1)

    if not opp.jd_raw:
        click.echo("❌ No JD text stored for this opportunity. Re-add with paste.", err=True)
        sys.exit(1)

    resume_text = _load_resume()
    click.echo(f"\n⏳ Scoring fit: {opp.company} — {opp.role_title}...")

    try:
        result = ai_score_fit(resume_text, opp.jd_raw, opportunity_id=opp_id)
    except Exception as e:
        click.echo(f"❌ AI scoring failed: {e}", err=True)
        sys.exit(1)

    # Store result
    update_opportunity(opp_id, fit_score=result.get("fit_score"), ai_fit_summary=json.dumps(result))

    click.echo(f"\n{'='*50}")
    click.echo(f"FIT SCORE: {result.get('fit_score')}/10")
    click.echo(f"{'='*50}")
    click.echo(f"\n{result.get('score_rationale', '')}")
    click.echo(f"\n✅ Strengths:")
    for s in result.get("top_strengths", []):
        click.echo(f"   • {s}")
    click.echo(f"\n⚠ Gaps:")
    for g in result.get("gaps_or_risks", []):
        click.echo(f"   • {g}")
    click.echo(f"\n🔑 ATS Keywords: {', '.join(result.get('ats_keywords', []))}")
    click.echo(f"\n💡 Suggested bullet: {result.get('suggested_bullet_rewrite', '')}")


@cli.command("add-contact")
@click.argument("opp_id", type=int)
def add_contact_cmd(opp_id):
    """Add a contact to an opportunity."""
    from models.opportunity import get_opportunity
    from models.contact import create_contact
    from models.activity import log_activity

    opp = get_opportunity(opp_id)
    if not opp:
        click.echo(f"❌ Opportunity {opp_id} not found.", err=True)
        sys.exit(1)

    click.echo(f"\n👤 Add Contact — {opp.company}: {opp.role_title}")
    click.echo("─" * 40)

    full_name = click.prompt("Full name")
    title = click.prompt("Title", default="", show_default=False)
    company = click.prompt("Company", default=opp.company)
    linkedin = click.prompt("LinkedIn URL", default="", show_default=False)
    email = click.prompt("Email (optional)", default="", show_default=False)
    contact_type = click.prompt(
        "Contact type",
        type=click.Choice(["Hiring Manager", "Peer", "Recruiter", "Alumni", "Referral Source", "Other"]),
        default="Recruiter"
    )
    notes = click.prompt("Notes", default="", show_default=False)

    contact_id = create_contact(
        full_name=full_name,
        opportunity_id=opp_id,
        title=title or None,
        company=company or None,
        linkedin_url=linkedin or None,
        email=email or None,
        contact_type=contact_type,
        notes=notes or None,
    )

    log_activity(
        activity_type="Note Added",
        description=f"Contact added: {full_name} ({contact_type})",
        opportunity_id=opp_id,
        contact_id=contact_id,
    )

    click.echo(f"\n✅ Contact {contact_id} added: {full_name}")
    click.echo(f"   Send outreach: python main.py send-outreach {contact_id}")


@cli.command("send-outreach")
@click.argument("contact_id", type=int)
def send_outreach(contact_id):
    """Draft AI outreach for a contact, confirm, and log Day 0."""
    from models.contact import get_contact, update_contact
    from models.opportunity import get_opportunity
    from models.activity import log_activity
    from modules.ai_engine import draft_outreach

    contact = get_contact(contact_id)
    if not contact:
        click.echo(f"❌ Contact {contact_id} not found.", err=True)
        sys.exit(1)

    opp = get_opportunity(contact.opportunity_id) if contact.opportunity_id else None

    click.echo(f"\n✉ Draft Outreach — {contact.full_name}")
    hook = click.prompt("Hook / reason for reaching out (1-2 sentences)")

    context = {
        "contact_name": contact.full_name,
        "contact_title": contact.title or "Professional",
        "company": contact.company or (opp.company if opp else "their company"),
        "contact_type": contact.contact_type or "Other",
        "hook": hook,
    }

    click.echo("\n⏳ Drafting outreach with AI...")
    try:
        result = draft_outreach(context)
    except Exception as e:
        click.echo(f"❌ AI draft failed: {e}", err=True)
        sys.exit(1)

    click.echo(f"\n{'='*50}")
    click.echo("📎 LINKEDIN NOTE (≤300 chars):")
    click.echo(result.get("linkedin_note", ""))
    click.echo(f"\n📧 EMAIL SUBJECT: {result.get('subject_line', '')}")
    click.echo(f"\n📧 INMAIL / EMAIL:")
    click.echo(result.get("inmail_or_email", ""))
    click.echo("="*50)

    if click.confirm("\nMark Day 0 outreach as sent?", default=True):
        today = date.today().isoformat()
        update_contact(contact_id, outreach_day0=today, response_status="Pending")
        log_activity(
            activity_type="Outreach Sent",
            description=f"Day 0 outreach sent to {contact.full_name}",
            opportunity_id=contact.opportunity_id,
            contact_id=contact_id,
        )
        click.echo(f"✅ Day 0 logged for {contact.full_name} on {today}")
        click.echo(f"   Follow-up will be due in 3 days ({date.today().__class__.today().__class__.fromordinal(date.today().toordinal()+3).isoformat()})")


@cli.command("follow-up")
def follow_up():
    """Show today's follow-up queue and mark as sent."""
    from modules.workflow import get_followup_queue
    from models.contact import update_contact
    from models.activity import log_activity

    queue = get_followup_queue()
    if not queue:
        click.echo("✓ No follow-ups due today.")
        return

    click.echo(f"\n📬 Follow-up Queue ({len(queue)} contacts)")
    click.echo("─" * 50)

    for item in queue:
        click.echo(f"\n  {item['full_name']} ({item.get('contact_type', '?')})")
        click.echo(f"  {item.get('opp_company') or item.get('company', '?')} — {item['role_title']}")
        click.echo(f"  Reason: {item['followup_reason']}")
        click.echo(f"  Day 0 was: {item['outreach_day0']}")

        action = click.prompt(
            "  Action",
            type=click.Choice(["sent", "skip", "responded", "no-response"]),
            default="sent"
        )

        today = date.today().isoformat()
        if action == "sent":
            # Determine which day field to update
            day0 = item.get("outreach_day0")
            from datetime import datetime, timedelta
            d0 = datetime.fromisoformat(day0) if day0 else None
            days_since = (datetime.today() - d0).days if d0 else 0
            if days_since >= 6:
                update_contact(item["contact_id"], outreach_day7=today)
                field = "Day 7"
            else:
                update_contact(item["contact_id"], outreach_day3=today)
                field = "Day 3"
            log_activity(
                activity_type="Follow-Up Sent",
                description=f"{field} follow-up sent to {item['full_name']}",
                opportunity_id=item["opportunity_id"],
                contact_id=item["contact_id"],
            )
            click.echo(f"  ✅ {field} follow-up logged.")
        elif action == "responded":
            update_contact(item["contact_id"], response_status="Responded")
            log_activity(
                activity_type="Response Received",
                description=f"{item['full_name']} responded",
                opportunity_id=item["opportunity_id"],
                contact_id=item["contact_id"],
            )
            click.echo("  ✅ Marked as Responded.")
        elif action == "no-response":
            update_contact(item["contact_id"], response_status="No Response")
            click.echo("  ✅ Marked as No Response.")
        else:
            click.echo("  ⏭ Skipped.")


@cli.command("advance")
@click.argument("opp_id", type=int)
@click.argument("new_stage")
def advance(opp_id, new_stage):
    """Move an opportunity to a new stage."""
    from modules.workflow import advance_stage
    from config import STAGE_ORDER

    valid = STAGE_ORDER
    if new_stage not in valid:
        click.echo(f"❌ Invalid stage. Choose from: {', '.join(valid)}", err=True)
        sys.exit(1)

    note = click.prompt("Note (optional)", default="", show_default=False)
    advance_stage(opp_id, new_stage, note=note or None)
    click.echo(f"✅ Opportunity {opp_id} advanced to: {new_stage}")


@cli.command("prep")
@click.argument("opp_id", type=int)
def prep(opp_id):
    """Generate interview prep materials for an opportunity."""
    from models.opportunity import get_opportunity
    from modules.ai_engine import generate_interview_prep

    opp = get_opportunity(opp_id)
    if not opp:
        click.echo(f"❌ Opportunity {opp_id} not found.", err=True)
        sys.exit(1)
    if not opp.jd_raw:
        click.echo("❌ No JD text stored.", err=True)
        sys.exit(1)

    click.echo(f"\n⏳ Generating interview prep: {opp.company} — {opp.role_title}...")
    try:
        result = generate_interview_prep(opp.role_title, opp.company, opp.jd_raw, opp_id)
    except Exception as e:
        click.echo(f"❌ AI prep failed: {e}", err=True)
        sys.exit(1)

    click.echo(f"\n{'='*55}")
    click.echo(f"INTERVIEW PREP: {opp.role_title} @ {opp.company}")
    click.echo("="*55)
    click.echo(f"\n🏢 COMPANY BRIEFING\n{result.get('company_briefing', '')}")
    click.echo(f"\n⚠ WATCH OUT FOR\n{result.get('watch_out_for', '')}")
    click.echo(f"\n🎯 BEHAVIORAL QUESTIONS")
    for i, q in enumerate(result.get("behavioral_questions", []), 1):
        click.echo(f"  {i}. {q}")
    click.echo(f"\n⚙ TECHNICAL QUESTIONS")
    for i, q in enumerate(result.get("technical_questions", []), 1):
        click.echo(f"  {i}. {q}")
    click.echo(f"\n❓ QUESTIONS TO ASK THEM")
    for i, q in enumerate(result.get("questions_to_ask_them", []), 1):
        click.echo(f"  {i}. {q}")


@cli.command("tailor")
@click.argument("opp_id", type=int)
def tailor(opp_id):
    """Tailor resume bullets to match a JD's keywords."""
    from models.opportunity import get_opportunity
    from modules.ai_engine import tailor_resume_bullets

    opp = get_opportunity(opp_id)
    if not opp:
        click.echo(f"❌ Opportunity {opp_id} not found.", err=True)
        sys.exit(1)

    keywords = json.loads(opp.jd_keywords) if opp.jd_keywords else []
    jd_context = (opp.jd_raw or "")[:2000]

    click.echo("\nPaste your resume bullets (one per line, type END when done):\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        if line.strip():
            lines.append(line.strip())

    if not lines:
        click.echo("❌ No bullets entered.", err=True)
        sys.exit(1)

    click.echo(f"\n⏳ Tailoring {len(lines)} bullets...")
    try:
        result = tailor_resume_bullets(lines, keywords, jd_context)
    except Exception as e:
        click.echo(f"❌ AI tailoring failed: {e}", err=True)
        sys.exit(1)

    click.echo(f"\n{'='*55}")
    for i, bullet in enumerate(result.get("rewritten_bullets", []), 1):
        click.echo(f"\n[{i}] ORIGINAL:  {bullet.get('original', '')}")
        click.echo(f"    REWRITTEN: {bullet.get('rewritten', '')}")
        click.echo(f"    CHANGES:   {bullet.get('changes_made', '')}")
    click.echo(f"\n📝 {result.get('overall_notes', '')}")


@cli.command("digest")
def digest():
    """Run and print the daily digest."""
    from modules.digest import run_daily_digest
    run_daily_digest(write_log=True)


@cli.command("dashboard")
def dashboard():
    """Launch the local web dashboard on port 5001."""
    click.echo("🌐 Starting Job Search Ops dashboard at http://127.0.0.1:5001")
    click.echo("   Press Ctrl+C to stop.\n")
    from web.app import run
    run()


@cli.command("export")
def export():
    """Export all opportunities to CSV."""
    import csv
    from models.opportunity import list_opportunities

    opps = list_opportunities()
    filename = f"jobsearch_export_{date.today().isoformat()}.csv"

    if not opps:
        click.echo("No opportunities to export.")
        return

    fieldnames = [f for f in opps[0].to_dict().keys()
                  if not f.endswith("_parsed") and not f.endswith("_list")]

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for opp in opps:
            writer.writerow({k: v for k, v in opp.to_dict().items() if k in fieldnames})

    click.echo(f"✅ Exported {len(opps)} opportunities to {filename}")


@cli.command("list")
@click.option("--stage", default=None, help="Filter by stage")
def list_opps(stage):
    """List all opportunities in the pipeline."""
    from models.opportunity import list_opportunities
    from config import JOB_FAMILIES

    opps = list_opportunities(stage=stage, exclude_closed=(stage is None))
    if not opps:
        click.echo("No opportunities found.")
        return

    click.echo(f"\n{'ID':<5} {'Company':<25} {'Role':<35} {'Stage':<20} {'Tier':<5} {'Score':<6} {'Due'}")
    click.echo("─" * 100)
    for opp in opps:
        click.echo(
            f"{opp.id:<5} {(opp.company or '')[:24]:<25} {(opp.role_title or '')[:34]:<35} "
            f"{opp.stage:<20} {'T'+str(opp.tier) if opp.tier else '—':<5} "
            f"{str(opp.fit_score)+'/10' if opp.fit_score else '—':<6} "
            f"{opp.next_action_date or '—'}"
        )


if __name__ == "__main__":
    cli()
