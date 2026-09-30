"""Vendor supply cards (PDF) and the public QR count page."""
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import card_service

router = APIRouter(prefix="/cards", tags=["cards"])
public_router = APIRouter(prefix="/public", tags=["public"])


class VendorOut(BaseModel):
    vendor: str
    stores: int
    number: str | None = None


class DailyCount(BaseModel):
    date: date
    bottles: int


class PublicCount(BaseModel):
    store_name: str
    store_code: str
    platform: str | None
    city: str | None
    state: str | None
    this_month_label: str
    this_month_bottles: int
    this_month_entries: int
    last_month_label: str
    last_month_bottles: int
    last_month_entries: int
    daily: list[DailyCount]


def _is_admin(perms: set[str]) -> bool:
    return "orders.correct" in perms


def _month(value: str | None) -> date:
    today = datetime.now(timezone.utc).date()
    if not value:
        return today.replace(day=1)
    try:
        y, m = (int(x) for x in value.split("-"))
        d = date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-09.") from exc
    if d > today.replace(day=1) or d.year < 2020:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose the current or a past month.")
    return d


@router.get("/vendors", response_model=list[VendorOut], dependencies=[Depends(require_permission("orders.view"))])
def vendors(
    partner: str | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VendorOut]:
    """Vendors (with store counts) among the stores you can print cards for."""
    return [VendorOut(**v) for v in card_service.list_vendors(db, user, is_admin=_is_admin(perms), partner=partner)]


@router.get("/pdf", dependencies=[Depends(require_permission("orders.view"))])
def pdf(
    partner: str | None = None,
    vendor: str | None = None,
    store_id: uuid.UUID | None = None,
    month: str | None = None,
    with_entry: bool = Query(False, description="Pre-fill dates, filled bottles and total"),
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """One PDF: a card per live store of the vendor (or a single store)."""
    if not vendor and store_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a vendor or a store.")
    m = _month(month)
    data, count = card_service.build_pdf(
        db, user, is_admin=_is_admin(perms), partner=partner, vendor=vendor, month=m,
        with_entry=with_entry, store_id=store_id,
    )
    name = f"cards-{(vendor or 'store').replace(' ', '_')[:40]}-{m:%Y-%m}{'-with-entry' if with_entry else ''}.pdf"
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}"', "X-Card-Count": str(count),
                 "Access-Control-Expose-Headers": "X-Card-Count", "Cache-Control": "private, no-store"},
    )


@public_router.get("/count", response_model=PublicCount)
def public_count(s: uuid.UUID, sig: str, db: Session = Depends(get_db)) -> PublicCount:
    """Target of the QR code: bottles supplied this and last month. No login — the HMAC signature is the key."""
    return PublicCount(**card_service.public_count(db, s, sig))
