"""Region CRUD. All operations scoped to the caller's organization."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.region import Region
from app.models.user import User
from app.repositories.region_repository import RegionRepository
from app.schemas.common import Page, PageParams
from app.schemas.region import RegionCreate, RegionOut, RegionUpdate
from app.services import activity_service


def _to_out(region: Region, store_count: int = 0) -> RegionOut:
    return RegionOut(
        id=region.id,
        name=region.name,
        code=region.code,
        is_active=region.is_active,
        store_count=store_count,
    )


def list_regions(db: Session, actor: User, params: PageParams) -> Page[RegionOut]:
    repo = RegionRepository(db)
    regions, total = repo.list(actor.organization_id, offset=params.offset, limit=params.limit)
    counts = repo.store_counts([r.id for r in regions])
    items = [_to_out(r, counts.get(r.id, 0)) for r in regions]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)


def get_region(db: Session, actor: User, region_id: uuid.UUID) -> RegionOut:
    region = _require(db, actor, region_id)
    count = RegionRepository(db).store_counts([region.id]).get(region.id, 0)
    return _to_out(region, count)


def create_region(db: Session, actor: User, payload: RegionCreate) -> RegionOut:
    repo = RegionRepository(db)
    if repo.get_by_code(actor.organization_id, payload.code):
        raise HTTPException(status.HTTP_409_CONFLICT, "A region with this code already exists.")
    region = repo.add(
        Region(organization_id=actor.organization_id, name=payload.name, code=payload.code)
    )
    activity_service.record(
        db, actor=actor, action="region.created", entity_type="region", entity_id=region.id,
        metadata={"name": region.name, "code": region.code},
    )
    db.commit()
    return _to_out(region)


def update_region(db: Session, actor: User, region_id: uuid.UUID, payload: RegionUpdate) -> RegionOut:
    region = _require(db, actor, region_id)
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != region.code:
        if RegionRepository(db).get_by_code(actor.organization_id, data["code"]):
            raise HTTPException(status.HTTP_409_CONFLICT, "A region with this code already exists.")
    for field, value in data.items():
        setattr(region, field, value)
    activity_service.record(
        db, actor=actor, action="region.updated", entity_type="region", entity_id=region.id,
        metadata=data,
    )
    db.commit()
    count = RegionRepository(db).store_counts([region.id]).get(region.id, 0)
    return _to_out(region, count)


def deactivate_region(db: Session, actor: User, region_id: uuid.UUID) -> None:
    region = _require(db, actor, region_id)
    region.is_active = False
    activity_service.record(
        db, actor=actor, action="region.deactivated", entity_type="region", entity_id=region.id,
    )
    db.commit()


def _require(db: Session, actor: User, region_id: uuid.UUID) -> Region:
    region = RegionRepository(db).get(actor.organization_id, region_id)
    if region is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found.")
    return region
