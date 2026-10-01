"""Monthwise virtual cards (PDF / ZIP) and the public QR count page."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import card_service

router = APIRouter(prefix="/cards", tags=["cards"])
public_router = APIRouter(prefix="/public", tags=["public"])


class StoreMatch(BaseModel):
    id: uuid.UUID
    name: str
    code: str


class VendorOut(BaseModel):
    vendor: str
    stores: int
    number: str | None = None
    matches: list[StoreMatch] = []
    match_total: int = 0


class MonthOption(BaseModel):
    value: str   # YYYY-MM
    label: str   # SEP-2026 (till date)


class RegionOut(BaseModel):
    id: uuid.UUID
    name: str


class VendorsOut(BaseModel):
    vendors: list[VendorOut]
    regions: list[RegionOut] = []
    months: list[MonthOption]


class ZipRequest(BaseModel):
    vendors: list[str] = Field(..., min_length=1, max_length=300)
    partner: str | None = None
    region: uuid.UUID | None = None
    month: str | None = None   # omit -> blank cards (no month on them)


class PublicCount(BaseModel):
    store_name: str
    store_code: str
    vendor_name: str | None
    platform: str | None
    this_month_label: str
    this_month_bottles: int
    last_month_label: str | None
    last_month_bottles: int | None
    as_on: datetime


def _is_admin(perms: set[str]) -> bool:
    return "orders.correct" in perms


@router.get("/vendors", response_model=VendorsOut, dependencies=[Depends(require_permission("orders.view"))])
def vendors(
    partner: str | None = None,
    region: uuid.UUID | None = None,
    q: str | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VendorsOut:
    """Vendors (with store counts) among the stores you can print cards for, and the months a card can be filled for."""
    return VendorsOut(
        vendors=[VendorOut(**v) for v in card_service.list_vendors(db, user, is_admin=_is_admin(perms), partner=partner, region=region, q=q)],
        regions=[RegionOut(**r) for r in card_service.list_regions(db, user, is_admin=_is_admin(perms), partner=partner)],
        months=[MonthOption(**m) for m in card_service.available_months()],
    )


@router.get("/pdf", dependencies=[Depends(require_permission("orders.view"))])
def pdf(
    partner: str | None = None,
    region: uuid.UUID | None = None,
    vendor: str | None = None,
    store_id: uuid.UUID | None = None,
    month: str | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """One PDF: a card per live store of the vendor. No month -> blank cards; a month -> cards with entry."""
    if not vendor and store_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a vendor or a store.")
    data, count, name = card_service.build_pdf(
        db, user, is_admin=_is_admin(perms), partner=partner, vendor=vendor,
        month=card_service.parse_card_month(month), store_id=store_id, region=region,
    )
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"', "X-Card-Count": str(count),
                 "Access-Control-Expose-Headers": "X-Card-Count", "Cache-Control": "private, no-store"},
    )


@router.post("/zip", dependencies=[Depends(require_permission("orders.view"))])
def zip_download(
    payload: ZipRequest,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """A ZIP with one PDF per selected vendor (blank, or pre-filled for the chosen month)."""
    data, n_vendors, n_cards, name = card_service.build_zip(
        db, user, is_admin=_is_admin(perms), partner=payload.partner, vendors=payload.vendors,
        month=card_service.parse_card_month(payload.month), region=payload.region,
    )
    return Response(
        content=data, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Card-Count": str(n_cards),
                 "X-Vendor-Count": str(n_vendors), "Access-Control-Expose-Headers": "X-Card-Count, X-Vendor-Count",
                 "Cache-Control": "private, no-store"},
    )


@public_router.get("/count", response_model=PublicCount)
def public_count(s: uuid.UUID, sig: str, db: Session = Depends(get_db)) -> PublicCount:
    """Target of the QR code: bottles supplied this month (till date) and last month. No login — the HMAC signature is the key."""
    return PublicCount(**card_service.public_count(db, s, sig))
