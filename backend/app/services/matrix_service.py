"""
Daily distribution matrix: one row per store, one column per day, cells = bottles
delivered (blank = nothing marked, 0 = marked zero). Rows are every live store plus
any other store that has entries in the range, so history for stores that have since
closed is never hidden.
"""
from __future__ import annotations

import io
import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import distinct, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.user import User

MAX_DAYS = 62


def _validate(start: date, end: date) -> list[date]:
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The 'to' date must not be before the 'from' date.")
    n = (end - start).days + 1
    if n > MAX_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Choose a range of at most {MAX_DAYS} days.")
    return [start + timedelta(days=i) for i in range(n)]


def _stores(
    db: Session, admin: User, start: date, end: date, partner: str | None, state: str | None, city: str | None,
    region: uuid.UUID | None = None,
) -> list[Store]:
    has_entry = exists().where(OrderEntry.store_id == Store.id, OrderEntry.order_date >= start, OrderEntry.order_date <= end)
    stmt = (
        select(Store)
        .where(Store.organization_id == admin.organization_id, or_(Store.status == StoreStatus.LIVE.value, has_entry),
               # not yet supplied by the end of this period: not shown, UNLESS it has entries in the period (a bottle that was delivered
               # must never drop out of the matrix, or its totals stop matching the region report)
               or_(Store.start_date.is_(None), Store.start_date <= end, has_entry))
        .options(joinedload(Store.partner_organization), joinedload(Store.region))
        .order_by(Store.state, Store.city, Store.name)
    )
    if partner:
        stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == partner)
    if state and state.strip():
        stmt = stmt.where(func.lower(Store.state) == state.strip().lower())
    if city and city.strip():
        stmt = stmt.where(Store.city.ilike(f"%{city.strip()}%"))
    if region is not None:
        stmt = stmt.where(Store.region_id == region)
    return list(db.execute(stmt).unique().scalars().all())


def _store_rows(
    db: Session, admin: User, start: date, end: date, partner: str | None, state: str | None, city: str | None,
    region: uuid.UUID | None = None,
) -> list[tuple]:
    """(id, name, code, platform, state, city) for the same stores as `_stores`, as plain columns — the on-screen
    matrix needs nothing else, and not building ~1,500 ORM objects per request is several times faster."""
    has_entry = exists().where(OrderEntry.store_id == Store.id, OrderEntry.order_date >= start, OrderEntry.order_date <= end)
    stmt = (
        select(Store.id, Store.name, Store.external_code, Organization.name, Store.state, Store.city)
        .select_from(Store)
        .join(Organization, Organization.id == Store.partner_organization_id)
        .where(Store.organization_id == admin.organization_id, or_(Store.status == StoreStatus.LIVE.value, has_entry),
               # not yet supplied by the end of this period: not shown, UNLESS it has entries in the period (a bottle that was delivered
               # must never drop out of the matrix, or its totals stop matching the region report)
               or_(Store.start_date.is_(None), Store.start_date <= end, has_entry))
        .order_by(Store.state, Store.city, Store.name)
    )
    if partner:
        stmt = stmt.where(Organization.slug == partner)
    if state and state.strip():
        stmt = stmt.where(func.lower(Store.state) == state.strip().lower())
    if city and city.strip():
        stmt = stmt.where(Store.city.ilike(f"%{city.strip()}%"))
    if region is not None:
        stmt = stmt.where(Store.region_id == region)
    return list(db.execute(stmt).all())


def _entries(db: Session, store_ids: list[uuid.UUID], start: date, end: date) -> dict[uuid.UUID, dict[date, int]]:
    out: dict[uuid.UUID, dict[date, int]] = {}
    if not store_ids:
        return out
    for sid, d, n in db.execute(
        select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count).where(
            OrderEntry.store_id.in_(store_ids), OrderEntry.order_date >= start, OrderEntry.order_date <= end
        )
    ):
        out.setdefault(sid, {})[d] = int(n)
    return out


def _totals(db: Session, store_ids: list[uuid.UUID], start: date, end: date) -> tuple[int, int]:
    """(bottles in total, stores that have at least one entry) over `store_ids` in the range — one aggregate query."""
    if not store_ids:
        return 0, 0
    row = db.execute(
        select(func.coalesce(func.sum(OrderEntry.bottle_count), 0), func.count(distinct(OrderEntry.store_id))).where(
            OrderEntry.store_id.in_(store_ids), OrderEntry.order_date >= start, OrderEntry.order_date <= end
        )
    ).one()
    return int(row[0]), int(row[1])


def _day_totals(db: Session, store_ids: list[uuid.UUID], start: date, end: date) -> dict[str, int]:
    """{date: bottles} over ALL the matching stores (not just the rows loaded so far), for the footer."""
    if not store_ids:
        return {}
    return {
        d.isoformat(): int(n) for d, n in db.execute(
            select(OrderEntry.order_date, func.sum(OrderEntry.bottle_count))
            .where(OrderEntry.store_id.in_(store_ids), OrderEntry.order_date >= start, OrderEntry.order_date <= end)
            .group_by(OrderEntry.order_date)
        )
    }


def regions_for(db: Session, admin: User, partner: str | None) -> list[dict]:
    """Regions that have stores of this channel (all regions when no channel is chosen), for the report's Region filter."""
    stmt = (
        select(Region.id, Region.name).select_from(Store)
        .join(Region, Region.id == Store.region_id)
        .where(Store.organization_id == admin.organization_id, Region.is_active.is_(True))
        .distinct().order_by(Region.name)
    )
    if partner:
        stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == partner)
    return [{"id": rid, "name": name} for rid, name in db.execute(stmt)]


def _row(s: tuple, vals: dict[date, int], dates: list[date]) -> dict:
    sid, name, code, platform, state, city = s
    return {
        "store_id": sid, "name": name, "external_code": code,
        "platform": platform,
        "state": state, "city": city,
        "values": {d.isoformat(): vals[d] for d in dates if d in vals},
        "total_bottles": sum(vals.get(d, 0) for d in dates),
        "days_marked": sum(1 for d in dates if d in vals),
    }


def matrix(
    db: Session, admin: User, start: date, end: date, *, partner: str | None, state: str | None, city: str | None,
    page: int, page_size: int, region: uuid.UUID | None = None,
) -> dict:
    dates = _validate(start, end)
    stores = _store_rows(db, admin, start, end, partner, state, city, region)
    begin = (page - 1) * page_size
    page_stores = stores[begin:begin + page_size]
    # Only the visible rows' cells come back to Python; the grand totals are summed by the database.
    cells = _entries(db, [s[0] for s in page_stores], start, end)
    grand, with_entries = _totals(db, [s[0] for s in stores], start, end)
    return {
        "start": start, "end": end, "dates": [d.isoformat() for d in dates],
        "total": len(stores), "page": page, "page_size": page_size,
        "stores_with_entries": with_entries,
        "grand_total_bottles": grand,
        "day_totals": _day_totals(db, [s[0] for s in stores], start, end),
        "rows": [_row(s, cells.get(s[0], {}), dates) for s in page_stores],
    }


def _rate_cells(book, store: Store, bottles: int) -> list:
    """[vendor rate, amount]; blank when no rate is set for the store's city."""
    rate = book.for_store(store) if book is not None else None
    return [None, None] if rate is None else [float(rate), round(float(rate) * bottles, 2)]


def matrix_xlsx(
    db: Session, admin: User, start: date, end: date, *, partner: str | None, state: str | None, city: str | None,
    totals: bool = True, with_rates: bool = False, region: uuid.UUID | None = None, blank_as_zero: bool = True,
) -> bytes:
    """The daily matrix as an Excel file. A day nobody marked is written as 0 (`blank_as_zero`, the default) or left as an empty cell, so a real 0 and "not marked" can be told apart."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    dates = _validate(start, end)
    stores = _stores(db, admin, start, end, partner, state, city, region)
    entries = _entries(db, [s.id for s in stores], start, end)
    book = None
    if with_rates:   # admin report: vendor rate (per bottle, city-wise) in force at the end of the period, and the amount
        from app.services.vendor_rate_service import RateBook

        book = RateBook(db, list({s.partner_organization_id for s in stores}), end)

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    head = [
        "Region", "Channel", "Entity", "STATE", "City", "Outlet ID", "Outlet Name", "POC Name", "Contact No",
        "PRIMARY VENDOR NAME", "PRIMARY LICENSE NUMBER", "SECONDARY VENDOR NAME", "SECONDARY LICENSE NUMBER",
        *(["Total Count"] if totals else []),
        *(["Vendor Rate", "Amount"] if with_rates else []),
        *[f"{d.day}-{d.strftime('%b')}" for d in dates],  # plain text, no leading zero
    ]
    ws.append(head)
    side = Side(style="thin")
    for c in ws[1]:
        c.font = Font(name="Calibri", size=11, bold=True)
        c.alignment = Alignment(horizontal="center", vertical="top")
        c.border = Border(left=side, right=side, top=side, bottom=side)

    def text(v: str | None) -> str:
        return v.strip() if v and v.strip() else "N/A"

    for s in stores:
        v = entries.get(s.id, {})
        days = [v.get(d, 0 if blank_as_zero else None) for d in dates]
        done = sum(x or 0 for x in days)
        ws.append([
            text(s.region.name.upper() if s.region else None),
            s.partner_organization.name.upper() if s.partner_organization else "N/A",
            text(s.entity),
            s.state or "N/A",
            s.city or "N/A",
            str(s.external_code),
            s.name,
            text(s.poc_name),
            text(s.poc_number),
            "VeeKay Aquatech PVT Ltd",
            "10013064000321",
            None,
            None,
            *([done] if totals else []),
            *(_rate_cells(book, s, done) if with_rates else []),
            *days,
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
