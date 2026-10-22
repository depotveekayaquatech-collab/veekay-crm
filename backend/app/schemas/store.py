"""Store request/response contracts."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.store import StoreStatus


class StoreBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    external_code: str = Field(..., min_length=1, max_length=64)
    state: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    poc_name: str | None = Field(default=None, max_length=128)
    poc_number: str | None = Field(default=None, max_length=32)
    vendor_name: str | None = Field(default=None, max_length=128)
    vendor_number: str | None = Field(default=None, max_length=32)
    start_date: date | None = None


class StoreCreate(StoreBase):
    start_date: date   # mandatory for every new store: the day supply began
    partner_organization_id: uuid.UUID
    region_id: uuid.UUID | None = None
    status: StoreStatus = StoreStatus.LIVE


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    external_code: str | None = Field(default=None, min_length=1, max_length=64)
    region_id: uuid.UUID | None = None
    state: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    poc_name: str | None = Field(default=None, max_length=128)
    poc_number: str | None = Field(default=None, max_length=32)
    vendor_name: str | None = Field(default=None, max_length=128)
    vendor_number: str | None = Field(default=None, max_length=32)
    start_date: date | None = None
    status: StoreStatus | None = None


class StoreOut(BaseModel):
    id: uuid.UUID
    name: str
    external_code: str
    crm_code: str | None = None          # the permanent system code (BKT000123 / ZPT000045)
    status: str
    entity: str | None = None
    start_date: date | None = None
    state: str | None
    city: str | None
    address: str | None
    poc_name: str | None
    poc_number: str | None
    vendor_name: str | None
    vendor_number: str | None
    region_id: uuid.UUID | None = None
    region_name: str | None = None
    partner_organization_id: uuid.UUID
    partner_slug: str | None = None
    partner_name: str | None = None

    model_config = {"from_attributes": True}


class StoreSyncResult(BaseModel):
    platform: str
    created: int
    updated: int
    unchanged: int
    rows_read: int
    vendor_changes: int = 0
    without_start_date: int = 0
    warnings: list[str]


class VendorPeriodOut(BaseModel):
    vendor_name: str
    vendor_number: str | None
    start_date: date | None
    end_date: date | None          # None = the current vendor
    start_confirmed: bool          # False: start is provisional until the first order of this vendor is imported
    current: bool
    changed_by: str | None = None  # who made the change (None for vendors that pre-date this record)
    source: str = ""               # manual | file | sheet | backfill
    recorded_on: datetime | None = None
