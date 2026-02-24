from __future__ import annotations
import sqlite3
from dataclasses import dataclass, asdict
from typing import Optional

from db.database import execute_query


@dataclass
class Contact:
    id: Optional[int] = None
    opportunity_id: Optional[int] = None
    full_name: str = ""
    title: Optional[str] = None
    company: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    contact_type: Optional[str] = None
    outreach_day0: Optional[str] = None
    outreach_day3: Optional[str] = None
    outreach_day7: Optional[str] = None
    response_status: str = "Pending"
    call_completed: bool = False
    referral_asked: bool = False
    referral_given: bool = False
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Contact":
        return cls(**{k: row[k] for k in row.keys()})

    def to_dict(self) -> dict:
        return asdict(self)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_contact(
    full_name: str,
    opportunity_id: int = None,
    title: str = None,
    company: str = None,
    linkedin_url: str = None,
    email: str = None,
    contact_type: str = None,
    notes: str = None,
) -> int:
    sql = """
        INSERT INTO contacts
          (opportunity_id, full_name, title, company, linkedin_url, email, contact_type, notes)
        VALUES (?,?,?,?,?,?,?,?)
    """
    return execute_query(sql, (
        opportunity_id, full_name, title, company, linkedin_url, email, contact_type, notes
    ))


def get_contact(contact_id: int) -> Optional[Contact]:
    row = execute_query(
        "SELECT * FROM contacts WHERE id = ?", (contact_id,), fetch="one"
    )
    return Contact.from_row(row) if row else None


def update_contact(contact_id: int, **kwargs) -> int:
    if not kwargs:
        return 0
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [contact_id]
    return execute_query(
        f"UPDATE contacts SET {set_clause} WHERE id = ?", tuple(values)
    )


def list_contacts(opportunity_id: int = None, response_status: str = None) -> list[Contact]:
    conditions = []
    params = []
    if opportunity_id is not None:
        conditions.append("opportunity_id = ?")
        params.append(opportunity_id)
    if response_status:
        conditions.append("response_status = ?")
        params.append(response_status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = execute_query(
        f"SELECT * FROM contacts {where} ORDER BY created_at DESC",
        tuple(params),
        fetch="all"
    )
    return [Contact.from_row(r) for r in rows] if rows else []


def get_contacts_for_opportunity(opportunity_id: int) -> list[Contact]:
    return list_contacts(opportunity_id=opportunity_id)
