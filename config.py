from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
assert ANTHROPIC_API_KEY, "ANTHROPIC_API_KEY not set in .env"

DB_PATH = os.getenv("DB_PATH", "jobsearch.db")
CLAUDE_MODEL = "claude-sonnet-4-6"

# Store master resume text here after first run (never in DB, never in git)
RESUME_CACHE_PATH = os.getenv("RESUME_CACHE_PATH", ".resume_cache.txt")

# Job family labels
JOB_FAMILIES = {
    "A": "Analytics Manager",
    "B": "Data Manager",
    "C": "BI Manager",
    "D": "Decision Science",
    "E": "Director Stretch"
}

# Stage order for pipeline display
STAGE_ORDER = [
    "Prospect", "Warm Lead", "Applied",
    "Recruiter Screen", "HM Interview",
    "Loop", "Offer Pending", "Closed"
]

# Owner context defaults for AI engine
OWNER_CONTEXT = {
    "role_target": "Data & Analytics Manager",
    "industries": "Fintech, Lending, Payments",
    "core_stack": (
        "SQL (T-SQL, MySQL, BigQuery, Redshift), Python (Pandas, SQLAlchemy), "
        "Tableau, Power BI (DAX), Amazon QuickSight, Looker"
    ),
    "governance_pii": "Yes — field-level encryption, PII-safe data handling",
    "management_experience": "Yes — team of 3, intake/QA/prioritization",
    "years_experience": "20+ years financial services",
    "location": "Remote or hybrid (Charlotte NC metro)",
}

OWNER_BACKGROUND_SUMMARY = (
    f"Data & Analytics Manager with {OWNER_CONTEXT['years_experience']} in {OWNER_CONTEXT['industries']}. "
    f"Core stack: {OWNER_CONTEXT['core_stack']}. "
    f"Management: {OWNER_CONTEXT['management_experience']}. "
    f"PII/governance: {OWNER_CONTEXT['governance_pii']}. "
    f"Location: {OWNER_CONTEXT['location']}."
)
