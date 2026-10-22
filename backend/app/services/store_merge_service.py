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


def merge(db: Session, actor: User, platform_slug: str, pairs: list[dict], *, dry_run: bool = True) -> dict:
    """Merge each (old store, new store) pair of one platform. A side is named by its store id (exact) or by its Outlet ID (only
    when no other store shares that ID). `dry_run` only reports what would move."""
    partner = _partner(db, platform_slug)
    if not pairs:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Add at least one pair of stores.")
    if len(pairs) > 2000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Merge at most 2,000 stores at a time.")
    all_stores = db.execute(
        select(Store).where(Store.organization_id == actor.organization_id, Store.partner_organization_id == partner.id)
    ).scalars().all()
    by_id = {s.id: s for s in all_stores}
    by_code: dict[str, list[Store]] = {}
    for s in all_stores:
        by_code.setdefault(s.external_code, []).append(s)

    def find(store_id, code: str) -> tuple[Store | None, str]:
        if store_id is not None:
            s = by_id.get(store_id)
            return s, "" if s else f"A store of {partner.name} with that id was not found."
        hits = by_code.get(code, [])
        if len(hits) == 1:
            return hits[0], ""
        if not hits:
            return None, f"Outlet ID '{code}' was not found on {partner.name}."
        return None, f"{len(hits)} stores share Outlet ID '{code}': merge them from Stores > Duplicates, where each is picked exactly."

    results, used = [], set()
    merged = 0
    for pair in pairs:
        old_code, new_code = (pair.get("old_code") or "").strip(), (pair.get("new_code") or "").strip()
        old, why_old = find(pair.get("old_id"), old_code)
        new, why_new = find(pair.get("new_id"), new_code)
        row = {"old_code": old.external_code if old else old_code, "new_code": new.external_code if new else new_code,
               "name": None, "ok": False, "reason": None, "moved": {}}
        if old is None:
            row["reason"] = why_old
        elif new is None:
            row["reason"] = why_new + (" Upload the sheet with the real IDs first." if "was not found" in why_new else "")
        elif old.id == new.id:
            row["reason"] = "The old and the new store are the same."
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


def _code_key(code: str | None) -> str:
    return "".join(ch for ch in (code or "").lower() if ch.isalnum())


def duplicates(db: Session, actor: User) -> dict:
    """Stores that exist more than once: the same name on one platform, or the same Outlet ID once capitals, spaces and dashes are
    ignored. Names are the store's identity, so every group here is something to fix (edit the ID, or merge)."""
    from app.services import store_service

    stores = db.execute(
        select(Store).where(Store.organization_id == actor.organization_id)
    ).scalars().all()
    by_name: dict[tuple, list[Store]] = {}
    by_code: dict[tuple, list[Store]] = {}
    for s in stores:
        nk = store_service.name_key(s.name)
        if nk:
            by_name.setdefault((s.partner_organization_id, nk), []).append(s)
        ck = _code_key(s.external_code)
        if ck:
            by_code.setdefault((s.partner_organization_id, ck), []).append(s)
    wanted = [(k, "name", g) for k, g in by_name.items() if len(g) > 1] + [(k, "id", g) for k, g in by_code.items() if len(g) > 1]
    ids = {s.id for _, _, g in wanted for s in g}
    days = dict(
        db.execute(select(OrderEntry.store_id, func.count()).where(OrderEntry.store_id.in_(ids)).group_by(OrderEntry.store_id)).all()
    ) if ids else {}
    month_start = date.today().replace(day=1)
    this_month = dict(
        db.execute(
            select(OrderEntry.store_id, func.count()).where(OrderEntry.store_id.in_(ids), OrderEntry.order_date >= month_start).group_by(OrderEntry.store_id)
        ).all()
    ) if ids else {}
    groups = []
    for _, kind, g in wanted:
        g = sorted(g, key=lambda s: s.created_at)
        first = g[0]
        groups.append({
            "kind": kind,
            "label": first.name if kind == "name" else first.external_code,
            "platform": first.partner_organization.name if first.partner_organization else None,
            "stores": [{**store_service.to_out(s).model_dump(mode="json"), "order_days": int(days.get(s.id, 0)),
                        "order_days_this_month": int(this_month.get(s.id, 0)), "created_at": s.created_at.isoformat()} for s in g],
            # entries for the current month sit on more than one copy: employees and the CRM can be looking at different ones
            "entries_split": sum(1 for s in g if this_month.get(s.id)) > 1,
        })
    groups.sort(key=lambda x: ((x["platform"] or "").lower(), x["kind"], x["label"].lower()))
    return {"total_groups": len(groups), "total_stores": len(ids), "groups": groups}


def import_issues(db: Session, actor: User) -> dict:
    """What each platform's latest store upload could not use, with the stores the CRM holds under the same name, so one person can
    work through them. The upload keeps up to 300 rows per run."""
    from app.models.audit_log import AuditLog
    from app.services import store_service

    out = []
    partners = db.execute(
        select(Organization).where(Organization.kind == OrganizationKind.PARTNER.value).order_by(Organization.name)
    ).scalars().all()
    for partner in partners:
        run = db.execute(
            select(AuditLog).where(AuditLog.action == "store.synced", AuditLog.entity_id == str(partner.id))
            .order_by(AuditLog.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if run is None:
            continue
        meta = run.metadata_json or {}
        issues = list(meta.get("issues") or [])
        by_name: dict[str, list[Store]] = {}
        if issues:
            for s in db.execute(select(Store).where(Store.organization_id == actor.organization_id, Store.partner_organization_id == partner.id)).scalars():
                by_name.setdefault(store_service.name_key(s.name), []).append(s)
        for it in issues:
            same = by_name.get(store_service.name_key(it.get("name")), [])
            it["crm_stores"] = [{"id": str(s.id), "external_code": s.external_code, "status": s.status} for s in same[:6]]
        out.append({
            "platform": partner.name, "platform_slug": partner.slug, "at": run.created_at.isoformat(), "source": meta.get("source"),
            "rows_read": meta.get("rows_read"), "created": meta.get("created"), "updated": meta.get("updated"),
            "issue_count": int(meta.get("issue_count") or len(issues)), "issues": issues,
        })
    return {"runs": out, "total_issues": sum(r["issue_count"] for r in out)}
