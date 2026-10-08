"""Test report contracts."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel


class TestReportOut(BaseModel):
    __test__ = False

    id: uuid.UUID
    period_start: date
    period_end: date
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime
    uploaded_by: str | None = None
    days_left: int                # negative once expired
    status: str                   # VALID | EXPIRING | EXPIRED


class StateReports(BaseModel):
    state: str
    stores: int                   # live stores of the platform in this state
    status: str                   # VALID | EXPIRING | EXPIRED | MISSING
    current: TestReportOut | None # the newest report; null when none was ever uploaded
    history: list[TestReportOut]  # older reports, newest first


class PlatformFlag(BaseModel):
    slug: str
    name: str
    enabled: bool


class TestReportSummary(BaseModel):
    __test__ = False

    states_total: int
    valid: int
    expiring: int
    expired: int
    missing: int
    reports_total: int            # reports on file (current ones, one per state)


class TestReportOverview(BaseModel):
    __test__ = False

    platform: PlatformFlag
    platforms: list[PlatformFlag]
    alert_days: int
    summary: TestReportSummary
    states: list[StateReports]
