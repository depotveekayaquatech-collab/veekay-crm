import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class SyncSummary(BaseModel):
    sync_id: uuid.UUID
    sync_code: str
    synced_at: datetime
    records_found: int
    new_records: int
    changed_records: int
    already_processed: int      # applied or skipped earlier
    pending_review: int         # synced earlier, still waiting for the developer


class SyncRunOut(BaseModel):
    sync_id: uuid.UUID
    sync_code: str
    synced_at: datetime
    developer: str
    records_found: int
    new_records: int
    changed_records: int
    already_processed: int
    applied: int                # records from this sync that have since been applied


class SourceSnapshot(BaseModel):
    store_id: str | None = None
    store_code: str | None = None
    store_name: str | None = None
    purchase_date: str
    amount: str
    reason: str | None = None
    added_by: str | None = None


class SyncRecordOut(BaseModel):
    id: uuid.UUID
    purchase_id: uuid.UUID
    purchase_code: str
    status: str
    store_id: uuid.UUID | None
    outlet_code: str | None
    outlet_name: str | None
    purchase_date: date
    amount: Decimal
    price_per_item: Decimal | None
    auto_qty: int | None
    final_qty: int | None
    overridden: bool
    reason: str | None
    added_by: str | None
    sync_code: str | None
    applied_qty: int | None
    applied_at: datetime | None
    # For CHANGED records: the source as it was when synced, and as it is now.
    previous_source: SourceSnapshot | None = None
    current_source: SourceSnapshot | None = None
    ever_applied: bool = False


class SyncOverview(BaseModel):
    last_sync: SyncSummary | None
    counts: dict[str, int]          # status -> number of records
    items: list[SyncRecordOut]
    total: int
    page: int
    page_size: int


class RecordEdit(BaseModel):
    """Only the fields that are sent change. `final_qty: null` clears the override (back to the calculated one)."""
    store_id: uuid.UUID | None = None
    purchase_date: date | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    price_per_item: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    final_qty: int | None = Field(default=None, ge=0, le=100000)


class StandardRate(BaseModel):
    price_per_item: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # False: only purchases that have no price yet. True: every purchase still to review gets this price.
    overwrite: bool = False


class StandardRateResult(BaseModel):
    updated: int
    kept: int          # already had a price and were left alone


class ResolveRequest(BaseModel):
    action: Literal["accept_source", "keep_mine", "acknowledge", "reopen", "skip", "unskip"]


class RecordIds(BaseModel):
    record_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class SyncPreviewPurchase(BaseModel):
    record_id: uuid.UUID
    purchase_code: str
    amount: Decimal
    price_per_item: Decimal | None
    auto_qty: int | None
    final_qty: int | None
    error: str | None = None


class SyncPreviewRow(BaseModel):
    store_id: uuid.UUID | None
    outlet_code: str
    outlet_name: str
    purchase_date: date
    employee_entry: int | None
    previous: int
    added: int
    new_total: int
    purchases: list[SyncPreviewPurchase]
    error: str | None = None


class SyncPreview(BaseModel):
    rows: list[SyncPreviewRow]
    total_stores: int
    total_records: int
    total_qty: int
    can_apply: bool


class SyncApplyFailure(BaseModel):
    outlet_code: str
    outlet_name: str
    purchase_date: date
    error: str


class SyncApplyResult(BaseModel):
    batch_id: uuid.UUID
    applied_records: int
    applied_rows: list[SyncPreviewRow]
    failed: list[SyncApplyFailure]
