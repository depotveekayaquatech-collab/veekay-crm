"""
Store start dates and vendor history, driven by the sheets / uploads.

  * A store's start date is the first day it was supplied: the earliest order (more than 0 bottles) we hold for it.
    It is only filled when empty, so a date typed by hand or given by the store sheet is never overwritten.
  * A vendor change closes the old vendor's period and opens the new one. The new vendor's start is the first order
    date seen for the store on or after the day the change was noticed; until such an order is imported the start is
    "unconfirmed" (the day the change was noticed) and the order import fixes it.
  * Store.vendor_name / vendor_number always mirror the CURRENT vendor, so every existing screen is unchanged.

All of it works in bulk (a handful of queries however many stores there are).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.store_vendor_period import StoreVendorPeriod


def same_vendor(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").lower().split()) == " ".join((b or "").lower().split())


def open_periods(db: Session, store_ids: list[uuid.UUID]) -> dict[uuid.UUID, StoreVendorPeriod]:
    out: dict[uuid.UUID, StoreVendorPeriod] = {}
    for i in range(0, len(store_ids), 5000):   # bounded parameter lists
        chunk = store_ids[i:i + 5000]
        for p in db.execute(select(StoreVendorPeriod).where(StoreVendorPeriod.store_id.in_(chunk), StoreVendorPeriod.end_date.is_(None))).scalars():
            out[p.store_id] = p
    return out


def record_vendors(
    db: Session, stores: list[Store], *, source: str, today: date, changed_from: dict[uuid.UUID, str | None] | None = None,
) -> int:
    """Make the history match each store's current vendor. `changed_from` holds the previous vendor name of stores whose
    vendor was just overwritten (so a rename is told apart from a first-time fill). Returns how many vendors changed."""
    stores = [s for s in stores if (s.vendor_name or "").strip()]
    if not stores:
        return 0
    periods = open_periods(db, [s.id for s in stores])
    changes = 0
    for s in stores:
        cur = periods.get(s.id)
        if cur is None:
            db.add(StoreVendorPeriod(store_id=s.id, vendor_name=s.vendor_name, vendor_number=s.vendor_number,
                                     start_date=s.start_date, start_confirmed=True, source=source))
        elif same_vendor(cur.vendor_name, s.vendor_name):
            if (s.vendor_number or None) != cur.vendor_number:
                cur.vendor_number = s.vendor_number   # same vendor, new phone number
        else:
            floor = cur.start_date or date.min
            cur.end_date = max(today - timedelta(days=1), floor)
            db.add(StoreVendorPeriod(store_id=s.id, vendor_name=s.vendor_name, vendor_number=s.vendor_number,
                                     start_date=today, start_confirmed=(source == "manual"), source=source))
            changes += 1
    db.flush()
    return changes


def set_start_dates_from_orders(db: Session, partner_id: uuid.UUID) -> int:
    """Fill every EMPTY store start date with the store's first supplied day. Also dates the open vendor period of a
    store whose history had no start. Never overwrites an existing date."""
    first = (
        select(OrderEntry.store_id.label("store_id"), func.min(OrderEntry.order_date).label("d"))
        .where(OrderEntry.bottle_count > 0)
        .group_by(OrderEntry.store_id)
        .subquery()
    )
    res = db.execute(
        update(Store)
        .where(Store.id == first.c.store_id, Store.partner_organization_id == partner_id, Store.start_date.is_(None))
        .values(start_date=first.c.d)
    )
    db.execute(
        update(StoreVendorPeriod)
        .where(StoreVendorPeriod.store_id == Store.id, Store.partner_organization_id == partner_id, Store.start_date.is_not(None),
               StoreVendorPeriod.start_date.is_(None), StoreVendorPeriod.end_date.is_(None))
        .values(start_date=Store.start_date)
    )
    return res.rowcount or 0


def sync_start_dates(
    db: Session, org_id: uuid.UUID, *, partner_id: uuid.UUID | None = None, overwrite: bool = False, dry_run: bool = True,
) -> dict:
    """Developer tool: set each store's start date to the first day it was supplied (earliest order with bottles).

    Empty dates are always filled. A date that already differs from the first supply is only replaced when `overwrite`
    is true (otherwise it is counted as `differs` and left alone). `dry_run` only counts, so the developer can see the
    effect first. Stores that have no supplied day yet are never touched."""
    first = (
        select(OrderEntry.store_id.label("store_id"), func.min(OrderEntry.order_date).label("d"))
        .where(OrderEntry.bottle_count > 0)
        .group_by(OrderEntry.store_id)
        .subquery()
    )
    cond = [Store.organization_id == org_id]
    if partner_id is not None:
        cond.append(Store.partner_organization_id == partner_id)
    stores, fill, differs, same = db.execute(
        select(
            func.count(),
            func.count().filter(first.c.d.is_not(None), Store.start_date.is_(None)),
            func.count().filter(first.c.d.is_not(None), Store.start_date.is_not(None), Store.start_date != first.c.d),
            func.count().filter(first.c.d.is_not(None), Store.start_date == first.c.d),
        ).select_from(Store).outerjoin(first, first.c.store_id == Store.id).where(*cond)
    ).one()
    out = {
        "stores": int(stores), "to_fill": int(fill), "differs": int(differs), "unchanged": int(same),
        "no_orders": int(stores - fill - differs - same), "replace_existing": overwrite, "dry_run": dry_run,
    }
    out["to_change"] = out["to_fill"] + (out["differs"] if overwrite else 0)
    if dry_run or not out["to_change"]:
        return out
    change = Store.start_date.is_(None) if not overwrite else Store.start_date.is_distinct_from(first.c.d)
    db.execute(update(Store).where(Store.id == first.c.store_id, *cond, change).values(start_date=first.c.d))
    # A current vendor with no known start inherits the store's start (same rule the order import applies).
    db.execute(
        update(StoreVendorPeriod)
        .where(StoreVendorPeriod.store_id == Store.id, *cond, Store.start_date.is_not(None),
               StoreVendorPeriod.start_date.is_(None), StoreVendorPeriod.end_date.is_(None))
        .values(start_date=Store.start_date)
    )
    return out


def confirm_vendor_starts(db: Session, partner_id: uuid.UUID) -> int:
    """For vendors whose start was only "the day the change was noticed": use the first order on or after that day."""
    pending = db.execute(
        select(StoreVendorPeriod).join(Store, Store.id == StoreVendorPeriod.store_id)
        .where(Store.partner_organization_id == partner_id, StoreVendorPeriod.start_confirmed.is_(False))
    ).scalars().all()
    confirmed = 0
    for p in pending:
        first = db.execute(
            select(func.min(OrderEntry.order_date)).where(
                OrderEntry.store_id == p.store_id, OrderEntry.bottle_count > 0, OrderEntry.order_date >= (p.start_date or date.min))
        ).scalar()
        if first is None:
            continue
        old_start = p.start_date
        prev = db.execute(
            select(StoreVendorPeriod).where(StoreVendorPeriod.store_id == p.store_id, StoreVendorPeriod.id != p.id,
                                            StoreVendorPeriod.end_date == (old_start - timedelta(days=1) if old_start else None))
        ).scalars().first()
        p.start_date, p.start_confirmed = first, True
        if prev is not None:
            prev.end_date = max(first - timedelta(days=1), prev.start_date or date.min)
        confirmed += 1
    db.flush()
    return confirmed


def unconfirmed_count(db: Session, partner_id: uuid.UUID) -> int:
    return int(db.execute(
        select(func.count()).select_from(StoreVendorPeriod).join(Store, Store.id == StoreVendorPeriod.store_id)
        .where(Store.partner_organization_id == partner_id, StoreVendorPeriod.start_confirmed.is_(False))
    ).scalar_one())


def history(db: Session, store_id: uuid.UUID) -> list[StoreVendorPeriod]:
    return list(db.execute(
        select(StoreVendorPeriod).where(StoreVendorPeriod.store_id == store_id)
        .order_by(StoreVendorPeriod.start_date.desc().nulls_last(), StoreVendorPeriod.created_at.desc())
    ).scalars())
