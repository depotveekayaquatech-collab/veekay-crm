"""
Per-store entry health for the current month.

pending_days (spec): the days up to *yesterday* with no entry after the last
filled day. If nothing is filled this month the count starts on the 1st.
Today is never counted — a store still has all day to be marked.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.models.region import Region
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.schemas.inventory import Inventory, InventoryStore, InventorySummary
from app.services import assignment_service

_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def pending_days(last_entry: date | None, today: date, start_date: date | None = None) -> int:
    """Days from (last filled day + 1, or the 1st, or the store's start date) through yesterday."""
    month_start = today.replace(day=1)
    start = month_start if last_entry is None else max(month_start, last_entry + timedelta(days=1))
    if start_date is not None:
        start = max(start, start_date)  # a store can't be behind on days before it began
    yesterday = today - timedelta(days=1)
    return max(0, (yesterday - start).days + 1)


def month_stats(db: Session, store_ids: list[uuid.UUID], today: date) -> dict[uuid.UUID, tuple[date | None, int, int, bool]]:
    """{store_id: (last_entry_date, bottles, entries, marked_today)} for this month."""
    if not store_ids:
        return {}
    rows = db.execute(
        select(
            OrderEntry.store_id,
            func.max(OrderEntry.order_date),
            func.coalesce(func.sum(OrderEntry.bottle_count), 0),
            func.count(OrderEntry.id),
            func.bool_or(OrderEntry.order_date == today),
        )
        .where(
            OrderEntry.store_id.in_(store_ids),
            OrderEntry.order_date >= today.replace(day=1),
            OrderEntry.order_date <= today,
        )
        .group_by(OrderEntry.store_id)
    ).all()
    return {r[0]: (r[1], int(r[2]), int(r[3]), bool(r[4])) for r in rows}


def inventory(db: Session, user: User, *, is_admin: bool, partner_slug: str | None) -> Inventory:
    today = _today()
    cols = (
        Store.id, Store.name, Store.external_code, Organization.name, Organization.slug, Region.name, Store.state,
        Store.city, Store.vendor_name, Store.vendor_number, Store.poc_name, Store.poc_number, Store.start_date,
    )
    if is_admin:
        # Plain columns, not ~1,500 ORM objects with joined relationships: several times faster and lighter.
        stmt = (
            select(*cols)
            .select_from(Store)
            .join(Organization, Organization.id == Store.partner_organization_id)
            .outerjoin(Region, Region.id == Store.region_id)
            .where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value)
            .order_by(Store.name)
        )
        if partner_slug:
            stmt = stmt.where(Organization.slug == partner_slug)
        recs = db.execute(stmt).all()
    else:
        recs = [
            (s.id, s.name, s.external_code, s.partner_organization.name if s.partner_organization else None,
             s.partner_organization.slug if s.partner_organization else None, s.region.name if s.region else None,
             s.state, s.city, s.vendor_name, s.vendor_number, s.poc_name, s.poc_number, s.start_date)
            for s in sorted(assignment_service.visible_stores(db, user), key=lambda s: s.name.lower())
        ]

    stats = month_stats(db, [r[0] for r in recs], today)
    items: list[InventoryStore] = []
    for sid, name, code, plat, plat_slug, region, state, city, vendor, vendor_no, poc, poc_no, start in recs:
        last, bottles, entries, marked_today = stats.get(sid, (None, 0, 0, False))
        items.append(InventoryStore(
            id=sid, name=name, external_code=code, platform=plat, platform_slug=plat_slug, region_name=region,
            state=state, city=city, vendor_name=vendor, vendor_number=vendor_no, poc_name=poc, poc_number=poc_no,
            start_date=start,
            last_entry_date=last, pending_days=pending_days(last, today, start),
            marked_today=marked_today, month_bottles=bottles, month_entries=entries,
        ))

    summary = InventorySummary(
        stores=len(items),
        behind=sum(1 for i in items if i.pending_days > 0),
        marked_today=sum(1 for i in items if i.marked_today),
        total_pending_days=sum(i.pending_days for i in items),
    )
    return Inventory(month_label=f"{_MONTHS[today.month]} {today.year}", summary=summary, items=items)
