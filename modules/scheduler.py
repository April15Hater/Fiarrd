"""
modules/scheduler.py — Background job scheduler.
Runs in a daemon thread while the Flask dashboard is up.
Activated by web/app.py:run() — not used during CLI-only sessions.
"""
import json
import threading
import time

import schedule

from config import APP_SETTINGS_PATH
from modules.digest import run_daily_digest
from modules.workflow import flag_stale_records

DEFAULT_DIGEST_TIME = "08:00"


def _load_digest_time() -> str:
    try:
        with open(APP_SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f).get("digest_time", DEFAULT_DIGEST_TIME)
    except Exception:
        return DEFAULT_DIGEST_TIME


def _run_stale_check():
    stale = flag_stale_records(days_stale=7)
    if stale:
        print(f"[scheduler] WARNING: {len(stale)} stale record(s) — no update in 7+ days:")
        for opp in stale:
            print(f"  - {opp.company} — {opp.role_title} (stage: {opp.stage})")
    else:
        print("[scheduler] Stale check: no stale records.")


def _scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(60)  # check every minute


def reschedule(new_time: str):
    """Clear all scheduled jobs and re-add with new_time. Called after settings save."""
    schedule.clear()
    schedule.every().day.at(new_time).do(run_daily_digest, write_log=True)
    schedule.every().day.at(new_time).do(_run_stale_check)
    print(f"[scheduler] Rescheduled — digest + stale check at {new_time} daily.")


def start_scheduler():
    """Schedule daily jobs and start background thread. Call once at Flask startup."""
    digest_time = _load_digest_time()
    schedule.every().day.at(digest_time).do(run_daily_digest, write_log=True)
    schedule.every().day.at(digest_time).do(_run_stale_check)
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="JobSearchScheduler")
    t.start()
    print(f"[scheduler] Started — digest + stale check scheduled at {digest_time} daily.")
