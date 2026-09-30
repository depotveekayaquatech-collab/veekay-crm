"""Store request/response contracts."""
import uuid
from datetime import date

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
    warnings: list[str]
