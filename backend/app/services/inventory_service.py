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
    if is_admin:
        stmt = (
            select(Store)
            .where(Store.organization_id == user.organization_id, Store.status == StoreStatus.LIVE.value)
            .options(joinedload(Store.region), joinedload(Store.partner_organization))
            .order_by(Store.name)
        )
        if partner_slug:
            stmt = stmt.join(Organization, Organization.id == Store.partner_organization_id).where(
                Organization.slug == partner_slug
            )
        stores = db.execute(stmt).unique().scalars().all()
    else:
        stores = sorted(assignment_service.visible_stores(db, user), key=lambda s: s.name.lower())

    stats = month_stats(db, [s.id for s in stores], today)
    items: list[InventoryStore] = []
    for s in stores:
        last, bottles, entries, marked_today = stats.get(s.id, (None, 0, 0, False))
        items.append(InventoryStore(
            id=s.id, name=s.name, external_code=s.external_code,
            platform=s.partner_organization.name if s.partner_organization else None,
            platform_slug=s.partner_organization.slug if s.partner_organization else None,
            region_name=s.region.name if s.region else None,
            state=s.state, city=s.city,
            vendor_name=s.vendor_name, vendor_number=s.vendor_number,
            poc_name=s.poc_name, poc_number=s.poc_number,
            start_date=s.start_date,
            last_entry_date=last, pending_days=pending_days(last, today, s.start_date),
            marked_today=marked_today, month_bottles=bottles, month_entries=entries,
        ))

    summary = InventorySummary(
        stores=len(items),
        behind=sum(1 for i in items if i.pending_days > 0),
        marked_today=sum(1 for i in items if i.marked_today),
        total_pending_days=sum(i.pending_days for i in items),
    )
    return Inventory(month_label=f"{_MONTHS[today.month]} {today.year}", summary=summary, items=items)
