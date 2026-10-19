"""Zepto monthly capping. Employees view and edit caps one store at a time; developers and administrators load them in bulk
from an uploaded sheet (a developer can also read the Google Capping sheet). Employees with capping.alerts see the alerts."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services import capping_service, store_sync_service

router = APIRouter(prefix="/capping", tags=["capping"])


def require_bulk_upload(user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions)) -> User:
    """Bulk loading is for developers (sheets.sync) and administrators (orders.correct). Employees edit one store at a time."""
    if "sheets.sync" not in perms and "orders.correct" not in perms:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator or developer can upload the capping sheet.")
    return user


class CapIn(BaseModel):
    monthly_cap: int | None = Field(default=None, ge=0, le=capping_service.MAX_CAP, description="null clears the cap")


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
    return capping_service.set_cap(db, user, perms, store_id, payload.monthly_cap)


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
        rows = await run_in_threadpool(store_sync_service.rows_from_upload, file.filename or "", content)
    except store_sync_service.SyncError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await run_in_threadpool(capping_service.import_caps, db, user, rows, overwrite=overwrite, source="file")
