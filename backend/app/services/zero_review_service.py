"""Zero Review: find stores stuck at zero, review them every week, verify last month's data.

A "zero" is a day where somebody explicitly entered 0 for a store (an order_entries row with bottle_count = 0). A day with no row is UNMARKED, never a zero.
Everything is recomputed from order_entries on every call (one query for the entries of every store in view, one pass over them); only a person's decision
(reviewed / verified / flagged) is stored, in zero_review, with an append-only copy of every change in zero_review_log.

Who may do what (always derived from the signed-in user on the server):
  employee           their own stores, read only
  Team Lead          the stores of their team, may review weekly and verify monthly
  Reviewer / admin   everything in their scope (a platform-limited Reviewer: that platform), may review and verify
  admin / developer  also reopen a closed month, and act on a closed month
All dates use the CRM's display time zone (Asia/Kolkata): "today", the Saturday that closes a week, and where a month starts and ends.
"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.core import entry_access
from app.core.config import settings
from app.core.roles import ADMIN, DEVELOPER, PARTNER
from app.models.holiday import Holiday
from app.models.order_entry import OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.models.zero_review import ZeroReview, ZeroReviewLog
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.user_repository import UserRepository
from app.services import assignment_service
from app.services.zero_streak import NONZERO, SKIP, UNMARKED, ZERO, MODES, analyse, severity

GRACE_DAYS = 5                       # a month can still be verified this many days into the next one
REOPEN_DAYS = 7                      # a month an administrator reopened stays open this long
WEEKLY_THRESHOLD = 3                 # the "flagged store" line of the weekly review: this many zero days in a row
MAX_RANGE_DAYS = 93
MAX_PAGE = 200
MAX_BULK = 500
REASONS = {
    "store_closed": "Store closed", "stock_issue": "Stock issue", "employee_not_visiting": "Employee not visiting",
    "data_entry_missed": "Data entry missed", "other": "Other",
}
REVIEW_STATUSES = ("pending", "reviewed", "verified", "flagged")
SORTS = ("streak", "unmarked", "zero_days", "store")


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.DISPLAY_TIMEZONE)


def today() -> date:
    return datetime.now(_tz()).date()


def week_start_of(d: date) -> date:
    return d - timedelta(days=d.weekday())               # Monday


def default_week(t: date | None = None) -> date:
    """The Monday of the review cycle that ended on the most recent Saturday (on or before today)."""
    t = t or today()
    saturday = t - timedelta(days=(t.weekday() - 5) % 7)
    return saturday - timedelta(days=5)


def month_bounds(first: date) -> tuple[date, date]:
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def previous_month(t: date | None = None) -> date:
    t = t or today()
    return (t.replace(day=1) - timedelta(days=1)).replace(day=1)


# ------------------------------------------------------------------------------------------------------------------------------ scope

@dataclass
class ZeroScope:
    org_id: uuid.UUID
    user_id: uuid.UUID
    level: str
    store_ids: set[uuid.UUID]
    owners: dict[uuid.UUID, list[uuid.UUID]]              # store -> employees whose scope covers it
    people: dict[uuid.UUID, User]
    can_review: bool
    can_reopen: bool
    is_admin: bool


def scope_for(db: Session, user: User, perms: set[str]) -> ZeroScope:
    if "zero.view" not in perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    roles = set(UserRepository(db).get_role_codes(user.id))
    if PARTNER in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
    es = entry_access.scope_for(db, user, perms)
    owners: dict[uuid.UUID, list[uuid.UUID]] = {}
    people: dict[uuid.UUID, User] = {}
    live_ids: set[uuid.UUID] = set()
    for partner in db.execute(select(Organization).where(Organization.kind == OrganizationKind.PARTNER.value, Organization.is_active.is_(True))).scalars():
        if es.platform_id is not None and partner.id != es.platform_id:
            continue
        employees = EmployeeRepository(db).all_for_platform(user.organization_id, partner.id)
        scopes, all_ids = assignment_service.employee_store_scopes(db, partner, employees)
        live_ids.update(all_ids)
        for emp in employees:
            people[emp.id] = emp
            for sid in scopes.get(emp.id, []):
                owners.setdefault(sid, []).append(emp.id)
    is_admin = bool(roles & {ADMIN, DEVELOPER})
    if es.creator_ids is None:                                       # a Reviewer or administrator: every live store in view, owned or not
        store_ids = set(live_ids)
    else:                                                            # a Team Lead: their team's stores; an employee: their own
        store_ids = {sid for sid, who in owners.items() if any(w in es.creator_ids for w in who)}
    return ZeroScope(
        org_id=user.organization_id, user_id=user.id, level=es.level.value, store_ids=store_ids, owners=owners, people=people,
        can_review="zero.review" in perms, can_reopen="zero.reopen" in perms, is_admin=is_admin,
    )


def _need_review(sc: ZeroScope) -> None:
    if not sc.can_review:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can view this, but only a Team Lead, Reviewer or administrator can review it.")


# ------------------------------------------------------------------------------------------------------------------------------ filters

@dataclass
class Filters:
    date_from: date
    date_to: date
    regions: list[uuid.UUID]
    employees: list[uuid.UUID]
    platform: str | None = None
    search: str | None = None
    review_status: str | None = None             # pending | reviewed | verified | flagged
    n: int = 0                                   # 0 = off
    mode: str = "break"
    unmarked_ge: int = 0
    sort: str = "streak"
    period_type: str | None = None               # which stored decision to show next to each store: week | month | None (the latest)
    period_start: date | None = None


def validate(f: Filters) -> Filters:
    if f.date_to < f.date_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The end date is before the start date.")
    if (f.date_to - f.date_from).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Pick at most {MAX_RANGE_DAYS} days at a time.")
    if f.mode not in MODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unmarked days must be: break, ignore or count.")
    if not 0 <= f.n <= 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Consecutive zeros must be between 1 and 366 (or off).")
    if f.unmarked_ge < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unmarked days can't be negative.")
    if f.review_status and f.review_status not in REVIEW_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Review status must be pending, reviewed, verified or flagged.")
    if f.sort not in SORTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown sort.")
    return f


# ------------------------------------------------------------------------------------------------------------------------------ the report

def _holidays(db: Session, org_id: uuid.UUID, start: date, end: date) -> set[date]:
    return {h for (h,) in db.execute(select(Holiday.holiday_date).where(Holiday.organization_id == org_id, Holiday.holiday_date >= start, Holiday.holiday_date <= end))}


def _day_kind(d: date, entry, holidays: set[date], t: date) -> str:
    if entry is not None:
        return ZERO if entry["count"] == 0 else NONZERO
    if d in holidays or d >= t:                       # a holiday, or a day that is not over yet: nobody has failed to enter it
        return SKIP
    return UNMARKED


def _store_rows(db: Session, sc: ZeroScope, f: Filters) -> list[tuple[Store, str | None, str | None, str | None]]:
    """(store, region name, platform name, platform slug) for the stores in view after the region / platform / employee / search filters."""
    ids = set(sc.store_ids)
    if f.employees:
        ids &= {sid for sid, who in sc.owners.items() if any(e in f.employees for e in who)}
    if not ids:
        return []
    stmt = (
        select(Store, Region.name, Organization.name, Organization.slug)
        .outerjoin(Region, Region.id == Store.region_id).join(Organization, Organization.id == Store.partner_organization_id)
        .where(Store.id.in_(ids), Store.status == StoreStatus.LIVE.value)
    )
    if f.regions:
        stmt = stmt.where(Store.region_id.in_(f.regions))
    if f.platform:
        stmt = stmt.where(Organization.slug == f.platform.strip().lower())
    if f.search and f.search.strip():
        k = "%" + f.search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(Store.name.ilike(k, escape="\\"), Store.external_code.ilike(k, escape="\\"), Store.crm_code.ilike(k, escape="\\")))
    return [(s, r, pn, ps) for s, r, pn, ps in db.execute(stmt).all()]


def _entries(db: Session, store_ids: list[uuid.UUID], start: date, end: date) -> dict[uuid.UUID, dict[date, dict]]:
    """{store: {day: {count, marker, at, source}}}: one query for every store in view."""
    out: dict[uuid.UUID, dict[date, dict]] = {}
    if not store_ids:
        return out
    for i in range(0, len(store_ids), 5000):
        chunk = store_ids[i:i + 5000]
        rows = db.execute(
            select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count, OrderEntry.source, OrderEntry.created_by_name,
                   OrderEntry.updated_at, OrderEntry.created_at, User.full_name)
            .outerjoin(User, User.id == OrderEntry.marked_by_user_id)
            .where(OrderEntry.store_id.in_(chunk), OrderEntry.order_date >= start, OrderEntry.order_date <= end)
        ).all()
        for sid, d, count, source, created_by, updated, created, marker in rows:
            who = marker or created_by or ("Sheet sync" if source == "sheet" else None)
            out.setdefault(sid, {})[d] = {"count": int(count), "marker": who, "at": updated or created, "source": source}
    return out


def _decisions(db: Session, org_id: uuid.UUID, store_ids: list[uuid.UUID], f: Filters) -> dict[uuid.UUID, ZeroReview]:
    """The stored decision shown next to each store: for one period when the page is about one, else the most recent one overlapping the range."""
    if not store_ids:
        return {}
    stmt = select(ZeroReview).where(ZeroReview.organization_id == org_id, ZeroReview.store_id.in_(store_ids))
    if f.period_type and f.period_start:
        stmt = stmt.where(ZeroReview.period_type == f.period_type, ZeroReview.period_start == f.period_start)
    else:
        stmt = stmt.where(ZeroReview.period_end >= f.date_from, ZeroReview.period_start <= f.date_to)
    out: dict[uuid.UUID, ZeroReview] = {}
    for r in db.execute(stmt.order_by(ZeroReview.period_start)).scalars():
        out[r.store_id] = r                                   # a later period overwrites an earlier one
    return out


def _names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    return {i: n for i, n in db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))} if ids else {}


def build_report(db: Session, sc: ZeroScope, f: Filters, *, apply_status_filter: bool = True) -> list[dict]:
    """One row per store in view with its streak figures, filtered and sorted. This is the single place the numbers are made."""
    validate(f)
    t = today()
    stores = _store_rows(db, sc, f)
    ids = [s.id for s, *_ in stores]
    entries = _entries(db, ids, f.date_from, f.date_to)
    holidays = _holidays(db, sc.org_id, f.date_from, f.date_to)
    decisions = _decisions(db, sc.org_id, ids, f)
    calendar_days = [f.date_from + timedelta(days=i) for i in range((f.date_to - f.date_from).days + 1) if f.date_from + timedelta(days=i) <= t]

    rows = []
    for store, region, platform, slug in stores:
        mine = entries.get(store.id, {})
        result = analyse(((d, _day_kind(d, mine.get(d), holidays, t)) for d in calendar_days), f.mode)
        longest = result["longest"]
        if f.n and (longest is None or longest["length"] < f.n):
            continue
        if f.unmarked_ge and result["unmarked"] < f.unmarked_ge:
            continue
        dec = decisions.get(store.id)
        flagged = bool(longest and longest["length"] >= (f.n or WEEKLY_THRESHOLD))
        state = dec.status if dec else "pending"
        if apply_status_filter and f.review_status:
            if f.review_status == "pending" and not (state == "pending" and (longest is not None or result["unmarked"])):
                continue
            if f.review_status != "pending" and state != f.review_status:
                continue
        marker_day = None
        if longest:
            for d in reversed(longest["dates"]):
                if mine.get(d):
                    marker_day = mine[d]
                    break
        rows.append({
            "store": {"id": store.id, "name": store.name, "outlet_id": store.external_code, "crm_code": store.crm_code, "region": region, "platform": platform, "platform_slug": slug,
                      "city": store.city, "state": store.state},
            "employees": [{"id": e, "name": sc.people[e].full_name, "code": sc.people[e].employee_code} for e in sc.owners.get(store.id, []) if e in sc.people][:5],
            "longest": None if longest is None else {k: longest[k] for k in ("length", "start", "end", "ongoing")},
            "severity": severity(longest["length"]) if longest else "none",
            "total_zero": result["total_zero"], "unmarked": result["unmarked"], "last_nonzero": result["last_nonzero"],
            "marked_by": None if marker_day is None else {"name": marker_day["marker"], "at": marker_day["at"]},
            "flagged": flagged, "status": state,
            "review": None if dec is None else {"status": dec.status, "reason": dec.reason, "remark": dec.remark, "at": dec.reviewed_at, "by_id": dec.reviewed_by_user_id,
                                                "follow_up_date": dec.follow_up_date, "period_type": dec.period_type, "period_start": dec.period_start},
            "total_orders": sum(e["count"] for e in mine.values()),
        })
    names = _names(db, {r["review"]["by_id"] for r in rows if r["review"]})
    for r in rows:
        if r["review"]:
            r["review"]["by"] = names.get(r["review"].pop("by_id"))
    key = {
        "streak": lambda r: (-(r["longest"]["length"] if r["longest"] else 0), -r["unmarked"], r["store"]["name"].lower()),
        "unmarked": lambda r: (-r["unmarked"], -(r["longest"]["length"] if r["longest"] else 0), r["store"]["name"].lower()),
        "zero_days": lambda r: (-r["total_zero"], r["store"]["name"].lower()),
        "store": lambda r: r["store"]["name"].lower(),
    }[f.sort]
    rows.sort(key=key)
    return rows


def streaks(db: Session, user: User, perms: set[str], f: Filters, page: int, page_size: int) -> dict:
    sc = scope_for(db, user, perms)
    rows = build_report(db, sc, f)
    page, page_size = max(1, page), min(max(1, page_size), MAX_PAGE)
    start = (page - 1) * page_size
    return {
        "total": len(rows), "page": page, "page_size": page_size, "items": rows[start:start + page_size],
        "summary": {"stores": len(rows), "with_zero_streak": sum(1 for r in rows if r["longest"]), "ongoing": sum(1 for r in rows if r["longest"] and r["longest"]["ongoing"]),
                    "with_unmarked": sum(1 for r in rows if r["unmarked"]), "pending": sum(1 for r in rows if r["status"] == "pending" and r["longest"])},
        "can_review": sc.can_review, "level": sc.level, "today": today(), "range": {"from": f.date_from, "to": f.date_to},
    }


def store_days(db: Session, user: User, perms: set[str], store_id: uuid.UUID, f: Filters) -> dict:
    """The drawer: every day of the range for one store, who marked it, and which days belong to a streak."""
    sc = scope_for(db, user, perms)
    validate(f)
    if store_id not in sc.store_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    store = db.get(Store, store_id)
    t = today()
    mine = _entries(db, [store_id], f.date_from, f.date_to).get(store_id, {})
    holidays = _holidays(db, sc.org_id, f.date_from, f.date_to)
    days = [f.date_from + timedelta(days=i) for i in range((f.date_to - f.date_from).days + 1)]
    kinds = [(d, _day_kind(d, mine.get(d), holidays, t)) for d in days if d <= t]
    result = analyse(kinds, f.mode)
    in_run = set(result["longest"]["dates"]) if result["longest"] else set()
    # every run of the threshold or more is highlighted, not just the longest
    runs, run = [], []
    for d, k in kinds:
        if k == ZERO or (k == UNMARKED and f.mode == "count"):
            run.append(d)
        elif k == UNMARKED and f.mode == "ignore" or k == SKIP:
            continue
        else:
            if run:
                runs.append(run)
            run = []
    if run:
        runs.append(run)
    floor = f.n or 2
    streak_days = {d for r in runs if len(r) >= floor for d in r} | in_run
    out = []
    for d in days:
        kind = "future" if d > t else _day_kind(d, mine.get(d), holidays, t)
        e = mine.get(d)
        out.append({"date": d, "kind": "holiday" if d in holidays and e is None else kind, "count": e["count"] if e else None,
                    "marked_by": e["marker"] if e else None, "marked_at": e["at"] if e else None, "in_streak": d in streak_days})
    decision = _decisions(db, sc.org_id, [store_id], f).get(store_id)
    return {
        "store": {"id": store.id, "name": store.name, "outlet_id": store.external_code}, "days": out,
        "longest": None if not result["longest"] else {k: result["longest"][k] for k in ("length", "start", "end", "ongoing")},
        "total_zero": result["total_zero"], "unmarked": result["unmarked"], "last_nonzero": result["last_nonzero"],
        "review": None if decision is None else {"status": decision.status, "reason": decision.reason, "remark": decision.remark, "at": decision.reviewed_at},
    }


def options(db: Session, user: User, perms: set[str]) -> dict:
    """What the filter dropdowns offer: only regions, employees and partners inside the caller's scope."""
    sc = scope_for(db, user, perms)
    region_ids = {r for (r,) in db.execute(select(Store.region_id).where(Store.id.in_(sc.store_ids), Store.region_id.is_not(None)).distinct())} if sc.store_ids else set()
    regions = [{"id": r.id, "name": r.name} for r in db.execute(select(Region).where(Region.id.in_(region_ids)).order_by(Region.name)).scalars()] if region_ids else []
    owner_ids = {e for sid in sc.store_ids for e in sc.owners.get(sid, [])}
    employees = sorted(({"id": e, "name": sc.people[e].full_name, "code": sc.people[e].employee_code} for e in owner_ids if e in sc.people), key=lambda x: x["name"].lower())
    platforms = [{"slug": s, "name": n} for n, s in db.execute(
        select(Organization.name, Organization.slug).where(Organization.id.in_(select(Store.partner_organization_id).where(Store.id.in_(sc.store_ids))))).all()] if sc.store_ids else []
    return {"regions": regions, "employees": employees, "platforms": platforms, "reasons": [{"value": k, "label": v} for k, v in REASONS.items()],
            "grace_days": GRACE_DAYS, "weekly_threshold": WEEKLY_THRESHOLD, "default_week": default_week(), "previous_month": previous_month(), "today": today(),
            "can_review": sc.can_review, "can_reopen": sc.can_reopen, "level": sc.level}


# ------------------------------------------------------------------------------------------------------------------------------ decisions

def _actor(user: User) -> dict:
    return {"actor_user_id": user.id, "actor_name": user.full_name, "actor_code": user.employee_code}


def _record(db: Session, sc: ZeroScope, user: User, *, store_id: uuid.UUID, period_type: str, start: date, end: date, to_status: str, event: str, threshold: int | None,
            longest: int, reason: str | None, remark: str | None, follow_up: date | None) -> None:
    row = db.execute(select(ZeroReview).where(ZeroReview.store_id == store_id, ZeroReview.period_type == period_type, ZeroReview.period_start == start)).scalar_one_or_none()
    before = row.status if row else "pending"
    now = datetime.now(timezone.utc)
    if row is None:
        row = ZeroReview(organization_id=sc.org_id, store_id=store_id, period_type=period_type, period_start=start, period_end=end, status=to_status)
        db.add(row)
    row.status, row.threshold_used, row.longest_streak, row.reason, row.remark = to_status, threshold, longest, reason, remark
    row.reviewed_by_user_id, row.reviewed_at, row.follow_up_date = user.id, now, follow_up
    db.add(ZeroReviewLog(organization_id=sc.org_id, store_id=store_id, period_type=period_type, period_start=start, period_end=end, event=event, from_status=before,
                         to_status=to_status, threshold_used=threshold, longest_streak=longest, reason=reason, remark=remark, follow_up_date=follow_up, **_actor(user)))


def _clean_remark(remark: str | None, *, required: bool = True) -> str | None:
    r = " ".join((remark or "").split())
    if required and len(r) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write a remark (at least 3 characters).")
    return r[:1000] or None


def _in_scope(sc: ZeroScope, store_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    ids = list(dict.fromkeys(store_ids))
    if not ids or len(ids) > MAX_BULK:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Choose 1 to {MAX_BULK} stores.")
    if any(i not in sc.store_ids for i in ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One of those stores is not in your scope.")
    return ids


def week_range(week_start: date) -> tuple[date, date]:
    if week_start.weekday() != 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A review week starts on a Monday.")
    return week_start, week_start + timedelta(days=5)                  # Monday to Saturday


def weekly(db: Session, user: User, perms: set[str], week_start: date, threshold: int, f: Filters) -> dict:
    sc = scope_for(db, user, perms)
    start, end = week_range(week_start)
    if not 1 <= threshold <= 6:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A week has six review days: the threshold is 1 to 6.")
    f = Filters(**{**f.__dict__, "date_from": start, "date_to": end, "n": threshold, "period_type": "week", "period_start": start})
    rows = build_report(db, sc, f)
    pending = sum(1 for r in rows if r["status"] == "pending")
    reviewed = sum(1 for r in rows if r["status"] in ("reviewed", "verified"))
    # who marked the zeros: one person marking zeros in many stores is worth a look
    t = today()
    by_marker: dict[str, dict] = {}
    entries = _entries(db, [r["store"]["id"] for r in rows], start, end)
    for r in rows:
        for d, e in entries.get(r["store"]["id"], {}).items():
            if e["count"] == 0 and d <= t:
                m = by_marker.setdefault(e["marker"] or "Unknown", {"name": e["marker"] or "Unknown", "stores": set(), "zero_days": 0})
                m["stores"].add(r["store"]["id"])
                m["zero_days"] += 1
    markers = sorted(({"name": m["name"], "stores": len(m["stores"]), "zero_days": m["zero_days"]} for m in by_marker.values()), key=lambda m: (-m["stores"], -m["zero_days"]))
    return {
        "week_start": start, "week_end": end, "threshold": threshold, "is_current_default": start == default_week(), "today": t,
        "summary": {"flagged": len(rows), "reviewed": reviewed, "pending": pending, "complete": pending == 0},
        "items": rows, "markers": markers[:15], "can_review": sc.can_review, "reasons": [{"value": k, "label": v} for k, v in REASONS.items()],
    }


def review_week(db: Session, user: User, perms: set[str], week_start: date, store_ids: list[uuid.UUID], threshold: int, reason: str, remark: str | None,
                follow_up: date | None) -> dict:
    sc = scope_for(db, user, perms)
    _need_review(sc)
    start, end = week_range(week_start)
    if start > today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That week has not started yet.")
    if reason not in REASONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a reason.")
    remark = _clean_remark(remark)
    if follow_up is not None and follow_up < today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The follow-up date can't be in the past.")
    ids = _in_scope(sc, store_ids)
    f = Filters(date_from=start, date_to=end, regions=[], employees=[])
    entries, holidays, t = _entries(db, ids, start, end), _holidays(db, sc.org_id, start, end), today()
    days = [start + timedelta(days=i) for i in range(6) if start + timedelta(days=i) <= t]
    for sid in ids:
        mine = entries.get(sid, {})
        longest = analyse(((d, _day_kind(d, mine.get(d), holidays, t)) for d in days), f.mode)["longest"]
        _record(db, sc, user, store_id=sid, period_type="week", start=start, end=end, to_status="reviewed", event="reviewed", threshold=threshold,
                longest=longest["length"] if longest else 0, reason=reason, remark=remark, follow_up=follow_up)
    db.commit()
    return {"reviewed": len(ids), "week_start": start}


# ------------------------------------------------------------------------------------------------------------------------------ monthly

def _reopened(db: Session, org_id: uuid.UUID, first: date) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=REOPEN_DAYS)
    return db.execute(select(ZeroReviewLog.id).where(
        ZeroReviewLog.organization_id == org_id, ZeroReviewLog.event == "month_reopened", ZeroReviewLog.period_type == "month",
        ZeroReviewLog.period_start == first, ZeroReviewLog.created_at >= cutoff).limit(1)).first() is not None


def month_state(db: Session, org_id: uuid.UUID, first: date, t: date | None = None) -> dict:
    """Is this month open for verification? A month is open from its first day until GRACE_DAYS into the next month (or for REOPEN_DAYS after an administrator
    reopens it)."""
    t = t or today()
    start, end = month_bounds(first)
    closes = end + timedelta(days=GRACE_DAYS)
    reopened = _reopened(db, org_id, first)
    in_window = start <= t <= closes
    return {
        "month": f"{first:%Y-%m}", "start": start, "end": end, "closes_on": closes, "open": in_window or reopened, "reopened": reopened and not in_window,
        "finished": end < t, "days_left": max(0, (closes - t).days + 1) if in_window else None,
    }


def parse_month(value: str | None, default: date | None = None) -> date:
    if not value:
        return default or previous_month()
    try:
        y, m = (int(x) for x in value.split("-"))
        first = date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-09.") from exc
    if first > today().replace(day=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That month has not started yet.")
    return first


def monthly(db: Session, user: User, perms: set[str], first: date, f: Filters) -> dict:
    sc = scope_for(db, user, perms)
    start, end = month_bounds(first)
    f = Filters(**{**f.__dict__, "date_from": start, "date_to": end, "period_type": "month", "period_start": start})
    rows = build_report(db, sc, f)
    weeks: dict[uuid.UUID, dict[str, int]] = {}
    if rows:
        for sid, st, n in db.execute(select(ZeroReview.store_id, ZeroReview.status, func.count()).where(
                ZeroReview.organization_id == sc.org_id, ZeroReview.period_type == "week", ZeroReview.period_start >= start - timedelta(days=5), ZeroReview.period_start <= end,
                ZeroReview.store_id.in_([r["store"]["id"] for r in rows])).group_by(ZeroReview.store_id, ZeroReview.status)):
            weeks.setdefault(sid, {})[st] = int(n)
    for r in rows:
        r["weekly"] = weeks.get(r["store"]["id"], {})
    def progress(keyfn) -> list[dict]:
        out: dict[str, dict] = {}
        for r in rows:
            for label in keyfn(r) or ["Unassigned"]:
                p = out.setdefault(label, {"name": label, "total": 0, "verified": 0, "flagged": 0})
                p["total"] += 1
                p["verified"] += r["status"] == "verified"
                p["flagged"] += r["status"] == "flagged"
        return sorted(out.values(), key=lambda p: p["name"].lower())
    verified = sum(1 for r in rows if r["status"] == "verified")
    return {
        "period": month_state(db, sc.org_id, first), "items": rows, "can_review": sc.can_review, "can_reopen": sc.can_reopen, "is_admin": sc.is_admin,
        "progress": {"overall": {"verified": verified, "flagged": sum(1 for r in rows if r["status"] == "flagged"), "total": len(rows)},
                     "by_region": progress(lambda r: [r["store"]["region"]] if r["store"]["region"] else []),
                     "by_employee": progress(lambda r: [e["name"] for e in r["employees"]])},
        "reasons": [{"value": k, "label": v} for k, v in REASONS.items()],
    }


def verify_month(db: Session, user: User, perms: set[str], first: date, store_ids: list[uuid.UUID], new_status: str, remark: str | None) -> dict:
    sc = scope_for(db, user, perms)
    _need_review(sc)
    if new_status not in ("verified", "flagged"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Verify the store or flag it for correction.")
    state = month_state(db, sc.org_id, first)
    if first > today().replace(day=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That month has not started yet.")
    closed_but_admin = not state["open"]
    if closed_but_admin and not sc.is_admin:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{first:%B %Y} closed on {state['closes_on']:%d %b %Y}. An administrator can reopen it.")
    remark = _clean_remark(remark)
    ids = _in_scope(sc, store_ids)
    start, end = month_bounds(first)
    t = today()
    entries, holidays = _entries(db, ids, start, end), _holidays(db, sc.org_id, start, end)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1) if start + timedelta(days=i) <= t]
    for sid in ids:
        mine = entries.get(sid, {})
        longest = analyse(((d, _day_kind(d, mine.get(d), holidays, t)) for d in days), "break")["longest"]
        _record(db, sc, user, store_id=sid, period_type="month", start=start, end=end, to_status=new_status, event="closed_month_verified" if closed_but_admin else new_status,
                threshold=None, longest=longest["length"] if longest else 0, reason=None, remark=remark, follow_up=None)
    db.commit()
    return {"updated": len(ids), "status": new_status, "month": f"{first:%Y-%m}"}


def reopen_month(db: Session, user: User, perms: set[str], first: date, reason: str | None) -> dict:
    sc = scope_for(db, user, perms)
    if not sc.can_reopen:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can reopen a month.")
    reason = _clean_remark(reason)
    if first > today().replace(day=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That month has not started yet.")
    start, end = month_bounds(first)
    db.add(ZeroReviewLog(organization_id=sc.org_id, store_id=None, period_type="month", period_start=start, period_end=end, event="month_reopened", remark=reason, **_actor(user)))
    db.commit()
    return month_state(db, sc.org_id, first)


# ------------------------------------------------------------------------------------------------------------------------------ history, badge, export

def history(db: Session, user: User, perms: set[str], f: Filters, page: int, page_size: int, reviewer: str | None, status_filter: str | None,
            period_from: date | None, period_to: date | None) -> dict:
    sc = scope_for(db, user, perms)
    allowed = set(sc.store_ids)
    if f.employees:
        allowed &= {sid for sid, who in sc.owners.items() if any(e in f.employees for e in who)}
    stmt = (select(ZeroReviewLog, Store.name, Store.external_code).outerjoin(Store, Store.id == ZeroReviewLog.store_id)
            .where(ZeroReviewLog.organization_id == sc.org_id))
    conds = []
    if allowed:
        conds.append(ZeroReviewLog.store_id.in_(allowed))
    if sc.can_review and not f.employees and not f.search and not f.regions:         # month-level events (a month reopened) have no store
        conds.append(ZeroReviewLog.store_id.is_(None))
    stmt = stmt.where(or_(*conds)) if conds else stmt.where(false())
    if f.search and f.search.strip():
        k = "%" + f.search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(Store.name.ilike(k, escape="\\"), Store.external_code.ilike(k, escape="\\")))
    if f.regions:
        stmt = stmt.where(Store.region_id.in_(f.regions))
    if reviewer and reviewer.strip():
        k = "%" + reviewer.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(ZeroReviewLog.actor_name.ilike(k, escape="\\"), ZeroReviewLog.actor_code.ilike(k, escape="\\")))
    if status_filter:
        stmt = stmt.where(ZeroReviewLog.to_status == status_filter)
    if period_from:
        stmt = stmt.where(ZeroReviewLog.period_start >= period_from)
    if period_to:
        stmt = stmt.where(ZeroReviewLog.period_start <= period_to)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    page, page_size = max(1, page), min(max(1, page_size), MAX_PAGE)
    rows = db.execute(stmt.order_by(ZeroReviewLog.created_at.desc(), ZeroReviewLog.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": int(total), "page": page, "page_size": page_size, "items": [{
        "id": lg.id, "at": lg.created_at, "event": lg.event, "from_status": lg.from_status, "to_status": lg.to_status, "period_type": lg.period_type,
        "period_start": lg.period_start, "period_end": lg.period_end, "store": None if lg.store_id is None else {"id": lg.store_id, "name": name, "outlet_id": code},
        "threshold": lg.threshold_used, "longest_streak": lg.longest_streak, "reason": REASONS.get(lg.reason or "", lg.reason), "remark": lg.remark,
        "follow_up_date": lg.follow_up_date, "by": lg.actor_name, "by_code": lg.actor_code} for lg, name, code in rows]}


def badge(db: Session, user: User, perms: set[str]) -> dict:
    """The number on the tab: stores still waiting for the latest week's review, plus open months that still have stores to verify."""
    sc = scope_for(db, user, perms)
    if not sc.can_review:
        return {"pending": 0, "weekly": 0, "months": 0}
    week = default_week()
    rows = build_report(db, sc, Filters(date_from=week, date_to=week + timedelta(days=5), regions=[], employees=[], n=WEEKLY_THRESHOLD, period_type="week", period_start=week))
    weekly_pending = sum(1 for r in rows if r["status"] == "pending")
    months = 0
    t = today()
    for first in {t.replace(day=1), previous_month(t)}:
        if first > t.replace(day=1) or not month_state(db, sc.org_id, first)["open"] or not month_state(db, sc.org_id, first)["finished"]:
            continue
        start, end = month_bounds(first)
        done = {sid for (sid,) in db.execute(select(ZeroReview.store_id).where(
            ZeroReview.organization_id == sc.org_id, ZeroReview.period_type == "month", ZeroReview.period_start == start, ZeroReview.status == "verified"))}
        if sc.store_ids - done:
            months += 1
    return {"pending": weekly_pending + months, "weekly": weekly_pending, "months": months}


def export_csv(db: Session, user: User, perms: set[str], f: Filters) -> str:
    sc = scope_for(db, user, perms)
    rows = build_report(db, sc, f)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Store", "Outlet ID", "Platform", "Region", "Assigned employees", "Longest zero streak (days)", "Streak start", "Streak end", "Ongoing", "Total zero days",
                "Unmarked days", "Last non-zero date", "Zeros marked by", "Marked at", "Review status", "Reason", "Remark", "Reviewed by", "Reviewed at"])
    for r in rows:
        lg, rv = r["longest"], r["review"] or {}
        w.writerow([r["store"]["name"], r["store"]["outlet_id"], r["store"]["platform"], r["store"]["region"], "; ".join(e["name"] for e in r["employees"]),
                    lg["length"] if lg else 0, lg["start"] if lg else "", lg["end"] if lg else "", "yes" if lg and lg["ongoing"] else "no", r["total_zero"], r["unmarked"],
                    r["last_nonzero"] or "", (r["marked_by"] or {}).get("name", ""), (r["marked_by"] or {}).get("at", "") or "", r["status"], REASONS.get(rv.get("reason") or "", rv.get("reason") or ""),
                    rv.get("remark") or "", rv.get("by") or "", rv.get("at") or ""])
    return out.getvalue()
