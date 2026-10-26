"""Zero Review: stores stuck at zero, the weekly review and the monthly verification. Every route needs `zero.view` (all staff but partner logins); the
service narrows everything to the caller's own scope, and refuses review actions to anyone without `zero.review`."""
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import zero_review_service as svc

router = APIRouter(prefix="/zero-review", tags=["zero-review"], dependencies=[Depends(require_permission("zero.view"))])


def filters(
    date_from: date | None = None, date_to: date | None = None,
    region: list[uuid.UUID] = Query(default=[]), employee: list[uuid.UUID] = Query(default=[]),
    platform: str | None = Query(None, max_length=32), search: str | None = Query(None, max_length=100),
    review_status: str | None = Query(None, max_length=10), n: int = Query(0, ge=0, le=366),
    unmarked: str = Query("break", max_length=8), unmarked_ge: int = Query(0, ge=0, le=366),
    sort: str = Query("streak", max_length=12),
) -> svc.Filters:
    t = svc.today()
    return svc.Filters(
        date_from=date_from or svc.week_start_of(t), date_to=date_to or t, regions=region, employees=employee, platform=platform, search=search,
        review_status=review_status, n=n, mode=unmarked, unmarked_ge=unmarked_ge, sort=sort,
    )


def _no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/options")
def options(response: Response, perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _no_cache(response)
    return svc.options(db, user, perms)


@router.get("/badge")
def badge(response: Response, perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _no_cache(response)
    return svc.badge(db, user, perms)


@router.get("/streaks")
def streaks(
    response: Response, f: svc.Filters = Depends(filters), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=svc.MAX_PAGE),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """Stores with their longest run of zero days in the range. `n` keeps only runs of that many days or more; `unmarked` is break | ignore | count."""
    _no_cache(response)
    return svc.streaks(db, user, perms, f, page, page_size)


@router.get("/export")
def export(f: svc.Filters = Depends(filters), perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """The same rows as the Zero Streaks tab, as a CSV file (opens in Excel)."""
    body = svc.export_csv(db, user, perms, f)
    return Response("﻿" + body, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="zero-review-{f.date_from}-{f.date_to}.csv"', "Cache-Control": "private, no-store"})


@router.get("/stores/{store_id}/days")
def store_days(
    store_id: uuid.UUID, response: Response, f: svc.Filters = Depends(filters),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    _no_cache(response)
    return svc.store_days(db, user, perms, store_id, f)


@router.get("/weekly")
def weekly(
    response: Response, week_start: date | None = None, threshold: int = Query(svc.WEEKLY_THRESHOLD, ge=1, le=6), f: svc.Filters = Depends(filters),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """The flagged stores of one Monday-to-Saturday week (default: the cycle of the most recent Saturday) and where each stands in review."""
    _no_cache(response)
    return svc.weekly(db, user, perms, week_start or svc.default_week(), threshold, f)


class WeeklyReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    week_start: date
    store_ids: list[uuid.UUID] = Field(min_length=1, max_length=svc.MAX_BULK)
    threshold: int = Field(svc.WEEKLY_THRESHOLD, ge=1, le=6)
    reason: str = Field(max_length=32)
    remark: str = Field(max_length=1000)
    follow_up_date: date | None = None


@router.post("/weekly/review")
def review_week(payload: WeeklyReview, perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Mark stores reviewed for a week (one or many at once), with a reason and a remark. Logged; it can be reviewed again later, and every version is kept."""
    return svc.review_week(db, user, perms, payload.week_start, payload.store_ids, payload.threshold, payload.reason, payload.remark, payload.follow_up_date)


@router.get("/monthly")
def monthly(
    response: Response, month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), f: svc.Filters = Depends(filters),
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """One month (default: last month) per store: orders, zero days, unmarked days, longest streak, weekly review summary and verification state."""
    _no_cache(response)
    return svc.monthly(db, user, perms, svc.parse_month(month), f)


class MonthlyVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    store_ids: list[uuid.UUID] = Field(min_length=1, max_length=svc.MAX_BULK)
    status: str = Field(pattern="^(verified|flagged)$")
    remark: str = Field(max_length=1000)


@router.post("/monthly/verify")
def verify_month(payload: MonthlyVerify, perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return svc.verify_month(db, user, perms, svc.parse_month(payload.month), payload.store_ids, payload.status, payload.remark)


class MonthlyReopen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    reason: str = Field(max_length=1000)


@router.post("/monthly/reopen")
def reopen_month(payload: MonthlyReopen, perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Administrators only: reopen a closed month for a few days, with a reason that is logged."""
    return svc.reopen_month(db, user, perms, svc.parse_month(payload.month), payload.reason)


@router.get("/history")
def history(
    response: Response, f: svc.Filters = Depends(filters), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=svc.MAX_PAGE),
    reviewer: str | None = Query(None, max_length=100), status: str | None = Query(None, pattern="^(pending|reviewed|verified|flagged)$"),
    period_from: date | None = None, period_to: date | None = None,
    perms: set[str] = Depends(get_current_permissions), user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    """The audit trail: every review and verification ever made in the caller's scope, newest first."""
    _no_cache(response)
    return svc.history(db, user, perms, f, page, page_size, reviewer, status, period_from, period_to)
