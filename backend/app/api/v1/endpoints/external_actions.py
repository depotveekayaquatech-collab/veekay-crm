"""Vendor / POC app, actions: raise tickets (with photos), reply, upload documents, confirm deliveries,
notifications and push-device registration.

Same scoping rule as the read-only routes: only stores linked to the signed-in login. A vendor can never change a
ticket's status, priority or assignee, and can only upload cards and payment proofs (bills are issued by Veekay).
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_external_account
from app.api.v1.endpoints.external_data import _check_store, _own_store_ids, my_ticket
from app.core.idempotency import idempotency_key_header, run_once
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.compliance_document import ComplianceDocument
from app.models.external_account import AccountKind, ExternalAccount
from app.models.external_activity import (
    DeliveryConfirmation, DeliveryOutcome, ExternalDevice, ExternalNotification, TicketAttachment,
)
from app.models.store import Store
from app.models.ticket import Ticket, TicketComment, TicketStatus
from app.schemas.external_portal import DocumentRow, Page, TicketDetail
from app.services import compliance_service, external_uploads, staff_notify, ticket_service

router = APIRouter(prefix="/external", tags=["external-portal"])

MAX_TICKETS_PER_DAY = 20
MAX_COMMENTS_PER_DAY = 100
DELIVERY_WINDOW_DAYS = 14
Category = Literal["LATE_DELIVERY", "NO_DELIVERY", "SHORT_SUPPLY", "QUALITY", "DAMAGED", "BILLING", "OTHER"]


def _label(account: ExternalAccount) -> str:
    return f"{account.full_name} ({'Vendor' if account.kind == AccountKind.VENDOR else 'POC'})"[:128]


def _audit(db: Session, account: ExternalAccount, action: str, entity_type: str, entity_id, **meta) -> None:
    db.add(AuditLog(
        user_id=None, organization_id=account.organization_id, action=action, entity_type=entity_type, entity_id=str(entity_id),
        metadata_json={"external_account": account.email, **meta},
    ))


def _require_poc(account: ExternalAccount, what: str) -> None:
    """Vendors only watch: raising tickets, replying and confirming deliveries is the store POC's job."""
    if account.kind != AccountKind.POC:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Only the store POC can {what}. You can follow it here once the POC has done it.")


def _store(db: Session, account: ExternalAccount, store_id: uuid.UUID) -> Store:
    _check_store(db, account, store_id)
    store = db.execute(select(Store).where(Store.id == store_id).options(joinedload(Store.partner_organization))).scalar_one_or_none()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    return store


def _day_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _attach(db: Session, account: ExternalAccount, ticket: Ticket, photos: list[external_uploads.Photo], comment_id: uuid.UUID | None = None) -> None:
    for p in photos:
        key, name, size = external_uploads.store_photo(ticket.id, p)
        db.add(TicketAttachment(
            ticket_id=ticket.id, comment_id=comment_id, file_key=key, file_name=name, content_type="image/jpeg", size_bytes=size,
            uploaded_by_account_id=account.id,
        ))


def _new_ticket(
    db: Session, account: ExternalAccount, store: Store, category: str, priority: str, title: str, description: str | None,
    photos: list[external_uploads.Photo],
) -> Ticket:
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        organization_id=store.organization_id, store_id=store.id, partner_organization_id=store.partner_organization_id,
        category=category, priority=priority, status=TicketStatus.OPEN.value, title=title.strip(),
        description=(description or "").strip() or None, created_by_user_id=None, source="vendor_app",
        reporter=_label(account), due_at=ticket_service._due(priority, now),
    )
    db.add(ticket)
    db.flush()
    _attach(db, account, ticket, photos)
    _audit(db, account, "external.ticket_created", "ticket", ticket.id, number=ticket.number, store=store.name, category=category)
    # Ticket managers and the employees who handle the store hear about it straight away, without opening the app to look.
    ticket_service._announce(db, ticket, store, by=_label(account))
    return ticket


def _ticket_detail(db: Session, account: ExternalAccount, ticket_id: uuid.UUID) -> TicketDetail:
    db.expire_all()
    return my_ticket(ticket_id, account, db)


# ------------------------------------------------------------------ tickets

@router.post("/tickets", response_model=TicketDetail, status_code=201)
def raise_ticket(
    store_id: uuid.UUID = Form(...), category: Category = Form(...), title: str = Form(..., min_length=3, max_length=160),
    description: str | None = Form(None, max_length=2000), photos: list[UploadFile] = File(default=[]),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
    idem: str | None = Depends(idempotency_key_header),
) -> TicketDetail:
    _require_poc(account, "raise tickets")
    store = _store(db, account, store_id)

    def create() -> TicketDetail:
        today = db.execute(
            select(func.count()).select_from(Ticket).where(Ticket.source == "vendor_app", Ticket.reporter == _label(account), Ticket.created_at >= _day_start())
        ).scalar_one()
        if today >= MAX_TICKETS_PER_DAY:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You have raised the maximum number of tickets for today.")
        ticket = _new_ticket(db, account, store, category, "MEDIUM", title, description, external_uploads.read_photos(photos))
        db.commit()
        return _ticket_detail(db, account, ticket.id)

    return run_once(db, owner=str(account.id), endpoint="external.ticket.create", key=idem, produce=create)


@router.post("/tickets/{ticket_id}/comments", response_model=TicketDetail, status_code=201)
def comment(
    ticket_id: uuid.UUID, body: str = Form(..., min_length=1, max_length=2000), photos: list[UploadFile] = File(default=[]),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
    idem: str | None = Depends(idempotency_key_header),
) -> TicketDetail:
    _require_poc(account, "reply to tickets")
    t = db.execute(select(Ticket).where(Ticket.id == ticket_id)).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found.")
    _check_store_or_404(db, account, t.store_id, "Ticket not found.")

    def create() -> TicketDetail:
        if t.status == TicketStatus.CLOSED.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "This ticket is closed. Raise a new ticket instead.")
        recent = db.execute(
            select(func.count()).select_from(TicketComment).where(TicketComment.author_label == _label(account), TicketComment.created_at >= _day_start())
        ).scalar_one()
        if recent >= MAX_COMMENTS_PER_DAY:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many replies today.")
        prepared = external_uploads.read_photos(photos)
        c = TicketComment(ticket_id=t.id, author_user_id=None, author_label=_label(account), body=body.strip())
        db.add(c)
        db.flush()
        _attach(db, account, t, prepared, c.id)
        t.updated_at = datetime.now(timezone.utc)
        _audit(db, account, "external.ticket_commented", "ticket", t.id, number=t.number)
        db.commit()
        return _ticket_detail(db, account, t.id)

    return run_once(db, owner=str(account.id), endpoint=f"external.comment.{ticket_id.hex[:20]}", key=idem, produce=create)


def _check_store_or_404(db: Session, account: ExternalAccount, store_id: uuid.UUID, detail: str) -> None:
    try:
        _check_store(db, account, store_id)
    except HTTPException:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail) from None


# ------------------------------------------------------------------ documents

@router.post("/documents", response_model=DocumentRow, status_code=201)
def upload_document(
    store_id: uuid.UUID = Form(...), kind: Literal["card", "payment"] = Form(...), month: str | None = Form(None, description="2026-09; this month by default"),
    files: list[UploadFile] = File(...),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
    idem: str | None = Depends(idempotency_key_header),
) -> DocumentRow:
    """A compliance card or a payment proof for a month. Several photos are merged into one PDF, like the staff upload.
    Uploading again adds a new version; earlier files are kept. Resending with the same Idempotency-Key adds no extra version."""
    store = _store(db, account, store_id)
    the_month = compliance_service.parse_month(month)

    def create() -> DocumentRow:
        limit = compliance_service.settings.COMPLIANCE_MAX_FILE_MB * 1024 * 1024
        raw = [(f.filename or "file", f.file.read(limit + 1)) for f in files]
        data, ext = compliance_service._prepare(raw)
        doc, replaced = compliance_service.save_document(db, None, store, the_month, kind, data, ext, len(raw))
        _audit(db, account, "external.document_uploaded", "compliance_document", doc.id, store=store.name, month=f"{the_month:%Y-%m}", kind=kind, replaced=replaced)
        db.commit()
        doc = db.execute(select(ComplianceDocument).where(ComplianceDocument.id == doc.id).options(joinedload(ComplianceDocument.store))).scalar_one()
        return DocumentRow(
            id=doc.id, store_id=doc.store_id, store_name=doc.store.name, month=doc.month, kind=doc.kind, file_name=doc.file_name,
            content_type=doc.content_type, size_bytes=doc.size_bytes, updated_at=doc.updated_at, due_date=doc.due_date, status=doc.status,
        )

    return run_once(db, owner=str(account.id), endpoint="external.document.upload", key=idem, produce=create)


# ------------------------------------------------------------------ deliveries

class DeliveryOut(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    store_name: str
    delivery_date: date
    outcome: str
    expected_qty: int | None
    received_qty: int | None
    note: str | None
    ticket_id: uuid.UUID | None
    reported_by: str            # "Name (POC)"
    created_at: datetime


class DeliveryPage(Page):
    items: list[DeliveryOut]


def _delivery_out(d: DeliveryConfirmation, store_name: str, by: ExternalAccount) -> DeliveryOut:
    return DeliveryOut(
        reported_by=_label(by),
        id=d.id, store_id=d.store_id, store_name=store_name, delivery_date=d.delivery_date, outcome=d.outcome,
        expected_qty=d.expected_qty, received_qty=d.received_qty, note=d.note, ticket_id=d.ticket_id, created_at=d.created_at,
    )


@router.post("/deliveries", response_model=DeliveryOut, status_code=201)
def confirm_delivery(
    store_id: uuid.UUID = Form(...), delivery_date: date = Form(...), outcome: Literal["RECEIVED", "SHORT", "DAMAGED"] = Form(...),
    expected_qty: int | None = Form(None, ge=0, le=100000), received_qty: int | None = Form(None, ge=0, le=100000),
    note: str | None = Form(None, max_length=1000), photos: list[UploadFile] = File(default=[]),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> DeliveryOut:
    """Confirm a day's delivery arrived fine, or flag it short / damaged. A short or damaged report also opens a
    high-priority ticket (with the photos) so Veekay's team sees it straight away."""
    _require_poc(account, "confirm deliveries")
    store = _store(db, account, store_id)
    today = date.today()
    if delivery_date > today or (today - delivery_date).days > DELIVERY_WINDOW_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The delivery date must be within the last {DELIVERY_WINDOW_DAYS} days.")
    if outcome != DeliveryOutcome.RECEIVED and not ((note or "").strip() or received_qty is not None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Say what was wrong: add a note or the quantity received.")
    if db.execute(select(DeliveryConfirmation.id).where(
        DeliveryConfirmation.store_id == store.id, DeliveryConfirmation.delivery_date == delivery_date,
    )).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "This store's delivery for that day has already been reported.")
    prepared = external_uploads.read_photos(photos)

    ticket = None
    if outcome != DeliveryOutcome.RECEIVED:
        short = outcome == DeliveryOutcome.SHORT
        qty = f" Expected {expected_qty}, received {received_qty}." if expected_qty is not None and received_qty is not None else ""
        ticket = _new_ticket(
            db, account, store, "SHORT_SUPPLY" if short else "DAMAGED", "HIGH",
            f"{'Short supply' if short else 'Damaged delivery'} on {delivery_date:%d %b %Y}",
            f"Reported from the vendor app for {delivery_date:%d %b %Y}.{qty} {(note or '').strip()}".strip(), prepared,
        )
    elif prepared:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Photos are only for short or damaged deliveries.")
    d = DeliveryConfirmation(
        account_id=account.id, store_id=store.id, delivery_date=delivery_date, outcome=outcome, expected_qty=expected_qty,
        received_qty=received_qty, note=(note or "").strip() or None, ticket_id=ticket.id if ticket else None,
    )
    db.add(d)
    db.flush()
    _audit(db, account, "external.delivery_confirmed", "delivery_confirmation", d.id, store=store.name, date=str(delivery_date), outcome=outcome)
    db.commit()
    db.refresh(d)
    return _delivery_out(d, store.name, account)


@router.get("/deliveries", response_model=DeliveryPage)
def my_deliveries(
    store_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> DeliveryPage:
    """Deliveries confirmed or flagged at this login's stores, by anyone (the POC confirms; the vendor follows)."""
    _check_store(db, account, store_id)
    conds = [DeliveryConfirmation.store_id.in_(_own_store_ids(account))] + ([DeliveryConfirmation.store_id == store_id] if store_id else [])
    total = db.execute(select(func.count()).select_from(DeliveryConfirmation).where(*conds)).scalar_one()
    rows = db.execute(
        select(DeliveryConfirmation, Store.name, ExternalAccount)
        .join(Store, Store.id == DeliveryConfirmation.store_id).join(ExternalAccount, ExternalAccount.id == DeliveryConfirmation.account_id).where(*conds)
        .order_by(DeliveryConfirmation.delivery_date.desc(), DeliveryConfirmation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return DeliveryPage(items=[_delivery_out(d, n, by) for d, n, by in rows], total=total, page=page, page_size=page_size)


# ------------------------------------------------------------------ notifications + push devices

class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    ref_id: str | None
    read: bool
    created_at: datetime


class NotificationPage(Page):
    items: list[NotificationOut]
    unread: int


class MarkRead(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=200, description="Leave out to mark everything read.")


@router.get("/notifications", response_model=NotificationPage)
def notifications(
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> NotificationPage:
    mine = ExternalNotification.account_id == account.id
    total = db.execute(select(func.count()).select_from(ExternalNotification).where(mine)).scalar_one()
    unread = db.execute(select(func.count()).select_from(ExternalNotification).where(mine, ExternalNotification.read_at.is_(None))).scalar_one()
    rows = db.execute(
        select(ExternalNotification).where(mine).order_by(ExternalNotification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return NotificationPage(
        items=[NotificationOut(id=n.id, kind=n.kind, title=n.title, body=n.body, ref_id=n.ref_id, read=n.read_at is not None, created_at=n.created_at) for n in rows],
        total=total, unread=unread, page=page, page_size=page_size,
    )


@router.post("/notifications/read", status_code=204)
def mark_read(payload: MarkRead, account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db)) -> None:
    stmt = update(ExternalNotification).where(ExternalNotification.account_id == account.id, ExternalNotification.read_at.is_(None))
    if payload.ids is not None:
        stmt = stmt.where(ExternalNotification.id.in_(payload.ids))
    db.execute(stmt.values(read_at=datetime.now(timezone.utc)))
    db.commit()


class DeviceIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    platform: Literal["android", "ios", "web"]


@router.post("/devices", status_code=204)
def register_device(payload: DeviceIn, account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db)) -> None:
    """Register this phone for push messages. A token that was on another login moves to this one."""
    now = datetime.now(timezone.utc)
    dev = db.execute(select(ExternalDevice).where(ExternalDevice.token == payload.token)).scalar_one_or_none()
    if dev is None:
        db.add(ExternalDevice(account_id=account.id, token=payload.token, platform=payload.platform, last_seen_at=now))
    else:
        dev.account_id, dev.platform, dev.last_seen_at = account.id, payload.platform, now
    db.commit()


@router.delete("/devices", status_code=204)
def unregister_device(token: str = Query(..., max_length=512), account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db)) -> None:
    dev = db.execute(select(ExternalDevice).where(ExternalDevice.token == token, ExternalDevice.account_id == account.id)).scalar_one_or_none()
    if dev is not None:
        db.delete(dev)
        db.commit()
