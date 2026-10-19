"""
Zepto capping: how many bottles each store may take, and how close it is.

Who may use it (always re-checked on the server, whatever the app shows):
  * every ACTIVE employee whose platform is Zepto, whatever their state or region, and
  * administrators (they hold orders.correct), so the Capping page works for them too.
  Blinkit employees and partner logins are refused. Viewing and editing a store's cap are the same right.

The capping sheet gives ONE DAILY number per store (store_caps.daily_cap). The monthly limit a store must not exceed is that
number x 30 (always 30, whatever the month's length). No row = no cap; 0 is a real cap. Usage is the sum of the month's
order entries for the store, whoever entered them, so every employee sees the same figures. Alert levels:
  OVER   usage > monthly limit (daily x 30)
  AHEAD  usage is ahead of the pace: more than daily x day of the month (day 31 counts as 30) - current month only, not yet over
  NEAR   usage >= 80% of the monthly limit (and not over / ahead)        OK  below that        NO_CAP  no cap set
Example: sheet says 10 -> limit 300; on the 15th up to 150 is on pace, 160 marked gives an AHEAD alert.
Nothing limits a single day's entry: the only limit is the sheet's cap (or the one set by hand).

Who loads caps in bulk: developers and administrators (an uploaded sheet). Employees only change one store at a time.
Who is alerted: people holding capping.alerts - see alerts() - for the stores they cover.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.order_entry import OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store, StoreStatus
from app.models.store_cap import StoreCap
from app.models.user import User
from app.services import activity_service, assignment_service

PLATFORM = "zepto"
WARN_PERCENT = 80
CAP_DAYS = 30            # the monthly limit is the daily cap x 30, in every month
MAX_CAP = 1_000_000      # the largest daily cap accepted
_ORDER = {"OVER": 0, "AHEAD": 1, "NEAR": 2, "OK": 3, "NO_CAP": 4}
_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def is_eligible(user: User, perms: set[str]) -> bool:
    """Active Zepto employee, or an administrator. Never a Blinkit employee or a partner login."""
    if not user.is_active:
        return False
    if "orders.correct" in perms:   # administrators (same rule the rest of the order screens use)
        return True
    slug = user.platform_organization.slug if user.platform_organization is not None else None
    return (slug or "").strip().lower() == PLATFORM


def require_eligible(user: User, perms: set[str]) -> None:
    if not is_eligible(user, perms):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Capping is available to Zepto employees.")


def parse_month(value: str | None) -> date:
    """First day of the month. Default: this month. Future months are refused (there is nothing to report yet) and so is
    anything before the data starts."""
    today = _today()
    if not value:
        return date(today.year, today.month, 1)
    try:
        y, m = (int(x) for x in value.split("-"))
        d = date(y, m, 1)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-10.") from None
    if d > date(today.year, today.month, 1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That month has not started yet.")
    if d < date(2024, 1, 1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That month is too far back.")
    return d


def available_months(today: date | None = None) -> list[str]:
    today = today or _today()
    out, y, m = [], today.year, today.month
    for _ in range(12):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def monthly_limit(daily: int | None) -> int | None:
    """The most a store may take in a month: its daily cap x 30."""
    return None if daily is None else daily * CAP_DAYS


def alert_for(used: int, daily: int | None, day: int | None = None) -> str:
    """OVER / AHEAD / NEAR / OK / NO_CAP from the bottles used and the store's DAILY cap. Cap 0 is valid: zero used is OK,
    any use is OVER (no division). Pass `day` (the day of the month in progress) to also get AHEAD (used more than daily x day)."""
    if daily is None:
        return "NO_CAP"
    limit = daily * CAP_DAYS
    if used > limit:
        return "OVER"
    if limit == 0:
        return "OK"
    if day is not None and used > daily * min(day, CAP_DAYS):
        return "AHEAD"
    return "NEAR" if used * 100 >= WARN_PERCENT * limit else "OK"


def pace_for(daily: int | None, month: date, today: date) -> tuple[int | None, int | None]:
    """(day, bottles allowed so far) for the month in progress; (None, None) for a finished month or a store with no cap."""
    if daily is None or (month.year, month.month) != (today.year, today.month):
        return None, None
    return today.day, daily * min(today.day, CAP_DAYS)


def _partner(db: Session, org_id: uuid.UUID) -> Organization:
    p = db.execute(select(Organization).where(Organization.slug == PLATFORM, Organization.kind == OrganizationKind.PARTNER.value)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zepto is not set up in the CRM.")
    return p


def _owners(db: Session, org_id: uuid.UUID, partner: Organization) -> dict[uuid.UUID, tuple[str, str]]:
    """{store_id: (employee code, employee name)}: the first Zepto employee (by name) whose states include the store.
    Same bulk lookup the dashboard uses: a few queries however many employees there are."""
    from app.repositories.employee_repository import EmployeeRepository

    employees = EmployeeRepository(db).all_for_platform(org_id, partner.id)
    scopes, _ = assignment_service.employee_store_scopes(db, partner, employees)
    out: dict[uuid.UUID, tuple[str, str]] = {}
    for emp in sorted(employees, key=lambda e: e.full_name.lower()):
        for sid in scopes.get(emp.id, []):
            out.setdefault(sid, (emp.employee_code, emp.full_name))
    return out


def _rows(db: Session, user: User, partner: Organization, month: date, store_ids: set[uuid.UUID] | None = None) -> list[dict]:
    """One row per live Zepto store (or only `store_ids`) with the month's usage and alert, worst first."""
    today = _today()
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    q = (
        select(Store.id, Store.external_code, Store.name, Store.state, Store.city, StoreCap.daily_cap)
        .select_from(Store)
        .outerjoin(StoreCap, StoreCap.store_id == Store.id)
        .where(Store.organization_id == user.organization_id, Store.partner_organization_id == partner.id, Store.status == StoreStatus.LIVE.value)
    )
    if store_ids is not None:
        q = q.where(Store.id.in_(store_ids or {uuid.uuid4()}))
    stores = db.execute(q).all()
    usage = {
        r[0]: (int(r[1]), int(r[2]))
        for r in db.execute(
            select(OrderEntry.store_id, func.coalesce(func.sum(OrderEntry.bottle_count), 0), func.count(OrderEntry.id))
            .where(OrderEntry.order_date >= month, OrderEntry.order_date <= end, OrderEntry.store_id.in_([s[0] for s in stores] or [uuid.uuid4()]))
            .group_by(OrderEntry.store_id)
        )
    }
    owners = _owners(db, user.organization_id, partner)

    rows = []
    for sid, code, name, state, city, daily in stores:
        used, entries = usage.get(sid, (0, 0))
        day, allowed = pace_for(daily, month, today)
        level = alert_for(used, daily, day)
        cap = monthly_limit(daily)          # everything below is measured against the monthly limit (daily x 30)
        owner = owners.get(sid)
        rows.append({
            "store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city,
            "owner_code": owner[0] if owner else None, "owner_name": owner[1] if owner else None,
            "daily_cap": daily, "monthly_cap": cap, "used": used, "entries": entries,
            "remaining": None if cap is None else max(cap - used, 0),
            "excess": 0 if cap is None else max(used - cap, 0),
            "percent": None if not cap else round(used * 100 / cap, 1),   # cap 0 or none: no percentage
            "allowed_to_date": allowed,                                     # None for a finished month / no cap
            "ahead_by": None if allowed is None else max(used - allowed, 0),
            "alert": level,
        })
    rows.sort(key=lambda r: (_ORDER[r["alert"]], -(r["percent"] if r["percent"] is not None else (10_000 if r["alert"] == "OVER" else -1)), r["outlet_name"].lower()))
    return rows


def _summary(rows: list[dict]) -> dict:
    counts = {k: sum(1 for r in rows if r["alert"] == k) for k in _ORDER}
    return {"over": counts["OVER"], "ahead": counts["AHEAD"], "near": counts["NEAR"], "ok": counts["OK"], "no_cap": counts["NO_CAP"], "total": len(rows)}


def report(db: Session, user: User, perms: set[str], month_str: str | None) -> dict:
    require_eligible(user, perms)
    month = parse_month(month_str)
    partner = _partner(db, user.organization_id)
    rows = _rows(db, user, partner, month)
    return {
        "success": True,
        "month": f"{month:%Y-%m}", "month_label": f"{_MONTHS[month.month]} {month.year}", "months": available_months(),
        "warn_percent": WARN_PERCENT,
        "summary": _summary(rows),
        "rows": rows,
    }


def alerts(db: Session, user: User, perms: set[str]) -> dict:
    """This month's stores that need the employee's attention (OVER or AHEAD), for people holding capping.alerts.
    An administrator sees every Zepto store; a Zepto employee only the stores they cover (their assigned states)."""
    if "capping.alerts" not in perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Capping alerts are not switched on for you.")
    require_eligible(user, perms)
    partner = _partner(db, user.organization_id)
    today = _today()
    month = date(today.year, today.month, 1)
    scope = None if "orders.correct" in perms else assignment_service.visible_store_ids(db, user)
    rows = [r for r in _rows(db, user, partner, month, scope) if r["alert"] in ("OVER", "AHEAD")]
    return {
        "success": True, "month": f"{month:%Y-%m}", "month_label": f"{_MONTHS[month.month]} {month.year}",
        "day": today.day, "days_in_month": CAP_DAYS,
        "over": sum(1 for r in rows if r["alert"] == "OVER"), "ahead": sum(1 for r in rows if r["alert"] == "AHEAD"),
        "rows": rows[:50],
    }


def set_cap(db: Session, user: User, perms: set[str], store_id: uuid.UUID, cap: int | None) -> dict:
    """Set (or clear, with None) one store's DAILY cap (its monthly limit is that x 30). Logged with the old and new value."""
    require_eligible(user, perms)
    partner = _partner(db, user.organization_id)
    store = db.get(Store, store_id)
    if store is None or store.organization_id != user.organization_id or store.partner_organization_id != partner.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    if cap is not None and not (0 <= cap <= MAX_CAP):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The daily cap must be a whole number from 0 to {MAX_CAP:,}.")
    row = db.execute(select(StoreCap).where(StoreCap.store_id == store_id)).scalar_one_or_none()
    before = row.daily_cap if row else None
    if before == cap:
        return {"store_id": store_id, "daily_cap": cap, "monthly_cap": monthly_limit(cap), "changed": False}
    if cap is None and row is not None:
        db.delete(row)
    elif row is None:
        db.add(StoreCap(store_id=store_id, daily_cap=cap, source="manual", updated_by_user_id=user.id))
    else:
        row.daily_cap, row.source, row.updated_by_user_id = cap, "manual", user.id
    activity_service.record(
        db, actor=user, action="store.cap_changed", entity_type="store", entity_id=store_id,
        metadata={"outlet": store.external_code, "name": store.name, "from": before, "to": cap},
    )
    db.commit()
    return {"store_id": store_id, "daily_cap": cap, "monthly_cap": monthly_limit(cap), "changed": True}


# ---------------------------------------------------------------- loading caps from the sheet / a file (developer)

def _cap_value(raw: str) -> tuple[int | None, bool]:
    """(cap, is_invalid). Blank -> (None, False): no cap in that row. Whole numbers only; 0 is valid."""
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None, False
    try:
        f = float(text)
    except ValueError:
        return None, True
    if f != int(f) or not (0 <= f <= MAX_CAP):
        return None, True
    return int(f), False


_ID_KEYS = ("outlet id", "outlet_id", "store id", "store code")
# The sheet's number is a DAILY cap whatever the column is called (older sheets are headed "Monthly Capping"): x 30 = the monthly limit.
_CAP_KEYS = ("daily capping", "daily cap", "capping per day", "monthly capping", "monthly cap", "capping", "cap")


def import_caps(db: Session, actor: User, rows: list[dict[str, str]], *, overwrite: bool, source: str) -> dict:
    """Load caps from sheet rows (Outlet ID + the daily capping number). Existing caps are kept unless `overwrite` is on."""
    partner = _partner(db, actor.organization_id)
    if not rows:
        return {"rows_read": 0, "added": 0, "updated": 0, "kept": 0, "unknown_stores": 0, "invalid": 0, "warnings": ["The sheet has no rows."]}
    keys = {k.strip().lower(): k for k in rows[0]}
    id_col = next((keys[k] for k in _ID_KEYS if k in keys), None)
    cap_col = next((keys[k] for k in _CAP_KEYS if k in keys), None)
    if id_col is None or cap_col is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The sheet needs an 'Outlet ID' column and a 'Capping' column (the daily number per store).")
    stores = {s.external_code: s for s in db.execute(
        select(Store).where(Store.organization_id == actor.organization_id, Store.partner_organization_id == partner.id)).scalars()}
    existing = {c.store_id: c for c in db.execute(select(StoreCap).where(StoreCap.store_id.in_([s.id for s in stores.values()] or [uuid.uuid4()]))).scalars()}
    res = {"rows_read": 0, "added": 0, "updated": 0, "kept": 0, "unknown_stores": 0, "invalid": 0, "warnings": []}
    seen: set[str] = set()
    bad_rows: list[int] = []
    for i, row in enumerate(rows, start=2):
        code = (row.get(id_col) or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        res["rows_read"] += 1
        cap, invalid = _cap_value(row.get(cap_col) or "")
        if invalid:
            res["invalid"] += 1
            bad_rows.append(i)
            continue
        if cap is None:
            continue
        store = stores.get(code)
        if store is None:
            res["unknown_stores"] += 1
            continue
        cur = existing.get(store.id)
        if cur is None:
            row_new = StoreCap(store_id=store.id, daily_cap=cap, source=source, updated_by_user_id=actor.id)
            db.add(row_new)
            existing[store.id] = row_new
            res["added"] += 1
        elif cur.daily_cap == cap:
            res["kept"] += 1
        elif overwrite:
            cur.daily_cap, cur.source, cur.updated_by_user_id = cap, source, actor.id
            res["updated"] += 1
        else:
            res["kept"] += 1
    if bad_rows:
        res["warnings"].append(f"{res['invalid']} row(s) have a cap that is not a whole number from 0 to {MAX_CAP:,} and were skipped (first: row {bad_rows[0]}).")
    if res["unknown_stores"]:
        res["warnings"].append(f"{res['unknown_stores']} Outlet ID(s) are not Zepto stores in the CRM and were skipped.")
    if res["kept"] and not overwrite:
        res["warnings"].append("Caps already set in the CRM were kept (turn on Overwrite to replace them with the sheet's values).")
    activity_service.record(
        db, actor=actor, action="store.caps_imported", entity_type="store", entity_id=partner.id,
        metadata={"source": source, "overwrite": overwrite, "added": res["added"], "updated": res["updated"], "kept": res["kept"]},
    )
    db.commit()
    return res
