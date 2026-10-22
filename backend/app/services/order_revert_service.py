"""
Undo an order-sheet import for ONE month (developer only).

An import (Data sync > Orders, the daily sheet sync, or an uploaded file) writes entries marked `admin` and may overwrite numbers an
employee had entered. This puts the month back the way it was before a chosen import:

  * entries the import CREATED for that month are deleted (the database copies every deleted row into `deleted_rows`, so nothing is lost
    and the order-audit tool can restore them);
  * numbers the import OVERWROTE (recorded in `order_entry_changes`) are put back to what they were, with the employee who had marked
    them when the audit log still knows who it was;
  * anything touched since by someone else (a later correction, a cash adjustment) is left alone and counted.

Only the chosen month is touched; the same import's other months stay. An import is recognised from the audit log: its entries were
written by its actor, as `admin`, in the minutes before the log line.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.deleted_row import OrderEntryChange
from app.models.order_entry import EntrySource, OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store
from app.models.user import User
from app.services import activity_service

_WINDOW_BEFORE = timedelta(minutes=10)      # an import writes its entries just before it logs itself
_WINDOW_AFTER = timedelta(seconds=10)
_UNTOUCHED = timedelta(minutes=2)           # an entry changed later than this after it was written has been edited by someone


def _month(text: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in text.split("-"))
        first = date(y, m, 1)
    except (ValueError, AttributeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-10.") from None
    return first, date(y, m, calendar.monthrange(y, m)[1])


def _partner(db: Session, slug: str) -> Organization:
    org = db.execute(
        select(Organization).where(Organization.slug == slug.strip().lower(), Organization.kind == OrganizationKind.PARTNER.value)
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Platform '{slug}' not found.")
    return org


def _created_by(run: AuditLog, pid: uuid.UUID, first: date, last: date):
    """The entries this import created in the month, still exactly as it wrote them."""
    return (
        select(OrderEntry)
        .join(Store, Store.id == OrderEntry.store_id)
        .where(
            Store.partner_organization_id == pid,
            OrderEntry.order_date >= first, OrderEntry.order_date <= last,
            OrderEntry.source == EntrySource.ADMIN.value,
            OrderEntry.marked_by_user_id == run.user_id,
            OrderEntry.created_at >= run.created_at - _WINDOW_BEFORE, OrderEntry.created_at <= run.created_at + _WINDOW_AFTER,
        )
    )


def _overwrote(db: Session, run: AuditLog, pid: uuid.UUID, first: date, last: date) -> list[OrderEntryChange]:
    """The first recorded change of each entry inside the import's window (what it held before the import touched it)."""
    rows = db.execute(
        select(OrderEntryChange)
        .join(Store, Store.id == OrderEntryChange.store_id)
        .where(
            Store.partner_organization_id == pid,
            OrderEntryChange.order_date >= first, OrderEntryChange.order_date <= last,
            OrderEntryChange.new_source == EntrySource.ADMIN.value,
            OrderEntryChange.changed_at >= run.created_at - _WINDOW_BEFORE, OrderEntryChange.changed_at <= run.created_at + _WINDOW_AFTER,
        )
        .order_by(OrderEntryChange.changed_at)
    ).scalars().all()
    first_change: dict[uuid.UUID, OrderEntryChange] = {}
    for c in rows:
        first_change.setdefault(c.entry_id, c)
    return list(first_change.values())


def import_runs(db: Session, actor: User, platform_slug: str, month: str) -> dict:
    """The order imports of this platform that left entries in the month, newest first, with how much each one can undo."""
    pid = _partner(db, platform_slug).id
    first, last = _month(month)
    runs = db.execute(
        select(AuditLog).where(
            AuditLog.organization_id == actor.organization_id, AuditLog.action == "order.imported", AuditLog.entity_id == str(pid),
        ).order_by(AuditLog.created_at.desc())
    ).scalars().all()
    names = {u.id: u.full_name for u in db.execute(select(User).where(User.id.in_({r.user_id for r in runs if r.user_id}))).scalars()} if runs else {}
    out = []
    for run in runs:
        over = _overwrote(db, run, pid, first, last)
        overwritten_ids = {c.entry_id for c in over}                      # these existed before the import: restored, never deleted
        made = [e for e in db.execute(_created_by(run, pid, first, last)).scalars().all() if e.id not in overwritten_ids]
        untouched = [e for e in made if e.cash_adjustment == 0 and (e.updated_at - e.created_at) <= _UNTOUCHED]
        if not made and not over:
            continue
        meta = run.metadata_json or {}
        days = [e.order_date for e in made]
        out.append({
            "run_id": str(run.id), "at": run.created_at.isoformat(), "by": names.get(run.user_id, "unknown"), "source": meta.get("source"),
            "created_in_month": len(made), "can_delete": len(untouched), "changed_since": len(made) - len(untouched),
            "overwrote_in_month": len(over),
            "first_day": min(days).isoformat() if days else None, "last_day": max(days).isoformat() if days else None,
        })
    return {"platform": platform_slug, "month": month, "runs": out}


def revert(db: Session, actor: User, platform_slug: str, month: str, run_ids: list[uuid.UUID], *, dry_run: bool = True) -> dict:
    partner = _partner(db, platform_slug)
    first, last = _month(month)
    if not run_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one import to undo.")
    runs = db.execute(
        select(AuditLog).where(AuditLog.id.in_(run_ids), AuditLog.action == "order.imported", AuditLog.entity_id == str(partner.id),
                               AuditLog.organization_id == actor.organization_id)
    ).scalars().all()
    if len(runs) != len(set(run_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"One of those imports was not found on {partner.name}.")

    deleted = restored = kept = 0
    per_run = []
    doomed: dict[uuid.UUID, OrderEntry] = {}
    for run in sorted(runs, key=lambda r: r.created_at):
        over = _overwrote(db, run, partner.id, first, last)
        overwritten_ids = {c.entry_id for c in over}
        made = [e for e in db.execute(_created_by(run, partner.id, first, last)).scalars().all() if e.id not in overwritten_ids]
        gone = [e for e in made if e.cash_adjustment == 0 and (e.updated_at - e.created_at) <= _UNTOUCHED and e.id not in doomed]
        for e in gone:
            doomed[e.id] = e
        n_kept = len(made) - len(gone)
        back = []
        for c in over:
            e = db.get(OrderEntry, c.entry_id)
            if e is not None and c.old_count is not None and e.bottle_count == c.new_count and e.id not in doomed:
                back.append((e, c))
        deleted += len(gone)
        restored += len(back)
        kept += n_kept
        per_run.append({"run_id": str(run.id), "at": run.created_at.isoformat(), "will_delete": len(gone), "will_restore": len(back), "kept": n_kept})
        if not dry_run:
            for e, c in back:
                owner = None
                if c.old_source == EntrySource.EMPLOYEE.value:
                    owner = db.execute(
                        select(AuditLog.user_id).where(
                            AuditLog.action == "order.marked", AuditLog.entity_id == str(e.store_id), AuditLog.created_at < run.created_at - _WINDOW_BEFORE,
                            AuditLog.metadata_json["order_date"].astext == e.order_date.isoformat(),
                        ).order_by(AuditLog.created_at.desc()).limit(1)
                    ).scalar_one_or_none()
                e.bottle_count = c.old_count
                e.cash_adjustment = c.old_cash_adjustment or 0
                e.source = c.old_source or EntrySource.EMPLOYEE.value
                e.marked_by_user_id = owner
    out = {"platform": partner.name, "month": month, "dry_run": dry_run, "will_delete": deleted, "will_restore": restored, "kept_untouched_by_us": kept, "runs": per_run}
    if dry_run:
        return out
    for e in doomed.values():
        db.delete(e)                          # the database trigger copies each row into deleted_rows first
    activity_service.record(
        db, actor=actor, action="order.import_reverted", entity_type="organization", entity_id=partner.id,
        metadata={"platform": partner.slug, "month": month, "runs": [str(r.id) for r in runs], "deleted": deleted, "restored": restored, "kept": kept},
    )
    db.commit()
    out["deleted"], out["restored"] = deleted, restored
    return out
