"""Store routes — thin wrappers over store_service."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_page_params, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.store import StoreCreate, StoreOut, StoreSyncResult, StoreUpdate
from app.services import store_service, store_sync_service

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=Page[StoreOut], dependencies=[Depends(require_permission("stores.view"))])
def list_stores(
    region_id: uuid.UUID | None = None,
    partner: str | None = None,
    state: str | None = None,
    store_status: str | None = None,
    search: str | None = None,
    params: PageParams = Depends(get_page_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[StoreOut]:
    return store_service.list_stores(
        db, user, params, region_id=region_id, partner=partner, state=state, store_status=store_status, search=search
    )


@router.post(
    "/sync", response_model=list[StoreSyncResult],
    dependencies=[Depends(require_permission("stores.manage"))],
)
def sync_stores(
    platform: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StoreSyncResult]:
    """Pull stores from the configured Google Sheet(s). `platform` limits it
    to one (e.g. ?platform=blinkit); omitted syncs every configured sheet."""
    try:
        if platform:
            results = [store_sync_service.sync_platform(db, user, platform)]
        else:
            if not store_sync_service.settings.sheet_sources():
                raise store_sync_service.SyncError(
                    "No store sheets are configured. Set STORE_SYNC_SHEETS on the server first."
                )
            results = store_sync_service.sync_all(db, user)
    except store_sync_service.SyncError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return [StoreSyncResult(**r.as_dict()) for r in results]


@router.post(
    "/import", response_model=StoreSyncResult,
    dependencies=[Depends(require_permission("stores.manage"))],
)
async def import_stores(
    platform: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreSyncResult:
    """Upload a .csv / .xlsx outlet list for one platform. Same column
    mapping and upsert rules as the Google Sheet sync."""
    content = await file.read(store_sync_service.MAX_UPLOAD_BYTES + 1)
    try:
        result = store_sync_service.import_file(db, user, platform, file.filename or "", content)
    except store_sync_service.SyncError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except DBAPIError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "The database rejected a value in this file. Check for unusually long or malformed cells.",
        ) from exc
    return StoreSyncResult(**result.as_dict())


@router.post(
    "", response_model=StoreOut, status_code=201,
    dependencies=[Depends(require_permission("stores.manage"))],
)
def create_store(
    payload: StoreCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreOut:
    return store_service.create_store(db, user, payload)


@router.get(
    "/{store_id}", response_model=StoreOut,
    dependencies=[Depends(require_permission("stores.view"))],
)
def get_store(
    store_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreOut:
    return store_service.get_store(db, user, store_id)


@router.patch(
    "/{store_id}", response_model=StoreOut,
    dependencies=[Depends(require_permission("stores.manage"))],
)
def update_store(
    store_id: uuid.UUID,
    payload: StoreUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreOut:
    return store_service.update_store(db, user, store_id, payload)


@router.delete(
    "/{store_id}", response_model=StoreOut,
    dependencies=[Depends(require_permission("stores.manage"))],
)
def close_store(
    store_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreOut:
    """Soft close — sets status to CLOSE (order history is kept)."""
    return store_service.update_store(db, user, store_id, StoreUpdate(status="CLOSE"))
