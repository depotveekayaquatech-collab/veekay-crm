"""
Capping history: a store's daily capping with the date each value took effect, the capping sheet, and the average-vs-limit alert.

The capping of a store on day D is the capping of the row with the greatest effective_from <= D (10 from the 1st and 11 from the 15th give 10 on
days 1-14 and 11 from day 15). Rows are only ever added through the API (no edit, no delete). store_caps stays the "current capping": the capping
effective today, refreshed in the same transaction as every change. Dates are Asia/Kolkata days.

A store's capping can also be marked 0 for specific days (capping_zero_days): that day is 0 on the sheet and counts as 0 in the capping average, the days
either side keep their capping. These are per-day marks, kept apart from the timeline above; store_caps is not touched by them.

Who may do what (re-checked on the server, whatever the app shows):
  * see the history, the sheet and the summary: whoever may see Zepto capping (capping_service.is_eligible).
  * change a capping: holders of capping.change (administrators; a "manager" when it is ticked for them) who are not on another platform.

The alert is separate from the monthly-limit levels in capping_service. Two COLLECTIVE averages, across all live Zepto stores together, must stay at or
under settings.MAX_DAILY_LIMIT: the average daily ENTRY (all bottles / all store-days that have an entry; a zero is a real entry, a day with no row is not
counted) and the average CAPPING (all capping / all store-days, up to today, on which a capping was in force). The alert (`overall`) is raised when either
collective average is above the limit; exactly the limit is fine. Every store still gets its own averages and colour for reference, but a single store
above the limit does not raise the alert. Averages are shown to two decimals; the comparison itself uses the exact figures.
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
from app.models.capping_history import CappingHistory, CappingZeroDay
from app.models.order_entry import OrderEntry
from app.models.store import Store, StoreStatus
from app.models.store_cap import StoreCap
from app.models.user import User
from app.services import activity_service, capping_service

IST = ZoneInfo("Asia/Kolkata")
EARLIEST = date(2024, 1, 1)         # same floor as capping_service.parse_month
MAX_ZERO_DAYS = 62                 # days that can be marked in one request
ZERO_DAYS_AHEAD = 60                # a day can be marked up to this far ahead
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


def with_zero_days(total: int, days: int, history: Sequence[tuple[date, int]], zero_days: Sequence[date], start: date, end: date) -> tuple[int, int]:
    """capping_totals() with the marked zero days applied: a marked day inside start..end counts as 0 (taking away the capping that was in force that
    day, or adding the day when none was)."""
    for z in set(zero_days):
        if start <= z <= end:
            current = effective_capping(history, z)
            if current is None:
                days += 1
            else:
                total -= current
    return total, days


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


def _zero_days_by_store(db: Session, store_ids: list[uuid.UUID], start: date, end: date) -> dict[uuid.UUID, set[date]]:
    """One query: the marked zero days of these stores within start..end."""
    out: dict[uuid.UUID, set[date]] = defaultdict(set)
    if not store_ids:
        return out
    for sid, day in db.execute(
        select(CappingZeroDay.store_id, CappingZeroDay.day).where(CappingZeroDay.store_id.in_(store_ids), CappingZeroDay.day >= start, CappingZeroDay.day <= end)
    ):
        out[sid].add(day)
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
    zero = db.execute(
        select(CappingZeroDay, User.full_name, User.employee_code)
        .outerjoin(User, User.id == CappingZeroDay.created_by)
        .where(CappingZeroDay.store_id == store_id)
        .order_by(CappingZeroDay.day.desc())
    ).all()
    return {
        "store_id": store_id, "outlet_id": store.external_code, "outlet_name": store.name, "today": today_ist(),
        "rows": [
            {"id": h.id, "capping": h.capping, "effective_from": h.effective_from, "changed_by": name, "changed_by_code": code, "created_at": h.created_at}
            for h, name, code in rows
        ],
        "zero_days": [{"id": z.id, "day": z.day, "changed_by": name, "changed_by_code": code, "created_at": z.created_at} for z, name, code in zero],
    }

def mark_zero_days(db: Session, user: User, perms: set[str], store_id: uuid.UUID, days: Sequence[date]) -> dict:
    """Mark a store's capping as 0 on these days. A day already marked is reported, not an error. Past days, today and up to ZERO_DAYS_AHEAD days ahead."""
    _require_change(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    store = _store(db, user, partner.id, store_id)
    wanted = sorted(set(days))
    if not wanted:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one day.")
    if len(wanted) > MAX_ZERO_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Mark at most {MAX_ZERO_DAYS} days at a time.")
    today = today_ist()
    if wanted[0] < EARLIEST or wanted[-1] > today + timedelta(days=ZERO_DAYS_AHEAD):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Choose days from {EARLIEST:%d-%b-%Y} to {ZERO_DAYS_AHEAD} days from today.")
    have = set(db.execute(select(CappingZeroDay.day).where(CappingZeroDay.store_id == store_id, CappingZeroDay.day.in_(wanted))).scalars())
    new = [d for d in wanted if d not in have]
    for d in new:
        db.add(CappingZeroDay(store_id=store_id, day=d, created_by=user.id))
    try:
        db.flush()
    except IntegrityError:                  # the same day marked by someone else at the same moment: it is marked either way
        db.rollback()
        return {"store_id": store_id, "marked": [], "already": wanted}
    if new:
        activity_service.record(
            db, actor=user, action="store.capping_zero_marked", entity_type="store", entity_id=store_id,
            metadata={"outlet": store.external_code, "name": store.name, "days": [d.isoformat() for d in new]},
        )
    db.commit()
    return {"store_id": store_id, "marked": new, "already": sorted(have)}


def unmark_zero_day(db: Session, user: User, perms: set[str], store_id: uuid.UUID, day: date) -> dict:
    """Take a marked day back to the capping the timeline gives it (for a mark made by mistake). Recorded in the activity log."""
    _require_change(user, perms)
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    store = _store(db, user, partner.id, store_id)
    row = db.execute(select(CappingZeroDay).where(CappingZeroDay.store_id == store_id, CappingZeroDay.day == day)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That day is not marked as zero capping.")
    db.delete(row)
    activity_service.record(
        db, actor=user, action="store.capping_zero_unmarked", entity_type="store", entity_id=store_id,
        metadata={"outlet": store.external_code, "name": store.name, "day": day.isoformat()},
    )
    db.commit()
    return {"store_id": store_id, "removed": day}


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
    zero = _zero_days_by_store(db, [s[0] for s in stores], start, end)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    rows = []
    for sid, code, name, state, city, _ in stores:
        h, z = hist.get(sid, []), zero.get(sid, set())
        rows.append({"store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city, "cells": [0 if d in z else effective_capping(h, d) for d in days]})
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


# ---------------------------------------------------------------- stores with no capping, and the one-page print

DEFAULT_CAPPING = 10


def set_unset_default(
    db: Session, user: User, perms: set[str], capping: int = DEFAULT_CAPPING, *, dry_run: bool = True, effective_from: date | None = None,
) -> dict:
    """Give every live Zepto store that has NO capping at all (no history in force today and nothing in store_caps) `capping`, from `effective_from`
    (the 1st of this month unless chosen; never in the future). A store that already has a capping, including a 0, is never touched. Each store gets an
    ordinary history row naming the person, so it shows in the store's history like any other change. `dry_run` only counts."""
    _require_change(user, perms)
    if not 1 <= capping <= capping_service.MAX_CAP:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The capping must be a whole number from 1 to {capping_service.MAX_CAP:,}.")
    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    today = today_ist()
    effective_from = effective_from or date(today.year, today.month, 1)
    if effective_from > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The effective date cannot be in the future. Use today or an earlier date.")
    if effective_from < EARLIEST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That date is too far back.")
    stores = _stores(db, user, partner.id, None)
    hist = _history_by_store(db, [s[0] for s in stores], today)
    unset = [s for s in stores if effective_capping(hist.get(s[0], []), today) is None and s[5] is None]
    out = {"unset": len(unset), "applied": 0, "capping": capping, "effective_from": effective_from, "dry_run": dry_run, "examples": [f"{s[2]} ({s[1]})" for s in unset[:5]]}
    if dry_run or not unset:
        return out
    for sid, _code, _name, *_ in unset:
        db.add(CappingHistory(store_id=sid, capping=capping, effective_from=effective_from, created_by=user.id))
        db.flush()
        _sync_current(db, sid, user.id, today)
    activity_service.record(
        db, actor=user, action="capping.defaults_applied", entity_type="store", entity_id=user.organization_id,
        metadata={"capping": capping, "effective_from": effective_from.isoformat(), "stores": len(unset), "examples": out["examples"]},
    )
    db.commit()
    out["applied"] = len(unset)
    return out


def _print_layout(names: list[str], values: list[str], width: float, height: float, margin: float, top: float, font: str):
    """(font size, columns, rows per column) of the largest type at which every store fits on ONE page, or None when even the smallest does not."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    avail_w, avail_h = width - 2 * margin, height - margin - top
    widest_value = max((stringWidth(v, font, 10) for v in values), default=0)
    widths = sorted(stringWidth(n, font, 10) for n in names)
    typical = widths[int(len(widths) * 0.9)] if widths else 0          # the 90th-percentile name: the rare very long one is shortened, it does not widen every column
    for size in [x / 2 for x in range(24, 8, -1)]:                     # 12 pt down to 4.5 pt
        rows = int(avail_h // (size * 1.2))
        if rows < 1:
            continue
        cols = -(-len(names) // rows)
        need = (typical + widest_value) * size / 10 + size * 2.5
        if need <= avail_w / cols:
            return size, cols, rows
    return None


def print_file(db: Session, user: User, perms: set[str]) -> tuple[bytes, str]:
    """A PDF of every live Zepto store and the capping in force TODAY (per day), on one landscape A4 page: the type is made as large as still lets all of them
    fit (long names are shortened to their column). A store with no capping prints "-"; a day marked 0 prints 0. If there are too many for one page even at the
    smallest readable type, it continues on more pages."""
    capping_service.require_eligible(user, perms)
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    today = today_ist()
    stores = _stores(db, user, partner.id, None)
    ids = [s[0] for s in stores]
    hist = _history_by_store(db, ids, today)
    zero = _zero_days_by_store(db, ids, today, today)
    rows: list[tuple[str, str]] = []
    for sid, code, name, _state, _city, legacy in stores:
        cap = 0 if today in zero.get(sid, ()) else effective_capping(hist.get(sid, []), today)
        cap = legacy if cap is None else cap                      # a legacy store_caps value (a 0 or a cap the history cannot hold) still answers
        rows.append((" ".join((name or code or "").split()), "-" if cap is None else f"{cap:,}"))

    width, height = landscape(A4)
    margin, top, font, bold = 22.0, 58.0, "Helvetica", "Helvetica-Bold"
    fit = _print_layout([r[0] for r in rows], [r[1] for r in rows], width, height, margin, top, font)
    size, cols = (fit[0], fit[1]) if fit else (5.5, 7)
    row_h = size * 1.2
    per_col = max(1, int((height - margin - top) // row_h))
    col_w = (width - 2 * margin) / cols
    per_page = per_col * cols
    pages = max(1, -(-len(rows) // per_page))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setTitle(f"{partner.name} store capping, {today:%d %b %Y}")
    for page in range(pages):
        c.setFont(bold, 13)
        c.drawString(margin, height - 26, f"{partner.name}: store capping per day")
        c.setFont(font, 8)
        c.drawString(margin, height - 40, f"As on {today:%d %b %Y}. {len(rows):,} live stores. Capping = bottles allowed per day; - means no capping is set."
                     + (f" Page {page + 1} of {pages}." if pages > 1 else ""))
        c.setLineWidth(0.4)
        c.line(margin, height - 46, width - margin, height - 46)
        for i, (name, value) in enumerate(rows[page * per_page:(page + 1) * per_page]):
            col, row = divmod(i, per_col)
            x, y = margin + col * col_w, height - top - row * row_h
            room = col_w - 10 - stringWidth(value, bold, size) - size
            label = name
            while label and stringWidth(label, font, size) > room:
                label = label[:-1]
            c.setFont(font, size)
            c.drawString(x, y, label.rstrip())
            c.setFont(bold, size)
            c.drawRightString(x + col_w - 10, y, value)
        c.showPage()
    c.save()
    return buf.getvalue(), f"zepto-store-capping_{today:%Y-%m-%d}.pdf"


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
    zero = _zero_days_by_store(db, ids, start, capping_end)

    rows = []
    for sid, code, name, state, city, legacy in stores:
        total, n, top = totals.get(sid, (0, 0, None))
        cap_total, cap_days = capping_totals(hist.get(sid, []), start, capping_end)
        cap_total, cap_days = with_zero_days(cap_total, cap_days, hist.get(sid, []), zero.get(sid, ()), start, capping_end)
        a = assess(total, n, breaches.get(sid, []), limit, cap_total, cap_days)
        current = effective_capping(hist.get(sid, []), today)
        rows.append({
            "store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city,
            "average": round(total / n, 2) if n else None, "entry_days": n, "total": total, "max_day": top,
            "capping_average": round(cap_total / cap_days, 2) if cap_days else None, "capping_days": cap_days, "capping_zero_days": len(zero.get(sid, ())), "_cap_total": cap_total,
            "current_capping": current if current is not None else legacy,        # store_caps still answers for a 0 / a cap the history cannot hold
            "breach_days": [{"date": d, "value": v} for d, v in breaches.get(sid, [])],
            **a,
        })
    # the collective figures the alert is based on: every store's bottles / entry days, and every store's capping / capping days
    entry_total, entry_days = sum(r["total"] for r in rows), sum(r["entry_days"] for r in rows)
    cap_all, cap_days_all = sum(r["_cap_total"] for r in rows), sum(r["capping_days"] for r in rows)
    verdict = assess(entry_total, entry_days, [], limit, cap_all, cap_days_all)
    overall = {
        "entry_average": round(entry_total / entry_days, 2) if entry_days else None, "entry_days": entry_days, "total": entry_total,
        "capping_average": round(cap_all / cap_days_all, 2) if cap_days_all else None, "capping_days": cap_days_all,
        "entry_breach": verdict["average_breach"], "capping_breach": verdict["capping_breach"],
        "alert": verdict["alert"], "reasons": verdict["reasons"], "status": verdict["status"],
    }
    for r in rows:
        del r["_cap_total"]
    rows.sort(key=lambda r: (not r["alert"], -(r["average"] if r["average"] is not None else -1.0), r["outlet_name"].lower()))
    return {
        "from": start, "to": end, "today": today, "limit": limit, "amber_margin": AMBER_MARGIN,
        "totals": {"stores": len(rows), "in_alert": sum(1 for r in rows if r["alert"])},
        "overall": overall,
        "rows": rows,
    }
