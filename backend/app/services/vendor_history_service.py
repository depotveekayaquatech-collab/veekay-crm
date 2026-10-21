"""
Store start dates and vendor history, driven by the sheets / uploads.

  * A store's start date is the first day it was supplied: the earliest order (more than 0 bottles) we hold for it.
    It is filled when empty and moves EARLIER whenever older orders are imported (September -> March once the March
    sheet is in), but is never pushed later by an import: a date typed by hand that is earlier than our first order
    (the store began before our data does) is kept. The developer's "Sync start dates" can replace those too.
  * A vendor change closes the old vendor's period and opens the new one. The new vendor's start is the first order
    date seen for the store on or after the day the change was noticed; until such an order is imported the start is
    "unconfirmed" (the day the change was noticed) and the order import fixes it.
  * Store.vendor_name / vendor_number always mirror the CURRENT vendor, so every existing screen is unchanged.

All of it works in bulk (a handful of queries however many stores there are).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.models.store import Store, StoreStatus
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
    changed_by: str | None = None,
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
                                     start_date=s.start_date, start_confirmed=True, source=source, changed_by_name=changed_by))
        elif same_vendor(cur.vendor_name, s.vendor_name):
            if (s.vendor_number or None) != cur.vendor_number:
                cur.vendor_number = s.vendor_number   # same vendor, new phone number
        else:
            floor = cur.start_date or date.min
            cur.end_date = max(today - timedelta(days=1), floor)
            db.add(StoreVendorPeriod(store_id=s.id, vendor_name=s.vendor_name, vendor_number=s.vendor_number,
                                     start_date=today, start_confirmed=(source == "manual"), source=source, changed_by_name=changed_by))
            changes += 1
    db.flush()
    return changes


def _first_supply():
    return (
        select(OrderEntry.store_id.label("store_id"), func.min(OrderEntry.order_date).label("d"))
        .where(OrderEntry.bottle_count > 0)
        .group_by(OrderEntry.store_id)
        .subquery()
    )


def _move_first_vendor_start(db: Session, first, cond: list, *, allow_later: bool) -> None:
    """When a store's start date is about to change, the store's FIRST vendor (the period that began on the old start
    date) begins on the new one too, so the vendor history keeps matching the store."""
    earlier = aliased(StoreVendorPeriod)
    moves = (first.c.d != Store.start_date) if allow_later else (first.c.d < Store.start_date)
    db.execute(
        update(StoreVendorPeriod)
        .where(
            StoreVendorPeriod.store_id == Store.id, Store.id == first.c.store_id, *cond,
            Store.start_date.is_not(None), StoreVendorPeriod.start_date == Store.start_date, moves,
            or_(StoreVendorPeriod.end_date.is_(None), first.c.d <= StoreVendorPeriod.end_date),
            ~exists().where(earlier.store_id == StoreVendorPeriod.store_id, earlier.start_date < StoreVendorPeriod.start_date),
        )
        .values(start_date=first.c.d)
    )


def _date_open_vendor_periods(db: Session, cond: list) -> None:
    """A current vendor with no known start inherits the store's start."""
    db.execute(
        update(StoreVendorPeriod)
        .where(StoreVendorPeriod.store_id == Store.id, *cond, Store.start_date.is_not(None),
               StoreVendorPeriod.start_date.is_(None), StoreVendorPeriod.end_date.is_(None))
        .values(start_date=Store.start_date)
    )


def pull_start_back(db: Session, store: Store, order_date: date, bottle_count: int) -> bool:
    """A store's start date is its first supplied day. Marking bottles on a day EARLIER than the start date (a back-dated entry)
    moves it back to that day, as an order import does, so month-filtered lists (store cards ...) include the store for that month.
    Never moves a date later, never fills an empty one, ignores a zero count. Does not commit. Returns whether it moved."""
    old = store.start_date
    if bottle_count <= 0 or old is None or order_date >= old:
        return False
    earlier = aliased(StoreVendorPeriod)
    db.execute(   # the store's first vendor began on the old start date; it begins on the new one too
        update(StoreVendorPeriod)
        .where(
            StoreVendorPeriod.store_id == store.id, StoreVendorPeriod.start_date == old,
            or_(StoreVendorPeriod.end_date.is_(None), order_date <= StoreVendorPeriod.end_date),
            ~exists().where(earlier.store_id == StoreVendorPeriod.store_id, earlier.start_date < StoreVendorPeriod.start_date),
        )
        .values(start_date=order_date)
    )
    store.start_date = order_date
    return True


def set_start_dates_from_orders(db: Session, partner_id: uuid.UUID) -> int:
    """After an order import: fill every EMPTY start date with the store's first supplied day, and move a start date
    EARLIER when the orders now hold an earlier supplied day. Never moves a date later. Returns the stores changed."""
    first = _first_supply()
    cond = [Store.partner_organization_id == partner_id]
    _move_first_vendor_start(db, first, cond, allow_later=False)
    res = db.execute(
        update(Store)
        .where(Store.id == first.c.store_id, *cond, or_(Store.start_date.is_(None), Store.start_date > first.c.d))
        .values(start_date=first.c.d)
    )
    _date_open_vendor_periods(db, cond)
    return res.rowcount or 0


def sync_start_dates(
    db: Session, org_id: uuid.UUID, *, partner_id: uuid.UUID | None = None, overwrite: bool = False, dry_run: bool = True,
    vendor: str | None = None,
) -> dict:
    """Developer tool: set each store's start date to the first day it was supplied (earliest order with bottles).

    Always applied: empty dates are filled, and a date LATER than the first supply moves back to it (`earlier` in the
    counts). A date EARLIER than the first supply is usually one entered by hand for a store that began before our order
    data starts; it is only replaced when `overwrite` is true (counted as `later`). `dry_run` only counts. Stores with
    no supplied day yet are never touched. `vendor` limits it to the stores of that vendor (exact name, any case)."""
    first = _first_supply()
    cond = [Store.organization_id == org_id]
    if partner_id is not None:
        cond.append(Store.partner_organization_id == partner_id)
    if vendor and vendor.strip():
        cond.append(func.lower(func.trim(Store.vendor_name)) == vendor.strip().lower())
    stores, fill, earlier, later, same = db.execute(
        select(
            func.count(),
            func.count().filter(first.c.d.is_not(None), Store.start_date.is_(None)),
            func.count().filter(first.c.d.is_not(None), Store.start_date > first.c.d),
            func.count().filter(first.c.d.is_not(None), Store.start_date < first.c.d),
            func.count().filter(first.c.d.is_not(None), Store.start_date == first.c.d),
        ).select_from(Store).outerjoin(first, first.c.store_id == Store.id).where(*cond)
    ).one()
    out = {
        "stores": int(stores), "to_fill": int(fill), "move_earlier": int(earlier), "keep_hand_dates": int(later),
        "differs": int(earlier + later), "unchanged": int(same),
        "no_orders": int(stores - fill - earlier - later - same), "replace_existing": overwrite, "dry_run": dry_run,
    }
    out["to_change"] = out["to_fill"] + out["move_earlier"] + (out["keep_hand_dates"] if overwrite else 0)
    # Who are the stores with no supplied day? Usually stores that are not live (pending / closed), but a LIVE store here
    # means its orders never reached the order sheet under this store (wrong Outlet ID, or the sheet doesn't cover it).
    unsupplied = (*cond, first.c.d.is_(None))
    out["no_orders_by_status"] = {
        str(st): int(n) for st, n in db.execute(
            select(Store.status, func.count()).select_from(Store).outerjoin(first, first.c.store_id == Store.id)
            .where(*unsupplied).group_by(Store.status)
        )
    }
    out["no_orders_live_sample"] = [
        {"name": n, "code": c, "platform": p} for n, c, p in db.execute(
            select(Store.name, Store.external_code, Organization.name)
            .select_from(Store).join(Organization, Organization.id == Store.partner_organization_id)
            .outerjoin(first, first.c.store_id == Store.id)
            .where(*unsupplied, Store.status == StoreStatus.LIVE.value).order_by(Organization.name, Store.name).limit(25)
        )
    ]
    if dry_run or not out["to_change"]:
        return out
    change = Store.start_date.is_distinct_from(first.c.d) if overwrite else or_(Store.start_date.is_(None), Store.start_date > first.c.d)
    _move_first_vendor_start(db, first, cond, allow_later=overwrite)
    db.execute(update(Store).where(Store.id == first.c.store_id, *cond, change).values(start_date=first.c.d))
    _date_open_vendor_periods(db, cond)
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
