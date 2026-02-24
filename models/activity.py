from __future__ import annotations
import sqlite3
import json
from dataclasses import dataclass, asdict
from typing import Optional

from db.database import execute_query


@dataclass
class ActivityLog:
    id: Optional[int] = None
    opportunity_id: Optional[int] = None
    contact_id: Optional[int] = None
    activity_type: str = "Note Added"
    description: Optional[str] = None
    metadata: Optional[str] = None   # JSON blob
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ActivityLog":
        return cls(**{k: row[k] for k in row.keys()})

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("metadata"):
            try:
                d["metadata_parsed"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                d["metadata_parsed"] = {}
        return d


# ── CRUD ──────────────────────────────────────────────────────────────────────

def log_activity(
    activity_type: str,
    description: str = None,
    opportunity_id: int = None,
    contact_id: int = None,
    metadata: dict = None,
) -> int:
    """Append an immutable activity log entry. Returns the new row id."""
    meta_str = json.dumps(metadata) if metadata else None
    return execute_query(
        """INSERT INTO activity_log
             (opportunity_id, contact_id, activity_type, description, metadata)
           VALUES (?,?,?,?,?)""",
        (opportunity_id, contact_id, activity_type, description, meta_str)
    )


def get_activity_log(opportunity_id: int = None, limit: int = 50) -> list[ActivityLog]:
    if opportunity_id is not None:
        rows = execute_query(
            "SELECT * FROM activity_log WHERE opportunity_id = ? ORDER BY created_at DESC LIMIT ?",
            (opportunity_id, limit),
            fetch="all"
        )
    else:
        rows = execute_query(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
            fetch="all"
        )
    return [ActivityLog.from_row(r) for r in rows] if rows else []
