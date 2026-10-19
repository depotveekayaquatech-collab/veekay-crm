"""
Recovery of deleted order entries.

A database trigger copies every deleted order entry (and other valuable rows) into `deleted_rows` before it goes, whatever deleted it: an
admin clearing a day, "Remove all stores", a store removed, or SQL typed by hand (migration 0043). This service lists those copies for a
period and puts them back:

  - on the same store, or, when the store was deleted and added again (a new id), on the store with the same platform and code;
  - never over an entry that exists for that store and day;
  - each copy is marked restored once it is back, and the restore is written to the activity log.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deleted_row import DeletedRow
from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.user import User
from app.services import activity_service

MAX_ROWS = 1000


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _candidates(db: Session, org_id: uuid.UUID, *, start: date | None, end: date | None, ids: list[uuid.UUID] | None, include_restored: bool) -> list[DeletedRow]:
    q = select(DeletedRow).where(DeletedRow.table_name == "order_entries", DeletedRow.data["organization_id"].astext == str(org_id))
    if ids:
        q = q.where(DeletedRow.id.in_(ids))
    if start:
        q = q.where(DeletedRow.data["order_date"].astext >= start.isoformat())
    if end:
        q = q.where(DeletedRow.data["order_date"].astext <= end.isoformat())
    if not include_restored:
        q = q.where(DeletedRow.restored_at.is_(None))
    return list(db.execute(q.order_by(DeletedRow.deleted_at.desc()).limit(MAX_ROWS)).scalars())


class _Stores:
    """Finds the store a deleted entry belonged to: still there by id, or added again with the same platform and code."""

    def __init__(self, db: Session, org_id: uuid.UUID):
        self.db = db
        self.by_id = {s.id: s for s in db.execute(select(Store).where(Store.organization_id == org_id)).scalars().unique()}
        self.by_code = {(s.partner_organization_id, s.external_code): s for s in self.by_id.values()}
        self._gone: dict[str, dict] = {}

    def gone(self, store_id: str) -> dict | None:
        if store_id not in self._gone:
            row = self.db.execute(select(DeletedRow).where(DeletedRow.table_name == "stores", DeletedRow.row_id == store_id).order_by(DeletedRow.deleted_at.desc()).limit(1)).scalar_one_or_none()
            self._gone[store_id] = row.data if row else {}
        return self._gone[store_id] or None

    def find(self, store_id) -> tuple[Store | None, str | None, str | None]:
        """(the current store to put the entry on, its code, its name) for the store id a deleted entry carried."""
        sid = _uuid(store_id)
        s = self.by_id.get(sid) if sid else None
        if s is not None:
            return s, s.external_code, s.name
        old = self.gone(str(store_id)) or {}
        code, name = old.get("external_code"), old.get("name")
        partner = _uuid(old.get("partner_organization_id"))
        return (self.by_code.get((partner, code)) if code and partner else None), code, name


def list_deleted(db: Session, user: User, start: date | None, end: date | None, *, include_restored: bool = False) -> dict:
    org = user.organization_id
    stores = _Stores(db, org)
    names = {u.id: u.full_name for u in db.execute(select(User).where(User.organization_id == org)).scalars()}
    rows = _candidates(db, org, start=start, end=end, ids=None, include_restored=include_restored)
    items, counts = [], {"restorable": 0, "already_there": 0, "store_gone": 0, "restored": 0}
    taken = {(e.store_id, e.order_date) for e in db.execute(select(OrderEntry).where(OrderEntry.organization_id == org)).scalars()} if rows else set()
    for r in rows:
        d = r.data
        store, code, name = stores.find(d.get("store_id"))
        day = date.fromisoformat(d["order_date"])
        if r.restored_at is not None:
            state = "RESTORED"
        elif store is None:
            state = "STORE_GONE"
        elif (store.id, day) in taken:
            state = "ALREADY_THERE"
        else:
            state = "RESTORABLE"
        counts[{"RESTORABLE": "restorable", "ALREADY_THERE": "already_there", "STORE_GONE": "store_gone", "RESTORED": "restored"}[state]] += 1
        items.append({
            "id": r.id, "order_date": day, "store_code": code, "store_name": name, "bottles": d.get("bottle_count"),
            "cash_adjustment": d.get("cash_adjustment"), "source": d.get("source"), "marked_by": names.get(_uuid(d.get("marked_by_user_id"))),
            "deleted_at": r.deleted_at, "restored_at": r.restored_at, "state": state,
        })
    return {"summary": counts, "items": items, "truncated": len(rows) >= MAX_ROWS}


def restore(db: Session, user: User, *, ids: list[uuid.UUID] | None, start: date | None, end: date | None, dry_run: bool) -> dict:
    if not ids and not (start and end):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose entries to restore, or a start and end date.")
    org = user.organization_id
    stores = _Stores(db, org)
    rows = _candidates(db, org, start=start, end=end, ids=ids, include_restored=False)
    users = {u.id for u in db.execute(select(User).where(User.organization_id == org)).scalars()}
    taken = {(e.store_id, e.order_date) for e in db.execute(select(OrderEntry).where(OrderEntry.organization_id == org)).scalars()}
    plan, out = [], {"restorable": 0, "restored": 0, "already_there": 0, "store_gone": 0, "dry_run": dry_run, "examples": []}
    for r in rows:
        d = r.data
        store, code, _name = stores.find(d.get("store_id"))
        day = date.fromisoformat(d["order_date"])
        if store is None:
            out["store_gone"] += 1
        elif (store.id, day) in taken:
            out["already_there"] += 1
        else:
            out["restorable"] += 1
            taken.add((store.id, day))
            plan.append((r, store, day))
            if len(out["examples"]) < 10:
                out["examples"].append(f"{day} {code} ({d.get('bottle_count')})")
    if dry_run or not plan:
        return out
    now = datetime.now(timezone.utc)
    for r, store, day in plan:
        d = r.data
        marker = _uuid(d.get("marked_by_user_id"))
        db.add(OrderEntry(
            organization_id=org, store_id=store.id, order_date=day, bottle_count=int(d["bottle_count"]),
            cash_adjustment=int(d.get("cash_adjustment") or 0), source=d.get("source") or "employee",
            marked_by_user_id=marker if marker in users else None,
        ))
        r.restored_at = now
        out["restored"] += 1
    activity_service.record(
        db, actor=user, action="order.restored_from_deleted", entity_type="order_entry", entity_id=org,
        metadata={"restored": out["restored"], "from": start.isoformat() if start else None, "to": end.isoformat() if end else None},
    )
    db.commit()
    return out
