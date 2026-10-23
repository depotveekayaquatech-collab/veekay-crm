"""Keeps the activity log from growing for ever (thousands of rows a day add up and slow every write and read).

Rows older than AUDIT_KEEP_DAYS are removed in small batches, except the few kinds the app still needs later (the order-sheet import
records an import can be reverted from, and the snapshot of a permanently deleted account).

audit_logs has a protective BEFORE DELETE trigger that copies every removed row into `deleted_rows`. Without cleaning those copies too
the purge would only move the data, so the copies of the rows removed here are deleted in the same transaction."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

log = logging.getLogger("veekay.audit")

KEEP_ACTIONS = ("order.imported", "employee.deleted_permanently")
BATCH = 2000


def purge_old_audit(db: Session, *, keep_days: int | None = None, max_batches: int = 200) -> int:
    """Delete audit rows older than the retention window. Returns how many were removed. Safe to run from several machines at once."""
    days = settings.AUDIT_KEEP_DAYS if keep_days is None else keep_days
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for _ in range(max_batches):
        ids = [r[0] for r in db.execute(
            text("SELECT id FROM audit_logs WHERE created_at < :c AND action <> ALL(:keep) ORDER BY created_at LIMIT :n FOR UPDATE SKIP LOCKED"),
            {"c": cutoff, "keep": list(KEEP_ACTIONS), "n": BATCH},
        )]
        if not ids:
            break
        db.execute(text("DELETE FROM audit_logs WHERE id = ANY(:ids)"), {"ids": ids})
        db.execute(
            text("DELETE FROM deleted_rows WHERE table_name = 'audit_logs' AND row_id = ANY(:ids)"),
            {"ids": [str(i) for i in ids]},
        )
        db.commit()
        removed += len(ids)
        if len(ids) < BATCH:
            break
    if removed:
        log.info("audit log: removed %d rows older than %d days", removed, days)
    return removed


def run_audit_purge() -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        purge_old_audit(db)
    except Exception:  # noqa: BLE001 — a background job must never crash the worker
        log.exception("audit purge failed")
        db.rollback()
    finally:
        db.close()
