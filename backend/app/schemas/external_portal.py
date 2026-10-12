"""Read-only shapes for the vendor / POC app. Deliberately narrow: no staff names, no internal fields."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel


class Page(BaseModel):
    total: int
    page: int
    page_size: int


class OrderRow(BaseModel):
    store_id: uuid.UUID
    store_name: str
    order_date: date
    bottle_count: int


class OrderPage(Page):
    items: list[OrderRow]
    total_bottles: int          # across every row matching the filter, not just this page


class DayTotal(BaseModel):
    order_date: date
    bottles: int
    stores: int                 # stores marked that day


class TicketRow(BaseModel):
    id: uuid.UUID
    number: int
    store_id: uuid.UUID
    store_name: str
    category: str
    priority: str
    status: str
    title: str
    created_at: datetime
    due_at: datetime | None
    resolved_at: datetime | None


class TicketPage(Page):
    items: list[TicketRow]


class TicketCommentOut(BaseModel):
    id: uuid.UUID
    body: str
    event: str | None
    mine: bool                  # written by this login (staff replies are shown without a name)
    created_at: datetime


class AttachmentOut(BaseModel):
    id: uuid.UUID
    comment_id: uuid.UUID | None
    file_name: str
    content_type: str
    size_bytes: int


class TicketDetail(TicketRow):
    description: str | None
    comments: list[TicketCommentOut]
    attachments: list[AttachmentOut]


class DocumentRow(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    store_name: str
    month: date
    kind: str                   # card | bill | payment
    file_name: str
    content_type: str
    size_bytes: int
    updated_at: datetime
    due_date: date | None       # bills only
    status: str | None          # bills only: PENDING | CLEARED


class DocumentPage(Page):
    items: list[DocumentRow]


class BottleRow(BaseModel):
    serial: str
    store_id: uuid.UUID
    store_name: str
    last_in_at: datetime | None


class BottlePage(Page):
    items: list[BottleRow]
    per_store: dict[str, int]   # store_id -> bottles currently there (all stores of the login, ignores paging)
