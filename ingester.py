"""
ingester.py — Parse job descriptions from pasted text or URL.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _fetch_url(url: str) -> str:
    """Fetch a URL and extract main text content."""
    try:
        import httpx
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove navigation/footer/script noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find main content area first
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id="job-description")
            or soup.find(class_="job-description")
            or soup.find(class_="description")
        )
        target = main if main else soup.find("body")
        text = target.get_text(separator="\n", strip=True) if target else soup.get_text()

        # Clean up excessive blank lines
        lines = [line.strip() for line in text.splitlines()]
        cleaned = "\n".join(line for line in lines if line)
        return cleaned

    except Exception as e:
        logger.error(f"URL fetch failed for {url}: {e}")
        raise RuntimeError(f"Could not fetch JD from URL: {e}") from e


def ingest_jd(source: str) -> dict:
    """
    Parse a job description from a URL or pasted text.

    Args:
        source: Either a URL (starts with http) or raw JD text (>200 chars).

    Returns:
        Structured dict with company, role_title, job_family_guess, keywords, etc.
        Also includes raw_text key for storage.
    """
    from modules.ai_engine import extract_jd_structure

    # Determine source type
    source = source.strip()
    if source.lower().startswith("http"):
        logger.info(f"Fetching JD from URL: {source}")
        raw_text = _fetch_url(source)
        source_url = source
    elif len(source) > 200:
        raw_text = source
        source_url = None
    else:
        raise ValueError(
            f"Source must be a URL or text >200 characters. Got {len(source)} chars."
        )

    logger.info(f"Extracting structure from {len(raw_text)} chars of JD text...")
    structured = extract_jd_structure(raw_text)

    # Attach the raw text and URL for storage
    structured["raw_text"] = raw_text
    structured["source_url"] = source_url

    return structured
