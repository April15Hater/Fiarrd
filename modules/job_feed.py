"""
modules/job_feed.py — Poll RSS/Atom job feeds for new postings.

Feed URLs and an optional keyword filter are stored in app_settings.json:
  feed_urls     — newline-separated list of RSS/Atom feed URLs
  feed_keywords — comma-separated keywords; only titles containing at least
                  one keyword are imported (leave blank to import everything)

New postings are created as Prospect opportunities with data extracted from
the feed itself — no AI/Claude calls happen here.  Run Score Fit from the
opportunity detail page once you decide a posting is worth pursuing.
"""
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "JobSearchOps/1.0 (personal-use job search tool)"}


# ---------------------------------------------------------------------------
# RSS / Atom parsing
# ---------------------------------------------------------------------------

def _fetch_feed(url: str) -> list[dict]:
    """Fetch one RSS/Atom URL; return list of {title, link, description}."""
    try:
        resp = httpx.get(url.strip(), timeout=15, follow_redirects=True, headers=_HEADERS)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Feed fetch failed (%s): %s", url, e)
        return []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        logger.warning("Feed XML parse error (%s): %s", url, e)
        return []

    items: list[dict] = []

    # RSS 2.0 — items nested anywhere below root
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        if not link:
            continue
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": link,
            "description": (item.findtext("description") or "").strip(),
        })

    # Atom 1.0
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        link_el = entry.find("a:link", ns)
        if link_el is None:
            continue
        href = link_el.get("href", "").strip()
        if not href:
            continue
        title_el = entry.find("a:title", ns)
        summary_el = entry.find("a:summary", ns)
        items.append({
            "title": title_el.text.strip() if title_el is not None and title_el.text else "",
            "link": href,
            "description": summary_el.text.strip() if summary_el is not None and summary_el.text else "",
        })

    return items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _url_exists(url: str) -> bool:
    from db.database import execute_query
    return execute_query(
        "SELECT id FROM opportunities WHERE jd_url = ?", (url,), fetch="one"
    ) is not None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _split_title_company(raw: str) -> tuple[str, str]:
    """
    Heuristic split for common job-board title formats:
      "Analytics Manager at Acme Corp"   → ("Analytics Manager", "Acme Corp")
      "Data Manager | Acme Corp"          → ("Data Manager", "Acme Corp")
      "BI Manager - Acme Corp"            → ("BI Manager", "Acme Corp")
    Returns (role_title, company); company may be empty.
    """
    for sep in (" at ", " @ "):
        if sep.lower() in raw.lower():
            idx = raw.lower().index(sep.lower())
            return raw[:idx].strip(), raw[idx + len(sep):].strip()
    m = re.match(r"^(.+?)\s*[|\u2013\u2014-]\s*(.+)$", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw.strip(), ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def poll_feeds(
    feed_urls: list[str],
    keyword_filter: list[str] | None = None,
    auto_score: bool = False,
    min_score: int = 0,
    resume_text: str = "",
) -> dict:
    """
    Poll all configured feed URLs and add new postings as Prospect opportunities.

    If ``auto_score`` is True and ``resume_text`` is provided, each new posting
    is immediately scored via Claude.  If ``min_score`` > 0, postings whose
    fit score falls below the threshold are discarded automatically.

    Returns {"added": int, "skipped": int, "filtered": int, "errors": int, "new": list[str]}
    """
    from models.opportunity import create_opportunity, delete_opportunity, update_opportunity
    from models.activity import log_activity
    from modules.workflow import calculate_next_action

    kw_lower = [k.strip().lower() for k in (keyword_filter or []) if k.strip()]
    next_action, days_out = calculate_next_action("Prospect")
    next_action_date = (date.today() + timedelta(days=days_out)).isoformat()

    should_score = auto_score and bool(resume_text.strip())

    added = skipped = errors = filtered = 0
    new_titles: list[str] = []

    for feed_url in feed_urls:
        if not feed_url.strip():
            continue
        for item in _fetch_feed(feed_url):
            link = item["link"]
            title = item["title"]

            # Keyword filter (skip if title matches none of the configured keywords)
            if kw_lower and not any(kw in title.lower() for kw in kw_lower):
                skipped += 1
                continue

            # Dedup by URL
            if _url_exists(link):
                skipped += 1
                continue

            role_title, company = _split_title_company(title)
            jd_raw = _strip_html(item["description"]) or title

            try:
                opp_id = create_opportunity(
                    company=company or "Unknown",
                    role_title=role_title or title,
                    stage="Prospect",
                    source="Other",
                    jd_url=link,
                    jd_raw=jd_raw,
                    jd_keywords=json.dumps([]),
                    next_action=next_action,
                    next_action_date=next_action_date,
                )
                log_activity(
                    activity_type="Note Added",
                    description=f"Auto-added from job feed: {title}",
                    opportunity_id=opp_id,
                )

                # Auto-score and optionally filter below threshold
                if should_score:
                    try:
                        from modules.ai_engine import score_fit
                        score_result = score_fit(resume_text, jd_raw, opportunity_id=opp_id)
                        fit_score = score_result.get("fit_score", 0)
                        if min_score > 0 and fit_score < min_score:
                            # Score too low — discard silently
                            delete_opportunity(opp_id)
                            filtered += 1
                            logger.info(
                                "Feed: filtered '%s' (score %s < threshold %s)",
                                title, fit_score, min_score,
                            )
                            continue
                        update_opportunity(
                            opp_id,
                            fit_score=fit_score,
                            ai_fit_summary=json.dumps(score_result),
                        )
                        log_activity(
                            activity_type="AI Action",
                            description=f"Auto-scored on feed import: {fit_score}/10",
                            opportunity_id=opp_id,
                        )
                    except Exception as e:
                        logger.warning("Feed: auto-score failed for %s: %s", link, e)

                logger.info("Feed: added '%s' from %s", title, link)
                added += 1
                new_titles.append(f"{company or '?'} — {role_title or title}")
            except Exception as e:
                logger.warning("Feed: failed to create opportunity for %s: %s", link, e)
                errors += 1

    return {"added": added, "skipped": skipped, "filtered": filtered, "errors": errors, "new": new_titles}


def load_feed_config() -> dict:
    """Load feed URLs, keyword filter, and auto-score settings from app_settings.json."""
    from config import APP_SETTINGS_PATH
    try:
        if os.path.exists(APP_SETTINGS_PATH):
            with open(APP_SETTINGS_PATH, encoding="utf-8") as f:
                s = json.load(f)
            urls = [u.strip() for u in s.get("feed_urls", "").splitlines() if u.strip()]
            keywords = [k.strip() for k in s.get("feed_keywords", "").split(",") if k.strip()]
            auto_score = bool(s.get("feed_auto_score", False))
            try:
                min_score = int(s.get("feed_min_score", 0))
            except (TypeError, ValueError):
                min_score = 0
            return {"urls": urls, "keywords": keywords, "auto_score": auto_score, "min_score": min_score}
    except Exception:
        pass
    return {"urls": [], "keywords": [], "auto_score": False, "min_score": 0}
