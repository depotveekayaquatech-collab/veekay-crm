import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CashPurchaseCreate(BaseModel):
    """Sent as multipart form fields next to the payment-proof file."""
    kind: Literal["OFFICE", "STORE"]
    store_id: uuid.UUID | None = None
    purchase_date: date
    category: str = Field(min_length=1, max_length=32)
    other_reason: str | None = Field(default=None, max_length=300)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)


class CashPurchaseOut(BaseModel):
    id: uuid.UUID
    kind: str
    purchase_date: date
    store_id: uuid.UUID | None
    store_name: str | None
    store_code: str | None
    category: str
    category_label: str
    other_reason: str | None
    amount: Decimal
    notes: str | None
    has_proof: bool
    proof_name: str | None
    added_by: str | None
    created_at: datetime


class CashPurchaseList(BaseModel):
    items: list[CashPurchaseOut]
    total: int
    page: int
    page_size: int
    # Totals cover every row matching the filters, not just this page.
    amount_total: Decimal
    office_total: Decimal
    store_total: Decimal


class Reason(BaseModel):
    code: str
    label: str


class StoreChoice(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    platform: str | None
    state: str | None


class CashPurchaseOptions(BaseModel):
    office_reasons: list[Reason]
    store_reasons: list[Reason]
    stores: list[StoreChoice]
    can_view_all: bool
    max_amount: Decimal
