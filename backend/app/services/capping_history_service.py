"""
Capping history: a Zepto store's DAILY capping with the date each value took effect, so the latest capping and everything before it is on record.

The capping of a store on day D is the capping of the row with the greatest effective_from <= D (10 from the 1st and 11 from the 15th give 10 on days 1-14 and
11 from day 15). store_caps stays the "current capping": the capping effective today, refreshed in the same transaction as every change. Dates are Asia/Kolkata days.

Who may do what (re-checked on the server, whatever the app shows):
  * see the list and a store's history: whoever may see Zepto capping (capping_service.is_eligible).
  * change a capping or move its start date: holders of capping.change (administrators; a "manager" when it is ticked for them) who are not on another platform.
There is no delete, and a capping's value cannot be edited: a new value is a new change from a date.
"""
from __future__ import annotations

import uuid
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime
from typing import Sequence
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.capping_history import CappingHistory
from app.models.store import Store, StoreStatus
from app.models.store_cap import StoreCap
from app.models.user import User
from app.services import activity_service, capping_service

IST = ZoneInfo("Asia/Kolkata")
EARLIEST = date(2024, 1, 1)         # the earliest date a capping can start


def today_ist() -> date:
    return datetime.now(IST).date()


def effective_capping(history: Sequence[tuple[date, int]], day: date) -> int | None:
    """The capping on `day`: the value of the entry with the greatest effective_from <= day. `history` is (effective_from, capping) sorted by
    effective_from, oldest first. None before the first entry."""
    i = bisect_right([h[0] for h in history], day)
    return history[i - 1][1] if i else None


def _require_change(user: User, perms: set[str]) -> None:
    if "capping.change" not in perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator or manager can change capping.")
    slug = ((user.platform_organization.slug if user.platform_organization is not None else None) or "").strip().lower()
    if not user.is_active or slug not in ("", capping_service.PLATFORM):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Capping is available to Zepto employees.")


def _store(db: Session, user: User, partner_id: uuid.UUID, store_id: uuid.UUID) -> Store:
    store = db.get(Store, store_id)
    if store is None or store.organization_id != user.organization_id or store.partner_organization_id != partner_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    return store


def _stores(db: Session, user: User, partner_id: uuid.UUID, store_id: uuid.UUID | None) -> list[tuple]:
    """(id, outlet id, name, state, city, current store_caps value) of the live Zepto stores, by name; or just `store_id`."""
    q = (
        select(Store.id, Store.external_code, Store.name, Store.state, Store.city, StoreCap.daily_cap)
        .select_from(Store).outerjoin(StoreCap, StoreCap.store_id == Store.id)
        .where(Store.organization_id == user.organization_id, Store.partner_organization_id == partner_id, Store.status == StoreStatus.LIVE.value)
        .order_by(func.lower(Store.name), Store.external_code)
    )
    if store_id is not None:
        q = q.where(Store.id == store_id)
    return list(db.execute(q).all())


def _history_by_store(db: Session, store_ids: list[uuid.UUID], up_to: date) -> dict[uuid.UUID, list[tuple[date, int]]]:
    """One query: every history row up to `up_to` for these stores, oldest first, grouped by store."""
    out: dict[uuid.UUID, list[tuple[date, int]]] = defaultdict(list)
    if not store_ids:
        return out
    rows = db.execute(
        select(CappingHistory.store_id, CappingHistory.effective_from, CappingHistory.capping)
        .where(CappingHistory.store_id.in_(store_ids), CappingHistory.effective_from <= up_to)
        .order_by(CappingHistory.store_id, CappingHistory.effective_from)
    )
    for sid, eff, cap in rows:
        out[sid].append((eff, cap))
    return out


def _sync_current(db: Session, store_id: uuid.UUID, user_id: uuid.UUID | None, today: date) -> int | None:
    """Make store_caps.daily_cap the capping effective today (the one existing code reads). Returns it; leaves store_caps alone when no entry applies yet."""
    current = effective_capping(_history_by_store(db, [store_id], today)[store_id], today)
    if current is None:
        return None
    row = db.execute(select(StoreCap).where(StoreCap.store_id == store_id)).scalar_one_or_none()
    if row is None:
        db.add(StoreCap(store_id=store_id, daily_cap=current, source="manual", updated_by_user_id=user_id))
    elif row.daily_cap != current:
        row.daily_cap, row.source, row.updated_by_user_id = current, "manual", user_id
    return current


def change(db: Session, user: User, perms: set[str], store_id: uuid.UUID, capping: int, effective_from: date) -> dict:
    """Add a capping change for one store, effective from a date (today or earlier). One transaction: the history row, store_caps and the activity log."""
    _require_change(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    store = _store(db, user, partner.id, store_id)
    today = today_ist()
    if not 1 <= capping <= capping_service.MAX_CAP:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The capping must be a whole number from 1 to {capping_service.MAX_CAP:,}.")
    if effective_from > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The effective date cannot be in the future. Use today or an earlier date.")
    if effective_from < EARLIEST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That date is too far back.")

    clash = f"A capping change for {effective_from:%d-%b-%Y} already exists for this store."
    if db.execute(select(CappingHistory.id).where(CappingHistory.store_id == store_id, CappingHistory.effective_from == effective_from)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, clash)
    row = CappingHistory(store_id=store_id, capping=capping, effective_from=effective_from, created_by=user.id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:                   # two people saved the same date at once: the unique constraint decides
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, clash) from None
    before = db.execute(select(StoreCap.daily_cap).where(StoreCap.store_id == store_id)).scalar_one_or_none()
    current = _sync_current(db, store_id, user.id, today)
    activity_service.record(
        db, actor=user, action="store.capping_changed", entity_type="store", entity_id=store_id,
        metadata={"outlet": store.external_code, "name": store.name, "capping": capping, "effective_from": effective_from.isoformat(), "current_from": before, "current_to": current},
    )
    db.commit()
    return {
        "id": row.id, "store_id": store_id, "capping": capping, "effective_from": effective_from,
        "backdated": effective_from < today, "current_capping": current,
    }


def change_effective_date(db: Session, user: User, perms: set[str], history_id: uuid.UUID, effective_from: date) -> dict:
    """Move one capping change to another start date (a sheet said it started on the 1st, not today). The capping value stays; the date must not be in
    the future or already used by another change of the same store. The old and new dates go to the activity log, and the store's current capping is
    recomputed."""
    _require_change(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    row = db.get(CappingHistory, history_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That capping change was not found.")
    store = _store(db, user, partner.id, row.store_id)
    today = today_ist()
    if effective_from > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The effective date cannot be in the future. Use today or an earlier date.")
    if effective_from < EARLIEST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That date is too far back.")
    old = row.effective_from
    if effective_from != old:
        if db.execute(select(CappingHistory.id).where(CappingHistory.store_id == row.store_id, CappingHistory.effective_from == effective_from)).first():
            raise HTTPException(status.HTTP_409_CONFLICT, f"A capping change for {effective_from:%d-%b-%Y} already exists for this store.")
        before = db.execute(select(StoreCap.daily_cap).where(StoreCap.store_id == row.store_id)).scalar_one_or_none()
        row.effective_from = effective_from
        db.flush()
        current = _sync_current(db, row.store_id, user.id, today)
        activity_service.record(
            db, actor=user, action="store.capping_date_changed", entity_type="store", entity_id=row.store_id,
            metadata={"outlet": store.external_code, "name": store.name, "capping": row.capping, "from": old.isoformat(), "to": effective_from.isoformat(),
                      "current_from": before, "current_to": current},
        )
        db.commit()
    return {"id": row.id, "store_id": row.store_id, "capping": row.capping, "effective_from": row.effective_from, "was": old,
            "current_capping": effective_capping(_history_by_store(db, [row.store_id], today)[row.store_id], today)}


def current_list(db: Session, user: User, perms: set[str]) -> dict:
    """Every live Zepto store with its latest capping (the one in force today) and the date it started. A store with no capping has none (null)."""
    capping_service.require_eligible(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    today = today_ist()
    stores = _stores(db, user, partner.id, None)
    hist = _history_by_store(db, [s[0] for s in stores], today)
    rows = []
    for sid, code, name, state, city, legacy in stores:
        h = hist.get(sid, [])
        capping = effective_capping(h, today)
        since = max((d for d, _ in h), default=None) if h else None
        rows.append({
            "store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city,
            "capping": capping if capping is not None else legacy, "since": since if capping is not None else None,
        })
    return {"today": today, "total": len(rows), "without_capping": sum(1 for r in rows if r["capping"] is None), "rows": rows}


def history(db: Session, user: User, perms: set[str], store_id: uuid.UUID) -> dict:
    """One store's changes, newest effective date first."""
    capping_service.require_eligible(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    store = _store(db, user, partner.id, store_id)
    rows = db.execute(
        select(CappingHistory, User.full_name, User.employee_code)
        .outerjoin(User, User.id == CappingHistory.created_by)
        .where(CappingHistory.store_id == store_id)
        .order_by(CappingHistory.effective_from.desc())
    ).all()
    return {
        "store_id": store_id, "outlet_id": store.external_code, "outlet_name": store.name, "today": today_ist(),
        "rows": [
            {"id": h.id, "capping": h.capping, "effective_from": h.effective_from, "changed_by": name, "changed_by_code": code, "created_at": h.created_at}
            for h, name, code in rows
        ],
    }
