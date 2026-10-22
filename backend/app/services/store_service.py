"""Store CRUD. Scoped to the caller's (Veekay) organization."""
import uuid
from datetime import datetime, timezone

import re

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

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
        crm_code=store.crm_code,
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


def name_key(name: str | None) -> str:
    """A store name as a match key: capitals and extra spaces do not matter. The name is the store's identity."""
    return " ".join((name or "").lower().split())


def stores_named(db: Session, org_id: uuid.UUID, partner_id: uuid.UUID, name: str | None) -> list[Store]:
    """Stores of this platform that already carry this name."""
    key = name_key(name)
    if not key:
        return []
    squashed = func.lower(func.regexp_replace(func.btrim(Store.name), r"\s+", " ", "g"))
    return list(db.execute(
        select(Store).where(Store.organization_id == org_id, Store.partner_organization_id == partner_id, squashed == key)
    ).scalars().all())


def create_store(db: Session, actor: User, payload: StoreCreate) -> StoreOut:
    _validate_partner(db, payload.partner_organization_id)
    if payload.region_id is not None:
        _validate_region(db, actor, payload.region_id)
    repo = StoreRepository(db)
    if repo.get_by_code(payload.partner_organization_id, payload.external_code):
        raise HTTPException(status.HTTP_409_CONFLICT, "A store with this code already exists for this partner.")
    same_name = stores_named(db, actor.organization_id, payload.partner_organization_id, payload.name)
    if same_name:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A store named '{same_name[0].name}' already exists on this platform (Outlet ID {same_name[0].external_code}). "
            "Store names are unique; to change its Outlet ID, edit that store.",
        )
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
    # The store name is its identity: it is never changed, by anyone. Sending the same name again is harmless.
    if "name" in data:
        if name_key(data["name"]) != name_key(store.name):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A store's name can't be changed. It is how the store is recognised.")
        data.pop("name")
    if "external_code" in data:
        code = (data["external_code"] or "").strip()
        if not code:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The Outlet ID can't be empty.")
        if code == store.external_code:
            data.pop("external_code")
        else:
            clash = StoreRepository(db).get_by_code(store.partner_organization_id, code)
            if clash is not None and clash.id != store.id:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"Outlet ID {code} already belongs to another store on this platform ('{clash.name}'). "
                    "If that is the same outlet, use Merge duplicate stores instead.",
                )
            data["external_code"] = code
    if "region_id" in data and data["region_id"] is not None:
        _validate_region(db, actor, data["region_id"])
    if "status" in data and data["status"] is not None:
        data["status"] = data["status"].value if hasattr(data["status"], "value") else data["status"]
    if "start_date" in data and data["start_date"] is None and store.start_date is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A store's start date can be changed but not removed.")
    old_status = store.status
    old_vendor = store.vendor_name
    for field, value in data.items():
        setattr(store, field, value)
    if ("vendor_name" in data or "vendor_number" in data) and (store.vendor_name or "").strip():
        from app.services import vendor_history_service   # a hand-made vendor change is history too, effective today

        vendor_history_service.record_vendors(
            db, [store], source="manual", today=datetime.now(timezone.utc).date(), changed_by=actor.full_name
        )
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
    moving = list(db.execute(select(Store.id).where(*movable)).scalars().all())
    db.execute(update(Store).where(*movable).values(partner_organization_id=dst.id))
    _drop_caps_outside_zepto(db, moving, dst)
    _reissue_codes(db, moving, dst)
    activity_service.record(
        db, actor=actor, action="store.platform_moved", entity_type="organization", entity_id=actor.organization_id,
        metadata={"from": src.slug, "to": dst.slug, "contains": needle, "moved": int(n)},
    )
    db.commit()
    return out


CAPPING_PLATFORM = "zepto"      # per-store capping exists for this platform only (see capping_service.PLATFORM)


def _reissue_codes(db: Session, store_ids: list[uuid.UUID], dst: Organization) -> None:
    """A store that changes platform gets a code with the new platform's prefix (its id, orders and history do not change)."""
    from app.models.store import issue_crm_code

    conn = db.connection()
    for sid in store_ids:
        db.execute(update(Store).where(Store.id == sid).values(crm_code=issue_crm_code(conn, dst.id)))


def _drop_caps_outside_zepto(db: Session, store_ids: list[uuid.UUID], dst: Organization) -> int:
    """A capping number belongs to a Zepto store. A store that leaves Zepto must not carry it along."""
    if not store_ids or (dst.slug or "").lower() == CAPPING_PLATFORM:
        return 0
    from app.models.store_cap import StoreCap

    n = 0
    for i in range(0, len(store_ids), 1000):
        n += db.execute(delete(StoreCap).where(StoreCap.store_id.in_(store_ids[i:i + 1000]))).rowcount or 0
    return int(n)


def move_store_platform(db: Session, actor: User, store_id: uuid.UUID, to_slug: str) -> dict:
    """Move ONE store to the other platform. It keeps its id, so its orders, documents, tickets and history go with it; a capping number
    stays only when the store is (still) a Zepto store. Refused when the target platform already has a store with this name."""
    store = require_store(db, actor, store_id)
    dst = _partner_by_slug(db, to_slug)
    if store.partner_organization_id == dst.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"This store is already on {dst.name}.")
    same = stores_named(db, actor.organization_id, dst.id, store.name)
    if same:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{dst.name} already has a store named '{same[0].name}' (Outlet ID {same[0].external_code}). Names are unique on a platform: "
            "check which one is the real store before moving.",
        )
    src = db.get(Organization, store.partner_organization_id)
    store.partner_organization_id = dst.id
    caps_removed = _drop_caps_outside_zepto(db, [store.id], dst)
    old_code = store.crm_code
    from app.models.store import issue_crm_code

    store.crm_code = issue_crm_code(db.connection(), dst.id)          # a new platform means a new prefix; the store itself does not change
    from app.services import assignment_service

    if assignment_service.is_employee_model(dst.slug):
        store.region_id = None                 # Zepto stores are scoped by state, not region
    activity_service.record(
        db, actor=actor, action="store.platform_moved", entity_type="store", entity_id=store.id,
        metadata={"name": store.name, "external_code": store.external_code, "from": src.slug if src else None, "to": dst.slug, "capping_removed": caps_removed,
                  "crm_code_from": old_code, "crm_code_to": store.crm_code},
    )
    db.commit()
    return {"id": str(store.id), "name": store.name, "platform": dst.name, "capping_removed": caps_removed}


_ZEPTO_CODE = re.compile(r"^[A-Za-z]{2,5}[_ ][A-Za-z0-9_ ]{3,}$|^[A-Z]{3}\d{3}S$")
_ZEPTO_NAME = re.compile(r"^[A-Za-z]{2,4}-")
_BLINKIT_NAME = re.compile(r"^SS ", re.IGNORECASE)


def platform_check(db: Session, actor: User) -> dict:
    """Stores that look like they are filed under the wrong platform, so someone can check them one by one.

    Evidence used (shown with each store, nothing is moved automatically):
      * the same store name exists on both platforms;
      * a store on Zepto with a Blinkit-style name ("SS ...") or an all-digit Outlet ID, or on Blinkit with a Zepto-style Outlet ID
        ("DEL_CNGTPL_P01R0CC") or a Zepto-style name;
      * a capping number on a store that is not on Zepto (capping is Zepto-only).
    """
    from app.models.store_cap import StoreCap

    partners = {p.id: p for p in db.execute(select(Organization).where(Organization.kind == OrganizationKind.PARTNER.value)).scalars()}
    stores = db.execute(select(Store).where(Store.organization_id == actor.organization_id)).scalars().all()
    capped = set(db.execute(select(StoreCap.store_id)).scalars().all())
    days = dict(db.execute(select(OrderEntry.store_id, func.count()).group_by(OrderEntry.store_id)).all())
    names: dict[str, list[Store]] = {}
    for s in stores:
        names.setdefault(name_key(s.name), []).append(s)

    rows: dict[uuid.UUID, dict] = {}

    def flag(s: Store, reason: str, suggest: str | None) -> None:
        plat = partners.get(s.partner_organization_id)
        row = rows.setdefault(s.id, {
            "store": to_out(s).model_dump(mode="json"), "order_days": int(days.get(s.id, 0)), "has_capping": s.id in capped,
            "reasons": [], "suggested_platform": suggest, "platform": plat.name if plat else None,
        })
        row["reasons"].append(reason)
        row["suggested_platform"] = row["suggested_platform"] or suggest

    for key, group in names.items():
        plats = {s.partner_organization_id for s in group}
        if key and len(plats) > 1:
            for s in group:
                others = sorted({partners[o.partner_organization_id].name for o in group if o.partner_organization_id != s.partner_organization_id if o.partner_organization_id in partners})
                flag(s, f"The same name also exists on {', '.join(others)}", None)
    for s in stores:
        plat = partners.get(s.partner_organization_id)
        slug = (plat.slug if plat else "").lower()
        code, name = (s.external_code or "").strip(), (s.name or "").strip()
        if slug == "zepto":
            if _BLINKIT_NAME.match(name):
                flag(s, f"On Zepto but named like a Blinkit store ('{name}')", "blinkit")
            elif code.isdigit():
                flag(s, f"On Zepto but its Outlet ID ({code}) is a plain number, like Blinkit's", "blinkit")
        elif slug == "blinkit":
            if _ZEPTO_CODE.match(code) and ("_" in code):
                flag(s, f"On Blinkit but its Outlet ID ({code}) looks like a Zepto code", "zepto")
        if slug != CAPPING_PLATFORM and s.id in capped:
            flag(s, "Has a Zepto capping number although it is not a Zepto store", None)
    out = sorted(rows.values(), key=lambda r: (r["platform"] or "", r["store"]["name"].lower()))
    return {"total": len(out), "stores": out[:500]}


def restore_archived_history(db: Session, org_id: uuid.UUID, partner_id: uuid.UUID | None = None) -> int:
    """Put archived order days back for stores that exist again (same platform + code). Days a store already has
    are left alone, and every restored archive row is removed. Returns how many days came back.

    Done entirely inside the database (INSERT ... SELECT, then DELETE ... USING): after "Remove all stores" the archive
    holds a platform's WHOLE order history (hundreds of thousands of rows), and pulling that into Python and building one
    giant statement is what exhausted the server's memory. Memory use here no longer depends on the archive size."""
    A = OrderEntryArchive
    twin = aliased(Store)
    same_store = (
        (Store.partner_organization_id == A.partner_organization_id)
        & (Store.external_code == A.external_code)
        & (Store.organization_id == A.organization_id)
        # an Outlet ID that two stores share could put the history on the wrong one: those wait until it is corrected
        & ~select(twin.id).where(twin.partner_organization_id == Store.partner_organization_id,
                                 twin.external_code == Store.external_code, twin.id != Store.id).exists()
    )
    cond = [A.organization_id == org_id]
    if partner_id is not None:
        cond.append(A.partner_organization_id == partner_id)

    src = (
        select(func.gen_random_uuid(), func.now(), func.now(), Store.organization_id, Store.id, A.order_date,
               A.bottle_count, A.cash_adjustment, A.source)
        .select_from(A).join(Store, same_store).where(*cond)
    )
    ins = pg_insert(OrderEntry).from_select(
        ["id", "created_at", "updated_at", "organization_id", "store_id", "order_date", "bottle_count",
         "cash_adjustment", "source"], src,
    ).on_conflict_do_nothing(constraint="uq_order_entry_store_date")
    db.execute(ins)

    # drop the archive rows whose store exists again (their days are now in order_entries, or the store already had that day)
    matched = select(A.id).select_from(A).join(Store, same_store).where(*cond)
    res = db.execute(delete(A).where(A.id.in_(matched)))
    return int(res.rowcount or 0)


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


def delete_closed(
    db: Session, actor: User, *, platform_slug: str | None = None, store_ids: list[uuid.UUID] | None = None, dry_run: bool = True
) -> dict:
    """Delete Closed stores that hold no history at all. A closed store is kept (and counted) when it has any order day, any
    archived order history under its Outlet ID, or any other record (documents, tickets, cash purchases, bottles, deliveries...):
    deleting it would lose that. `store_ids` narrows it to chosen stores; `dry_run` only reports."""
    from app.services.store_merge_service import _MOVES      # every column that points at a store

    cond = [Store.organization_id == actor.organization_id, Store.status == "CLOSE"]
    if platform_slug:
        cond.append(Store.partner_organization_id == _partner_by_slug(db, platform_slug).id)
    if store_ids is not None:
        cond.append(Store.id.in_(store_ids))
    closed = db.execute(
        select(Store.id, Store.name, Store.external_code, Store.partner_organization_id, Organization.name)
        .join(Organization, Organization.id == Store.partner_organization_id)
        .where(*cond).order_by(Organization.name, Store.name)
    ).all()
    ids = [r[0] for r in closed]

    def holders(col) -> set[uuid.UUID]:
        return set(db.execute(select(col).where(col.in_(ids)).distinct()).scalars().all()) if ids else set()

    with_orders = holders(OrderEntry.store_id)
    archived: set[uuid.UUID] = set()
    if ids:
        pairs = {(r[3], r[2]): r[0] for r in closed}
        for partner_id, code in db.execute(
            select(OrderEntryArchive.partner_organization_id, OrderEntryArchive.external_code)
            .where(OrderEntryArchive.organization_id == actor.organization_id,
                   OrderEntryArchive.partner_organization_id.in_({p for p, _ in pairs}))
            .distinct()
        ).all():
            if (partner_id, code) in pairs:
                archived.add(pairs[(partner_id, code)])
    with_orders |= archived
    with_other: set[uuid.UUID] = set()
    for label, col in _MOVES:
        if col is not OrderEntry.store_id:
            with_other |= holders(col)
    with_other -= with_orders

    deletable = [r for r in closed if r[0] not in with_orders and r[0] not in with_other]
    out = {
        "dry_run": dry_run, "closed": len(closed), "deletable_count": len(deletable),
        "kept_with_orders": len([r for r in closed if r[0] in with_orders]),
        "kept_with_other_records": len([r for r in closed if r[0] in with_other]),
        "deletable": [{"id": str(r[0]), "name": r[1], "external_code": r[2], "platform": r[4]} for r in deletable[:500]],
        "deleted": 0,
    }
    if dry_run or not deletable:
        return out
    gone = [r[0] for r in deletable]
    for i in range(0, len(gone), 500):
        db.execute(delete(Store).where(Store.id.in_(gone[i:i + 500])))
    activity_service.record(
        db, actor=actor, action="store.deleted_closed", entity_type="organization", entity_id=actor.organization_id,
        metadata={"deleted": len(gone), "stores": [{"name": r[1], "external_code": r[2], "platform": r[4]} for r in deletable[:200]]},
    )
    db.commit()
    out["deleted"] = len(gone)
    return out
