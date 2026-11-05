"""
Zepto capping overflow: which stores went over their capping in a month, by how much, and which stores still had room. READ-ONLY - it moves nothing and changes
no entry; it is the picture to plan supply and to talk to the platform about capping, built on the same usage figures as the Usage tab.

Two kinds of "over", both shown:
  * monthly: bottles used above the monthly limit (daily capping x the days in the month) - the figure the Usage tab alerts on, and
  * daily: a day whose bottles for the store were above the capping in force ON THAT DAY (capping history, so a later change never rewrites an earlier day).
Room is what a store with a capping still has left of its monthly limit.
"""
from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order_entry import OrderEntry
from app.models.user import User
from app.services import capping_history_service as hist
from app.services import capping_service as cs


def _day_totals(db: Session, store_ids: list[uuid.UUID], month: date) -> dict[uuid.UUID, list[tuple[date, int]]]:
    """{store id: [(day, bottles that day)]} for the month, oldest day first. Every entry of the day counts, whoever entered it."""
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    out: dict[uuid.UUID, list[tuple[date, int]]] = defaultdict(list)
    if not store_ids:
        return out
    rows = db.execute(
        select(OrderEntry.store_id, OrderEntry.order_date, func.coalesce(func.sum(OrderEntry.bottle_count), 0))
        .where(OrderEntry.store_id.in_(store_ids), OrderEntry.order_date >= month, OrderEntry.order_date <= end)
        .group_by(OrderEntry.store_id, OrderEntry.order_date)
        .order_by(OrderEntry.order_date)
    )
    for sid, day, bottles in rows:
        out[sid].append((day, int(bottles)))
    return out


def over_days(days: list[tuple[date, int]], history: list[tuple[date, int | None]], legacy: int | None) -> list[dict]:
    """The days whose bottles were above the capping in force that day. A store with capping history uses it; one without falls back to its current capping.
    A day with no capping in force can never be over."""
    out = []
    for day, bottles in days:
        cap = hist.effective_capping(history, day) if history else legacy
        if cap is not None and bottles > cap:
            out.append({"date": day, "bottles": bottles, "cap": cap, "over_by": bottles - cap})
    return out


def overflow(db: Session, user: User, perms: set[str], month_str: str | None) -> dict:
    """Every live Zepto store that is over its capping (monthly or on any day) or has room left, with the totals."""
    cs.require_eligible(user, perms)
    month = cs.parse_month(month_str)
    partner = cs._partner(db, user.organization_id)  # noqa: SLF001
    usage = cs._rows(db, user, partner, month)  # noqa: SLF001
    ids = [r["store_id"] for r in usage]
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    history = hist._history_by_store(db, ids, end)  # noqa: SLF001
    days = _day_totals(db, ids, month)

    rows = []
    for r in usage:
        late = over_days(days.get(r["store_id"], []), history.get(r["store_id"], []), r["daily_cap"])
        room = r["remaining"] if r["monthly_cap"] is not None and r["excess"] == 0 else 0
        if not (r["excess"] or late or room):
            continue
        rows.append({
            "store_id": r["store_id"], "outlet_id": r["outlet_id"], "outlet_name": r["outlet_name"], "state": r["state"], "city": r["city"],
            "vendor_name": r["vendor_name"], "daily_cap": r["daily_cap"], "monthly_cap": r["monthly_cap"], "used": r["used"],
            "excess": r["excess"], "room": room, "percent": r["percent"],
            "days_over": len(late), "daily_excess": sum(d["over_by"] for d in late), "over_days": late,
        })
    rows.sort(key=lambda x: (-x["excess"], -x["daily_excess"], -x["room"], x["outlet_name"].lower()))

    over = [x for x in rows if x["excess"] or x["days_over"]]
    with_room = [x for x in rows if x["room"]]
    return {
        "success": True, "month": f"{month:%Y-%m}", "month_label": f"{cs._MONTHS[month.month]} {month.year}", "months": cs.available_months(),  # noqa: SLF001
        "summary": {
            "stores": len(usage),
            "stores_over_month": sum(1 for x in rows if x["excess"]), "month_excess": sum(x["excess"] for x in rows),
            "stores_over_days": sum(1 for x in rows if x["days_over"]), "days_over": sum(x["days_over"] for x in rows), "daily_excess": sum(x["daily_excess"] for x in rows),
            "stores_with_room": len(with_room), "room": sum(x["room"] for x in with_room),
            "used": sum(r["used"] for r in usage), "limit": sum(r["monthly_cap"] for r in usage if r["monthly_cap"] is not None),
            "over_total": len(over),
        },
        "rows": rows,
    }
