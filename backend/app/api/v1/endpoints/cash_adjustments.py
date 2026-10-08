import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.cash_adjustment import AdjustmentList, AdjustRequest, ApplyResult, Preview, StoreChoice
from app.schemas.cash_sync import (
    RecordEdit, RecordIds, ResolveRequest, StandardRate, StandardRateResult, SyncApplyResult, SyncOverview, SyncPreview, SyncRecordOut, SyncRunOut, SyncSummary,
)
from app.services import cash_adjustment_service as svc
from app.services import cash_analysis_service as analysis_svc
from app.services import cash_purchase_service, cash_sync_service as sync_svc

# Developer-only: every route needs the reserved `cash.adjust` permission, which only the developer role can hold.
router = APIRouter(
    prefix="/developer/cash-adjustments", tags=["developer"],
    dependencies=[Depends(require_permission("cash.adjust"))],
)


@router.get("/stores", response_model=list[StoreChoice])
def stores(
    q: str | None = Query(None, max_length=100), limit: int = Query(200, ge=1, le=500),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[StoreChoice]:
    """Live stores to pick from."""
    return svc.search_stores(db, user, q, limit)


@router.post("/preview", response_model=Preview)
def preview(body: AdjustRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Preview:
    """Calculates the quantity and shows 'existing -> new' per store. Changes nothing."""
    return svc.preview(db, user, body)


@router.post("/apply", response_model=ApplyResult)
def apply(body: AdjustRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ApplyResult:
    """Adds the quantity to each store's existing entry for the date (never replaces it) and records the history."""
    return svc.apply(db, user, body)


@router.get("/history", response_model=AdjustmentList)
def history(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    start: date | None = None, end: date | None = None, q: str | None = Query(None, max_length=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> AdjustmentList:
    return svc.history(db, user, page=page, page_size=page_size, start=start, end=end, q=q)


@router.get("/history/export")
def history_export(
    start: date | None = None, end: date | None = None, q: str | None = Query(None, max_length=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    return Response(
        content=svc.history_xlsx(db, user, start=start, end=end, q=q),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="cash-purchase-history.xlsx"', "Cache-Control": "private, no-store"},
    )


# ---- the store purchase sheet: download + Sync Cash Purchase ------------------------------------------------------

@router.get("/purchase-sheet")
def purchase_sheet(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Download the Cash Purchase / Store Purchase sheet (every recorded purchase, office and stores)."""
    data = cash_purchase_service.export_xlsx(
        db, user, {"cash.view"}, kind=None, start=None, end=None, category=None, store_id=None, q=None
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="cash-purchase-sheet.xlsx"', "Cache-Control": "private, no-store"},
    )


@router.get("/analysis", response_model=analysis_svc.Analysis)
def analysis(
    start: date | None = None, end: date | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> analysis_svc.Analysis:
    """Vendors ranked by how many cash purchases their stores needed, with flags and the store names."""
    return analysis_svc.analyse(db, user, start, end)


@router.get("/analysis/export")
def analysis_export(
    start: date | None = None, end: date | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    return Response(
        content=analysis_svc.analysis_xlsx(db, user, start, end),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="cash-purchase-vendor-analysis.xlsx"', "Cache-Control": "private, no-store"},
    )


@router.post("/sync", response_model=SyncSummary)
def sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SyncSummary:
    """Bring the latest store purchases into the developer working area. Does NOT change the order sheet."""
    return sync_svc.sync(db, user)


@router.get("/sync/runs", response_model=list[SyncRunOut])
def sync_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SyncRunOut]:
    return sync_svc.runs(db, user)


@router.get("/sync/records", response_model=SyncOverview)
def sync_records(
    status: Literal["PENDING", "CHANGED", "APPLIED", "SKIPPED"] | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> SyncOverview:
    return sync_svc.overview(db, user, status_filter=status, page=page, page_size=page_size)


@router.patch("/sync/records/{record_id}", response_model=SyncRecordOut)
def edit_record(record_id: uuid.UUID, body: RecordEdit, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SyncRecordOut:
    """Correct the store / date / amount / price / final quantity of a synced purchase before applying it."""
    return sync_svc.edit(db, user, record_id, body)


@router.post("/sync/records/{record_id}/resolve", response_model=SyncRecordOut)
def resolve_record(record_id: uuid.UUID, body: ResolveRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SyncRecordOut:
    return sync_svc.resolve(db, user, record_id, body.action)


@router.post("/sync/standard-rate", response_model=StandardRateResult)
def standard_rate(body: StandardRate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StandardRateResult:
    """Set one standard price on every purchase still waiting for review (not just the current page)."""
    return sync_svc.set_standard_rate(db, user, body)


@router.post("/sync/preview", response_model=SyncPreview)
def sync_preview(body: RecordIds, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SyncPreview:
    """'Existing -> new' per store and day for the chosen records. Changes nothing."""
    return sync_svc.preview(db, user, body.record_ids)


@router.post("/sync/apply", response_model=SyncApplyResult)
def sync_apply(body: RecordIds, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SyncApplyResult:
    """The confirmed step: adds the quantities to the order sheet. Anything already applied is refused."""
    return sync_svc.apply(db, user, body.record_ids)
