"""What an Entry Contributor (Level 1) is told about their own entries after somebody senior touched them: who changed the number, in which role, when,
from what to what, and where the entry stands in the verification workflow. Built from the append-only history, so it is the real record, never a copy.

A developer's cash adjustment is deliberately left out: it is hidden from everyone below the developer (the number the contributor sees is their own
part, `bottle_count - cash_adjustment`), so an event that touched `cash_adjustment` is never reported and the old / new values have the adjustment removed.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.order_entry import OrderEntry

ROLE_LABEL = {
    "entry_contributor": "Data Entry", "team_lead": "Team Lead", "entry_reviewer": "Reviewer", "administrator": "Administrator",
    "developer": "Developer", "custom_admin": "Admin", "accountant": "Accounts", "partner": "Partner", "unknown": "Staff",
}
STATUS_LABEL = {"submitted": "Submitted", "verified_l2": "Verified by Team Lead", "reviewed_l3": "Reviewed by Reviewer"}


def role_label(role: str | None) -> str:
    return ROLE_LABEL.get(role or "", role or "Staff")


def last_changes(db: Session, entries: Iterable[OrderEntry]) -> dict[uuid.UUID, dict]:
    """{entry_id: the latest change to the employee's number} for the entries that have one."""
    return last_changes_for(db, {e.id: (e.cash_adjustment or 0) for e in entries if e.version and e.version > 1})


def last_changes_for(db: Session, adjustments: dict[uuid.UUID, int]) -> dict[uuid.UUID, dict]:
    """The same for plain ids: `adjustments` maps each entry that was changed (version > 1) to its developer cash adjustment (removed from the numbers shown)."""
    changed = adjustments
    if not changed:
        return {}
    rows = db.execute(
        text("""
            SELECT DISTINCT ON (entry_id) entry_id, created_at, actor_name, actor_role, old_values, new_values, reason
              FROM order_entry_events
             WHERE entry_id = ANY(:ids) AND event_type = 'EDITED'
               AND new_values -> 'bottle_count' IS NOT NULL AND new_values -> 'cash_adjustment' IS NULL
             ORDER BY entry_id, seq DESC
        """),
        {"ids": list(changed)},
    ).mappings().all()
    out: dict[uuid.UUID, dict] = {}
    for r in rows:
        adj = changed[r["entry_id"]]
        old, new = (r["old_values"] or {}).get("bottle_count"), (r["new_values"] or {}).get("bottle_count")
        if old is None or new is None:
            continue
        out[r["entry_id"]] = {
            "by_name": r["actor_name"], "by_role": r["actor_role"], "by_role_label": role_label(r["actor_role"]), "at": r["created_at"],
            "old_count": int(old) - adj, "new_count": int(new) - adj, "reason": r["reason"],
        }
    return out


def status_for_contributor(entry: OrderEntry, names: dict[uuid.UUID, str]) -> dict:
    """The entry's state for its owner. The person's name is left out where a hidden cash adjustment is involved."""
    hide_names = bool(entry.cash_adjustment)
    who = None
    if not hide_names:
        if entry.verification_status == "reviewed_l3":
            who = names.get(entry.l3_reviewed_by_user_id)
        elif entry.verification_status == "verified_l2":
            who = names.get(entry.verified_by_user_id)
    return {"status": entry.verification_status, "label": STATUS_LABEL.get(entry.verification_status, entry.verification_status), "by_name": who,
            "at": entry.l3_reviewed_at if entry.verification_status == "reviewed_l3" else entry.verified_at if entry.verification_status == "verified_l2" else None}
