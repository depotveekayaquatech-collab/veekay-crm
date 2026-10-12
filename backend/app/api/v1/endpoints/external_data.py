"""Vendor / POC app, read-only data: orders, tickets, compliance documents, bottles.

Every query is limited to the stores linked to the signed-in login (external_account_stores); a store id that
isn't linked to it answers 404, the same as one that doesn't exist.
"""
import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.deps import get_current_external_account
from app.core import storage
from app.db.session import get_db
from app.models.bottle import Bottle, BottleStatus
from app.models.compliance_document import ComplianceDocument
from app.models.external_account import AccountKind, ExternalAccount, ExternalAccountStore
from app.models.external_activity import TicketAttachment
from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.ticket import Ticket
from app.schemas.external_portal import (
    AttachmentOut, BottlePage, DayTotal, BottleRow, DocumentPage, DocumentRow, OrderPage, OrderRow, TicketCommentOut, TicketDetail, TicketPage, TicketRow,
)

router = APIRouter(prefix="/external", tags=["external-portal"])


def _own_store_ids(account: ExternalAccount):
    return select(ExternalAccountStore.store_id).where(ExternalAccountStore.account_id == account.id)


def _check_store(db: Session, account: ExternalAccount, store_id: uuid.UUID | None) -> None:
    if store_id is None:
        return
    linked = db.execute(
        select(ExternalAccountStore.store_id).where(ExternalAccountStore.account_id == account.id, ExternalAccountStore.store_id == store_id)
    ).first()
    if linked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")


@router.get("/orders", response_model=OrderPage)
def my_orders(
    store_id: uuid.UUID | None = None, date_from: date | None = None, date_to: date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> OrderPage:
    """Daily bottle counts per store, newest first. Defaults to the last 31 days; a range is capped at 92 days."""
    _check_store(db, account, store_id)
    date_to = date_to or date.today()
    date_from = date_from or date_to - timedelta(days=30)
    if date_from > date_to or (date_to - date_from).days > 92:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a date range of at most 92 days.")
    conds = [OrderEntry.store_id.in_(_own_store_ids(account)), OrderEntry.order_date >= date_from, OrderEntry.order_date <= date_to]
    if store_id:
        conds.append(OrderEntry.store_id == store_id)
    total, bottles = db.execute(select(func.count(), func.coalesce(func.sum(OrderEntry.bottle_count), 0)).where(*conds)).one()
    rows = db.execute(
        select(OrderEntry.store_id, Store.name, OrderEntry.order_date, OrderEntry.bottle_count)
        .join(Store, Store.id == OrderEntry.store_id).where(*conds)
        .order_by(OrderEntry.order_date.desc(), Store.name).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return OrderPage(
        items=[OrderRow(store_id=r[0], store_name=r[1], order_date=r[2], bottle_count=r[3]) for r in rows],
        total=total, total_bottles=int(bottles), page=page, page_size=page_size,
    )


@router.get("/orders/daily", response_model=list[DayTotal])
def my_orders_daily(
    store_id: uuid.UUID | None = None, date_from: date | None = None, date_to: date | None = None,
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> list[DayTotal]:
    """One line per day: total bottles and how many stores were marked. Same range rules as /orders."""
    _check_store(db, account, store_id)
    date_to = date_to or date.today()
    date_from = date_from or date_to - timedelta(days=30)
    if date_from > date_to or (date_to - date_from).days > 92:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a date range of at most 92 days.")
    conds = [OrderEntry.store_id.in_(_own_store_ids(account)), OrderEntry.order_date >= date_from, OrderEntry.order_date <= date_to]
    if store_id:
        conds.append(OrderEntry.store_id == store_id)
    rows = db.execute(
        select(OrderEntry.order_date, func.sum(OrderEntry.bottle_count), func.count()).where(*conds)
        .group_by(OrderEntry.order_date).order_by(OrderEntry.order_date.desc())
    ).all()
    return [DayTotal(order_date=d, bottles=int(b), stores=n) for d, b, n in rows]


def _ticket_row(t: Ticket) -> dict:
    return dict(
        id=t.id, number=t.number, store_id=t.store_id, store_name=t.store.name, category=t.category, priority=t.priority,
        status=t.status, title=t.title, created_at=t.created_at, due_at=t.due_at, resolved_at=t.resolved_at,
    )


@router.get("/tickets", response_model=TicketPage)
def my_tickets(
    store_id: uuid.UUID | None = None, ticket_status: Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"] | None = Query(None, alias="status"),
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> TicketPage:
    _check_store(db, account, store_id)
    conds = [Ticket.store_id.in_(_own_store_ids(account))]
    if store_id:
        conds.append(Ticket.store_id == store_id)
    if ticket_status:
        conds.append(Ticket.status == ticket_status)
    total = db.execute(select(func.count()).select_from(Ticket).where(*conds)).scalar_one()
    rows = db.execute(
        select(Ticket).where(*conds).options(joinedload(Ticket.store))
        .order_by(Ticket.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return TicketPage(items=[TicketRow(**_ticket_row(t)) for t in rows], total=total, page=page, page_size=page_size)


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def my_ticket(ticket_id: uuid.UUID, account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db)) -> TicketDetail:
    t = db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.store_id.in_(_own_store_ids(account)))
        .options(joinedload(Ticket.store), selectinload(Ticket.comments))
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found.")
    return TicketDetail(
        **_ticket_row(t), description=t.description,
        comments=[
            TicketCommentOut(
                id=c.id, body=c.body, event=c.event, created_at=c.created_at,
                mine=c.author_label == f"{account.full_name} ({'Vendor' if account.kind == AccountKind.VENDOR else 'POC'})"[:128],
            ) for c in t.comments
        ],
        attachments=[
            AttachmentOut(id=a.id, comment_id=a.comment_id, file_name=a.file_name, content_type=a.content_type, size_bytes=a.size_bytes)
            for a in db.execute(select(TicketAttachment).where(TicketAttachment.ticket_id == t.id).order_by(TicketAttachment.created_at)).scalars()
        ],
    )


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}")
def my_ticket_photo(
    ticket_id: uuid.UUID, attachment_id: uuid.UUID,
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> Response:
    t = db.execute(select(Ticket.id).where(Ticket.id == ticket_id, Ticket.store_id.in_(_own_store_ids(account)))).first()
    a = db.get(TicketAttachment, attachment_id)
    if t is None or a is None or a.ticket_id != ticket_id or not storage.exists(a.file_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found.")
    return Response(content=storage.read(a.file_key), media_type=a.content_type, headers={"Content-Disposition": "inline", "Cache-Control": "private, no-store"})


def _doc_conds(account: ExternalAccount) -> list:
    return [ComplianceDocument.store_id.in_(_own_store_ids(account)), ComplianceDocument.deleted_at.is_(None)]


@router.get("/documents", response_model=DocumentPage)
def my_documents(
    store_id: uuid.UUID | None = None, kind: Literal["card", "bill", "payment"] | None = None, month: date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> DocumentPage:
    """Cards, invoices and payment proofs of the login's stores. `month` is any date inside the month."""
    _check_store(db, account, store_id)
    conds = _doc_conds(account)
    if store_id:
        conds.append(ComplianceDocument.store_id == store_id)
    if kind:
        conds.append(ComplianceDocument.kind == kind)
    if month:
        conds.append(ComplianceDocument.month == month.replace(day=1))
    total = db.execute(select(func.count()).select_from(ComplianceDocument).where(*conds)).scalar_one()
    rows = db.execute(
        select(ComplianceDocument).where(*conds).options(joinedload(ComplianceDocument.store))
        .order_by(ComplianceDocument.month.desc(), ComplianceDocument.kind).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return DocumentPage(
        items=[DocumentRow(
            id=d.id, store_id=d.store_id, store_name=d.store.name, month=d.month, kind=d.kind, file_name=d.file_name,
            content_type=d.content_type, size_bytes=d.size_bytes, updated_at=d.updated_at, due_date=d.due_date, status=d.status,
        ) for d in rows],
        total=total, page=page, page_size=page_size,
    )


@router.get("/documents/{doc_id}/file")
def my_document_file(doc_id: uuid.UUID, account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db)) -> Response:
    d = db.execute(select(ComplianceDocument).where(ComplianceDocument.id == doc_id, *_doc_conds(account))).scalar_one_or_none()
    if d is None or not storage.exists(d.file_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    name = d.file_name.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=storage.read(d.file_key), media_type=d.content_type,
        headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store"},
    )


@router.get("/bottles", response_model=BottlePage)
def my_bottles(
    store_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db),
) -> BottlePage:
    """Bottles currently at the login's stores (their last scan was IN)."""
    _check_store(db, account, store_id)
    here = [Bottle.current_store_id.in_(_own_store_ids(account)), Bottle.status == BottleStatus.AT_STORE]
    conds = here + ([Bottle.current_store_id == store_id] if store_id else [])
    total = db.execute(select(func.count()).select_from(Bottle).where(*conds)).scalar_one()
    per_store = {str(sid): n for sid, n in db.execute(select(Bottle.current_store_id, func.count()).where(*here).group_by(Bottle.current_store_id)).all()}
    rows = db.execute(
        select(Bottle.serial, Bottle.current_store_id, Store.name, Bottle.last_in_at)
        .join(Store, Store.id == Bottle.current_store_id).where(*conds)
        .order_by(Bottle.last_in_at.asc().nulls_last(), Bottle.serial).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return BottlePage(
        items=[BottleRow(serial=r[0], store_id=r[1], store_name=r[2], last_in_at=r[3]) for r in rows],
        total=total, page=page, page_size=page_size, per_store=per_store,
    )
