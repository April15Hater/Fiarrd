"""
tests/test_ai_engine.py — Unit tests for ai_engine.py
All Anthropic API calls are mocked — no tokens burned in CI.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock the env key before importing config
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-mock")

# We need to prevent init_db from running during import in tests
import db.database as _db_module
_db_module.init_db = lambda: None


MOCK_FIT_RESPONSE = json.dumps({
    "fit_score": 8,
    "score_rationale": "Strong SQL and analytics background aligns well. Management experience matches.",
    "top_strengths": ["20+ years fintech experience", "Team leadership", "BI tooling breadth"],
    "gaps_or_risks": ["No Looker experience mentioned", "No payments-specific depth shown"],
    "ats_keywords": ["data governance", "SQL", "BI dashboards", "KPIs", "fintech"],
    "suggested_bullet_rewrite": "Led data governance initiative reducing PII exposure by 40% across 3 platforms."
})

MOCK_JD_RESPONSE = json.dumps({
    "company": "Acme Fintech",
    "role_title": "Analytics Manager",
    "job_family_guess": "Analytics Manager",
    "required_skills": ["SQL", "Python", "Tableau"],
    "preferred_skills": ["dbt", "Looker"],
    "keywords": ["data governance", "KPIs", "fintech", "stakeholder management", "SQL"],
    "salary_range": "$130,000 - $160,000",
    "remote_ok": True,
    "seniority": "Manager"
})

MOCK_OUTREACH_RESPONSE = json.dumps({
    "linkedin_note": "Hi Alex — saw Acme's analytics team is growing. Your work on the data platform caught my eye. Would love to connect.",
    "inmail_or_email": "Hi Alex,\n\nI noticed Acme Fintech is expanding the analytics function. With 20 years in fintech data and analytics leadership, I've led similar platform builds — most recently at a regional lender.\n\nWould you be open to a 20-minute call to compare notes?",
    "subject_line": "Analytics leadership background — open to a conversation"
})


def _make_mock_response(text: str):
    """Build a mock Anthropic API response object."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=text)]
    return mock_resp


@patch("modules.ai_engine._log_ai_action")
@patch("modules.ai_engine._get_client")
def test_score_fit_returns_dict(mock_client_fn, mock_log):
    """score_fit should parse and return a dict with fit_score."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(MOCK_FIT_RESPONSE)
    mock_client_fn.return_value = mock_client

    from modules.ai_engine import score_fit
    result = score_fit("My resume text", "JD text")

    assert isinstance(result, dict)
    assert result["fit_score"] == 8
    assert len(result["top_strengths"]) == 3
    assert len(result["ats_keywords"]) == 5


@patch("modules.ai_engine._log_ai_action")
@patch("modules.ai_engine._get_client")
def test_extract_jd_structure_returns_dict(mock_client_fn, mock_log):
    """extract_jd_structure should parse JD fields correctly."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(MOCK_JD_RESPONSE)
    mock_client_fn.return_value = mock_client

    from modules.ai_engine import extract_jd_structure
    result = extract_jd_structure("Some long job description text...")

    assert result["company"] == "Acme Fintech"
    assert result["role_title"] == "Analytics Manager"
    assert result["remote_ok"] is True
    assert "SQL" in result["required_skills"]


@patch("modules.ai_engine._log_ai_action")
@patch("modules.ai_engine._get_client")
def test_draft_outreach_returns_three_variants(mock_client_fn, mock_log):
    """draft_outreach should return linkedin_note, inmail_or_email, subject_line."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(MOCK_OUTREACH_RESPONSE)
    mock_client_fn.return_value = mock_client

    from modules.ai_engine import draft_outreach
    result = draft_outreach({
        "contact_name": "Alex Chen",
        "contact_title": "Head of Analytics",
        "company": "Acme Fintech",
        "contact_type": "Hiring Manager",
        "hook": "Saw the analytics manager role posted on LinkedIn.",
    })

    assert "linkedin_note" in result
    assert len(result["linkedin_note"]) <= 300
    assert "inmail_or_email" in result
    assert "subject_line" in result


@patch("modules.ai_engine._log_ai_action")
@patch("modules.ai_engine._get_client")
def test_score_fit_handles_markdown_fenced_json(mock_client_fn, mock_log):
    """_parse_json_response should strip markdown fences."""
    mock_client = MagicMock()
    fenced = f"```json\n{MOCK_FIT_RESPONSE}\n```"
    mock_client.messages.create.return_value = _make_mock_response(fenced)
    mock_client_fn.return_value = mock_client

    from modules.ai_engine import score_fit
    result = score_fit("resume", "jd text")
    assert result["fit_score"] == 8


def test_parse_json_strips_fences():
    """_parse_json_response strips both ``` and ```json variants."""
    from modules.ai_engine import _parse_json_response
    raw = '```json\n{"key": "value"}\n```'
    result = _parse_json_response(raw)
    assert result == {"key": "value"}

    raw2 = '```\n{"key": "value"}\n```'
    result2 = _parse_json_response(raw2)
    assert result2 == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
