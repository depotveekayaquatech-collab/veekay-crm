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


class ComplianceRow(BaseModel):
    store_id: uuid.UUID
    name: str
    external_code: str
    platform: str | None
    platform_slug: str | None
    entity: str | None
    state: str | None
    city: str | None
    region_name: str | None
    vendor_name: str | None
    manager: str | None              # the responsible employee ("delivery manager")
    status: str                      # PENDING (nothing logged) | PARTIAL | COMPLETE
    percent: int                     # share of the 3 required items logged (card, invoice, payment proof)
    card: DocBrief | None
    bill: DocBrief | None            # the invoice
    payment: DocBrief | None         # proof of payment


class ComplianceKpis(BaseModel):
    total: int
    card_logged: int
    card_missing: int
    invoice_logged: int
    invoice_missing: int
    payment_logged: int
    payment_missing: int
    compliance_percent: float


class RegionOption(BaseModel):
    id: uuid.UUID
    name: str


class ComplianceOptions(BaseModel):
    regions: list[RegionOption]
    cities: list[str]
    managers: list[str]
    has_unassigned: bool


class ComplianceStorePage(BaseModel):
    month: str                       # YYYY-MM
    month_label: str
    months: list[str]                # selectable months, newest first
    items: list[ComplianceRow]
    total: int                       # rows after ALL filters
    page: int
    page_size: int
    kpis: ComplianceKpis             # over the store-level filters (region, city, channel, manager, search)
    options: ComplianceOptions


class BulkFailure(BaseModel):
    store: str
    error: str


class BulkUploadResult(BaseModel):
    kind: str
    month: str
    files_received: int
    files_matched: int
    stores_updated: int
    unmatched: list[str]
    failed: list[BulkFailure]


class SummaryPdfRequest(BaseModel):
    store_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=600)
    month: str | None = None


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
    payment: DocBrief | None = None


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
