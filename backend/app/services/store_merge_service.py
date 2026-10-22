"""
Merge a store into another one (developer only).

Why: stores are created from the outlet sheet keyed by Outlet ID. When the real Outlet IDs arrive after stores were
created under temporary ones, uploading the corrected sheet creates NEW stores. This moves everything the temporary store
holds (order history, documents, tickets, cash purchases, bottles, vendor history...) onto the new store and then removes
the temporary one, so nothing is counted twice and nothing is lost.

A pair is refused, and left completely untouched, when moving would collide with data the target already has for the same
day / month (two order entries for one date, two documents of one kind for one month...). Nothing is ever overwritten.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.bottle import Bottle, BottleScan
from app.models.cash_adjustment import CashAdjustment, CashSyncRecord
from app.models.cash_purchase import CashPurchase
from app.models.compliance_document import ComplianceDocument
from app.models.external_account import ExternalAccountStore
from app.models.external_activity import DeliveryConfirmation
from app.models.order_entry import OrderEntry
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store, StoreStatus
from app.models.store_cap import StoreCap
from app.models.store_vendor_period import StoreVendorPeriod
from app.models.ticket import Ticket
from app.models.user import User
from app.models.vendor_rate import VendorRate
from app.services import activity_service, vendor_history_service

# (label shown to the developer, column pointing at the store). These rows move to the target store as they are.
_MOVES = (
    ("order days", OrderEntry.store_id),
    ("documents", ComplianceDocument.store_id),
    ("tickets", Ticket.store_id),
    ("cash purchases", CashPurchase.store_id),
    ("cash adjustments", CashAdjustment.store_id),
    ("cash sync records", CashSyncRecord.store_id),
    ("bottles", Bottle.current_store_id),
    ("bottle scans", BottleScan.store_id),
    ("delivery confirmations", DeliveryConfirmation.store_id),
    ("vendor rates", VendorRate.store_id),
)

_FILL_FIELDS = ("entity", "state", "city", "address", "poc_name", "poc_number", "vendor_name", "vendor_number", "region_id")


def _partner(db: Session, slug: str) -> Organization:
    org = db.execute(
        select(Organization).where(Organization.slug == slug.strip().lower(), Organization.kind == OrganizationKind.PARTNER.value)
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Platform '{slug}' not found.")
    return org


def _counts(db: Session, store_id: uuid.UUID) -> dict[str, int]:
    out = {}
    for label, col in _MOVES:
        out[label] = int(db.execute(select(func.count()).select_from(col.class_).where(col == store_id)).scalar_one())
    return out


def _collisions(db: Session, old_id: uuid.UUID, new_id: uuid.UUID) -> list[str]:
    """Reasons this pair cannot be merged without overwriting something."""
    why = []
    n = db.execute(
        select(func.count()).select_from(OrderEntry).where(
            OrderEntry.store_id == old_id,
            OrderEntry.order_date.in_(select(OrderEntry.order_date).where(OrderEntry.store_id == new_id)),
        )
    ).scalar_one()
    if n:
        why.append(f"{n} order day{'s' if n > 1 else ''} are entered on both stores")
    old_docs = db.execute(select(ComplianceDocument.month, ComplianceDocument.kind).where(ComplianceDocument.store_id == old_id)).all()
    if old_docs:
        have = set(db.execute(select(ComplianceDocument.month, ComplianceDocument.kind).where(ComplianceDocument.store_id == new_id)).all())
        both = sum(1 for d in old_docs if tuple(d) in have)
        if both:
            why.append(f"{both} compliance document{'s' if both > 1 else ''} exist for the same month on both stores")
    old_del = db.execute(select(DeliveryConfirmation.account_id, DeliveryConfirmation.delivery_date).where(DeliveryConfirmation.store_id == old_id)).all()
    if old_del:
        have = set(db.execute(select(DeliveryConfirmation.account_id, DeliveryConfirmation.delivery_date).where(DeliveryConfirmation.store_id == new_id)).all())
        both = sum(1 for d in old_del if tuple(d) in have)
        if both:
            why.append(f"{both} delivery confirmation{'s' if both > 1 else ''} exist for the same day on both stores")
    return why


def suggestions(db: Session, actor: User, platform_slug: str) -> list[dict]:
    """Pairs that look like the same outlet under two Outlet IDs: exactly two stores of the platform with the same name.
    The older one is offered as the temporary (old) store."""
    partner = _partner(db, platform_slug)
    stores = db.execute(
        select(Store).where(Store.organization_id == actor.organization_id, Store.partner_organization_id == partner.id)
    ).scalars().all()
    groups: dict[str, list[Store]] = {}
    for s in stores:
        key = " ".join((s.name or "").lower().split())
        if key:
            groups.setdefault(key, []).append(s)
    days = dict(
        db.execute(
            select(OrderEntry.store_id, func.count()).where(OrderEntry.store_id.in_([s.id for g in groups.values() if len(g) == 2 for s in g])).group_by(OrderEntry.store_id)
        ).all()
    ) if any(len(g) == 2 for g in groups.values()) else {}
    out = []
    for g in groups.values():
        if len(g) != 2:
            continue
        old, new = sorted(g, key=lambda s: s.created_at)
        out.append({
            "name": new.name, "old_code": old.external_code, "new_code": new.external_code,
            "old_order_days": int(days.get(old.id, 0)), "new_order_days": int(days.get(new.id, 0)),
        })
    return sorted(out, key=lambda r: r["name"].lower())


def _merge_one(db: Session, actor: User, old: Store, new: Store) -> dict[str, int]:
    moved = _counts(db, old.id)
    for _, col in _MOVES:
        db.execute(update(col.class_).where(col == old.id).values({col.key: new.id}))

    # vendors / POCs that look after the old store now look after the new one
    db.execute(
        pg_insert(ExternalAccountStore)
        .from_select(["account_id", "store_id"], select(ExternalAccountStore.account_id, literal(new.id)).where(ExternalAccountStore.store_id == old.id))
        .on_conflict_do_nothing()
    )

    # a per-store cap stays with the new store when it already has one
    if db.execute(select(StoreCap.id).where(StoreCap.store_id == new.id)).first() is None:
        moved["caps"] = db.execute(update(StoreCap).where(StoreCap.store_id == old.id).values(store_id=new.id)).rowcount or 0

    # vendor history: the old store's past vendors follow; its current vendor's period replaces the new store's when it is the
    # same vendor (it carries the real start date), otherwise it is closed today and kept as history
    today = datetime.now(timezone.utc).date()
    old_open = db.execute(select(StoreVendorPeriod).where(StoreVendorPeriod.store_id == old.id, StoreVendorPeriod.end_date.is_(None))).scalar_one_or_none()
    new_open = db.execute(select(StoreVendorPeriod).where(StoreVendorPeriod.store_id == new.id, StoreVendorPeriod.end_date.is_(None))).scalar_one_or_none()
    if old_open is not None:
        if new_open is None:
            pass                                              # moves as it is (still the open one)
        elif vendor_history_service.same_vendor(old_open.vendor_name, new_open.vendor_name):
            db.execute(delete(StoreVendorPeriod).where(StoreVendorPeriod.id == new_open.id))
        else:
            old_open.end_date = today
        db.flush()
    moved["vendor periods"] = db.execute(update(StoreVendorPeriod).where(StoreVendorPeriod.store_id == old.id).values(store_id=new.id)).rowcount or 0

    # details typed in by hand on the old store fill the blanks of the new one; the sheet's values win where it has them
    for f in _FILL_FIELDS:
        if not getattr(new, f) and getattr(old, f):
            setattr(new, f, getattr(old, f))
    if old.start_date and (new.start_date is None or old.start_date < new.start_date):
        new.start_date = old.start_date
    if new.status == StoreStatus.PENDING.value and old.status != StoreStatus.PENDING.value:
        new.status = old.status
    db.flush()

    activity_service.record(
        db, actor=actor, action="store.merged", entity_type="store", entity_id=new.id,
        metadata={"from_code": old.external_code, "to_code": new.external_code, "name": new.name,
                  "moved": {k: int(v) for k, v in moved.items() if v}},
    )
    db.execute(delete(Store).where(Store.id == old.id))
    return moved


def merge(db: Session, actor: User, platform_slug: str, pairs: list[tuple[str, str]], *, dry_run: bool = True) -> dict:
    """Merge each (old Outlet ID, new Outlet ID) pair of one platform. `dry_run` only reports what would move."""
    partner = _partner(db, platform_slug)
    if not pairs:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Add at least one pair of Outlet IDs.")
    if len(pairs) > 2000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Merge at most 2,000 stores at a time.")
    by_code = {
        s.external_code: s
        for s in db.execute(
            select(Store).where(Store.organization_id == actor.organization_id, Store.partner_organization_id == partner.id)
        ).scalars()
    }
    results, used = [], set()
    merged = 0
    for old_code, new_code in pairs:
        old_code, new_code = old_code.strip(), new_code.strip()
        row = {"old_code": old_code, "new_code": new_code, "name": None, "ok": False, "reason": None, "moved": {}}
        old, new = by_code.get(old_code), by_code.get(new_code)
        if old is None:
            row["reason"] = f"Outlet ID '{old_code}' was not found on {partner.name}."
        elif new is None:
            row["reason"] = f"Outlet ID '{new_code}' was not found on {partner.name}. Upload the sheet with the real IDs first."
        elif old.id == new.id:
            row["reason"] = "The old and the new Outlet ID are the same."
        elif old.id in used or new.id in used:
            row["reason"] = "This store appears in more than one pair."
        else:
            row["name"] = new.name
            blockers = _collisions(db, old.id, new.id)
            if blockers:
                row["reason"] = "Not merged: " + "; ".join(blockers) + ". Resolve those first."
            elif dry_run:
                row["ok"] = True
                row["moved"] = {k: v for k, v in _counts(db, old.id).items() if v}
            else:
                try:
                    with db.begin_nested():
                        row["moved"] = {k: int(v) for k, v in _merge_one(db, actor, old, new).items() if v}
                    row["ok"] = True
                except Exception as exc:  # one bad pair must not undo the others
                    row["reason"] = f"Could not merge: {type(exc).__name__}"
            used.update({old.id, new.id})
        merged += 1 if row["ok"] else 0
        results.append(row)
    if not dry_run and merged:
        db.commit()
    elif not dry_run:
        db.rollback()
    return {"platform": partner.name, "dry_run": dry_run, "merged": merged, "skipped": len(results) - merged, "results": results}
