"""Ticket request/response contracts."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["LATE_DELIVERY", "NO_DELIVERY", "SHORT_SUPPLY", "QUALITY", "DAMAGED", "BILLING", "OTHER"]
Priority = Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
Status = Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]


class StoreBrief(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    city: str | None = None
    state: str | None = None
    region_id: uuid.UUID | None = None
    region_name: str | None = None
    vendor_name: str | None = None
    vendor_number: str | None = None
    platform_slug: str | None = None
    platform_name: str | None = None


class Assignee(BaseModel):
    id: uuid.UUID
    name: str
    code: str


class TicketOut(BaseModel):
    id: uuid.UUID
    number: int
    store: StoreBrief
    category: Category
    priority: Priority
    status: Status
    title: str
    description: str | None = None
    created_by_name: str | None = None
    source: str = "app"          # app | google
    assigned_to_id: uuid.UUID | None = None
    assigned_to_name: str | None = None
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None = None
    resolved_at: datetime | None = None
    is_overdue: bool = False
    comments_count: int = 0
    # What the caller may do with this ticket (so the UI shows only valid actions).
    next_statuses: list[Status] = []
    can_assign: bool = False
    can_set_priority: bool = False


class CommentOut(BaseModel):
    id: uuid.UUID
    author_name: str | None = None
    body: str
    event: str | None = None
    created_at: datetime


class TicketDetail(TicketOut):
    comments: list[CommentOut] = []
    assignees: list[Assignee] = []


class TicketCreate(BaseModel):
    store_id: uuid.UUID
    category: Category
    priority: Priority = "MEDIUM"
    title: str = Field(..., min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    assigned_to_id: uuid.UUID | None = None


class TicketUpdate(BaseModel):
    status: Status | None = None
    priority: Priority | None = None
    assigned_to_id: uuid.UUID | None = None
    unassign: bool = False


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class StoreChoice(StoreBrief):
    pass


# ---- admin insights ----

class Bucket(BaseModel):
    label: str
    total: int          # tickets raised in the window
    active: int         # open + in progress right now
    delivery: int       # late / no-delivery tickets in the window
    overdue: int        # active and past their SLA
    severity: Literal["ok", "medium", "high"]


class Hotspot(BaseModel):
    store_id: uuid.UUID
    name: str
    code: str
    state: str | None = None
    region_name: str | None = None
    vendor_name: str | None = None
    platform_name: str | None = None
    active: int
    delivery: int
    overdue: int
    total: int


class TrendPoint(BaseModel):
    label: str
    created: int
    resolved: int


class CategoryCount(BaseModel):
    category: Category
    count: int


class TicketSummary(BaseModel):
    open: int
    in_progress: int
    overdue: int
    delivery_active: int
    raised: int
    resolved: int
    avg_resolution_hours: float | None = None


class TicketAnalytics(BaseModel):
    days: int
    summary: TicketSummary
    by_region: list[Bucket]
    by_state: list[Bucket]
    by_vendor: list[Bucket]
    by_platform: list[Bucket]
    by_category: list[CategoryCount]
    trend: list[TrendPoint]
    hotspots: list[Hotspot]
