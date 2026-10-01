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
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.order_entry import OrderEntry
from app.models.organization import Organization
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


def _stores(db: Session, admin: User, start: date, end: date, partner: str | None, state: str | None, city: str | None) -> list[Store]:
    has_entry = exists().where(OrderEntry.store_id == Store.id, OrderEntry.order_date >= start, OrderEntry.order_date <= end)
    stmt = (
        select(Store)
        .where(Store.organization_id == admin.organization_id, or_(Store.status == StoreStatus.LIVE.value, has_entry))
        .options(joinedload(Store.partner_organization))
        .order_by(Store.state, Store.city, Store.name)
    )
    if partner:
        stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(Organization.slug == partner)
    if state and state.strip():
        stmt = stmt.where(func.lower(Store.state) == state.strip().lower())
    if city and city.strip():
        stmt = stmt.where(Store.city.ilike(f"%{city.strip()}%"))
    return list(db.execute(stmt).unique().scalars().all())


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


def _row(s: Store, vals: dict[date, int], dates: list[date]) -> dict:
    return {
        "store_id": s.id, "name": s.name, "external_code": s.external_code,
        "platform": s.partner_organization.name if s.partner_organization else None,
        "state": s.state, "city": s.city,
        "values": {d.isoformat(): vals[d] for d in dates if d in vals},
        "total_bottles": sum(vals.get(d, 0) for d in dates),
        "days_marked": sum(1 for d in dates if d in vals),
    }


def matrix(
    db: Session, admin: User, start: date, end: date, *, partner: str | None, state: str | None, city: str | None,
    page: int, page_size: int,
) -> dict:
    dates = _validate(start, end)
    stores = _stores(db, admin, start, end, partner, state, city)
    all_entries = _entries(db, [s.id for s in stores], start, end)  # one query; also gives the grand totals
    grand = sum(sum(v.values()) for v in all_entries.values())
    begin = (page - 1) * page_size
    return {
        "start": start, "end": end, "dates": [d.isoformat() for d in dates],
        "total": len(stores), "page": page, "page_size": page_size,
        "stores_with_entries": sum(1 for s in stores if all_entries.get(s.id)),
        "grand_total_bottles": grand,
        "rows": [_row(s, all_entries.get(s.id, {}), dates) for s in stores[begin:begin + page_size]],
    }


def matrix_xlsx(
    db: Session, admin: User, start: date, end: date, *, partner: str | None, state: str | None, city: str | None,
) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    dates = _validate(start, end)
    stores = _stores(db, admin, start, end, partner, state, city)
    entries = _entries(db, [s.id for s in stores], start, end)

    wb = Workbook()
    ws = wb.active
    ws.title = "Daily distribution"
    head = ["#", "Store", "Store code", "Channel", "State", "City", *[d.strftime("%d-%b") for d in dates], "Total"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E46A0")
        c.alignment = Alignment(horizontal="center", vertical="center")
    for i, s in enumerate(stores, start=1):
        v = entries.get(s.id, {})
        ws.append([
            i, s.name, s.external_code, s.partner_organization.name if s.partner_organization else "", s.state or "", s.city or "",
            *[v.get(d) for d in dates],        # blank cell = not marked; 0 stays 0
            sum(v.values()),
        ])
    n_fixed = 6
    ws.freeze_panes = ws.cell(row=2, column=n_fixed + 1)
    ws.column_dimensions["B"].width = 38
    for col, w in ((1, 5), (3, 18), (4, 10), (5, 16), (6, 16)):
        ws.column_dimensions[get_column_letter(col)].width = w
    for j in range(n_fixed + 1, len(head) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 8
        for r in range(2, ws.max_row + 1):
            ws.cell(row=r, column=j).alignment = Alignment(horizontal="center")
    ws.cell(row=ws.max_row + 1, column=2, value="TOTAL").font = Font(bold=True)
    total_row = ws.max_row
    for j in range(n_fixed + 1, len(head) + 1):
        col = get_column_letter(j)
        cell = ws.cell(row=total_row, column=j, value=f"=SUM({col}2:{col}{total_row - 1})")
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
