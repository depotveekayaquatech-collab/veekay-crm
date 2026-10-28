"""Employee performance: how much of what each employee should have marked this month they have actually marked.

Nothing is stored. Every call recounts from the entries as they are right now, from the 1st of the month up to yesterday (a day is only judged
once it is over). So when an employee goes back and marks earlier days, those days improve on the very next look: "70% on the 11th" is simply
what the 1st-to-10th now adds up to. A store counts as covered on a day when it has an entry that day (the same rule as the Daily overview),
and an employee should cover every live store in their scope on every day.
"""
from __future__ import annotations

import calendar
import uuid
from collections import Counter
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.order_entry import OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store, StoreStatus
from app.models.store_vendor_period import StoreVendorPeriod
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.services import assignment_service, holiday_service


def _pct(done: int, expected: int) -> float:
    return round(done * 100 / expected, 1) if expected else 0.0


def parse_month(value: str | None, today: date) -> date:
    """The first day of the month asked for ("2026-10"); by default the month of YESTERDAY, so on the 1st the finished month is shown."""
    if not value:
        return (today - timedelta(days=1)).replace(day=1)
    try:
        y, m = (int(x) for x in value.split("-"))
        return date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-10.") from exc


def performance(db: Session, admin: User, partner_slug: str, month: date, today: date) -> dict:
    partner = db.execute(select(Organization).where(Organization.slug == partner_slug)).scalar_one_or_none()
    if partner is None or partner.kind != OrganizationKind.PARTNER.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{partner_slug} is not a configured platform.")

    last_of_month = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    as_of = min(today - timedelta(days=1), last_of_month)
    holidays = holiday_service.between(db, admin.organization_id, month, last_of_month)
    # a company holiday is not a day anyone is expected to mark
    days = [d for d in (month + timedelta(days=i) for i in range((as_of - month).days + 1)) if d not in holidays] if as_of >= month else []

    employees = EmployeeRepository(db).all_for_platform(admin.organization_id, partner.id)
    scopes, all_ids = assignment_service.employee_store_scopes(db, partner, employees)

    covered: dict[date, set[uuid.UUID]] = {d: set() for d in days}
    if days and all_ids:
        for store_id, day in db.execute(
            select(OrderEntry.store_id, OrderEntry.order_date).where(
                OrderEntry.store_id.in_(all_ids), OrderEntry.order_date >= days[0], OrderEntry.order_date <= days[-1])
        ):
            if day in covered:  # an entry marked on a holiday is not a judged day
                covered[day].add(store_id)

    # What each person entered themselves anywhere on this platform, 1st of the month to today (any store, live or not, in scope or not).
    # An employee with no store of their own still shows up with this number, so their work is not invisible.
    made: dict[uuid.UUID, int] = {}
    if employees and last_of_month >= month:
        who = func.coalesce(OrderEntry.created_by_user_id, OrderEntry.marked_by_user_id)
        made = dict(db.execute(
            select(who, func.count(OrderEntry.id)).join(Store, Store.id == OrderEntry.store_id)
            .where(Store.organization_id == admin.organization_id, Store.partner_organization_id == partner.id,
                   OrderEntry.order_date >= month, OrderEntry.order_date <= min(today, last_of_month), who.in_([e.id for e in employees]))
            .group_by(who)
        ).all())

    rows, storeless = [], []
    for emp in employees:
        stores = set(scopes.get(emp.id, []))
        if not stores:  # nothing to mark (a team lead with no store assigned, a new employee): no percentage, listed only if they entered something
            if made.get(emp.id):
                storeless.append({
                    "employee_id": emp.id, "employee_code": emp.employee_code, "employee_name": emp.full_name,
                    "region_name": emp.region.name if emp.region else None,
                    "stores": 0, "expected": 0, "done": 0, "missing": 0, "percent": 0.0, "yesterday_percent": None, "daily": [],
                    "entries_made": made[emp.id], "no_stores": True,
                })
            continue
        daily, done_total, running_expected = [], 0, 0
        for d in days:
            done = len(stores & covered[d])
            done_total += done
            running_expected += len(stores)
            daily.append({"date": d, "done": done, "expected": len(stores), "percent": _pct(done, len(stores)), "cumulative": _pct(done_total, running_expected)})
        expected = len(stores) * len(days)
        rows.append({
            "employee_id": emp.id, "employee_code": emp.employee_code, "employee_name": emp.full_name,
            "region_name": emp.region.name if emp.region else None,
            "stores": len(stores), "expected": expected, "done": done_total, "missing": expected - done_total, "percent": _pct(done_total, expected),
            "yesterday_percent": daily[-1]["percent"] if daily and daily[-1]["date"] == today - timedelta(days=1) else None,
            "daily": daily, "entries_made": made.get(emp.id, 0), "no_stores": False,
        })
    rows.sort(key=lambda r: (r["percent"], r["employee_name"].lower()))
    storeless.sort(key=lambda r: (-r["entries_made"], r["employee_name"].lower()))

    expected_all = sum(r["expected"] for r in rows)
    done_all = sum(r["done"] for r in rows)
    return {
        "partner_slug": partner.slug, "partner_label": partner.name, "month": f"{month:%Y-%m}", "month_label": month.strftime("%B %Y"),
        "from": days[0] if days else None, "as_of": days[-1] if days else None, "days": len(days), "today": today,
        "holidays": {d.isoformat(): n for d, n in holidays.items() if d <= as_of},
        "summary": {"employees": len(rows), "expected": expected_all, "done": done_all, "percent": _pct(done_all, expected_all),
                    "below_50": sum(1 for r in rows if r["expected"] and r["percent"] < 50)},
        "employees": rows + storeless,      # people with no store of their own come last, and are not part of the summary
    }


def _vendor_key(name: str | None) -> str:
    return " ".join((name or "").split()).lower()


def vendors(db: Session, user: User, partner_slug: str, month: date, today: date, *, full: bool = True) -> dict:
    """Vendor-wise: for each vendor of a platform, its stores and the bottles marked at each store this month (1st to today, as the inventory page counts).
    A store that changed vendor part-way through the month counts each vendor's bottles only for the dates that vendor supplied it (store_vendor_periods);
    an entry no period covers goes to the store's current vendor. A vendor with one store simply has one row.

    `full` (an administrator or anyone with the daily overview): every store of the platform, bottles as entered. Otherwise (an employee, a Team Lead):
    only the stores in the person's own scope, and the bottles they are allowed to see (never a developer's cash adjustment)."""
    partner = db.execute(select(Organization).where(Organization.slug == partner_slug)).scalar_one_or_none()
    if partner is None or partner.kind != OrganizationKind.PARTNER.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{partner_slug} is not a configured platform.")

    last = min(today, date(month.year, month.month, calendar.monthrange(month.year, month.month)[1]))
    P = StoreVendorPeriod
    org = user.organization_id
    if full:
        stores = {s.id: s for s in db.execute(select(Store).where(Store.organization_id == org, Store.partner_organization_id == partner.id)).scalars()}
    else:
        stores = {s.id: s for s in assignment_service.visible_stores(db, user) if s.partner_organization_id == partner.id}

    vendor_name = func.coalesce(P.vendor_name, Store.vendor_name)
    vendor_number = func.coalesce(P.vendor_number, Store.vendor_number)
    in_period = and_(P.store_id == OrderEntry.store_id, OrderEntry.order_date >= func.coalesce(P.start_date, date(1900, 1, 1)),
                     or_(P.end_date.is_(None), OrderEntry.order_date <= P.end_date))
    amount = OrderEntry.bottle_count if full else OrderEntry.bottle_count - OrderEntry.cash_adjustment
    entries = [] if last < month or not stores else db.execute(
        select(OrderEntry.store_id, vendor_name, vendor_number, func.coalesce(func.sum(amount), 0), func.count(OrderEntry.id))
        .join(Store, Store.id == OrderEntry.store_id).outerjoin(P, in_period)
        .where(Store.organization_id == org, Store.partner_organization_id == partner.id, OrderEntry.order_date >= month, OrderEntry.order_date <= last,
               *([] if full else [OrderEntry.store_id.in_(list(stores))]))
        .group_by(OrderEntry.store_id, vendor_name, vendor_number)
    ).all()

    groups: dict[str, dict] = {}

    def row(name: str | None, number: str | None, sid: uuid.UUID) -> dict:
        g = groups.setdefault(_vendor_key(name), {"spellings": Counter(), "vendor_number": number, "stores": {}, "bottles": 0})
        g["vendor_number"] = g["vendor_number"] or number
        st = stores[sid]
        if sid not in g["stores"]:
            g["spellings"][" ".join((name or "").split())] += 1
        return g["stores"].setdefault(sid, {
            "store_id": sid, "store_name": st.name, "external_code": st.external_code, "state": st.state, "city": st.city,
            "live": st.status == StoreStatus.LIVE.value, "bottles": 0, "days_marked": 0,
        })

    for sid, name, number, bottles, days in entries:
        r = row(name, number, sid)
        r["bottles"] += int(bottles)
        r["days_marked"] += int(days)
        groups[_vendor_key(name)]["bottles"] += int(bottles)
    for sid, st in stores.items():  # a live store with no entries yet still belongs to its vendor
        if st.status == StoreStatus.LIVE.value:
            row(st.vendor_name, st.vendor_number, sid)

    out = []
    for g in groups.values():
        rows = sorted(g["stores"].values(), key=lambda r: (-r["bottles"], r["store_name"].lower()))
        label = min(g["spellings"].items(), key=lambda kv: (-kv[1], kv[0]))[0] or None      # the spelling most stores use
        out.append({"vendor_name": label, "vendor_number": g["vendor_number"], "store_count": len(rows), "bottles": g["bottles"], "stores": rows})
    out.sort(key=lambda v: (v["vendor_name"] or "~").lower())
    return {
        "partner_slug": partner.slug, "partner_label": partner.name, "month": f"{month:%Y-%m}", "month_label": month.strftime("%B %Y"),
        "from": month if last >= month else None, "to": last if last >= month else None,
        "summary": {"vendors": len(out), "stores": sum(v["store_count"] for v in out), "bottles": sum(v["bottles"] for v in out)},
        "vendors": out,
    }
