"""Region routes — thin wrappers over region_service."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_page_params, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.region import RegionCreate, RegionOut, RegionUpdate
from app.services import region_service

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("", response_model=Page[RegionOut], dependencies=[Depends(require_permission("regions.view"))])
def list_regions(
    params: PageParams = Depends(get_page_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[RegionOut]:
    return region_service.list_regions(db, user, params)


@router.post(
    "", response_model=RegionOut, status_code=201,
    dependencies=[Depends(require_permission("regions.manage"))],
)
def create_region(
    payload: RegionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RegionOut:
    return region_service.create_region(db, user, payload)


@router.get(
    "/{region_id}", response_model=RegionOut,
    dependencies=[Depends(require_permission("regions.view"))],
)
def get_region(
    region_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RegionOut:
    return region_service.get_region(db, user, region_id)


@router.patch(
    "/{region_id}", response_model=RegionOut,
    dependencies=[Depends(require_permission("regions.manage"))],
)
def update_region(
    region_id: uuid.UUID,
    payload: RegionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RegionOut:
    return region_service.update_region(db, user, region_id, payload)


@router.delete(
    "/{region_id}", status_code=204,
    dependencies=[Depends(require_permission("regions.manage"))],
)
def deactivate_region(
    region_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    region_service.deactivate_region(db, user, region_id)
