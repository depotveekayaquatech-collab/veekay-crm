"""
Zepto monthly capping: how many bottles each store may take in a month, and how close it is.

Who may use it (always re-checked on the server, whatever the app shows):
  * every ACTIVE employee whose platform is Zepto, whatever their state or region, and
  * administrators (they hold orders.correct), so the Capping page works for them too.
  Blinkit employees and partner logins are refused. Viewing and editing a store's cap are the same right.

The cap is one number per store (store_caps). No row = no cap; 0 is a real cap. Usage is the sum of the month's order
entries for the store, whoever entered them, so every employee sees the same figures. Alert levels:
  OVER  usage > cap        NEAR  usage >= 80% of the cap (and not over)        OK  below that        NO_CAP  no cap set
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
MAX_CAP = 1_000_000
_ORDER = {"OVER": 0, "NEAR": 1, "OK": 2, "NO_CAP": 3}
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


def alert_for(used: int, cap: int | None) -> str:
    """OVER / NEAR / OK / NO_CAP. Cap 0 is valid: zero used is OK, any use is OVER (no division)."""
    if cap is None:
        return "NO_CAP"
    if used > cap:
        return "OVER"
    if cap == 0:
        return "OK"
    return "NEAR" if used * 100 >= WARN_PERCENT * cap else "OK"


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


def report(db: Session, user: User, perms: set[str], month_str: str | None) -> dict:
    require_eligible(user, perms)
    month = parse_month(month_str)
    partner = _partner(db, user.organization_id)
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])

    stores = db.execute(
        select(Store.id, Store.external_code, Store.name, Store.state, Store.city, StoreCap.monthly_cap)
        .select_from(Store)
        .outerjoin(StoreCap, StoreCap.store_id == Store.id)
        .where(Store.organization_id == user.organization_id, Store.partner_organization_id == partner.id, Store.status == StoreStatus.LIVE.value)
    ).all()
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
    for sid, code, name, state, city, cap in stores:
        used, entries = usage.get(sid, (0, 0))
        level = alert_for(used, cap)
        owner = owners.get(sid)
        rows.append({
            "store_id": sid, "outlet_id": code, "outlet_name": name, "state": state, "city": city,
            "owner_code": owner[0] if owner else None, "owner_name": owner[1] if owner else None,
            "monthly_cap": cap, "used": used, "entries": entries,
            "remaining": None if cap is None else max(cap - used, 0),
            "excess": 0 if cap is None else max(used - cap, 0),
            "percent": None if not cap else round(used * 100 / cap, 1),   # cap 0 or none: no percentage
            "alert": level,
        })
    rows.sort(key=lambda r: (_ORDER[r["alert"]], -(r["percent"] if r["percent"] is not None else (10_000 if r["alert"] == "OVER" else -1)), r["outlet_name"].lower()))
    counts = {k: sum(1 for r in rows if r["alert"] == k) for k in _ORDER}
    return {
        "success": True,
        "month": f"{month:%Y-%m}", "month_label": f"{_MONTHS[month.month]} {month.year}", "months": available_months(),
        "warn_percent": WARN_PERCENT,
        "summary": {"over": counts["OVER"], "near": counts["NEAR"], "ok": counts["OK"], "no_cap": counts["NO_CAP"], "total": len(rows)},
        "rows": rows,
    }


def set_cap(db: Session, user: User, perms: set[str], store_id: uuid.UUID, cap: int | None) -> dict:
    """Set (or clear, with None) one store's monthly cap. Logged with the old and new value."""
    require_eligible(user, perms)
    partner = _partner(db, user.organization_id)
    store = db.get(Store, store_id)
    if store is None or store.organization_id != user.organization_id or store.partner_organization_id != partner.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    if cap is not None and not (0 <= cap <= MAX_CAP):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The cap must be a whole number from 0 to {MAX_CAP:,}.")
    row = db.execute(select(StoreCap).where(StoreCap.store_id == store_id)).scalar_one_or_none()
    before = row.monthly_cap if row else None
    if before == cap:
        return {"store_id": store_id, "monthly_cap": cap, "changed": False}
    if cap is None and row is not None:
        db.delete(row)
    elif row is None:
        db.add(StoreCap(store_id=store_id, monthly_cap=cap, source="manual", updated_by_user_id=user.id))
    else:
        row.monthly_cap, row.source, row.updated_by_user_id = cap, "manual", user.id
    activity_service.record(
        db, actor=user, action="store.cap_changed", entity_type="store", entity_id=store_id,
        metadata={"outlet": store.external_code, "name": store.name, "from": before, "to": cap},
    )
    db.commit()
    return {"store_id": store_id, "monthly_cap": cap, "changed": True}


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
_CAP_KEYS = ("monthly capping", "monthly cap", "capping", "cap")


def import_caps(db: Session, actor: User, rows: list[dict[str, str]], *, overwrite: bool, source: str) -> dict:
    """Load caps from sheet rows (Outlet ID + Monthly Capping). Existing caps are kept unless `overwrite` is on."""
    partner = _partner(db, actor.organization_id)
    if not rows:
        return {"rows_read": 0, "added": 0, "updated": 0, "kept": 0, "unknown_stores": 0, "invalid": 0, "warnings": ["The sheet has no rows."]}
    keys = {k.strip().lower(): k for k in rows[0]}
    id_col = next((keys[k] for k in _ID_KEYS if k in keys), None)
    cap_col = next((keys[k] for k in _CAP_KEYS if k in keys), None)
    if id_col is None or cap_col is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The sheet needs an 'Outlet ID' column and a 'Monthly Capping' column.")
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
            row_new = StoreCap(store_id=store.id, monthly_cap=cap, source=source, updated_by_user_id=actor.id)
            db.add(row_new)
            existing[store.id] = row_new
            res["added"] += 1
        elif cur.monthly_cap == cap:
            res["kept"] += 1
        elif overwrite:
            cur.monthly_cap, cur.source, cur.updated_by_user_id = cap, source, actor.id
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
