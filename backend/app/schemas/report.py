"""Schemas for the Reports and Pending-entries admin views."""
import uuid
from datetime import date

from pydantic import BaseModel


class ReportRow(BaseModel):
    key: str
    label: str
    sub: str | None = None
    entries: int
    bottles: int
    active_days: int
    avg_per_entry: float
    share_percent: float


class ReportPoint(BaseModel):
    date: date
    label: str
    bottles: int
    entries: int


class SalesReport(BaseModel):
    start: date
    end: date
    group_by: str
    total_bottles: int
    total_entries: int
    days: int
    avg_bottles_per_day: float
    rows: list[ReportRow]
    row_count: int = 0          # rows before any `limit` was applied (e.g. how many stores had orders)
    series: list[ReportPoint]


class PendingStore(BaseModel):
    id: uuid.UUID
    name: str
    external_code: str
    platform: str | None
    platform_slug: str | None
    region_name: str | None
    state: str | None
    city: str | None
    vendor_name: str | None
    vendor_number: str | None
    poc_name: str | None
    poc_number: str | None
    pending_days: int = 0
    last_entry_date: date | None = None


class PendingEntries(BaseModel):
    date: date
    date_label: str
    day_offset: int
    live_stores: int
    marked: int
    pending: int
    items: list[PendingStore]
