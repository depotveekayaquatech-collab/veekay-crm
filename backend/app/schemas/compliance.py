"""Compliance cards & bills contracts."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class DocBrief(BaseModel):
    id: uuid.UUID
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: str | None = None
    # bills only
    due_date: date | None = None
    status: str | None = None          # PENDING | CLEARED
    overdue: bool = False


class ComplianceStoreRow(BaseModel):
    store_id: uuid.UUID
    name: str
    external_code: str
    platform: str | None
    platform_slug: str | None
    entity: str | None
    state: str | None
    city: str | None
    vendor_name: str | None
    card: DocBrief | None
    bill: DocBrief | None


class ComplianceStorePage(BaseModel):
    month: str                       # YYYY-MM
    month_label: str
    months: list[str]                # selectable months, newest first
    items: list[ComplianceStoreRow]
    total: int
    page: int
    page_size: int
    cards_done: int                  # across ALL matching stores, not just this page
    bills_done: int
    bills_pending: int


class SearchRow(BaseModel):
    store_id: uuid.UUID
    month: str
    name: str
    external_code: str
    platform: str | None
    entity: str | None
    state: str | None
    city: str | None
    vendor_name: str | None
    card: DocBrief | None
    bill: DocBrief | None


class SearchPage(BaseModel):
    items: list[SearchRow]
    total: int
    page: int
    page_size: int


class DueBill(BaseModel):
    id: uuid.UUID
    store_id: uuid.UUID
    store_name: str
    external_code: str
    platform: str | None
    entity: str | None
    state: str | None
    vendor_name: str | None
    month: str
    due_date: date
    days_overdue: int
    file_name: str


class DueBills(BaseModel):
    total: int
    items: list[DueBill]


class DownloadRequest(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=300)
