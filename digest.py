"""
digest.py — Daily digest: pull queue data, call AI, print and optionally log.
"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DIGEST_LOG = Path("digest_log.txt")


def run_daily_digest(write_log: bool = True) -> str:
    """
    Pull today_queue, follow-up queue, and pipeline summary.
    Call AI to generate a digest. Print and optionally write to digest_log.txt.
    Returns the digest text.
    """
    from modules.workflow import get_today_queue, get_followup_queue, get_pipeline_summary
    from modules.ai_engine import generate_daily_digest

    today_queue = get_today_queue()
    followup_needed = get_followup_queue()
    pipeline_summary = get_pipeline_summary()

    if not today_queue and not followup_needed and not pipeline_summary:
        msg = "No active opportunities in pipeline. Add your first job with: python main.py add-job"
        print(msg)
        return msg

    digest = generate_daily_digest(today_queue, followup_needed, pipeline_summary)

    header = f"\n{'='*60}\nJOB SEARCH DAILY DIGEST — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{'='*60}\n"
    output = header + digest + "\n"

    print(output)

    if write_log:
        with open(DIGEST_LOG, "a") as f:
            f.write(output)
        logger.info(f"Digest written to {DIGEST_LOG}")

    return digest
