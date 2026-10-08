"""
Water-test reports per platform and state, each valid for six months.

Only platforms listed in TEST_REPORT_PLATFORMS accept reports (Zepto for now; Blinkit is switched off).
A state's *current* report is its newest one (latest period_end). It is VALID until
TEST_REPORT_ALERT_DAYS before it ends, EXPIRING after that, and EXPIRED once period_end has passed;
a state with stores but no report is MISSING. Files are never deleted from storage: replacing a report for the
same period, or removing one, only archives the old row.
"""
from __future__ import annotations

import calendar
import hashlib
import re
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import settings
from app.models.organization import Organization, OrganizationKind
from app.models.store import Store, StoreStatus
from app.models.test_report import TestReport
from app.models.user import User
from app.schemas.test_report import (
    PlatformFlag, StateReports, TestReportOut, TestReportOverview, TestReportSummary,
)
from app.services import activity_service
from app.services.compliance_service import _CONTENT_TYPES, _err, _prepare, _today

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MONTHS_BACK = 24      # how far back a report period may start
VALID_MONTHS = 6


# --------------------------------------------------------------------------
# dates + status
# --------------------------------------------------------------------------

def period_end_for(start: date) -> date:
    """Last day of the sixth month counting `start`'s month as the first (Oct -> Mar 31)."""
    idx = start.year * 12 + (start.month - 1) + (VALID_MONTHS - 1)
    y, m = divmod(idx, 12)
    return date(y, m + 1, calendar.monthrange(y, m + 1)[1])


def parse_period_start(value: str) -> date:
    m = _MONTH.match((value or "").strip())
    if not m:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick the month the 6-month period starts in (YYYY-MM).")
    start = date(int(m.group(1)), int(m.group(2)), 1)
    today = _today()
    this_month = today.replace(day=1)
    earliest = date((this_month.year * 12 + this_month.month - 1 - MONTHS_BACK) // 12,
                    (this_month.year * 12 + this_month.month - 1 - MONTHS_BACK) % 12 + 1, 1)
    latest = date(this_month.year + (this_month.month // 12), this_month.month % 12 + 1, 1)  # next month
    if start < earliest or start > latest:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, "That period is too far in the past or the future.")
    return start


def _days_left(end: date, today: date) -> int:
    return (end - today).days


def _status_for(days_left: int) -> str:
    if days_left < 0:
        return "EXPIRED"
    return "EXPIRING" if days_left <= settings.TEST_REPORT_ALERT_DAYS else "VALID"


# --------------------------------------------------------------------------
# platforms
# --------------------------------------------------------------------------

def _platform_flags(db: Session, org_id: uuid.UUID) -> list[PlatformFlag]:
    enabled = {s.lower() for s in settings.TEST_REPORT_PLATFORMS}
    rows = db.execute(
        select(Organization).where(Organization.kind == OrganizationKind.PARTNER.value).order_by(Organization.name)
    ).scalars().all()
    return [PlatformFlag(slug=o.slug, name=o.name, enabled=o.slug.lower() in enabled) for o in rows]


def _partner(db: Session, slug: str) -> Organization:
    p = db.execute(
        select(Organization).where(
            Organization.slug == (slug or "").strip().lower(), Organization.kind == OrganizationKind.PARTNER.value
        )
    ).scalar_one_or_none()
    if p is None:
        raise _err(status.HTTP_404_NOT_FOUND, "That platform does not exist.")
    return p


def _enabled_partner(db: Session, slug: str) -> Organization:
    p = _partner(db, slug)
    if p.slug.lower() not in {s.lower() for s in settings.TEST_REPORT_PLATFORMS}:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Test reports are not enabled for {p.name} yet.")
    return p


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def _out(r: TestReport, today: date, uploader: str | None) -> TestReportOut:
    left = _days_left(r.period_end, today)
    return TestReportOut(
        id=r.id, period_start=r.period_start, period_end=r.period_end, file_name=r.file_name,
        content_type=r.content_type, size_bytes=r.size_bytes, uploaded_at=r.updated_at, uploaded_by=uploader,
        days_left=left, status=_status_for(left),
    )


def _state_key(s: str) -> str:
    return " ".join((s or "").split()).lower()


def partner_states(db: Session, org_id: uuid.UUID, partner_id: uuid.UUID) -> dict[str, tuple[str, int]]:
    """{normalised state: (display name, live store count)} for the platform's stores."""
    rows = db.execute(
        select(Store.state, func.count(Store.id))
        .where(Store.organization_id == org_id, Store.partner_organization_id == partner_id,
               Store.state.is_not(None), Store.status == StoreStatus.LIVE.value)
        .group_by(Store.state)
    ).all()
    out: dict[str, tuple[str, int]] = {}
    for name, n in rows:
        key = _state_key(name)
        if key:
            prev = out.get(key)
            out[key] = (prev[0] if prev else " ".join(name.split()), (prev[1] if prev else 0) + int(n))
    return out


def overview(db: Session, user: User, partner_slug: str) -> TestReportOverview:
    partner = _partner(db, partner_slug)
    flags = _platform_flags(db, user.organization_id)
    flag = next(f for f in flags if f.slug == partner.slug)
    empty = TestReportSummary(states_total=0, valid=0, expiring=0, expired=0, missing=0, reports_total=0)
    if not flag.enabled:
        return TestReportOverview(platform=flag, platforms=flags, alert_days=settings.TEST_REPORT_ALERT_DAYS, summary=empty, states=[])

    today = _today()
    states = partner_states(db, user.organization_id, partner.id)
    reports = db.execute(
        select(TestReport)
        .where(TestReport.organization_id == user.organization_id, TestReport.partner_organization_id == partner.id,
               TestReport.deleted_at.is_(None))
        .order_by(TestReport.period_end.desc(), TestReport.created_at.desc())
    ).scalars().all()
    names: dict[uuid.UUID, str] = {
        u.id: u.full_name for u in db.execute(
            select(User).where(User.id.in_({r.uploaded_by_user_id for r in reports if r.uploaded_by_user_id}))
        ).scalars()
    } if reports else {}

    by_state: dict[str, list[TestReport]] = {}
    for r in reports:
        by_state.setdefault(_state_key(r.state), []).append(r)
        states.setdefault(_state_key(r.state), (r.state, 0))   # a state with a report but no live store still shows

    rows: list[StateReports] = []
    for key, (display, n_stores) in states.items():
        mine = [_out(r, today, names.get(r.uploaded_by_user_id)) for r in by_state.get(key, [])]
        rows.append(StateReports(
            state=display, stores=n_stores, status=mine[0].status if mine else "MISSING",
            current=mine[0] if mine else None, history=mine[1:],
        ))
    # Problems first: expired, expiring, missing, then the healthy ones.
    order = {"EXPIRED": 0, "EXPIRING": 1, "MISSING": 2, "VALID": 3}
    rows.sort(key=lambda s: (order[s.status], s.state.lower()))

    def n(st: str) -> int:
        return sum(1 for s in rows if s.status == st)

    summary = TestReportSummary(
        states_total=len(rows), valid=n("VALID"), expiring=n("EXPIRING"), expired=n("EXPIRED"), missing=n("MISSING"),
        reports_total=sum(1 for s in rows if s.current),
    )
    return TestReportOverview(platform=flag, platforms=flags, alert_days=settings.TEST_REPORT_ALERT_DAYS, summary=summary, states=rows)


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------

def upload(
    db: Session, user: User, partner_slug: str, state: str, period_start: str, filename: str, data: bytes,
) -> TestReportOut:
    partner = _enabled_partner(db, partner_slug)
    start = parse_period_start(period_start)
    end = period_end_for(start)

    known = partner_states(db, user.organization_id, partner.id)
    key = _state_key(state)
    if key not in known:
        raise _err(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{partner.name} has no live stores in '{state}'. Pick one of its states.")
    display = known[key][0]

    body, ext = _prepare([(filename or "report", data)])

    # Re-uploading the same state + period replaces it: the old row is archived, its file stays in storage.
    same = db.execute(
        select(TestReport).where(
            TestReport.partner_organization_id == partner.id, TestReport.period_start == start,
            func.lower(TestReport.state) == key, TestReport.deleted_at.is_(None),
        )
    ).scalars().all()
    for old in same:
        old.deleted_at = datetime.now(timezone.utc)
        old.deleted_by_user_id = user.id
    version = db.execute(
        select(func.count(TestReport.id)).where(
            TestReport.partner_organization_id == partner.id, TestReport.period_start == start, func.lower(TestReport.state) == key
        )
    ).scalar_one() + 1

    storage_key = (
        f"Test reports/{storage.safe_segment(partner.name)}/{storage.safe_segment(display.upper())}/"
        f"{start:%Y-%m}-to-{end:%Y-%m}-v{version}.{ext}"
    )
    storage.save(storage_key, body)
    report = TestReport(
        organization_id=user.organization_id, partner_organization_id=partner.id, state=display,
        period_start=start, period_end=end, file_key=storage_key,
        file_name=f"{partner.slug}_{display.replace(' ', '-')}_test-report_{start:%Y-%m}.{ext}",
        content_type=_CONTENT_TYPES[ext], size_bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
        storage_backend=settings.STORAGE_BACKEND, uploaded_by_user_id=user.id,
    )
    db.add(report)
    db.flush()
    activity_service.record(
        db, actor=user, action="test_report.uploaded", entity_type="test_report", entity_id=report.id,
        metadata={"platform": partner.slug, "state": display, "period": f"{start:%Y-%m} to {end:%Y-%m}", "replaced": len(same)},
    )
    db.commit()
    db.refresh(report)
    return _out(report, _today(), user.full_name)


def _get(db: Session, user: User, report_id: uuid.UUID) -> TestReport:
    r = db.get(TestReport, report_id)
    if r is None or r.organization_id != user.organization_id or r.deleted_at is not None:
        raise _err(status.HTTP_404_NOT_FOUND, "Test report not found.")
    return r


def remove(db: Session, user: User, report_id: uuid.UUID) -> None:
    r = _get(db, user, report_id)
    r.deleted_at = datetime.now(timezone.utc)
    r.deleted_by_user_id = user.id
    activity_service.record(
        db, actor=user, action="test_report.removed", entity_type="test_report", entity_id=r.id,
        metadata={"state": r.state, "period": f"{r.period_start:%Y-%m} to {r.period_end:%Y-%m}"},
    )
    db.commit()


def _ref(db: Session, user: User, report_id: uuid.UUID) -> tuple[str, str, str]:
    r = _get(db, user, report_id)
    if not storage.exists(r.file_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The file is missing from storage. Please upload it again.")
    return r.file_key, r.content_type, r.file_name


def read_file(db: Session, user: User, report_id: uuid.UUID) -> tuple[bytes, str, str]:
    key, content_type, name = _ref(db, user, report_id)
    return storage.read(key), content_type, name


def file_link(db: Session, user: User, report_id: uuid.UUID) -> dict:
    key, content_type, name = _ref(db, user, report_id)
    return {
        "url": storage.signed_url(key, filename=name, content_type=content_type),
        "content_type": content_type, "file_name": name, "expires_in": settings.S3_URL_EXPIRE_SECONDS,
    }
