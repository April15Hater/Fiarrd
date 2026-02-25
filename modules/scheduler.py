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


def _run_feed_poll():
    try:
        from modules.job_feed import poll_feeds, load_feed_config
        cfg = load_feed_config()
        if not cfg["urls"]:
            return
        result = poll_feeds(cfg["urls"], cfg["keywords"])
        print(f"[scheduler] Feed poll: {result['added']} added, {result['skipped']} skipped, {result['errors']} errors.")
        for title in result.get("new", []):
            print(f"  + {title}")
    except Exception as e:
        print(f"[scheduler] Feed poll error: {e}")


def _run_stale_check():
    stale = flag_stale_records(days_stale=7)
    if stale:
        print(f"[scheduler] WARNING: {len(stale)} stale record(s) — no update in 7+ days:")
        for opp in stale:
            print(f"  - {opp['company']} — {opp['role_title']} (stage: {opp['stage']})")
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
    schedule.every().day.at(new_time).do(_run_feed_poll)
    print(f"[scheduler] Rescheduled — digest + stale check + feed poll at {new_time} daily.")


def start_scheduler():
    """Schedule daily jobs and start background thread. Call once at Flask startup."""
    digest_time = _load_digest_time()
    schedule.every().day.at(digest_time).do(run_daily_digest, write_log=True)
    schedule.every().day.at(digest_time).do(_run_stale_check)
    schedule.every().day.at(digest_time).do(_run_feed_poll)
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="JobSearchScheduler")
    t.start()
    print(f"[scheduler] Started — digest + stale check + feed poll scheduled at {digest_time} daily.")
