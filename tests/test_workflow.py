"""
tests/test_workflow.py — Tests for workflow.py
Uses an in-memory SQLite database so no real DB is touched.
"""
import os
import sys
import pytest
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-mock")

# Point to an in-memory DB for tests
os.environ["DB_PATH"] = ":memory:"

import db.database as _db
# Force reinit with in-memory DB
_db.init_db()

from models.opportunity import create_opportunity
from models.contact import create_contact, update_contact
from models.activity import get_activity_log
from modules.workflow import (
    get_followup_queue, advance_stage, calculate_next_action, flag_stale_records
)


def _make_opp(**kwargs):
    defaults = dict(company="Test Co", role_title="Analytics Manager")
    defaults.update(kwargs)
    return create_opportunity(**defaults)


def _make_contact(opp_id, day0=None, response_status="Pending", **kwargs):
    cid = create_contact(full_name="Test Contact", opportunity_id=opp_id, **kwargs)
    if day0:
        update_contact(cid, outreach_day0=day0, response_status=response_status)
    return cid


class TestFollowupQueue:
    def test_day3_contact_appears_in_queue(self):
        opp_id = _make_opp()
        day3_ago = (date.today() - timedelta(days=3)).isoformat()
        _make_contact(opp_id, day0=day3_ago, response_status="Pending")

        queue = get_followup_queue()
        opp_contacts = [c for c in queue if c["opportunity_id"] == opp_id]
        assert len(opp_contacts) >= 1
        assert "Day 3" in opp_contacts[0]["followup_reason"]

    def test_day7_contact_appears_in_queue(self):
        opp_id = _make_opp()
        day7_ago = (date.today() - timedelta(days=7)).isoformat()
        _make_contact(opp_id, day0=day7_ago, response_status="Pending")

        queue = get_followup_queue()
        opp_contacts = [c for c in queue if c["opportunity_id"] == opp_id]
        assert len(opp_contacts) >= 1
        assert "Day 7" in opp_contacts[0]["followup_reason"]

    def test_responded_contact_not_in_queue(self):
        opp_id = _make_opp()
        day3_ago = (date.today() - timedelta(days=3)).isoformat()
        cid = _make_contact(opp_id, day0=day3_ago, response_status="Responded")

        queue = get_followup_queue()
        contact_ids = [c["contact_id"] for c in queue]
        assert cid not in contact_ids

    def test_fresh_contact_not_in_queue(self):
        opp_id = _make_opp()
        today = date.today().isoformat()
        cid = _make_contact(opp_id, day0=today, response_status="Pending")

        queue = get_followup_queue()
        contact_ids = [c["contact_id"] for c in queue]
        assert cid not in contact_ids


class TestStageTransitions:
    def test_advance_stage_updates_correctly(self):
        opp_id = _make_opp()
        advance_stage(opp_id, "Applied", note="Submitted via LinkedIn")

        from models.opportunity import get_opportunity
        opp = get_opportunity(opp_id)
        assert opp.stage == "Applied"
        assert opp.date_applied is not None

    def test_advance_stage_logs_activity(self):
        opp_id = _make_opp()
        advance_stage(opp_id, "Recruiter Screen")

        log = get_activity_log(opportunity_id=opp_id)
        stage_changes = [e for e in log if e.activity_type == "Stage Change"]
        assert len(stage_changes) >= 1
        assert "Recruiter Screen" in stage_changes[0].description

    def test_advance_to_closed_sets_date(self):
        opp_id = _make_opp()
        advance_stage(opp_id, "Closed")

        from models.opportunity import get_opportunity
        opp = get_opportunity(opp_id)
        assert opp.stage == "Closed"
        assert opp.date_closed == date.today().isoformat()

    def test_calculate_next_action_all_stages(self):
        from config import STAGE_ORDER
        for stage in STAGE_ORDER:
            if stage != "Closed":
                action_text, days = calculate_next_action(stage)
                assert isinstance(action_text, str)
                assert len(action_text) > 0
                assert isinstance(days, int)
                assert days > 0


class TestStaleRecords:
    def test_stale_record_detected(self):
        opp_id = _make_opp()
        # Manually set updated_at to old date
        from db.database import execute_query
        old_date = (date.today() - timedelta(days=10)).isoformat()
        execute_query(
            "UPDATE opportunities SET updated_at = ? WHERE id = ?",
            (old_date, opp_id)
        )

        stale = flag_stale_records(days_stale=7)
        stale_ids = [r["id"] for r in stale]
        assert opp_id in stale_ids

    def test_recent_record_not_stale(self):
        opp_id = _make_opp()
        stale = flag_stale_records(days_stale=7)
        stale_ids = [r["id"] for r in stale]
        assert opp_id not in stale_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
