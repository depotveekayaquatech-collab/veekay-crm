"""
Zepto capping: how many bottles each store may take per day, and how close it is. The capping itself (its history, setting and removing it, the collective
"Reduce capping" alert) is capping_history_service; this module decides WHO may use it and builds the monthly USAGE report and the employee alerts.

Who may use it (always re-checked on the server, whatever the app shows):
  * every ACTIVE employee whose platform is Zepto, whatever their state or region,
  * the Zepto partner login (the platform's own account), and
  * administrators (they hold orders.correct and belong to no platform), so the Capping page works for them too.
  Blinkit employees and Blinkit partner logins (whatever else they hold) are refused. Changing a capping needs capping.change on top.

A store's capping is ONE DAILY number (store_caps.daily_cap, the capping in force today). The monthly limit a store must not exceed is that number x 30 (always 30,
whatever the month's length). No capping = no limit; 0 is a real capping. Usage is the sum of the month's order entries for the store, EVERY entry whoever entered
it (an employee, a Team Lead, an admin, a sheet), so everyone sees the same figures. Alert levels:
  OVER   usage > monthly limit (daily x 30)
  AHEAD  usage is ahead of the pace: more than daily x day of the month (day 31 counts as 30) - current month only, not yet over
  NEAR   usage >= 80% of the monthly limit (and not over / ahead)        OK  below that        NO_CAP  no capping set
Example: capping 10 -> limit 300; on the 15th up to 150 is on pace, 160 marked gives an AHEAD alert.

Who is alerted: people holding capping.alerts (and the platform's own login) - see alerts() - for the stores they cover.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order_entry import OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store, StoreStatus
from app.models.store_cap import StoreCap
from app.models.user import User
from app.services import assignment_service

PLATFORM = "zepto"
WARN_PERCENT = 80
CAP_DAYS = 30            # the monthly limit is the daily capping x 30, in every month
MAX_CAP = 1_000_000      # the largest daily capping accepted
_ORDER = {"OVER": 0, "AHEAD": 1, "NEAR": 2, "OK": 3, "NO_CAP": 4}
_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_IST = ZoneInfo("Asia/Kolkata")


def _today() -> date:
    return datetime.now(_IST).date()


def is_eligible(user: User, perms: set[str]) -> bool:
    """Active Zepto employee or partner login, or an administrator. Never anyone on another platform."""
    if not user.is_active:
        return False
    slug = ((user.platform_organization.slug if user.platform_organization is not None else None) or "").strip().lower()
    if slug == PLATFORM:
        return True
    # Administrators (they hold orders.correct and belong to no platform). Someone who works on another platform (a Blinkit Team Lead, say) never sees Zepto
    # capping, even if "correct any entry" was ticked for them.
    return "orders.correct" in perms and not slug


def require_eligible(user: User, perms: set[str]) -> None:
    if not is_eligible(user, perms):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Capping is available to Zepto employees.")


def parse_month(value: str | None) -> date:
    """First day of the month. Default: this month. Future months are refused (there is nothing to report yet) and so is anything before the data starts."""
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
    """The most a store may take in a month: its daily capping x 30."""
    return None if daily is None else daily * CAP_DAYS


def alert_for(used: int, daily: int | None, day: int | None = None) -> str:
    """OVER / AHEAD / NEAR / OK / NO_CAP from the bottles used and the store's DAILY capping. A capping of 0 is valid: zero used is OK, any use is OVER (no
    division). Pass `day` (the day of the month in progress) to also get AHEAD (used more than daily x day)."""
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
    """(day, bottles allowed so far) for the month in progress; (None, None) for a finished month or a store with no capping."""
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
    """One row per live Zepto store (or only `store_ids`) with the month's usage and alert, worst first. Usage counts EVERY entry of the month for the store."""
    today = _today()
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    q = (
        select(Store.id, Store.external_code, Store.name, Store.state, Store.city, StoreCap.daily_cap, Store.vendor_name)
        .select_from(Store)
        .outerjoin(StoreCap, StoreCap.store_id == Store.id)
        .where(Store.organization_id == user.organization_id, Store.partner_organization_id == partner.id, Store.status == StoreStatus.LIVE.value)
    )
    if store_ids is not None:
        q = q.where(Store.id.in_(store_ids or {uuid.uuid4()}))
    stores = db.execute(q).all()
    usage = {
        r[0]: (int(r[1]), int(r[2]), int(r[3]), r[4])
        for r in db.execute(
            select(OrderEntry.store_id, func.coalesce(func.sum(OrderEntry.bottle_count), 0), func.count(OrderEntry.id), func.coalesce(func.max(OrderEntry.bottle_count), 0),
                   func.max(OrderEntry.order_date))
            .where(OrderEntry.order_date >= month, OrderEntry.order_date <= end, OrderEntry.store_id.in_([s[0] for s in stores] or [uuid.uuid4()]))
            .group_by(OrderEntry.store_id)
        )
    }
    owners = _owners(db, user.organization_id, partner)

    rows = []
    for sid, code, name, state, city, daily, vendor in stores:
        used, entries, highest, last = usage.get(sid, (0, 0, 0, None))
        day, allowed = pace_for(daily, month, today)
        level = alert_for(used, daily, day)
        cap = monthly_limit(daily)          # everything below is measured against the monthly limit (daily x 30)
        owner = owners.get(sid)
        rows.append({
            "store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city, "vendor_name": " ".join(vendor.split()) if vendor else None,
            "owner_code": owner[0] if owner else None, "owner_name": owner[1] if owner else None,
            "daily_cap": daily, "monthly_cap": cap, "used": used, "entries": entries, "highest_day": highest, "last_entry": last,
            "remaining": None if cap is None else max(cap - used, 0),
            "excess": 0 if cap is None else max(used - cap, 0),
            "percent": None if not cap else round(used * 100 / cap, 1),   # capping 0 or none: no percentage
            "allowed_to_date": allowed,                                     # None for a finished month / no capping
            "ahead_by": None if allowed is None else max(used - allowed, 0),
            "alert": level,
        })
    rows.sort(key=lambda r: (_ORDER[r["alert"]], -(r["percent"] if r["percent"] is not None else (10_000 if r["alert"] == "OVER" else -1)), r["outlet_name"].lower()))
    return rows


def _summary(rows: list[dict]) -> dict:
    counts = {k: sum(1 for r in rows if r["alert"] == k) for k in _ORDER}
    return {
        "over": counts["OVER"], "ahead": counts["AHEAD"], "near": counts["NEAR"], "ok": counts["OK"], "no_cap": counts["NO_CAP"], "total": len(rows),
        "entries": sum(r["entries"] for r in rows), "bottles": sum(r["used"] for r in rows),
    }


def report(db: Session, user: User, perms: set[str], month_str: str | None) -> dict:
    """The monthly usage of every live Zepto store against its limit: store, daily capping, monthly limit, bottles used so far, what is left, the percentage and
    the alert level, with the counts of each level."""
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
    """This month's stores that need the employee's attention (OVER or AHEAD), for people holding capping.alerts and the platform's own login.
    An administrator sees every Zepto store; a Zepto employee only the stores they cover (their assigned states)."""
    if "capping.alerts" not in perms and not assignment_service.is_partner_account(db, user):
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
