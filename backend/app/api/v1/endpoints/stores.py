"""Store routes — thin wrappers over store_service."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, TypeAdapter
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_page_params, require_permission
from app.core.cache import read_cache
from app.core.cached_json import cached_json_response
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.store import StoreCreate, StoreOut, StoreSyncResult, StoreUpdate, VendorPeriodOut
from app.services import store_service, store_sync_service, vendor_history_service

router = APIRouter(prefix="/stores", tags=["stores"])
_ALL_STORES = TypeAdapter(list[StoreOut])


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


@router.get("/all", response_model=list[StoreOut], dependencies=[Depends(require_permission("stores.view"))])
def all_stores(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Every store in ONE request (the filter dropdowns and pickers need the full list). Built, serialised and gzipped
    once, then shared between users until any write happens — instead of the browser walking 16 pages of 100."""
    return cached_json_response(
        request, ("stores-all", user.organization_id),
        lambda: _ALL_STORES.dump_json(store_service.list_stores(db, user, PageParams(page=1, page_size=5000)).items),
    )


@router.post(
    "/sync", response_model=list[StoreSyncResult],
    dependencies=[Depends(require_permission("sheets.sync"))],
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
    dependencies=[Depends(require_permission("sheets.sync"))],
)
def import_stores(
    platform: str = Form(...),
    allow_mismatch: bool = Form(False),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoreSyncResult:
    """Upload a .csv / .xlsx outlet list for one platform. Same column
    mapping and upsert rules as the Google Sheet sync."""
    # A plain `def`: FastAPI runs it in a worker thread. The import is blocking work (parsing + database), and in an
    # `async def` it froze the whole event loop for its duration, so health checks and every other request stalled.
    content = file.file.read(store_sync_service.MAX_UPLOAD_BYTES + 1)
    try:
        result = store_sync_service.import_file(
            db, user, platform, file.filename or "", content, allow_mismatch=allow_mismatch
        )
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


class MovePlatformRequest(BaseModel):
    from_platform: str
    to_platform: str
    contains: str = ""          # only stores whose name or Outlet ID contains this text (blank = all)
    dry_run: bool = True


@router.post("/move-platform", dependencies=[Depends(require_permission("sheets.sync"))])
def move_platform(
    payload: MovePlatformRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Developer only. Re-file stores imported under the wrong platform. Keeps every store id, so order history,
    documents and tickets follow the store. `dry_run` (default) only counts."""
    result = store_service.move_stores(
        db, user, payload.from_platform, payload.to_platform, payload.contains, dry_run=payload.dry_run
    )
    if not payload.dry_run:
        read_cache.invalidate()
    return result


@router.delete("", dependencies=[Depends(require_permission("sheets.sync"))])  # developer-only (reserved permission)
def delete_all_stores(
    platform: str | None = None,
    confirm: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Developer only. Wipe every store of one platform (`?platform=zepto`) or of all platforms (omit it), with their order
    history, so the list can be imported again; their order history is archived first and restored automatically when the
    same stores (platform + code) are added again. `confirm` must be exactly `DELETE <PLATFORM SLUG>` (or
    `DELETE ALL`): a stray call can never remove data."""
    expected = f"DELETE {platform.upper()}" if platform else "DELETE ALL"
    if confirm.strip().upper() != expected:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f'Type "{expected}" to confirm.')
    result = store_service.delete_all_stores(db, user, platform)
    read_cache.invalidate()
    return result


@router.get(
    "/{store_id}/vendors", response_model=list[VendorPeriodOut],
    dependencies=[Depends(require_permission("stores.view"))],
)
def store_vendors(store_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[VendorPeriodOut]:
    """Every vendor that has supplied this store, newest first; the current one has no end date."""
    store_service.require_store(db, user, store_id)
    return [
        VendorPeriodOut(vendor_name=p.vendor_name, vendor_number=p.vendor_number, start_date=p.start_date, end_date=p.end_date,
                        start_confirmed=p.start_confirmed, current=p.end_date is None)
        for p in vendor_history_service.history(db, store_id)
    ]


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
