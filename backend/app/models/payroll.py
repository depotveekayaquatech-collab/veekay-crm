"""
Payroll: a monthly salary per employee, a payout date per month, admin day marks, and the payslips that were paid.

EmployeeSalary = the current monthly salary of one employee (what the next payslips use). Nothing here is ever shown to
                 anyone but admins (payroll.manage) and the employee themself.
PayrollPeriod  = one month's payout: the date the salary is released (default the 15th of the next month, an admin can
                 change it) and for how many days the pay window stays open from that date.
DayMark        = an admin's decision on one person's day: FULL, HALF or ABSENT (unpaid). Without a mark the day counts by
                 what attendance shows (present = full day, Sunday off = paid, approved paid leave = paid).
Payslip        = written once, when an admin pays an employee for a month. It freezes the salary, the paid days, the
                 amount and the day-by-day breakdown, so later changes never alter a paid slip. `seen_at` is set when the
                 employee has seen the "salary received" popup.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmployeeSalary(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "employee_salaries"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    monthly_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PayrollPeriod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payroll_periods"
    __table_args__ = (UniqueConstraint("organization_id", "month", name="uq_payroll_period_month"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)                 # first day of the month being paid for
    release_date: Mapped[date] = mapped_column(Date)          # the day the salary is released
    window_days: Mapped[int] = mapped_column(Integer, default=3)   # days from release_date during which an admin can pay
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class DayMark(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payroll_day_marks"
    __table_args__ = (UniqueConstraint("user_id", "work_date", name="uq_payroll_day_mark"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date] = mapped_column(Date)
    mark: Mapped[str] = mapped_column(String(6))              # FULL | HALF | ABSENT
    marked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Payslip(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("period_id", "user_id", name="uq_payslip_period_user"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payroll_periods.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    monthly_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    days_in_month: Mapped[int] = mapped_column(Integer)
    paid_days: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    breakdown: Mapped[list] = mapped_column(JSONB)            # one entry per day, as it was when paid
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
