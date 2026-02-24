"""
web/routes.py — All Flask routes for the local dashboard.
"""
from flask import render_template, request, redirect, url_for, jsonify, flash

from models.opportunity import list_opportunities, get_opportunity, update_opportunity
from models.contact import list_contacts, get_contact, update_contact
from models.activity import get_activity_log, log_activity
from modules.workflow import (
    get_today_queue, get_pipeline_summary, get_followup_queue,
    flag_stale_records, advance_stage
)
from config import STAGE_ORDER, JOB_FAMILIES


def register_routes(app):

    @app.route("/")
    def dashboard():
        today_queue = get_today_queue()
        pipeline = get_pipeline_summary()
        stale = flag_stale_records(days_stale=7)
        # Build stage counts dict
        stage_counts = {row["stage"]: row["count"] for row in pipeline}
        return render_template(
            "dashboard.html",
            today_queue=today_queue,
            pipeline=pipeline,
            stage_counts=stage_counts,
            stale=stale,
            stage_order=STAGE_ORDER,
        )

    @app.route("/run-digest", methods=["POST"])
    def run_digest():
        from modules.digest import run_daily_digest
        digest = run_daily_digest(write_log=True)
        return jsonify({"digest": digest})

    @app.route("/opportunities")
    def opportunities():
        stage_filter = request.args.get("stage")
        tier_filter = request.args.get("tier", type=int)
        family_filter = request.args.get("job_family")
        opps = list_opportunities(
            stage=stage_filter,
            tier=tier_filter,
            job_family=family_filter,
            exclude_closed=False,
        )
        return render_template(
            "opportunities.html",
            opportunities=opps,
            stage_order=STAGE_ORDER,
            job_families=JOB_FAMILIES,
            current_stage=stage_filter,
            current_tier=tier_filter,
            current_family=family_filter,
        )

    @app.route("/opportunity/<int:opp_id>")
    def opportunity_detail(opp_id):
        opp = get_opportunity(opp_id)
        if not opp:
            return "Opportunity not found", 404
        contacts = list_contacts(opportunity_id=opp_id)
        activity = get_activity_log(opportunity_id=opp_id)
        import json
        fit_summary = None
        if opp.ai_fit_summary:
            try:
                fit_summary = json.loads(opp.ai_fit_summary)
            except Exception:
                pass
        keywords = []
        if opp.jd_keywords:
            try:
                keywords = json.loads(opp.jd_keywords)
            except Exception:
                pass
        return render_template(
            "opportunity.html",
            opp=opp,
            contacts=contacts,
            activity=activity,
            fit_summary=fit_summary,
            keywords=keywords,
            stage_order=STAGE_ORDER,
            job_families=JOB_FAMILIES,
        )

    @app.route("/opportunity/<int:opp_id>/advance", methods=["POST"])
    def advance_opp(opp_id):
        new_stage = request.form.get("new_stage")
        note = request.form.get("note", "")
        if new_stage:
            advance_stage(opp_id, new_stage, note=note or None)
        return redirect(url_for("opportunity_detail", opp_id=opp_id))

    @app.route("/opportunity/<int:opp_id>/note", methods=["POST"])
    def add_note(opp_id):
        note_text = request.form.get("note", "").strip()
        if note_text:
            opp = get_opportunity(opp_id)
            existing = opp.notes or ""
            from datetime import date
            new_notes = f"{existing}\n[{date.today()}] {note_text}".strip()
            update_opportunity(opp_id, notes=new_notes)
            log_activity(
                activity_type="Note Added",
                description=note_text,
                opportunity_id=opp_id,
            )
        return redirect(url_for("opportunity_detail", opp_id=opp_id))

    @app.route("/contacts")
    def contacts():
        all_contacts = list_contacts()
        # Color-code by response_status
        status_colors = {
            "Pending": "#f59e0b",
            "Responded": "#10b981",
            "No Response": "#ef4444",
            "Meeting Scheduled": "#3b82f6",
        }
        followups = get_followup_queue()
        followup_ids = {f["contact_id"] for f in followups}
        return render_template(
            "contacts.html",
            contacts=all_contacts,
            status_colors=status_colors,
            followup_ids=followup_ids,
        )

    @app.route("/contact/<int:contact_id>/mark-response", methods=["POST"])
    def mark_response(contact_id):
        status = request.form.get("status", "Responded")
        update_contact(contact_id, response_status=status)
        contact = get_contact(contact_id)
        log_activity(
            activity_type="Response Received",
            description=f"Response status updated to: {status}",
            opportunity_id=contact.opportunity_id if contact else None,
            contact_id=contact_id,
        )
        return redirect(url_for("contacts"))
