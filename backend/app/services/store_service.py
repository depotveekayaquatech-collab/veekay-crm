"""Store CRUD. Scoped to the caller's (Veekay) organization."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization, OrganizationKind
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
    activity_service.record(
        db, actor=actor, action="store.created", entity_type="store", entity_id=store.id,
        metadata={"name": store.name, "external_code": store.external_code},
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
    for field, value in data.items():
        setattr(store, field, value)
    activity_service.record(
        db, actor=actor, action="store.updated", entity_type="store", entity_id=store.id,
        metadata={k: str(v) for k, v in data.items()},
    )
    db.commit()
    return to_out(require_store(db, actor, store.id))


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
