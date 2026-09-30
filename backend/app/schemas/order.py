"""Order-entry (bottle-count) request/response contracts."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class CalendarDay(BaseModel):
    day: int
    date: date
    marked: bool
    count: int | None
    source: str | None
    is_today: bool
    is_future: bool


class OrderCalendar(BaseModel):
    store_id: uuid.UUID
    store_name: str
    store_code: str
    region_name: str | None
    year: int
    month: int
    month_label: str
    days: list[CalendarDay]


class MarkRequest(BaseModel):
    store_id: uuid.UUID
    order_date: date
    bottle_count: int = Field(..., ge=0, le=200)


class AdminEntryRequest(BaseModel):
    store_id: uuid.UUID
    order_date: date
    bottle_count: int | None = Field(default=None, ge=0, le=200)  # None = clear


class MyStore(BaseModel):
    id: uuid.UUID
    name: str
    external_code: str
    state: str | None
    city: str | None
    region_name: str | None
    vendor_name: str | None
    vendor_number: str | None
    poc_name: str | None
    poc_number: str | None


class EmployeeOverviewRow(BaseModel):
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    region_name: str | None
    total_stores: int
    entries_done: int
    bottles: int
    percent: float
    error: str | None = None


class SubmissionRow(BaseModel):
    id: uuid.UUID
    submitted_at: datetime
    employee_name: str | None
    source: str
    store_code: str
    store_name: str
    order_date: date
    bottle_count: int


class DailyOverview(BaseModel):
    partner_slug: str
    partner_label: str
    date: date
    date_label: str
    day_offset: int
    employees: list[EmployeeOverviewRow]
    recent_submissions: list[SubmissionRow]


class TrendPoint(BaseModel):
    date: date
    label: str  # e.g. "Mon 8"
    entries: int
    bottles: int


class PlatformSummary(BaseModel):
    slug: str
    label: str
    total_stores: int          # stores currently visible to employees (assigned)
    entries_done: int
    bottles: int
    percent: float
    employees: int
    all_stores: int = 0        # every store on the platform, assigned or not
    live_stores: int = 0


class LeaderRow(BaseModel):
    employee_name: str
    region_name: str | None
    entries_done: int
    total_stores: int
    bottles: int
    percent: float


class CoverageRow(BaseModel):
    label: str
    live: int
    total: int


class AttentionStore(BaseModel):
    id: uuid.UUID
    name: str
    external_code: str
    platform: str | None
    status: str
    city: str | None
    state: str | None
    region_name: str | None


class DashboardInsights(BaseModel):
    trend: list[TrendPoint]
    store_status: dict[str, int]  # {LIVE: n, PENDING: n, CLOSE: n}
    platforms: list[PlatformSummary]
    leaderboard: list[LeaderRow]
    bottles_today: int
    bottles_yesterday: int
    entries_today: int
    stores_by_region: list[CoverageRow]
    stores_by_state: list[CoverageRow]
    attention_stores: list[AttentionStore]
    all_stores: list[AttentionStore]
    last_store_sync: datetime | None = None


class OrderImportResult(BaseModel):
    platform: str
    sheets: list[str]
    rows_read: int
    created: int
    updated: int
    unchanged: int
    kept_existing: int
    unknown_stores: int
    invalid_values: int
    future_skipped: int
    warnings: list[str]
