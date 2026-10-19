"""Payroll: salaries, the payout date, day marks and paying (payroll.manage), and each employee's own payslips."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.user import User
from app.services import payroll_service

router = APIRouter(prefix="/payroll", tags=["payroll"])
manage = Depends(require_permission("payroll.manage"))


class PeriodIn(BaseModel):
    release_date: date
    window_days: int = Field(..., ge=1, le=payroll_service.MAX_WINDOW_DAYS)


class SalaryIn(BaseModel):
    monthly_salary: Decimal | None = Field(default=None, ge=0, le=payroll_service.MAX_SALARY, max_digits=12, decimal_places=2, description="null clears it")


class MarkIn(BaseModel):
    date: date
    mark: Literal["FULL", "HALF", "ABSENT"] | None = Field(default=None, description="null removes the mark")


class MarksIn(BaseModel):
    marks: list[MarkIn] = Field(..., max_length=62)


# ---------------------------------------------------------------- the employee's own (any signed-in employee)

@router.get("/me")
def my_payslips(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Your paid payslips, newest first, each with its day-by-day breakdown."""
    return payroll_service.my_payslips(db, user)


@router.get("/me/unseen")
def my_unseen(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Salaries paid to you whose 'salary received' popup has not been shown yet."""
    return payroll_service.my_unseen(db, user)


@router.post("/me/{payslip_id}/seen")
def mark_seen(payslip_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return payroll_service.mark_seen(db, user, payslip_id)


# ---------------------------------------------------------------- admin

@router.get("", dependencies=[manage])
def overview(month: str | None = Query(None, description="2026-09; last month by default"), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Every employee's pay for a finished month, and the month's payout date and pay window."""
    return payroll_service.overview(db, user, month)


@router.put("/period", dependencies=[manage])
def update_period(payload: PeriodIn, month: str = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Change the release date and how many days the pay window stays open."""
    return payroll_service.update_period(db, user, month, payload.release_date, payload.window_days)


@router.put("/salaries/{user_id}", dependencies=[manage])
def set_salary(user_id: uuid.UUID, payload: SalaryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return payroll_service.set_salary(db, user, user_id, payload.monthly_salary)


@router.get("/employees/{user_id}", dependencies=[manage])
def detail(user_id: uuid.UUID, month: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """One payslip: salary, amount, and every day with its check-in / check-out and the admin's mark."""
    return payroll_service.detail(db, user, month, user_id)


@router.put("/employees/{user_id}/marks", dependencies=[manage])
def save_marks(user_id: uuid.UUID, payload: MarksIn, month: str = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return payroll_service.save_marks(db, user, month, user_id, [(m.date, m.mark) for m in payload.marks])


@router.post("/employees/{user_id}/pay", dependencies=[manage])
def pay(user_id: uuid.UUID, month: str = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Mark the salary as paid (inside the pay window). The employee gets a 'Salary received' notification."""
    return payroll_service.pay(db, user, month, user_id)
