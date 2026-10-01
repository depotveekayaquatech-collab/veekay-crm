"""Attendance (check in / check out + location), leave requests, and the offices that define "at the office"."""
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import attendance_service, leave_service

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
