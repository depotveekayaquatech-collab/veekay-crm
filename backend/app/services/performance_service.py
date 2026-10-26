"""Employee performance: how much of what each employee should have marked this month they have actually marked.

Nothing is stored. Every call recounts from the entries as they are right now, from the 1st of the month up to yesterday (a day is only judged
once it is over). So when an employee goes back and marks earlier days, those days improve on the very next look: "70% on the 11th" is simply
what the 1st-to-10th now adds up to. A store counts as covered on a day when it has an entry that day (the same rule as the Daily overview),
and an employee should cover every live store in their scope on every day.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order_entry import OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.user import User
from app.repositories.employee_repository import EmployeeRepository
from app.services import assignment_service


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
    days = [month + timedelta(days=i) for i in range((as_of - month).days + 1)] if as_of >= month else []

    employees = EmployeeRepository(db).all_for_platform(admin.organization_id, partner.id)
    scopes, all_ids = assignment_service.employee_store_scopes(db, partner, employees)

    covered: dict[date, set[uuid.UUID]] = {d: set() for d in days}
    if days and all_ids:
        for store_id, day in db.execute(
            select(OrderEntry.store_id, OrderEntry.order_date).where(
                OrderEntry.store_id.in_(all_ids), OrderEntry.order_date >= days[0], OrderEntry.order_date <= days[-1])
        ):
            covered[day].add(store_id)

    rows = []
    for emp in employees:
        stores = set(scopes.get(emp.id, []))
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
            "daily": daily,
        })
    rows.sort(key=lambda r: (r["percent"], r["employee_name"].lower()))

    expected_all = sum(r["expected"] for r in rows)
    done_all = sum(r["done"] for r in rows)
    return {
        "partner_slug": partner.slug, "partner_label": partner.name, "month": f"{month:%Y-%m}", "month_label": month.strftime("%B %Y"),
        "from": days[0] if days else None, "as_of": days[-1] if days else None, "days": len(days), "today": today,
        "summary": {"employees": len(rows), "expected": expected_all, "done": done_all, "percent": _pct(done_all, expected_all),
                    "below_50": sum(1 for r in rows if r["expected"] and r["percent"] < 50)},
        "employees": rows,
    }
