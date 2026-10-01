"""Attendance (sign-in / sign-out times + location) and the offices that define "at the office"."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_family, get_current_user, get_current_user_allow_pending, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import attendance_service

router = APIRouter(prefix="/attendance", tags=["attendance"])


class OfficeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=10, le=5000)


class LoginLocation(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100000)


class OfficeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=10, le=5000)
    is_active: bool | None = None


@router.post("/location")
def login_location(
    payload: LoginLocation,
    user: User = Depends(get_current_user_allow_pending),
    family: uuid.UUID = Depends(get_current_family),
    db: Session = Depends(get_db),
) -> dict:
    """Attach the device location to the sign-in you just made. Allowed once, in the minutes after signing in —
    location is checked at login and at no other time."""
    return attendance_service.set_login_location(db, user, family, payload.latitude, payload.longitude, payload.accuracy)


@router.get("/day", dependencies=[Depends(require_permission("attendance.view"))])
def day(
    date_: date | None = Query(None, alias="date"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Everyone's attendance for one day (default today): who signed in, when, from where — and who is absent."""
    return attendance_service.day_overview(db, user, date_ or attendance_service.today_local())


@router.get("/month", dependencies=[Depends(require_permission("attendance.view"))])
def month(
    month: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Month grid: per person, per day — first sign-in, last sign-out, hours, location."""
    return attendance_service.month_summary(db, user, attendance_service.parse_month(month))


@router.get("/me")
def mine(
    month: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Your own attendance for a month, with every sign-in of each day."""
    return attendance_service.my_month(db, user, attendance_service.parse_month(month))


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
