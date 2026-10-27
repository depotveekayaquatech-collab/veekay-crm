"""Zepto monthly capping. Employees view and edit caps one store at a time; developers and administrators load them in bulk
from an uploaded sheet (a developer can also read the Google Capping sheet). Employees with capping.alerts see the alerts."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services import capping_history_service, capping_service, store_sync_service

router = APIRouter(prefix="/capping", tags=["capping"])


def require_bulk_upload(user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions)) -> User:
    """Bulk loading is for developers (sheets.sync) and administrators (orders.correct). Employees edit one store at a time."""
    if "sheets.sync" not in perms and "orders.correct" not in perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator or developer can upload the capping sheet.")
    return user


class CapIn(BaseModel):
    # An unknown field is an error: a page still sending the old `monthly_cap` must not be read as "no cap" (which clears it).
    model_config = ConfigDict(extra="forbid")

    daily_cap: int | None = Field(default=None, ge=0, le=capping_service.MAX_CAP, description="bottles per day; the monthly limit is this x 30. null clears the cap")


class CappingChangeIn(BaseModel):
    """A new capping for one store from a date. The names are camelCase (storeId, effectiveFrom); snake_case works too."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    store_id: uuid.UUID = Field(alias="storeId")
    capping: StrictInt = Field(ge=1, le=capping_service.MAX_CAP, description="bottles per day, from the effective date")
    effective_from: date = Field(alias="effectiveFrom", description="today or an earlier date (Asia/Kolkata)")


@router.get("")
def get_report(
    month: str | None = Query(None, description="2026-10; this month by default"),
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Every live Zepto store with its cap, the month's bottles used and an alert level. Read-only for the caller."""
    return capping_service.report(db, user, perms, month)


@router.get("/alerts")
def get_alerts(
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """This month's over-cap / ahead-of-pace stores for the caller's own stores. Needs the capping.alerts permission."""
    return capping_service.alerts(db, user, perms)


@router.put("/stores/{store_id}")
def set_cap(
    store_id: uuid.UUID, payload: CapIn,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    return capping_service.set_cap(db, user, perms, store_id, payload.daily_cap)


@router.post("/sync", dependencies=[Depends(require_permission("sheets.sync"))])
def sync_from_sheet(
    overwrite: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Developer: read the Capping tab of the Zepto sheet. Caps already in the CRM are kept unless overwrite=true."""
    sources = settings.capping_sheet_sources()
    if capping_service.PLATFORM not in sources:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No Capping sheet is configured. Set CAPPING_SYNC_SHEETS (zepto=SHEET_ID:GID).")
    sheet_id, gid = sources[capping_service.PLATFORM]
    try:
        rows = store_sync_service._fetch_rows(sheet_id, gid)  # noqa: SLF001 - same sheet reader the store sync uses
    except store_sync_service.SyncError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return capping_service.import_caps(db, user, rows, overwrite=overwrite, source="sheet")


@router.post("/import", dependencies=[Depends(require_bulk_upload)])
async def import_file(
    overwrite: bool = Form(False), file: UploadFile = File(...),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Developer or administrator: load caps from an uploaded .csv / .xlsx (Outlet ID + Monthly Capping)."""
    from starlette.concurrency import run_in_threadpool

    content = await file.read(store_sync_service.MAX_UPLOAD_BYTES + 1)
    try:
        grids = await run_in_threadpool(capping_service.read_grids, file.filename or "", content)
    except store_sync_service.SyncError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await run_in_threadpool(capping_service.import_grids, db, user, grids, overwrite=overwrite, source="file")


# ---------------------------------------------------------------- capping history, the capping sheet and the average-vs-limit summary

@router.post("/change", status_code=status.HTTP_201_CREATED)
def change_capping(
    payload: CappingChangeIn,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Administrator / manager (capping.change): a store's capping from a date. A past date is allowed (`backdated` is true so the page can have asked first);
    a date that already has a change for the store is refused with 409. There is no edit and no delete."""
    return capping_history_service.change(db, user, perms, payload.store_id, payload.capping, payload.effective_from)


@router.get("/history")
def get_history(
    store_id: uuid.UUID = Query(alias="storeId"),
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """One store's capping changes, newest effective date first."""
    return capping_history_service.history(db, user, perms, store_id)


@router.get("/sheet")
def get_sheet(
    from_: date | None = Query(None, alias="from", description="first date; the 1st of this month by default"),
    to: date | None = Query(None, description="last date; the end of this month by default"),
    store_id: uuid.UUID | None = Query(None, alias="storeId"),
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """The capping in force for every live Zepto store (rows) on every date (columns)."""
    return capping_history_service.sheet(db, user, perms, from_, to, store_id)


@router.get("/sheet/download")
def download_sheet(
    from_: date | None = Query(None, alias="from"), to: date | None = None,
    store_id: uuid.UUID | None = Query(None, alias="storeId"), format: Literal["csv", "xlsx"] = "csv",
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> Response:
    """The same matrix as a file: header Store, then one dd-MMM column per date."""
    content, name = capping_history_service.sheet_file(db, user, perms, from_, to, store_id, format)
    return Response(
        content=content, media_type=capping_history_service.SHEET_MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"},
    )


@router.get("/summary")
def get_summary(
    from_: date | None = Query(None, alias="from"), to: date | None = None,
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> dict:
    """Per store: average daily entry, highest day, the capping in force today and the days above MAX_DAILY_LIMIT, with the alert and why."""
    return capping_history_service.summary(db, user, perms, from_, to)
