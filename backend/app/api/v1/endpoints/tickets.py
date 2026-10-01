"""Ticket routes — thin wrappers over ticket_service."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, get_page_params
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.ticket import (
    CommentCreate,
    StoreChoice,
    TicketAnalytics,
    TicketCreate,
    TicketDetail,
    TicketOut,
    TicketUpdate,
)
from app.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])

_FORBIDDEN = HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to access this.")


def _kind(perms: set[str], user: User, db: Session, *, need: tuple[str, ...]) -> str:
    """Resolve what kind of caller this is, and require at least one of the permissions in `need`."""
    if not perms.intersection(need):
        raise _FORBIDDEN
    return ticket_service.actor_kind(db, user, perms)


@router.get("", response_model=Page[TicketOut])
def list_tickets(
    ticket_status: str | None = Query(default=None, alias="status"),  # active | done | OPEN | IN_PROGRESS | RESOLVED | CLOSED
    category: str | None = None,
    priority: str | None = None,
    partner: str | None = None,
    region_id: uuid.UUID | None = None,
    state: str | None = None,          # geographic state of the store
    vendor: str | None = None,
    q: str | None = None,
    overdue: bool = False,
    mine: bool = False,
    params: PageParams = Depends(get_page_params),
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[TicketOut]:
    kind = _kind(perms, user, db, need=("tickets.view", "tickets.manage"))
    return ticket_service.list_tickets(
        db, user, kind, params, state_filter=ticket_status, category=category, priority=priority, partner=partner,
        region_id=region_id, state=state, vendor=vendor, q=q, overdue=overdue, mine=mine,
    )


@router.get("/analytics", response_model=TicketAnalytics)
def analytics(
    days: int = 30,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketAnalytics:
    if "tickets.manage" not in perms:
        raise _FORBIDDEN
    return ticket_service.analytics(db, user, days)


@router.get("/stores", response_model=list[StoreChoice])
def store_choices(
    q: str | None = None,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StoreChoice]:
    """Stores the caller may raise a ticket for (type-ahead)."""
    kind = _kind(perms, user, db, need=("tickets.create", "tickets.manage"))
    return ticket_service.store_choices(db, user, kind, q)


@router.post("", response_model=TicketDetail, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketDetail:
    kind = _kind(perms, user, db, need=("tickets.create", "tickets.manage"))
    return ticket_service.create_ticket(db, user, kind, payload)


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(
    ticket_id: uuid.UUID,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketDetail:
    kind = _kind(perms, user, db, need=("tickets.view", "tickets.manage"))
    return ticket_service.get_ticket(db, user, kind, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketDetail)
def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketDetail:
    kind = _kind(perms, user, db, need=("tickets.view", "tickets.manage"))
    return ticket_service.update_ticket(db, user, kind, ticket_id, payload)


@router.post("/{ticket_id}/comments", response_model=TicketDetail)
def add_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    perms: set[str] = Depends(get_current_permissions),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TicketDetail:
    kind = _kind(perms, user, db, need=("tickets.view", "tickets.manage"))
    return ticket_service.add_comment(db, user, kind, ticket_id, payload.body)
