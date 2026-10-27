"""
Capping history: a store's daily capping with the date each value took effect, the capping sheet, and the average-vs-limit alert.

The capping of a store on day D is the capping of the row with the greatest effective_from <= D (10 from the 1st and 11 from the 15th give 10 on
days 1-14 and 11 from day 15). Rows are only ever added through the API (no edit, no delete). store_caps stays the "current capping": the capping
effective today, refreshed in the same transaction as every change. Dates are Asia/Kolkata days.

Who may do what (re-checked on the server, whatever the app shows):
  * see the history, the sheet and the summary: whoever may see Zepto capping (capping_service.is_eligible).
  * change a capping: holders of capping.change (administrators; a "manager" when it is ticked for them) who are not on another platform.

The alert is separate from the monthly-limit levels in capping_service. Two averages must stay at or under settings.MAX_DAILY_LIMIT: the average
daily ENTRY (over the days that have an entry; a zero is a real entry, a day with no row is not counted) and the average CAPPING (over the days in the
period, up to today, on which a capping was in force). A store is IN ALERT when either average is above the limit, or any single day's entry is above it.
Exactly the limit is fine. Averages are shown to two decimals; the comparison itself uses the exact figures.
"""
from __future__ import annotations

import csv
import io
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
EARLIEST = date(2024, 1, 1)         # same floor as capping_service.parse_month
MAX_SHEET_DAYS = 365                # one year of columns at most (and no repeated dd-MMM header)
AMBER_MARGIN = 1                    # the card turns amber when the average is within this of the limit
SHEET_MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def today_ist() -> date:
    return datetime.now(IST).date()


def max_daily_limit() -> int:
    return settings.MAX_DAILY_LIMIT


# ---------------------------------------------------------------- the two rules (pure)

def effective_capping(history: Sequence[tuple[date, int]], day: date) -> int | None:
    """The capping on `day`: the value of the entry with the greatest effective_from <= day. `history` is (effective_from, capping) sorted by
    effective_from, oldest first. None before the first entry."""
    i = bisect_right([h[0] for h in history], day)
    return history[i - 1][1] if i else None


def capping_totals(history: Sequence[tuple[date, int]], start: date, end: date) -> tuple[int, int]:
    """(sum of the capping, number of days) over start..end, counting only the days on which a capping was in force (none before the first entry).
    Walks the entries once instead of looking every day up."""
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


def assess(total: int, days: int, breaches: Sequence[tuple[date, int]], limit: int, capping_total: int = 0, capping_days: int = 0) -> dict:
    """The alert for one store: `total` bottles over `days` days that have an entry, `breaches` = the (date, value) of every day above the limit, and the
    capping summed over `capping_days` days. In alert when either average is above the limit or any day is. Exactly the limit is never a breach
    (integer arithmetic: no rounding surprises)."""
    average_breach = days > 0 and total > limit * days
    capping_breach = capping_days > 0 and capping_total > limit * capping_days
    day_breach = len(breaches) > 0
    reasons = (["average"] if average_breach else []) + (["capping"] if capping_breach else []) + (["day"] if day_breach else [])
    near = (days > 0 and total > (limit - AMBER_MARGIN) * days) or (capping_days > 0 and capping_total > (limit - AMBER_MARGIN) * capping_days)
    if reasons:
        tone = "over"
    elif near:
        tone = "warn"
    else:
        tone = "ok" if days > 0 or capping_days > 0 else "none"
    return {
        "alert": bool(reasons), "reasons": reasons, "average_breach": average_breach, "capping_breach": capping_breach, "day_breach": day_breach, "status": tone,
    }


# ---------------------------------------------------------------- scope

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


def _period(start: date | None, end: date | None) -> tuple[date, date]:
    """The chosen dates; this month (to its last day) by default. Refused when backwards, before the data starts or longer than a year."""
    today = today_ist()
    first = date(today.year, today.month, 1)
    start = start or first
    end = end or (date(first.year + (first.month == 12), first.month % 12 + 1, 1) - timedelta(days=1))
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The 'to' date must not be before the 'from' date.")
    if start < EARLIEST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That period is too far back.")
    if (end - start).days + 1 > MAX_SHEET_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Choose a period of at most {MAX_SHEET_DAYS} days.")
    return start, end


# ---------------------------------------------------------------- change + history

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


# ---------------------------------------------------------------- legacy writers (the older "set a cap" and the sheet upload)

def record_current_many(db: Session, caps: dict[uuid.UUID, int], user_id: uuid.UUID | None) -> None:
    """The older single-store edit and the bulk upload set a store's cap "as of now". Keep the history in step: today's entry becomes that value
    (added, or corrected if one already exists for today). Only values of 1 or more are history: 0 and "no cap" stay in store_caps alone."""
    caps = {sid: c for sid, c in caps.items() if c >= 1}
    if not caps:
        return
    today = today_ist()
    existing = {
        h.store_id: h
        for h in db.execute(select(CappingHistory).where(CappingHistory.store_id.in_(list(caps)), CappingHistory.effective_from == today)).scalars()
    }
    for sid, cap in caps.items():
        row = existing.get(sid)
        if row is None:
            db.add(CappingHistory(store_id=sid, capping=cap, effective_from=today, created_by=user_id))
        else:
            row.capping = cap
    db.flush()


# ---------------------------------------------------------------- the capping sheet

def sheet(db: Session, user: User, perms: set[str], start: date | None, end: date | None, store_id: uuid.UUID | None) -> dict:
    """One row per live Zepto store, one column per date, each cell the capping in force that day (None before the store's first entry).
    Two queries however many stores and days: the stores, then every history row up to the last date."""
    capping_service.require_eligible(user, perms)
    start, end = _period(start, end)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    if store_id is not None:
        _store(db, user, partner.id, store_id)
    stores = _stores(db, user, partner.id, store_id)
    hist = _history_by_store(db, [s[0] for s in stores], end)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    rows = []
    for sid, code, name, state, city, _ in stores:
        h = hist.get(sid, [])
        rows.append({"store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city, "cells": [effective_capping(h, d) for d in days]})
    return {"from": start, "to": end, "dates": days, "rows": rows}


def _cell_text(text: str) -> str:
    """A store name that starts like a formula would run as one when the file is opened in Excel."""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def sheet_file(db: Session, user: User, perms: set[str], start: date | None, end: date | None, store_id: uuid.UUID | None, fmt: str) -> tuple[bytes, str]:
    """(file bytes, file name) of the same matrix: header Store, then dd-MMM per date."""
    data = sheet(db, user, perms, start, end, store_id)
    header = ["Store"] + [f"{d:%d-%b}" for d in data["dates"]]
    body = [[_cell_text(r["outlet_name"])] + ["" if c is None else c for c in r["cells"]] for r in data["rows"]]
    name = f"zepto-capping-sheet_{data['from']:%Y-%m-%d}_to_{data['to']:%Y-%m-%d}.{fmt}"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(body)
        return ("﻿" + buf.getvalue()).encode("utf-8"), name      # BOM: Excel reads it as UTF-8
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Capping sheet"
    ws.append(header)
    for r in body:
        ws.append(r)
    for c in ws[1]:
        c.font = Font(name="Calibri", size=11, bold=True)
        c.alignment = Alignment(horizontal="center", vertical="top")
    ws.column_dimensions["A"].width = 34
    for i in range(2, len(header) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 8
    ws.freeze_panes = "B2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), name


# ---------------------------------------------------------------- the average-vs-limit summary

def summary(db: Session, user: User, perms: set[str], start: date | None, end: date | None) -> dict:
    """Per live Zepto store, over the period: the average entry, the average capping, the highest day, the capping in force today and the days above the
    limit, with whether (and why) the store is in alert. Four queries however many stores: the stores, the per-store totals, the days above the limit
    and the capping history."""
    capping_service.require_eligible(user, perms)
    start, end = _period(start, end)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    limit = max_daily_limit()
    today = today_ist()
    stores = _stores(db, user, partner.id, None)
    ids = [s[0] for s in stores]
    in_period = (OrderEntry.order_date >= start, OrderEntry.order_date <= end, OrderEntry.store_id.in_(ids or [uuid.uuid4()]))
    totals = {
        sid: (int(total), int(n), int(top))
        for sid, total, n, top in db.execute(
            select(OrderEntry.store_id, func.sum(OrderEntry.bottle_count), func.count(OrderEntry.id), func.max(OrderEntry.bottle_count)).where(*in_period).group_by(OrderEntry.store_id)
        )
    }
    breaches: dict[uuid.UUID, list[tuple[date, int]]] = defaultdict(list)
    for sid, day, value in db.execute(
        select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count).where(*in_period, OrderEntry.bottle_count > limit).order_by(OrderEntry.order_date)
    ):
        breaches[sid].append((day, int(value)))
    capping_end = min(end, today)               # no capping average for days that have not happened yet
    hist = _history_by_store(db, ids, today)

    rows = []
    for sid, code, name, state, city, legacy in stores:
        total, n, top = totals.get(sid, (0, 0, None))
        cap_total, cap_days = capping_totals(hist.get(sid, []), start, capping_end)
        a = assess(total, n, breaches.get(sid, []), limit, cap_total, cap_days)
        current = effective_capping(hist.get(sid, []), today)
        rows.append({
            "store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city,
            "average": round(total / n, 2) if n else None, "entry_days": n, "total": total, "max_day": top,
            "capping_average": round(cap_total / cap_days, 2) if cap_days else None, "capping_days": cap_days,
            "current_capping": current if current is not None else legacy,        # store_caps still answers for a 0 / a cap the history cannot hold
            "breach_days": [{"date": d, "value": v} for d, v in breaches.get(sid, [])],
            **a,
        })
    rows.sort(key=lambda r: (not r["alert"], -(r["average"] if r["average"] is not None else -1.0), r["outlet_name"].lower()))
    return {
        "from": start, "to": end, "today": today, "limit": limit, "amber_margin": AMBER_MARGIN,
        "totals": {"stores": len(rows), "in_alert": sum(1 for r in rows if r["alert"])},
        "rows": rows,
    }
