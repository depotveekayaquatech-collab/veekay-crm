import uuid
from datetime import date
from typing import Literal

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.db.session import get_db
from app.core.config import settings
from app.models.user import User
from app.schemas.cash_purchase import CashPurchaseCreate, CashPurchaseList, CashPurchaseOptions, CashPurchaseOut
from app.services import cash_purchase_service as svc

router = APIRouter(prefix="/cash-purchases", tags=["cash-purchases"])


def _needs_any(user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions)) -> User:
    """cash.view or cash.add is enough to open the tab."""
    if not ({"cash.view", "cash.add"} & perms):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to access this.")
    return user


@router.get("/options", response_model=CashPurchaseOptions)
def options(
    user: User = Depends(_needs_any), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db)
) -> CashPurchaseOptions:
    """Reason dropdowns and the stores this person may pick."""
    return svc.options(db, user, perms)


@router.get("", response_model=CashPurchaseList)
def listing(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    kind: Literal["OFFICE", "STORE"] | None = None,
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
    store_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100),
    user: User = Depends(_needs_any),
    perms: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> CashPurchaseList:
    """cash.view: everyone's purchases. cash.add only: the caller's own."""
    return svc.listing(db, user, perms, page=page, page_size=page_size, kind=kind, start=start, end=end,
                       category=category, store_id=store_id, q=q)


@router.post("", response_model=CashPurchaseOut, status_code=status.HTTP_201_CREATED)
async def create(
    kind: Literal["OFFICE", "STORE"] = Form(...),
    purchase_date: date = Form(...),
    category: str = Form(...),
    amount: str = Form(...),
    store_id: uuid.UUID | None = Form(None),
    other_reason: str | None = Form(None),
    notes: str | None = Form(None),
    proof: UploadFile = File(..., description="Photo (JPG/PNG/WEBP) or PDF of the payment proof"),
    user: User = Depends(require_permission("cash.add")),
    perms: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> CashPurchaseOut:
    """Multipart: the purchase fields plus the payment-proof file (required)."""
    try:
        body = CashPurchaseCreate(
            kind=kind, purchase_date=purchase_date, category=category, amount=Decimal(amount.strip()),
            store_id=store_id or None, other_reason=other_reason or None, notes=notes or None,
        )
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter a valid amount (up to 2 decimals).") from exc
    data = await proof.read(settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024 + 1)
    return svc.create(db, user, perms, body, proof.filename or "", data)


@router.get("/{purchase_id}/proof")
def proof_file(
    purchase_id: uuid.UUID,
    user: User = Depends(_needs_any),
    perms: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> Response:
    data, content_type, name = svc.read_proof(db, user, perms, purchase_id)
    return Response(
        content=data, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store"},
    )


@router.get("/export")
def export(
    kind: Literal["OFFICE", "STORE"] | None = None,
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
    store_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100),
    user: User = Depends(require_permission("cash.view")),
    perms: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> Response:
    """The Excel sheet of every purchase matching the filters (office, stores, or both)."""
    data = svc.export_xlsx(db, user, perms, kind=kind, start=start, end=end, category=category, store_id=store_id, q=q)
    label = {"OFFICE": "office", "STORE": "stores"}.get(kind or "", "all")
    name = f"cash-purchases-{label}-{(start or date.today()).isoformat()}_{(end or date.today()).isoformat()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"},
    )
