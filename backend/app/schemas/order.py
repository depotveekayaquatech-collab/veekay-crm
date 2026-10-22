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
    entered_by: str | None = None          # who wrote this day's number (an employee, or the admin / developer who imported or corrected it)
    entered_at: datetime | None = None     # and when


class OrderCalendar(BaseModel):
    store_id: uuid.UUID
    store_name: str
    store_code: str
    region_name: str | None
    year: int
    month: int
    month_label: str
    days: list[CalendarDay]
    # False when the caller may not mark this month (an earlier month, or last month after the grace days): view only
    can_mark: bool = True
    # For last month during the grace days: the last day on which it can still be marked
    open_until: date | None = None


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
    status: str
    partner_slug: str | None = None
    partner_name: str | None = None
    region_id: uuid.UUID | None = None
    today: date  # the server's "today" — the date the quick-entry list marks against
    today_count: int | None = None
    yesterday_count: int | None = None
    # days up to yesterday with no entry since the store's last filled day (this month); 0 = only today is still due
    pending_days: int = 0
    # bottles marked for this store: so far this month, and in the whole of last month
    month_bottles: int = 0
    last_month_bottles: int = 0
    # During the first days of a month (while last month can still be marked): days of last month with no entry yet, and until when
    last_month_missing: int = 0
    last_month_open_until: date | None = None


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


class StatusByPlatform(BaseModel):
    slug: str
    label: str
    live: int
    pending: int
    close: int
    total: int


class ScopeRow(BaseModel):
    """One (platform, region, state) combination that has stores — feeds the dashboard's linked filter dropdowns."""
    partner_slug: str
    region: str | None
    state: str | None


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
    status_by_platform: list[StatusByPlatform]
    scopes: list[ScopeRow]
    dormant_live: int = 0   # live stores with no order in the last 30 days
    dormant_stores: list[AttentionStore] = []   # the first 24 of them, for the dashboard panel
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
    start_dates_set: int = 0
    vendor_starts_set: int = 0
    warnings: list[str]


class MarkEntry(BaseModel):
    order_date: date
    bottle_count: int = Field(..., ge=0, le=200)


class MarkManyRequest(BaseModel):
    """Several dates of one store, each with its own count, marked in one go."""
    store_id: uuid.UUID
    entries: list[MarkEntry] = Field(..., min_length=1, max_length=31)


class MarkResultItem(BaseModel):
    order_date: date
    ok: bool
    error: str | None = None


class MarkManyResult(BaseModel):
    saved: int
    failed: int
    results: list[MarkResultItem]
