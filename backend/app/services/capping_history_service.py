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
from datetime import date, datetime, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.capping_history import CappingHistory
from app.models.order_entry import OrderEntry
from app.models.store import Store, StoreStatus
from app.models.store_cap import StoreCap
from app.models.user import User
from app.services import activity_service, capping_service

IST = ZoneInfo("Asia/Kolkata")
EARLIEST = date(2024, 1, 1)         # the earliest date a capping can start
AMBER_MARGIN = 1                    # the card turns amber when the average is within this of the limit


def today_ist() -> date:
    return datetime.now(IST).date()


def max_daily_limit() -> int:
    return settings.MAX_DAILY_LIMIT


def effective_capping(history: Sequence[tuple[date, int | None]], day: date) -> int | None:
    """The capping on `day`: the value of the entry with the greatest effective_from <= day. `history` is (effective_from, capping) sorted by
    effective_from, oldest first. None before the first entry."""
    i = bisect_right([h[0] for h in history], day)
    return history[i - 1][1] if i else None


def capping_totals(history: Sequence[tuple[date, int | None]], start: date, end: date) -> tuple[int, int]:
    """(sum of the capping, number of days) over start..end, counting only the days on which a capping was in force (none before the first change, none after a
    removal). Walks the changes once instead of looking every day up."""
    if end < start:
        return 0, 0
    i = bisect_right([h[0] for h in history], start)
    current = history[i - 1][1] if i else None
    seg_start, total, days = start, 0, 0
    while True:
        nxt = history[i][0] if i < len(history) and history[i][0] <= end else None
        seg_end = nxt - timedelta(days=1) if nxt else end
        if current is not None:
            n = (seg_end - seg_start).days + 1
            total, days = total + current * n, days + n
        if nxt is None:
            return total, days
        seg_start, current, i = nxt, history[i][1], i + 1


def assess(total: int, days: int, limit: int, capping_total: int = 0, capping_days: int = 0) -> dict:
    """The alert: `total` bottles over `days` store-days that have an entry, and the capping summed over `capping_days` store-days with a capping in force.
    In alert when either average is above the limit. Exactly the limit is never a breach (integer arithmetic: no rounding surprises)."""
    entry_breach = days > 0 and total > limit * days
    capping_breach = capping_days > 0 and capping_total > limit * capping_days
    reasons = (["average"] if entry_breach else []) + (["capping"] if capping_breach else [])
    near = (days > 0 and total > (limit - AMBER_MARGIN) * days) or (capping_days > 0 and capping_total > (limit - AMBER_MARGIN) * capping_days)
    if reasons:
        tone = "over"
    elif near:
        tone = "warn"
    else:
        tone = "ok" if days > 0 or capping_days > 0 else "none"
    return {"alert": bool(reasons), "reasons": reasons, "entry_breach": entry_breach, "capping_breach": capping_breach, "status": tone}


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
    """(id, outlet id, name, state, city, current store_caps value, start date) of the live Zepto stores, by name; or just `store_id`."""
    q = (
        select(Store.id, Store.external_code, Store.name, Store.state, Store.city, StoreCap.daily_cap, Store.start_date)
        .select_from(Store).outerjoin(StoreCap, StoreCap.store_id == Store.id)
        .where(Store.organization_id == user.organization_id, Store.partner_organization_id == partner_id, Store.status == StoreStatus.LIVE.value)
        .order_by(func.lower(Store.name), Store.external_code)
    )
    if store_id is not None:
        q = q.where(Store.id == store_id)
    return list(db.execute(q).all())


def first_supply(db: Session, store_ids: list[uuid.UUID]) -> dict[uuid.UUID, date]:
    """The day each store was first supplied: its first entry with bottles in it. The same meaning the rest of the CRM gives a store's start date."""
    if not store_ids:
        return {}
    return dict(db.execute(
        select(OrderEntry.store_id, func.min(OrderEntry.order_date))
        .where(OrderEntry.store_id.in_(store_ids), OrderEntry.bottle_count > 0).group_by(OrderEntry.store_id)
    ).all())


def entry_start(db: Session, stores: list[tuple]) -> dict[uuid.UUID, date | None]:
    """{store id: the day its actual entries started}: the store's start date, else its first supply day, else None (never supplied)."""
    missing = [s[0] for s in stores if s[6] is None]
    found = first_supply(db, missing)
    return {s[0]: (s[6] or found.get(s[0])) for s in stores}


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
    """Make store_caps.daily_cap the capping effective today (the one existing code reads). Returns it. A removal (a row with no capping) deletes it; the cap is left
    alone when no entry applies yet."""
    rows = _history_by_store(db, [store_id], today)[store_id]
    current = effective_capping(rows, today)
    row = db.execute(select(StoreCap).where(StoreCap.store_id == store_id)).scalar_one_or_none()
    if current is None:
        if rows and row is not None:                       # the latest change up to today says "no capping"
            db.delete(row)
        return None
    if row is None:
        db.add(StoreCap(store_id=store_id, daily_cap=current, source="manual", updated_by_user_id=user_id))
    elif row.daily_cap != current:
        row.daily_cap, row.source, row.updated_by_user_id = current, "manual", user_id
    return current


def _set_today(db: Session, store_id: uuid.UUID, capping: int | None, effective: date, user_id: uuid.UUID) -> CappingHistory:
    """Today's change for a store: a new history row, or the row already made today (a correction the same day, not a second row)."""
    row = db.execute(select(CappingHistory).where(CappingHistory.store_id == store_id, CappingHistory.effective_from == effective)).scalar_one_or_none()
    if row is None:
        row = CappingHistory(store_id=store_id, capping=capping, effective_from=effective, created_by=user_id)
        db.add(row)
    else:
        row.capping, row.created_by = capping, user_id
    db.flush()
    return row


def change(db: Session, user: User, perms: set[str], store_id: uuid.UUID, capping: int) -> dict:
    """Set a store's capping. There is no date to choose: a change applies from today, and the FIRST capping a store ever gets applies from the day its actual
    entries started (its start date, else its first supply day), so its days since then are measured against it. A second change on the same day corrects
    that day's. One transaction: the history row, store_caps and the activity log."""
    _require_change(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    store = _store(db, user, partner.id, store_id)
    today = today_ist()
    if not 1 <= capping <= capping_service.MAX_CAP:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The capping must be a whole number from 1 to {capping_service.MAX_CAP:,}.")
    before = db.execute(select(StoreCap.daily_cap).where(StoreCap.store_id == store_id)).scalar_one_or_none()
    rows = _history_by_store(db, [store_id], today)[store_id]
    effective = today
    if not rows and before is None:                    # the first capping this store has ever had
        start = store.start_date or first_supply(db, [store_id]).get(store_id)
        if start is not None:
            effective = min(max(start, EARLIEST), today)
    row = _set_today(db, store_id, capping, effective, user.id)
    current = _sync_current(db, store_id, user.id, today)
    activity_service.record(
        db, actor=user, action="store.capping_changed", entity_type="store", entity_id=store_id,
        metadata={"outlet": store.external_code, "name": store.name, "capping": capping, "effective_from": effective.isoformat(), "current_from": before, "current_to": current},
    )
    db.commit()
    return {"id": row.id, "store_id": store_id, "capping": capping, "effective_from": effective, "current_capping": current}


def current_list(db: Session, user: User, perms: set[str]) -> dict:
    """Every live Zepto store with its latest capping (the one in force today) and the day its actual entries started. A store with no capping has none (null)."""
    capping_service.require_eligible(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    today = today_ist()
    stores = _stores(db, user, partner.id, None)
    hist = _history_by_store(db, [s[0] for s in stores], today)
    starts = entry_start(db, stores)
    rows = []
    for sid, code, name, state, city, legacy, _start in stores:
        capping = effective_capping(hist.get(sid, []), today)
        rows.append({
            "store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city,
            "capping": capping if capping is not None else legacy if not hist.get(sid) else None, "start_date": starts.get(sid),
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


def _period(start: date | None, end: date | None) -> tuple[date, date]:
    """The chosen dates; this month (to its last day) by default. Refused when backwards or before the data starts."""
    today = today_ist()
    first = date(today.year, today.month, 1)
    start = start or first
    end = end or (date(first.year + (first.month == 12), first.month % 12 + 1, 1) - timedelta(days=1))
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The 'to' date must not be before the 'from' date.")
    if start < EARLIEST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That period is too far back.")
    if (end - start).days + 1 > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a period of at most a year.")
    return start, end


def alert_summary(db: Session, user: User, perms: set[str], start: date | None, end: date | None) -> dict:
    """The "Reduce capping" alert. Two COLLECTIVE averages over all live Zepto stores together, from `start` to `end` (this month by default), each compared with the
    limit (MAX_DAILY_LIMIT): the average daily ENTRY (all bottles / all store-days that have an entry; a zero is a real entry, a day with no row is not counted) and
    the average CAPPING (all capping / all store-days, up to today, on which a capping was in force). Either above the limit raises the alert; exactly the limit is
    fine. Averages are shown to two decimals; the comparison uses the exact figures. One store above the limit does not raise it."""
    capping_service.require_eligible(user, perms)
    start, end = _period(start, end)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    limit = max_daily_limit()
    today = today_ist()
    stores = _stores(db, user, partner.id, None)
    ids = [s[0] for s in stores]
    starts = entry_start(db, stores)
    entry_total, entry_days = (int(v or 0) for v in db.execute(
        select(func.coalesce(func.sum(OrderEntry.bottle_count), 0), func.count(OrderEntry.id))
        .where(OrderEntry.store_id.in_(ids or [uuid.uuid4()]), OrderEntry.order_date >= start, OrderEntry.order_date <= end)
    ).one())
    capping_end = min(end, today)               # no capping average for days that have not happened yet
    hist = _history_by_store(db, ids, today)
    cap_total = cap_days = 0
    for sid, _code, _name, _state, _city, legacy, _start in stores:
        began = starts.get(sid)                  # a store's capping is measured from the day its actual entries started, never before
        if began is None:
            continue                              # never supplied: nothing to measure yet
        h = list(hist.get(sid, []))
        if h and h[0][1] is not None and began < h[0][0]:
            h.insert(0, (began, h[0][1]))         # its first capping has applied since it started
        elif not h and legacy is not None:
            h = [(began, legacy)]
        t, d = capping_totals(h, max(start, began), capping_end)
        cap_total, cap_days = cap_total + t, cap_days + d
    verdict = assess(entry_total, entry_days, limit, cap_total, cap_days)
    return {
        "from": start, "to": end, "today": today, "limit": limit, "amber_margin": AMBER_MARGIN,
        "overall": {
            "entry_average": round(entry_total / entry_days, 2) if entry_days else None, "entry_days": entry_days, "total": entry_total,
            "capping_average": round(cap_total / cap_days, 2) if cap_days else None, "capping_days": cap_days,
            "entry_breach": verdict["entry_breach"], "capping_breach": verdict["capping_breach"],
            "alert": verdict["alert"], "reasons": verdict["reasons"], "status": verdict["status"],
        },
    }


def remove_capping(db: Session, user: User, perms: set[str], store_id: uuid.UUID) -> dict:
    """Remove a store's capping from today: a history row that says "no capping from here". The days before keep the capping they had, the store's current
    capping becomes none, and the change is recorded like any other. Refused when the store has no capping to remove."""
    _require_change(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    store = _store(db, user, partner.id, store_id)
    today = today_ist()
    rows = _history_by_store(db, [store_id], today)[store_id]
    before = db.execute(select(StoreCap.daily_cap).where(StoreCap.store_id == store_id)).scalar_one_or_none()
    if effective_capping(rows, today) is None and (rows or before is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This store has no capping, so there is nothing to remove.")
    row = _set_today(db, store_id, None, today, user.id)
    current = _sync_current(db, store_id, user.id, today)
    activity_service.record(
        db, actor=user, action="store.capping_removed", entity_type="store", entity_id=store_id,
        metadata={"outlet": store.external_code, "name": store.name, "effective_from": today.isoformat(), "current_from": before, "current_to": current},
    )
    db.commit()
    return {"id": row.id, "store_id": store_id, "capping": None, "effective_from": today, "current_capping": current}
