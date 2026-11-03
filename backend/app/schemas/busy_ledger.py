"""Request / response shapes for the vendor-payments tab and its admin screen. Money travels as a 2-decimal string ("123456.00"), never a float."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.services.busy_codes import is_valid_code, normalize_code

Money = Annotated[Decimal, AfterValidator(lambda v: v.quantize(Decimal("0.01")))]


def _first_of_month(v: date | None) -> date | None:
    if v is not None and v.day != 1:
        raise ValueError("opening_date must be the 1st of a month (the opening balance is the balance before that month's entries)")
    return v


def _tidy_name(v: str | None) -> str | None:
    return " ".join(v.split()) if v is not None else None


class VendorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    vendor_code: str
    name: str
    city: str | None
    opening_balance: Money
    opening_date: date | None
    is_active: bool


class VendorChoice(BaseModel):
    """One row of the vendor dropdown."""
    vendor_code: str
    name: str
    city: str | None


class MonthFigures(BaseModel):
    month: str                  # YYYY-MM
    opening: Money              # opening balance of the month
    month_total: Money          # bills in the month
    paid: Money                 # payments in the month
    pending: Money              # month_total - paid
    closing: Money              # opening + month_total - paid


class SummaryRow(BaseModel):
    vendor_code: str
    name: str
    city: str | None
    month_total: Money
    paid: Money
    pending: Money
    closing: Money


class SummaryTotals(BaseModel):
    vendors: int
    month_total: Money
    paid: Money
    pending: Money
    closing: Money


class SummaryPage(BaseModel):
    month: str
    items: list[SummaryRow]
    total: int
    page: int
    page_size: int
    totals: SummaryTotals


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    entry_date: date
    entry_type: Literal["BILL", "PAYMENT"]
    voucher_no: str
    narration: str | None
    amount: Money


class VendorDetail(BaseModel):
    vendor: VendorChoice
    month: MonthFigures
    history: list[MonthFigures]         # oldest first, ending with the selected month
    entries: list[LedgerEntryOut]       # the selected month, by date
    entries_truncated: bool


class Freshness(BaseModel):
    last_updated: datetime | None       # the finish time of the last successful sync (API or CSV)
    last_source: str | None
    age_minutes: int | None
    stale: bool                         # older than BUSY_STALE_HOURS
    stale_hours: int
    never_synced: bool


# ---- admin -------------------------------------------------------------------

class SyncLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    source: str
    mode: str | None
    period_from: date | None
    period_to: date | None
    triggered_by: str | None
    rows_received: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    rows_deleted: int
    rows_unmatched: int
    rows_rejected: int
    status: str
    error_message: str | None


class AdminVendorOut(VendorOut):
    id: uuid.UUID
    created_at: datetime


class VendorCreate(BaseModel):
    vendor_code: str
    name: str = Field(min_length=1, max_length=160)
    city: str | None = Field(default=None, max_length=80)
    opening_balance: Decimal = Field(default=Decimal("0"), ge=Decimal("-999999999999.99"), le=Decimal("999999999999.99"), decimal_places=2)
    opening_date: date | None = None

    @field_validator("vendor_code")
    @classmethod
    def _code(cls, v: str) -> str:
        code = normalize_code(v)
        if not is_valid_code(code):
            raise ValueError("vendor_code must be 1 to 32 letters, digits, '-' or '_'")
        return code

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = _tidy_name(v) or ""
        if not v:
            raise ValueError("name is required")
        return v

    @field_validator("city")
    @classmethod
    def _city(cls, v: str | None) -> str | None:
        return _tidy_name(v) or None

    _first = field_validator("opening_date")(_first_of_month)


class VendorUpdate(BaseModel):
    """vendor_code is deliberately absent: it never changes after creation."""
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    city: str | None = Field(default=None, max_length=80)
    opening_balance: Decimal | None = Field(default=None, ge=Decimal("-999999999999.99"), le=Decimal("999999999999.99"), decimal_places=2)
    opening_date: date | None = None
    is_active: bool | None = None

    _first = field_validator("opening_date")(_first_of_month)


class CodeCheck(BaseModel):
    vendor_code: str
    valid: bool
    exists: bool
    alias_of: str | None
    message: str | None


class UnmatchedGroup(BaseModel):
    vendor_code: str | None
    account_name: str
    rows: int
    bills: Money
    payments: Money
    first_date: date
    last_date: date
    suggested_name: str


class UnmatchedSelector(BaseModel):
    """Which unmatched rows an action covers: those with this code, or (when Busy sent no code) those with exactly this account name."""
    vendor_code: str | None = None
    account_name: str | None = None

    @field_validator("vendor_code")
    @classmethod
    def _norm(cls, v: str | None) -> str | None:
        return normalize_code(v) or None


class UnmatchedCreateVendor(UnmatchedSelector):
    new_vendor: VendorCreate


class UnmatchedMap(UnmatchedSelector):
    map_to_vendor_code: str

    @field_validator("map_to_vendor_code")
    @classmethod
    def _target(cls, v: str) -> str:
        return normalize_code(v)


class ResolveResult(BaseModel):
    vendor_code: str
    moved: int
    inserted: int
    updated: int


class KeyInfo(BaseModel):
    configured: bool
    endpoint_path: str
    header: str
    env_variable: str
    stale_hours: int
    vendor_code_regex: str
    instructions: str


class GeneratedKey(BaseModel):
    key: str
    note: str


class CsvPreview(BaseModel):
    headers: list[str]
    mapping: dict[str, str | None]
    missing_fields: list[str]
    total_rows: int
    result: dict | None             # the dry-run counts, once every required column is mapped
