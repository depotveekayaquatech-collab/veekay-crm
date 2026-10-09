"""Inbound integrations. Today: raise tickets from a Google Apps Script / Form via a shared secret."""
import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.organization import Organization, OrganizationKind
from app.schemas.bottle import BottleDetail, BottleList, ExternalScan, ScanResult
from app.services import bottle_service, ticket_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


class ExternalTicket(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=128, description="Your unique id for this ticket (e.g. the sheet row or form response id). Resending it never creates a duplicate.")
    store_code: str | None = Field(default=None, max_length=64, description="The store's outlet code, as shown in the CRM. Send this or store_name.")
    platform: str | None = Field(default=None, max_length=32, description="blinkit / zepto — only needed if a code exists on both.")
    store_name: str | None = Field(default=None, max_length=128, description="Store name as shown in the CRM; used when there is no code (or the code isn't found).")
    category: str | None = Field(default=None, max_length=120, description="Free text is fine: 'Water arrived late', 'Bottles damaged'...")
    priority: str | None = Field(default=None, max_length=40)
    title: str = Field(..., min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    reporter: str | None = Field(default=None, max_length=255, description="Who raised it (name / email / phone).")
    raised_at: datetime | None = None


def _need_a_store(p: ExternalTicket) -> None:
    if not (p.store_code and p.store_code.strip()) and not (p.store_name and p.store_name.strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Send store_code or store_name.")


def _check_key(key: str | None) -> None:
    configured = settings.TICKET_WEBHOOK_KEY
    if not configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Ticket intake is not switched on (TICKET_WEBHOOK_KEY is not set).")
    if not key or not hmac.compare_digest(key.encode(), configured.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid integration key.")


@router.post("/tickets")
def intake_ticket(
    payload: ExternalTicket,
    response: Response,
    x_integration_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Create a ticket from outside the app. Header `X-Integration-Key` must match the server's TICKET_WEBHOOK_KEY."""
    _check_key(x_integration_key)
    _need_a_store(payload)
    org = db.execute(select(Organization).where(Organization.kind == OrganizationKind.INTERNAL.value)).scalars().first()
    if org is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Organization is not set up.")
    ticket, created = ticket_service.create_external(
        db, org.id, external_id=payload.external_id, store_code=payload.store_code, platform=payload.platform,
        store_name=payload.store_name, category=payload.category, priority=payload.priority, title=payload.title,
        description=payload.description, reporter=payload.reporter, raised_at=payload.raised_at,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {"created": created, "id": ticket.id, "number": ticket.number, "ticket": f"TK-{ticket.number:04d}", "category": ticket.category, "priority": ticket.priority}


# ---- bottle QR tracking: for a partner's / third-party scanner system ----------------------------------------------

def _check_bottle_key(key: str | None) -> None:
    configured = settings.BOTTLE_API_KEY
    if not configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Bottle tracking API is not switched on (BOTTLE_API_KEY is not set).")
    if not key or not hmac.compare_digest(key.encode(), configured.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid integration key.")


def _internal_org_id(db: Session):
    org = db.execute(select(Organization).where(Organization.kind == OrganizationKind.INTERNAL.value)).scalars().first()
    if org is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Organization is not set up.")
    return org.id


@router.post("/bottles/scan", response_model=ScanResult)
def bottle_scan(payload: ExternalScan, x_integration_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> ScanResult:
    """Push one IN / OUT scan. Send `scan_id` so a retry never double-counts. Header `X-Integration-Key` = BOTTLE_API_KEY."""
    _check_bottle_key(x_integration_key)
    org_id = _internal_org_id(db)
    store = bottle_service.find_store(db, org_id, code=payload.store_code, platform=payload.platform) if payload.store_code else None
    return bottle_service.scan(
        db, org_id, serial=payload.serial, direction=payload.direction, store=store, scanned_at=payload.scanned_at,
        scan_id=payload.scan_id, source="api", scanned_by=payload.scanned_by,
    )


@router.get("/bottles/overdue", response_model=BottleList)
def bottle_overdue(
    days: int | None = None, page: int = 1, page_size: int = 100,
    x_integration_key: str | None = Header(default=None), db: Session = Depends(get_db),
) -> BottleList:
    """Bottles scanned IN with no OUT for more than `days` (default BOTTLE_LOST_AFTER_DAYS), oldest first."""
    _check_bottle_key(x_integration_key)
    return bottle_service.search(
        db, _internal_org_id(db), state="OVERDUE", overdue_days=max(days, 0) if days is not None else None,
        page=max(page, 1), page_size=min(max(page_size, 1), 500),
    )


@router.get("/bottles/{serial}", response_model=BottleDetail)
def bottle_detail(serial: str, x_integration_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> BottleDetail:
    """One bottle's current state and full scan history."""
    _check_bottle_key(x_integration_key)
    return bottle_service.detail(db, _internal_org_id(db), serial)
