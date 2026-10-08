"""
Admin reporting: bottle totals over a date range, and which live stores
still have no entry for a given day. Read-only aggregates — the source of
truth stays the `order_entries` table.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import distinct, exists, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.repositories.order_entry_repository import OrderEntryRepository
from app.services.inventory_service import month_stats, pending_days as _pending_days
from app.schemas.report import PendingEntries, PendingStore, ReportPoint, ReportRow, SalesReport

MAX_RANGE_DAYS = 366
GROUPINGS = ("region", "partner", "state", "store")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def sales_report(
    db: Session, admin: User, start: date, end: date, group_by: str,
    *, partner_slug: str | None = None, region: str | None = None, state: str | None = None,
) -> SalesReport:
    if group_by not in GROUPINGS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"group_by must be one of {', '.join(GROUPINGS)}.")
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "End date must not be before the start date.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Range is limited to {MAX_RANGE_DAYS} days.")

    org_id = admin.organization_id
    partner = Organization

    if group_by == "region":
        key_cols = (func.coalesce(Region.name, "Unassigned"),)
        sub_col = None
    elif group_by == "partner":
        key_cols = (partner.name,)
        sub_col = None
    elif group_by == "state":
        key_cols = (func.coalesce(Store.state, "—"),)
        sub_col = None
    else:
        key_cols = (Store.name,)
        sub_col = Store.external_code

    cols = [*key_cols, *( [sub_col] if sub_col is not None else [] )]
    stmt = (
        select(
            *cols,
            func.count(OrderEntry.id),
            func.coalesce(func.sum(OrderEntry.bottle_count), 0),
            func.count(distinct(OrderEntry.order_date)),
        )
        .select_from(OrderEntry)
        .join(Store, Store.id == OrderEntry.store_id)
        .outerjoin(Region, Region.id == Store.region_id)
        .join(partner, partner.id == Store.partner_organization_id)
        .where(
            OrderEntry.organization_id == org_id,
            OrderEntry.order_date >= start,
            OrderEntry.order_date <= end,
        )
        .group_by(*cols)
    )
    # Optional narrowing: one platform, one region, one state (the chart and the breakdown stay in step).
    if partner_slug:
        stmt = stmt.where(partner.slug == partner_slug)
    if region:
        stmt = stmt.where(func.lower(Region.name) == region.lower())
    if state:
        stmt = stmt.where(func.lower(Store.state) == state.lower())

    raw = db.execute(stmt).all()
    total_bottles = sum(int(r[len(cols) + 1]) for r in raw)
    total_entries = sum(int(r[len(cols)]) for r in raw)

    rows: list[ReportRow] = []
    for r in raw:
        entries, bottles, active = int(r[len(cols)]), int(r[len(cols) + 1]), int(r[len(cols) + 2])
        label = str(r[0])
        sub = str(r[1]) if sub_col is not None else None
        rows.append(ReportRow(
            key=f"{label}|{sub}" if sub else label,
            label=label, sub=sub, entries=entries, bottles=bottles, active_days=active,
            avg_per_entry=round(bottles / entries, 1) if entries else 0.0,
            share_percent=round(bottles / total_bottles * 100, 1) if total_bottles else 0.0,
        ))
    rows.sort(key=lambda x: (-x.bottles, x.label.lower()))

    days = (end - start).days + 1
    totals = OrderEntryRepository(db).daily_totals_between(org_id, start, end, partner_slug=partner_slug, region=region, state=state)
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        entries, bottles = totals.get(d, (0, 0))
        series.append(ReportPoint(date=d, label=f"{d.strftime('%b')} {d.day}", bottles=bottles, entries=entries))

    return SalesReport(
        start=start, end=end, group_by=group_by,
        total_bottles=total_bottles, total_entries=total_entries, days=days,
        avg_bottles_per_day=round(total_bottles / days, 1),
        rows=rows, row_count=len(rows), series=series,
    )


def pending_entries(db: Session, admin: User, day_offset: int, partner_slug: str | None) -> PendingEntries:
    day_offset = 1 if day_offset == 1 else 0
    target = _today() - timedelta(days=day_offset)
    org_id = admin.organization_id

    has_entry = exists().where(OrderEntry.store_id == Store.id, OrderEntry.order_date == target)
    base = (
        select(Store)
        .where(Store.organization_id == org_id, Store.status == StoreStatus.LIVE.value)
        .options(joinedload(Store.region), joinedload(Store.partner_organization))
    )
    if partner_slug:
        base = base.join(Organization, Organization.id == Store.partner_organization_id).where(
            Organization.slug == partner_slug
        )

    live_total = db.execute(
        select(func.count()).select_from(base.with_only_columns(Store.id).subquery())
    ).scalar_one()
    stores = (
        db.execute(base.where(~has_entry).order_by(Store.state, Store.name)).unique().scalars().all()
    )

    today = _today()
    stats = month_stats(db, [s.id for s in stores], today)
    items = [
        PendingStore(
            id=s.id, name=s.name, external_code=s.external_code,
            platform=s.partner_organization.name if s.partner_organization else None,
            platform_slug=s.partner_organization.slug if s.partner_organization else None,
            region_name=s.region.name if s.region else None,
            state=s.state, city=s.city,
            vendor_name=s.vendor_name, vendor_number=s.vendor_number,
            poc_name=s.poc_name, poc_number=s.poc_number,
            last_entry_date=stats.get(s.id, (None,))[0],
            pending_days=_pending_days(stats.get(s.id, (None,))[0], today, s.start_date),
        )
        for s in stores
    ]
    items.sort(key=lambda i: (-i.pending_days, i.state or '', i.name))
    return PendingEntries(
        date=target, date_label="Yesterday" if day_offset == 1 else "Today", day_offset=day_offset,
        live_stores=int(live_total), marked=int(live_total) - len(items), pending=len(items), items=items,
    )
