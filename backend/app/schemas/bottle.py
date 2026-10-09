import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    quantity: int = Field(..., ge=1, le=200000, description="How many new, unique QR codes to create.")
    note: str | None = Field(default=None, max_length=255)


class BatchOut(BaseModel):
    id: uuid.UUID
    quantity: int
    note: str | None
    created_by_name: str
    created_at: datetime
    first_serial: str | None = None
    last_serial: str | None = None


class ScanRequest(BaseModel):
    serial: str = Field(..., min_length=4, max_length=40, description="The text of the QR code, e.g. VK-7F3K-9Q2M.")
    direction: Literal["IN", "OUT"]
    store_id: uuid.UUID | None = Field(default=None, description="Required for IN; OUT defaults to the store the bottle is at.")
    scanned_at: datetime | None = Field(default=None, description="When it was really scanned (offline re-sends). Defaults to now.")
    scan_id: str | None = Field(default=None, max_length=128, description="Your unique id for this scan; sending it again never double-counts.")


class ExternalScan(BaseModel):
    serial: str = Field(..., min_length=4, max_length=40)
    direction: Literal["IN", "OUT"]
    store_code: str | None = Field(default=None, max_length=64, description="The store's outlet code as shown in the CRM.")
    platform: str | None = Field(default=None, max_length=32, description="blinkit / zepto — only needed if a code exists on both.")
    scanned_at: datetime | None = None
    scan_id: str | None = Field(default=None, max_length=128)
    scanned_by: str | None = Field(default=None, max_length=255, description="Who scanned it (name / device) on the other system.")


class ScanOut(BaseModel):
    id: uuid.UUID
    direction: str
    store_id: uuid.UUID | None
    store_name: str | None
    scanned_at: datetime
    source: str
    scanned_by_name: str | None
    warning: str | None


class BottleOut(BaseModel):
    id: uuid.UUID
    serial: str
    status: str
    store_id: uuid.UUID | None = None
    store_name: str | None = None
    last_in_at: datetime | None = None
    last_out_at: datetime | None = None
    last_scan_at: datetime | None = None
    days_at_store: int | None = None
    overdue: bool = False
    replaces_serial: str | None = None
    replaced_by_serial: str | None = None
    retired_at: datetime | None = None
    retire_reason: str | None = None


class ScanResult(BaseModel):
    duplicate: bool = False        # the same scan_id was already recorded; nothing changed
    warning: str | None = None     # recorded, but out of the normal IN -> OUT order
    bottle: BottleOut
    scan: ScanOut


class BottleDetail(BaseModel):
    bottle: BottleOut
    scans: list[ScanOut]


class BottleList(BaseModel):
    items: list[BottleOut]
    total: int
    page: int
    page_size: int


class Summary(BaseModel):
    total_active: int
    unused: int
    at_store: int
    returned: int
    retired: int
    deleted: int = 0
    overdue: int
    lost_after_days: int


class ReasonBody(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class ReplaceResult(BaseModel):
    old: BottleOut
    new: BottleOut


class DeleteRequest(BaseModel):
    serials: list[str] = Field(..., min_length=1, max_length=5000)
    reason: str | None = Field(default=None, max_length=255)


class BatchDeleteRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class DeleteResult(BaseModel):
    deleted: int
    already_deleted: int = 0
    skipped_in_use: list[str] = []   # batch delete leaves codes that are already in circulation (scanned)
    not_found: list[str] = []
