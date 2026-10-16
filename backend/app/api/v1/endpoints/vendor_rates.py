"""City-wise vendor rates (what Veekay charges per bottle). Admins only (rates.manage)."""
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import store_sync_service, vendor_rate_service

router = APIRouter(prefix="/vendor-rates", tags=["vendor-rates"], dependencies=[Depends(require_permission("rates.manage"))])


@router.get("")
def list_rates(platform: str = "blinkit", on: date | None = None, db: Session = Depends(get_db)) -> list[dict]:
    """The rates in force on a date (today by default): city rates first, then store-specific ones."""
    return vendor_rate_service.current_rates(db, platform, on)


@router.post("/upload")
async def upload_rates(
    platform: str = Form("blinkit"), confirm: bool = Form(False), effective_from: date | None = Form(None),
    file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Without confirm, a sheet that would CHANGE an existing rate writes nothing and returns what would change;
    upload again with confirm=true to apply. New rates are added without asking."""
    content = await file.read(store_sync_service.MAX_UPLOAD_BYTES + 1)
    return await run_in_threadpool(
        vendor_rate_service.upload, db, user, platform, file.filename or "", content, confirm=confirm, effective_from=effective_from,
    )
