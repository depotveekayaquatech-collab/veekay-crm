"""Schemas for the Inventory (stores grouped by vendor) view."""
import uuid
from datetime import date

from pydantic import BaseModel


class InventoryStore(BaseModel):
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
    start_date: date | None = None
    last_entry_date: date | None   # latest entry this month
    pending_days: int              # days up to yesterday with no entry after the last filled day
    marked_today: bool
    month_bottles: int
    month_entries: int


class InventorySummary(BaseModel):
    stores: int
    behind: int          # stores with pending_days > 0
    marked_today: int
    total_pending_days: int


class Inventory(BaseModel):
    month_label: str
    summary: InventorySummary
    items: list[InventoryStore]
