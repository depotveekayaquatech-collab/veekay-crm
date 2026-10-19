"""
Order entry audit: what employees submitted (the append-only audit log) against what is stored and visible now.

Every employee marking, admin correction and clearing is written to audit_logs in the same transaction as the entry, with the store,
the date and the count. That makes the log the record of what really reached the server, whichever app build sent it. This service
lines the log up against `order_entries` and the stores, and explains each difference:

  MISSING             logged, but there is no entry for that store and date now.
                        - LOST:           the store is still there, the entry is not.
                        - STORE_RECREATED: the store was deleted and added again (a new id); the entry stayed with the old one.
                        - STORE_GONE:     no store with that code exists any more.
  CLEARED             an admin cleared it on purpose (so nothing to restore).
  CHANGED             the entry is there with another number (admin correction, sheet import or cash adjustment).
  HIDDEN_NOT_LIVE     the entry is there, but its store is no longer LIVE, so the employee lists and every live-only view leave it out.

`restore` re-creates MISSING entries from the log (never over an existing one, never a cleared one).
`my_entries` is the employee's own view of everything they entered recently, whatever the store's status is now.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.order_entry import EntrySource, OrderEntry
from app.models.organization import Organization
from app.models.store import Store
from app.models.user import User
from app.services import activity_service

MAX_DAYS = 14
MAX_ROWS = 1000
_EVENTS = ("order.marked", "order.corrected", "order.cleared")


def _window(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The end date is before the start date.")
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Audit at most {MAX_DAYS} days at a time.")


def _since(start: date) -> datetime:
    return datetime.combine(start, time.min, tzinfo=timezone.utc) - timedelta(days=1)


def _final_events(db: Session, org_id: uuid.UUID, start: date, end: date) -> dict[tuple[str, date], dict]:
    """The last logged event for each (store id as logged, order date) in the window."""
    last: dict[tuple[str, date], dict] = {}
    rows = db.execute(
        select(AuditLog).where(AuditLog.organization_id == org_id, AuditLog.action.in_(_EVENTS), AuditLog.created_at >= _since(start))
        .order_by(AuditLog.created_at)
    ).scalars()
    for ev in rows:
        meta = ev.metadata_json or {}
        try:
            d = date.fromisoformat(str(meta.get("order_date")))
        except ValueError:
            continue
        if not (start <= d <= end):
            continue
        last[(ev.entity_id, d)] = {
            "action": ev.action, "at": ev.created_at, "user_id": ev.user_id, "count": meta.get("bottle_count"),
            "store_code": meta.get("store_code"), "store_name": meta.get("store_name"), "partner": meta.get("partner_slug"),
            "state": meta.get("state"),
        }
    return last


def audit(db: Session, user: User, start: date, end: date) -> dict:
    _window(start, end)
    org = user.organization_id
    events = _final_events(db, org, start, end)
    stores = {s.id: s for s in db.execute(select(Store).where(Store.organization_id == org)).scalars().unique()}
    partners = {o.id: o.slug for o in db.execute(select(Organization)).scalars()}
    by_code = {(partners.get(s.partner_organization_id), s.external_code): s for s in stores.values()}
    entries = {(e.store_id, e.order_date): e for e in db.execute(
        select(OrderEntry).where(OrderEntry.organization_id == org, OrderEntry.order_date >= start, OrderEntry.order_date <= end)).scalars()}
    names = {u.id: u.full_name for u in db.execute(select(User).where(User.organization_id == org)).scalars()}
    status_changes: dict[str, dict] = {}
    for ev in db.execute(select(AuditLog).where(AuditLog.organization_id == org, AuditLog.action == "store.status_changed",
                                                AuditLog.created_at >= _since(start)).order_by(AuditLog.created_at)).scalars():
        status_changes[ev.entity_id] = {"at": ev.created_at, **{k: (ev.metadata_json or {}).get(k) for k in ("from", "to")}}

    rows: list[dict] = []
    counts = {"logged": len(events), "ok": 0, "missing": 0, "cleared": 0, "changed": 0, "hidden_not_live": 0}
    for (sid, d), ev in sorted(events.items(), key=lambda kv: (kv[0][1], kv[1]["store_name"] or "")):
        try:
            logged_store = stores.get(uuid.UUID(sid))
        except ValueError:
            logged_store = None
        store = logged_store or by_code.get((ev["partner"], ev["store_code"]))
        entry = entries.get((store.id, d)) if store else None
        base = {
            "order_date": d, "store_id": store.id if store else None, "store_code": ev["store_code"], "store_name": ev["store_name"],
            "state": ev["state"], "employee": names.get(ev["user_id"]), "logged_count": ev["count"], "logged_at": ev["at"],
        }
        if ev["action"] == "order.cleared":
            if entry is None:
                counts["cleared"] += 1
                rows.append({**base, "kind": "CLEARED", "current_count": None, "restorable": False,
                             "detail": f"An admin cleared this entry ({names.get(ev['user_id']) or 'someone'}). Nothing to restore."})
            else:
                counts["ok"] += 1       # cleared and entered again afterwards
            continue
        if entry is None:
            counts["missing"] += 1
            if logged_store is not None:
                why, detail = "LOST", "The store is still there but this entry is not. It can be restored from the log."
            elif store is not None:
                why, detail = "STORE_RECREATED", "The store was deleted and added again; the entry stayed with the old store. It can be restored."
            else:
                why, detail = "STORE_GONE", "No store with this code exists any more, so it cannot be restored until the store is added again."
            rows.append({**base, "kind": "MISSING", "reason": why, "current_count": None, "restorable": store is not None and ev["count"] is not None, "detail": detail})
            continue
        shown = entry.bottle_count - entry.cash_adjustment
        if ev["count"] is not None and shown != ev["count"]:
            counts["changed"] += 1
            rows.append({**base, "kind": "CHANGED", "current_count": entry.bottle_count, "restorable": False,
                         "detail": f"The employee entered {ev['count']}; it now holds {entry.bottle_count} (source: {entry.source}, changed by an admin, a sheet import or a cash adjustment)."})
        else:
            counts["ok"] += 1
        if store is not None and store.status != "LIVE":
            counts["hidden_not_live"] += 1
            ch = status_changes.get(str(store.id))
            when = f", changed {ch['at']:%d %b %H:%M} UTC from {ch['from']}" if ch and ch.get("to") == store.status else ""
            rows.append({**base, "kind": "HIDDEN_NOT_LIVE", "current_count": entry.bottle_count, "restorable": False,
                         "store_status": store.status,
                         "detail": f"The entry is saved, but this store is now {store.status}{when}, so the employee list and live-only views leave it out."})
    return {"start": start, "end": end, "summary": counts, "rows": rows[:MAX_ROWS], "truncated": len(rows) > MAX_ROWS}


def restore(db: Session, user: User, start: date, end: date, *, dry_run: bool) -> dict:
    """Re-create the MISSING entries from the log: only where nothing exists for that store and date, never one an admin cleared."""
    report = audit(db, user, start, end)
    todo = [r for r in report["rows"] if r["kind"] == "MISSING" and r["restorable"]]
    out = {"restorable": len(todo), "restored": 0, "dry_run": dry_run, "examples": [f"{r['order_date']} {r['store_code']} ({r['logged_count']})" for r in todo[:10]]}
    if dry_run or not todo:
        return out
    existing = {(e.store_id, e.order_date) for e in db.execute(
        select(OrderEntry).where(OrderEntry.organization_id == user.organization_id, OrderEntry.order_date >= start, OrderEntry.order_date <= end)).scalars()}
    for r in todo:
        key = (r["store_id"], r["order_date"])
        if key in existing:
            continue
        db.add(OrderEntry(
            organization_id=user.organization_id, store_id=r["store_id"], order_date=r["order_date"], bottle_count=int(r["logged_count"]),
            source=EntrySource.EMPLOYEE.value, marked_by_user_id=None,
        ))
        existing.add(key)
        out["restored"] += 1
    activity_service.record(
        db, actor=user, action="order.restored_from_log", entity_type="order_entry", entity_id=user.organization_id,
        metadata={"start": start.isoformat(), "end": end.isoformat(), "restored": out["restored"]},
    )
    db.commit()
    return out


def my_entries(db: Session, user: User, days: int) -> dict:
    """Everything this person entered in the last `days` days, newest first, with each store's status today. A store that has since left
    LIVE is still listed (so an entry never seems to have vanished); the number is the one they entered."""
    days = max(1, min(days, MAX_DAYS))
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=days - 1)
    rows = db.execute(
        select(OrderEntry, Store).join(Store, Store.id == OrderEntry.store_id)
        .where(OrderEntry.marked_by_user_id == user.id, OrderEntry.order_date >= since, OrderEntry.order_date <= today)
        .order_by(OrderEntry.order_date.desc(), Store.name).limit(5000)
    ).all()
    items = [{
        "order_date": e.order_date, "store_id": s.id, "store_name": s.name, "store_code": s.external_code, "city": s.city, "state": s.state,
        "store_status": s.status, "bottles": e.bottle_count - e.cash_adjustment, "source": e.source, "entered_at": e.created_at,
    } for e, s in rows]
    return {"today": today, "days": days, "total": len(items), "items": items}
