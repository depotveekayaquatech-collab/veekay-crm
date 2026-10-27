"""Attendance (check in / check out + location), leave requests, and the offices that define "at the office"."""
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import attendance_import_service, attendance_service, holiday_service, leave_service

router = APIRouter(prefix="/attendance", tags=["attendance"])


class OfficeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=10, le=5000)


class OfficeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=10, le=5000)
    is_active: bool | None = None


class Reading(BaseModel):
    """Where the device is when the person taps Check in / Check out. Optional: no location is recorded as 'not shared'."""
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100000)


class RecordCorrection(BaseModel):
    """Developer fix for one person's day. Send only what changes."""
    user_id: uuid.UUID
    work_date: date
    check_in_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # local HH:MM; also marks a person with no check-in present
    check_out_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # local HH:MM
    presence: Literal["office", "away"] | None = None
    office_id: uuid.UUID | None = None
    late: bool | None = None
    half_day: bool | None = None
    clear_check_out: bool = False


class MarkDays(BaseModel):
    """Developer: mark one person present on these dates (backlog days too), or take a hand-made mark away."""
    user_id: uuid.UUID
    dates: list[date] = Field(min_length=1, max_length=62)
    present: bool = True


class LeaveApply(BaseModel):
    leave_type: Literal["CASUAL", "SICK", "PAID", "UNPAID"]
    start_date: date
    end_date: date
    half_day: bool = False
    reason: str = Field(..., min_length=1, max_length=500)


class LeaveReview(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- my day

@router.get("/today")
def today(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Your status today: checked in / out, late, on leave."""
    return attendance_service.today_status(db, user)


@router.post("/check-in")
def check_in(payload: Reading, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return attendance_service.check_in(db, user, payload.latitude, payload.longitude, payload.accuracy)


@router.post("/check-out")
def check_out(payload: Reading, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return attendance_service.check_out(db, user, payload.latitude, payload.longitude, payload.accuracy)


@router.get("/me")
def mine(month: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Your own attendance for a month: every day's check in / out, leave and absences."""
    return attendance_service.my_month(db, user, attendance_service.parse_month(month))


# ---------------------------------------------------------------- team views

@router.get("/day", dependencies=[Depends(require_permission("attendance.view"))])
def day(
    date_: date | None = Query(None, alias="date"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Everyone's attendance for one day (default today): who checked in, when, from where — and who is absent or on leave."""
    return attendance_service.day_overview(db, user, date_ or attendance_service.today_local())


@router.get("/month", dependencies=[Depends(require_permission("attendance.view"))])
def month(month: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Month grid: per person, per day — check in, check out, hours, location, leave."""
    return attendance_service.month_summary(db, user, attendance_service.parse_month(month))


@router.get("/month-brief", dependencies=[Depends(require_permission("attendance.view"))])
def month_brief(month: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """The month for the phone app: each person's present dates and leave dates, with the counts."""
    return attendance_service.month_brief(db, user, attendance_service.parse_month(month))


@router.post("/import", dependencies=[Depends(require_permission("attendance.edit"))])
async def import_sheet(
    month: str = Form(..., description="YYYY-MM"),
    apply: bool = Form(False, description="false = preview only (changes nothing); true = write it"),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Developer only. Fill a month's attendance from a sheet: one row per employee (Employee ID), one column per day, 'P' = present.
    Days that already have a record are overwritten (the old values are kept in the activity log). Not passed to payroll."""
    content = await file.read(attendance_import_service.MAX_BYTES + 1)
    if len(content) > attendance_import_service.MAX_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That file is too large (limit is 10 MB).")
    return await run_in_threadpool(
        attendance_import_service.run, db, user, attendance_service.parse_month(month), file.filename or "", content, apply=apply,
    )


@router.patch("/record", dependencies=[Depends(require_permission("attendance.edit"))])
def correct_record(payload: RecordCorrection, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Developer only: fix a day's check-in / check-out time and / or whether the person was at the office or away. Lateness is recomputed.
    A person who never checked in that day is marked present by sending a check-in time (a check-out time is optional)."""
    return attendance_service.correct_record(db, user, payload.user_id, payload.work_date, payload.check_in_time, payload.presence, payload.office_id,
                                           payload.late, payload.half_day, payload.clear_check_out, payload.check_out_time)


class HolidayIn(BaseModel):
    holiday_date: date
    name: str = Field(min_length=1, max_length=128)


@router.get("/holidays", dependencies=[Depends(require_permission("attendance.view"))])
def holidays(year: int | None = Query(None, ge=2000, le=2100), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    """The company holidays of a year (default this year)."""
    return holiday_service.listing(db, user.organization_id, year or attendance_service.today_local().year)


@router.post("/holidays", dependencies=[Depends(require_permission("attendance.manage"))])
def set_holiday(payload: HolidayIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Mark a date as a company holiday (or rename it). Nobody is counted absent on it, salary pays it, leave does not use it."""
    return holiday_service.add(db, user, payload.holiday_date, payload.name)


@router.delete("/holidays/{day}", status_code=204, dependencies=[Depends(require_permission("attendance.manage"))])
def remove_holiday(day: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    holiday_service.remove(db, user, day)
    return Response(status_code=204)


@router.post("/mark", dependencies=[Depends(require_permission("attendance.edit"))])
def mark_days(payload: MarkDays, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Developer only: mark an employee present on any dates up to today (backlog days included), or remove a hand-made mark."""
    return attendance_service.mark_days(db, user, payload.user_id, payload.dates, payload.present)


# ---------------------------------------------------------------- leave

@router.get("/leaves/me")
def my_leaves(year: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return leave_service.my_leaves(db, user, year)


@router.post("/leaves", status_code=201)
def apply_leave(payload: LeaveApply, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return leave_service.apply(db, user, payload.leave_type, payload.start_date, payload.end_date, payload.half_day, payload.reason)


@router.post("/leaves/{leave_id}/cancel")
def cancel_leave(leave_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return leave_service.cancel(db, user, leave_id)


@router.get("/leaves", dependencies=[Depends(require_permission("leave.review"))])
def all_leaves(
    status: str | None = None, q: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return leave_service.list_all(db, user, status, q)


@router.post("/leaves/{leave_id}/review", dependencies=[Depends(require_permission("leave.review"))])
def review_leave(
    leave_id: uuid.UUID, payload: LeaveReview, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return leave_service.review(db, user, leave_id, payload.approve, payload.note)


# ---------------------------------------------------------------- offices

@router.get("/offices", dependencies=[Depends(require_permission("attendance.view"))])
def offices(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return attendance_service.list_offices(db, user)


@router.post("/offices", status_code=201, dependencies=[Depends(require_permission("attendance.manage"))])
def create_office(payload: OfficeCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return attendance_service.create_office(db, user, payload.name, payload.latitude, payload.longitude, payload.radius_m)


@router.patch("/offices/{office_id}", dependencies=[Depends(require_permission("attendance.manage"))])
def update_office(
    office_id: uuid.UUID, payload: OfficeUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return attendance_service.update_office(db, user, office_id, payload.model_dump(exclude_unset=True))


@router.delete("/offices/{office_id}", status_code=204, dependencies=[Depends(require_permission("attendance.manage"))])
def delete_office(office_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    attendance_service.delete_office(db, user, office_id)
    return Response(status_code=204)
