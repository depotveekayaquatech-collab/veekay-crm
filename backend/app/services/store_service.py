"""Store CRUD. Scoped to the caller's (Veekay) organization."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationKind
from app.models.audit_log import AuditLog
from app.models.order_archive import OrderEntryArchive
from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.user import User
from app.repositories.region_repository import RegionRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.common import Page, PageParams
from app.schemas.store import StoreCreate, StoreOut, StoreUpdate
from app.services import activity_service

_STORE_FIELDS = (
    "name", "external_code", "state", "city", "address",
    "poc_name", "poc_number", "vendor_name", "vendor_number", "start_date",
)


def to_out(store: Store) -> StoreOut:
    return StoreOut(
        id=store.id,
        name=store.name,
        external_code=store.external_code,
        status=store.status,
        entity=store.entity,
        start_date=store.start_date,
        state=store.state,
        city=store.city,
        address=store.address,
        poc_name=store.poc_name,
        poc_number=store.poc_number,
        vendor_name=store.vendor_name,
        vendor_number=store.vendor_number,
        region_id=store.region_id,
        region_name=store.region.name if store.region else None,
        partner_organization_id=store.partner_organization_id,
        partner_slug=store.partner_organization.slug if store.partner_organization else None,
        partner_name=store.partner_organization.name if store.partner_organization else None,
    )


def list_stores(
    db: Session,
    actor: User,
    params: PageParams,
    *,
    region_id: uuid.UUID | None = None,
    partner: str | None = None,
    state: str | None = None,
    store_status: str | None = None,
    search: str | None = None,
) -> Page[StoreOut]:
    stores, total = StoreRepository(db).list(
        actor.organization_id,
        offset=params.offset,
        limit=params.limit,
        region_id=region_id,
        partner_slug=partner,
        state=state,
        status=store_status,
        search=search,
    )
    return Page(
        items=[to_out(s) for s in stores],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


def get_store(db: Session, actor: User, store_id: uuid.UUID) -> StoreOut:
    return to_out(require_store(db, actor, store_id))


def create_store(db: Session, actor: User, payload: StoreCreate) -> StoreOut:
    _validate_partner(db, payload.partner_organization_id)
    if payload.region_id is not None:
        _validate_region(db, actor, payload.region_id)
    repo = StoreRepository(db)
    if repo.get_by_code(payload.partner_organization_id, payload.external_code):
        raise HTTPException(status.HTTP_409_CONFLICT, "A store with this code already exists for this partner.")
    store = repo.add(
        Store(
            organization_id=actor.organization_id,
            partner_organization_id=payload.partner_organization_id,
            region_id=payload.region_id,
            status=payload.status.value,
            **{f: getattr(payload, f) for f in _STORE_FIELDS},
        )
    )
    restored = restore_archived_history(db, actor.organization_id, store.partner_organization_id)
    activity_service.record(
        db, actor=actor, action="store.created", entity_type="store", entity_id=store.id,
        metadata={"name": store.name, "external_code": store.external_code, "history_restored_days": restored},
    )
    db.commit()
    return to_out(require_store(db, actor, store.id))


def update_store(db: Session, actor: User, store_id: uuid.UUID, payload: StoreUpdate) -> StoreOut:
    store = require_store(db, actor, store_id)
    data = payload.model_dump(exclude_unset=True)
    if "region_id" in data and data["region_id"] is not None:
        _validate_region(db, actor, data["region_id"])
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value if hasattr(data["status"], "value") else data["status"]
    old_status = store.status
    for field, value in data.items():
        setattr(store, field, value)
    activity_service.record(
        db, actor=actor, action="store.updated", entity_type="store", entity_id=store.id,
        metadata={k: str(v) for k, v in data.items()},
    )
    if store.status != old_status:
        record_status_change(db, actor, store, old_status)
    db.commit()
    return to_out(require_store(db, actor, store.id))


def record_status_change(db: Session, actor: User, store: Store, old_status: str) -> None:
    """Audit a LIVE/PENDING/CLOSE change together with how much order history the store holds at that moment.
    Order entries are never touched by a status change: a store that leaves LIVE keeps every entry, and the
    matrix / reports keep showing it for any period that has entries."""
    entries, bottles, first, last = db.execute(
        select(func.count(OrderEntry.id), func.coalesce(func.sum(OrderEntry.bottle_count), 0),
               func.min(OrderEntry.order_date), func.max(OrderEntry.order_date))
        .where(OrderEntry.store_id == store.id)
    ).one()
    activity_service.record(
        db, actor=actor, action="store.status_changed", entity_type="store", entity_id=store.id,
        metadata={
            "from": old_status, "to": store.status, "name": store.name, "external_code": store.external_code,
            "order_days_kept": int(entries), "bottles_kept": int(bottles),
            "first_order": str(first) if first else None, "last_order": str(last) if last else None,
        },
    )


def record_status_changes(db: Session, actor: User, changes: list[tuple[Store, str]]) -> None:
    """record_status_change for many stores with two queries in total (used by the sheet sync / file import)."""
    if not changes:
        return
    stats = {
        sid: (n, b, first, last)
        for sid, n, b, first, last in db.execute(
            select(OrderEntry.store_id, func.count(OrderEntry.id), func.coalesce(func.sum(OrderEntry.bottle_count), 0),
                   func.min(OrderEntry.order_date), func.max(OrderEntry.order_date))
            .where(OrderEntry.store_id.in_([s.id for s, _ in changes]))
            .group_by(OrderEntry.store_id)
        )
    }
    for store, old in changes:
        n, b, first, last = stats.get(store.id, (0, 0, None, None))
        db.add(AuditLog(
            user_id=actor.id, organization_id=actor.organization_id, action="store.status_changed",
            entity_type="store", entity_id=str(store.id),
            metadata_json={
                "from": old, "to": store.status, "name": store.name, "external_code": store.external_code,
                "order_days_kept": int(n), "bottles_kept": int(b),
                "first_order": str(first) if first else None, "last_order": str(last) if last else None,
            },
        ))
    db.flush()


def delete_all_stores(db: Session, actor: User, platform_slug: str | None) -> dict:
    """Hard-delete every store of one platform (or of all platforms when `platform_slug` is None) so a wrongly
    imported list can be replaced. The database cascades to each store's order entries, compliance documents,
    tickets and partner logins; bottles / cash records only lose their store link. Not undoable."""
    cond = [Store.organization_id == actor.organization_id]
    label = "all platforms"
    if platform_slug:
        partner = db.execute(
            select(Organization).where(Organization.slug == platform_slug, Organization.kind == OrganizationKind.PARTNER.value)
        ).scalar_one_or_none()
        if partner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Platform not found.")
        cond.append(Store.partner_organization_id == partner.id)
        label = partner.name
    ids = select(Store.id).where(*cond)
    entries = db.execute(select(func.count(OrderEntry.id)).where(OrderEntry.store_id.in_(ids))).scalar_one()
    # Safety copy first: the delete below cascades to order_entries, but the history stays in the archive and
    # comes back by itself when a store with the same platform + code is created or imported again.
    src = (
        select(
            func.gen_random_uuid(), func.now(), func.now(), Store.organization_id, Store.partner_organization_id,
            Store.external_code, Store.name, Store.state, Store.city,
            OrderEntry.order_date, OrderEntry.bottle_count, OrderEntry.cash_adjustment, OrderEntry.source,
        )
        .select_from(OrderEntry).join(Store, Store.id == OrderEntry.store_id)
        .where(Store.id.in_(ids))
    )
    arch = pg_insert(OrderEntryArchive).from_select(
        ["id", "created_at", "updated_at", "organization_id", "partner_organization_id", "external_code", "store_name",
         "state", "city", "order_date", "bottle_count", "cash_adjustment", "source"], src,
    )
    db.execute(arch.on_conflict_do_update(
        constraint="uq_order_archive_store_date",
        set_={"bottle_count": arch.excluded.bottle_count, "cash_adjustment": arch.excluded.cash_adjustment,
              "source": arch.excluded.source, "store_name": arch.excluded.store_name, "updated_at": func.now()},
    ))
    result = db.execute(delete(Store).where(*cond))
    stores = int(result.rowcount or 0)
    activity_service.record(
        db, actor=actor, action="store.deleted_all", entity_type="organization", entity_id=actor.organization_id,
        metadata={"platform": platform_slug or "all", "stores": stores, "order_entries": int(entries), "archived": True},
    )
    db.commit()
    return {"platform": label, "stores_deleted": stores, "order_entries_deleted": int(entries), "order_entries_archived": int(entries)}


def _partner_by_slug(db: Session, slug: str) -> Organization:
    org = db.execute(
        select(Organization).where(Organization.slug == slug.strip().lower(), Organization.kind == OrganizationKind.PARTNER.value)
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Platform '{slug}' not found.")
    return org


def move_stores(db: Session, actor: User, from_slug: str, to_slug: str, contains: str = "", *, dry_run: bool = True) -> dict:
    """Re-file stores that were imported under the wrong platform. Store ids stay, so order history, documents and
    tickets move with them. A store whose Outlet ID already exists on the target platform is left where it is."""
    src, dst = _partner_by_slug(db, from_slug), _partner_by_slug(db, to_slug)
    if src.id == dst.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose two different platforms.")
    cond = [Store.organization_id == actor.organization_id, Store.partner_organization_id == src.id]
    needle = contains.strip()
    if needle:
        like = f"%{needle}%"
        cond.append(Store.name.ilike(like) | Store.external_code.ilike(like))
    taken = select(Store.external_code).where(Store.partner_organization_id == dst.id)
    total = db.execute(select(func.count(Store.id)).where(*cond)).scalar_one()
    movable = (*cond, Store.external_code.not_in(taken))
    n = db.execute(select(func.count(Store.id)).where(*movable)).scalar_one()
    out = {"from": src.name, "to": dst.name, "matched": int(total), "moved": int(n),
           "skipped_duplicates": int(total - n), "dry_run": dry_run}
    if dry_run or n == 0:
        return out
    db.execute(update(Store).where(*movable).values(partner_organization_id=dst.id))
    activity_service.record(
        db, actor=actor, action="store.platform_moved", entity_type="organization", entity_id=actor.organization_id,
        metadata={"from": src.slug, "to": dst.slug, "contains": needle, "moved": int(n)},
    )
    db.commit()
    return out


def restore_archived_history(db: Session, org_id: uuid.UUID, partner_id: uuid.UUID | None = None) -> int:
    """Put archived order days back for stores that exist again (same platform + code). Days a store already has
    are left alone, and every restored archive row is removed. Returns how many days came back."""
    cond = [OrderEntryArchive.organization_id == org_id]
    if partner_id is not None:
        cond.append(OrderEntryArchive.partner_organization_id == partner_id)
    rows = db.execute(
        select(Store.id, Store.organization_id, OrderEntryArchive.id, OrderEntryArchive.order_date,
               OrderEntryArchive.bottle_count, OrderEntryArchive.cash_adjustment, OrderEntryArchive.source)
        .select_from(OrderEntryArchive)
        .join(Store, (Store.partner_organization_id == OrderEntryArchive.partner_organization_id)
              & (Store.external_code == OrderEntryArchive.external_code)
              & (Store.organization_id == OrderEntryArchive.organization_id))
        .where(*cond)
    ).all()
    if not rows:
        return 0
    ins = pg_insert(OrderEntry).values([
        {"id": uuid.uuid4(), "organization_id": o, "store_id": sid, "order_date": d, "bottle_count": n,
         "cash_adjustment": adj, "source": src, "created_at": func.now(), "updated_at": func.now()}
        for sid, o, _aid, d, n, adj, src in rows
    ]).on_conflict_do_nothing(constraint="uq_order_entry_store_date")
    db.execute(ins)
    db.execute(delete(OrderEntryArchive).where(OrderEntryArchive.id.in_([r[2] for r in rows])))
    return len(rows)


def require_store(db: Session, actor: User, store_id: uuid.UUID) -> Store:
    store = StoreRepository(db).get(actor.organization_id, store_id)
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    return store


def _validate_partner(db: Session, partner_org_id: uuid.UUID) -> None:
    org = db.execute(
        select(Organization).where(Organization.id == partner_org_id)
    ).scalar_one_or_none()
    if org is None or org.kind != OrganizationKind.PARTNER.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid partner organization.")


def _validate_region(db: Session, actor: User, region_id: uuid.UUID) -> None:
    if RegionRepository(db).get(actor.organization_id, region_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid region.")
