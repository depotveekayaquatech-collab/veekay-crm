import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AdjustRequest(BaseModel):
    """One cash purchase applied to one or several stores for one date."""
    store_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    purchase_date: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    price_per_item: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # The developer's override of the calculated quantity (a whole number); None = use the calculated one.
    quantity: int | None = Field(default=None, ge=0, le=100000)


class PreviewRow(BaseModel):
    store_id: uuid.UUID
    outlet_code: str
    outlet_name: str
    has_entry: bool
    employee_entry: int | None        # the real entry, without earlier adjustments (None = nobody entered a count yet)
    previous: int                     # what the sheet shows now
    added: int
    new_total: int
    error: str | None = None


class Preview(BaseModel):
    purchase_date: date
    amount: Decimal
    price_per_item: Decimal
    auto_qty: int
    final_qty: int
    overridden: bool
    total_stores: int
    rows: list[PreviewRow]
    can_apply: bool


class FailedStore(BaseModel):
    store_id: uuid.UUID | None
    outlet_code: str
    outlet_name: str
    error: str


class ApplyResult(BaseModel):
    batch_id: uuid.UUID
    auto_qty: int
    final_qty: int
    applied: list[PreviewRow]
    failed: list[FailedStore]


class AdjustmentOut(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    created_at: datetime
    developer: str
    outlet_code: str
    outlet_name: str
    purchase_date: date
    amount: Decimal
    price_per_item: Decimal
    auto_qty: int
    final_qty: int
    previous_qty: int
    final_order_qty: int
    sync_code: str | None = None
    purchase_code: str | None = None
    source: str = "Manual"
    action: str = "Applied"


class AdjustmentList(BaseModel):
    items: list[AdjustmentOut]
    total: int
    page: int
    page_size: int


class StoreChoice(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    platform: str | None
    state: str | None
