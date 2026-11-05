"""
Smart Capping Planner - loads the store capacities for a month and runs capping_planner_engine over them. READ-ONLY: it reads stores, cappings and the month's
entries and writes nothing, so no supply record can change because of it.

Source of every figure (so it can be audited):
  monthly limit   the store's capping in force at the end of the month (today for the month in progress) x 30 - the same limit the Usage tab measures against
  current count   the sum of the month's order entries for the store, every entry whoever entered it
  remaining       limit - current count, never below 0
A store is VERIFIED (counts toward capacity) only with a valid capping, an Outlet ID, and when it is not one of several identical records (same project, Outlet ID
and name). The Outlet ID alone is not unique in the CRM (the store's name is its identity), so a shared Outlet ID is reported but the stores stay separate, and a
pasted line that fits more than one store is never guessed.

Who: holders of capping.planner who are Zepto staff or administrators. Administrators may plan Zepto and Blinkit; Zepto staff only Zepto. Blinkit stores have no
capping in the CRM yet, so they show as "No capping set" and add no capacity.
"""
from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order_entry import OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store, StoreStatus
from app.models.store_cap import StoreCap
from app.models.user import User
from app.services import capping_history_service as hist
from app.services import capping_planner_engine as engine
from app.services import capping_service as cs

PERMISSION = "capping.planner"
PROJECTS = ("zepto", "blinkit", "all")
MAX_PRIORITY_LINES = 5000
SEVERITY = {"over_cap": "warning", "shared_outlet_id": "warning", "same_name_other_outlet": "warning", "duplicate_record": "error", "missing_capping": "warning",
            "invalid_limit": "error", "missing_outlet_id": "error", "no_supply_records": "info", "zero_limit": "info"}


def authorise(user: User, perms: set[str], project: str) -> list[str]:
    """The platforms this person may plan for the requested project. 403 when they may not use the planner at all or ask for a platform that is not theirs."""
    if PERMISSION not in perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The Smart Capping Planner is not switched on for you.")
    cs.require_eligible(user, perms)
    slug = ((user.platform_organization.slug if user.platform_organization is not None else None) or "").strip().lower()
    allowed = ["zepto", "blinkit"] if not slug else ["zepto"]
    if project not in PROJECTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Project must be zepto, blinkit or all.")
    if project == "all":
        return allowed
    if project not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can plan only for your own platform.")
    return [project]


def _month_end(month: date) -> date:
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def _stores(db: Session, user: User, slugs: list[str]) -> list[tuple]:
    """(id, crm code, Outlet ID, name, state, city, project, current store_caps value) of the live stores of these platforms."""
    q = (
        select(Store.id, Store.crm_code, Store.external_code, Store.name, Store.state, Store.city, Organization.slug, StoreCap.daily_cap)
        .select_from(Store)
        .join(Organization, Organization.id == Store.partner_organization_id)
        .outerjoin(StoreCap, StoreCap.store_id == Store.id)
        .where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value,
               Organization.kind == OrganizationKind.PARTNER.value, Organization.slug.in_(slugs))
        .order_by(func.lower(Store.name), Store.crm_code)
    )
    return list(db.execute(q).all())


def _issue(code: str, row: dict, message: str) -> dict:
    return {"code": code, "severity": SEVERITY[code], "store_id": row["store_id"], "crm_code": row["crm_code"], "outlet_id": row["outlet_id"], "name": row["name"],
            "project": row["project"], "message": message}


def _verify(rows: list[dict]) -> list[dict]:
    """Fill each row's exclude_reason (None = verified) and return the validation issues found across the rows."""
    issues: list[dict] = []
    twins: dict[tuple, list[dict]] = defaultdict(list)
    by_outlet: dict[tuple, list[dict]] = defaultdict(list)
    by_name: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        twins[(r["project"], engine.norm(r["outlet_id"]), engine.norm(r["name"]))].append(r)
        if r["outlet_id"].strip():
            by_outlet[(r["project"], engine.norm(r["outlet_id"]))].append(r)
        by_name[(r["project"], engine.norm(r["city"] or ""), engine.norm(r["name"]))].append(r)

    for r in rows:
        cap = r["daily_cap"]
        if cap is None:
            r["exclude_reason"] = "No capping set"
            issues.append(_issue("missing_capping", r, "No capping is set, so it has no verified limit and adds no capacity."))
        elif cap < 0 or cap > cs.MAX_CAP:
            r["exclude_reason"] = "Invalid monthly limit"
            issues.append(_issue("invalid_limit", r, f"Daily capping {cap:,} is outside 0 to {cs.MAX_CAP:,}."))
        elif not r["outlet_id"].strip():
            r["exclude_reason"] = "Missing Outlet ID"
            issues.append(_issue("missing_outlet_id", r, "The store has no Outlet ID, so it cannot be verified."))
        elif len(twins[(r["project"], engine.norm(r["outlet_id"]), engine.norm(r["name"]))]) > 1:
            r["exclude_reason"] = "Duplicate store record"
            issues.append(_issue("duplicate_record", r, "Another store record has the same project, Outlet ID and name. Resolve it under Stores > Duplicates."))
        if cap == 0 and r["exclude_reason"] is None:
            issues.append(_issue("zero_limit", r, "The daily capping is 0: no bottles are allowed."))
        if cap is not None and r["entries"] == 0 and r["exclude_reason"] is None:
            issues.append(_issue("no_supply_records", r, "No supply was recorded for this store in the month."))
        if r["over_by"]:
            issues.append(_issue("over_cap", r, f"Recorded {r['used']:,} against a limit of {r['monthly_limit']:,}: over by {r['over_by']:,}. It has no remaining capacity."))
    for group in by_outlet.values():
        if len(group) > 1 and len({engine.norm(g["name"]) for g in group}) > 1:
            for r in group:
                issues.append(_issue("shared_outlet_id", r, f"{len(group)} different stores share the Outlet ID {r['outlet_id']!r}; they are kept separate. Use the system code to pick one."))
    for group in by_name.values():
        if len(group) > 1 and len({engine.norm(g["outlet_id"]) for g in group}) > 1:
            for r in group:
                issues.append(_issue("same_name_other_outlet", r, f"{len(group)} stores in {r['city'] or 'this city'} have this name with different Outlet IDs; they are not treated as one store."))
    return issues


def load(db: Session, user: User, perms: set[str], month: date, project: str) -> dict:
    """The verified/excluded store rows for the month, the master used to match pasted names, and the validation issues. Read-only."""
    slugs = authorise(user, perms, project)
    scope = _stores(db, user, slugs)                                     # every store the person may see (to match pasted lines)
    wanted = {project} if project != "all" else set(slugs)
    stores = [s for s in scope if s[6] in wanted]
    ids = [s[0] for s in stores]
    today = hist.today_ist()
    end = min(_month_end(month), today)
    history = hist._history_by_store(db, ids, end)  # noqa: SLF001
    usage = {
        sid: (int(total), int(n))
        for sid, total, n in db.execute(
            select(OrderEntry.store_id, func.coalesce(func.sum(OrderEntry.bottle_count), 0), func.count(OrderEntry.id))
            .where(OrderEntry.store_id.in_(ids or [uuid.uuid4()]), OrderEntry.order_date >= month, OrderEntry.order_date <= _month_end(month))
            .group_by(OrderEntry.store_id)
        )
    }
    rows = []
    for sid, code, outlet, name, state, city, slug, legacy in stores:
        cap = hist.capping_on(history.get(sid, []), legacy, end)
        used, entries = usage.get(sid, (0, 0))
        limit = cs.monthly_limit(cap)
        valid = cap is not None and 0 <= cap <= cs.MAX_CAP
        remaining = max(limit - used, 0) if valid else 0
        rows.append({
            "store_id": str(sid), "crm_code": code, "outlet_id": outlet or "", "name": name, "project": slug, "state": state, "city": city,
            "daily_cap": cap, "monthly_limit": limit if valid else None, "used": used, "entries": entries,
            "remaining": remaining, "over_by": max(used - limit, 0) if valid else 0, "exclude_reason": None,
        })
    issues = _verify(rows)
    master = [{"store_id": str(s[0]), "crm_code": s[1], "outlet_id": s[2] or "", "name": s[3], "project": s[6]} for s in scope]
    return {"rows": rows, "master": master, "issues": issues, "month": month, "allocation_allowed": (month.year, month.month) == (today.year, today.month)}


def run(db: Session, user: User, perms: set[str], *, month_str: str | None, project: str, mode: str, store_limit: int | None, target: int, priority: list[str]) -> dict:
    """Load the month, match the pasted priority lines and run the plan. The same function feeds the screen and the Excel export."""
    month = cs.parse_month(month_str)
    if len(priority) > MAX_PRIORITY_LINES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Paste at most {MAX_PRIORITY_LINES:,} priority stores.")
    data = load(db, user, perms, month, project)
    entries = engine.match_priority(priority, data["master"], project)
    result = engine.plan(data["rows"], mode=mode, store_limit=store_limit, target=target, priority=entries, allocation_allowed=data["allocation_allowed"])
    counts: dict[str, int] = defaultdict(int)
    for i in data["issues"]:
        counts[i["code"]] += 1
    return {
        "success": True, "month": f"{month:%Y-%m}", "month_label": f"{cs._MONTHS[month.month]} {month.year}", "months": cs.available_months(),  # noqa: SLF001
        "project": project, "mode": mode, "store_limit": store_limit, "target": target,
        "is_plan": True, "note": "Capacity planning only. Proposed allocations are not supply and change no record.",
        "allocation_note": None if data["allocation_allowed"] else f"{cs._MONTHS[month.month]} {month.year} is finished: capacity and fit are shown, but no per-store allocation is proposed.",  # noqa: SLF001
        **result, "issues": data["issues"], "issue_counts": dict(counts),
    }
