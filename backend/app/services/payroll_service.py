"""
Payroll: what to pay each employee for a finished month, from their attendance, and the record that it was paid.

How a month is counted (per-day rate = monthly salary / calendar days of that month):
  a day with a check-in .......... 1 day            an approved paid / casual / sick leave day ... 1 day (0.5 for a half day)
  Sunday (weekly off) with none .. 1 day            an approved UNPAID leave day ................ 0
  no check-in, not on leave ...... 0                a day before the person's account existed .... 0
An admin can override any day with a mark: FULL = 1, HALF = 0.5, ABSENT = 0 (this is how half days are decided after looking
at the check-in and check-out times). Pay = salary / days in month x counted days, rounded to the paisa.

Each month has a payout date (default the 15th of the next month) and a window of days from it in which salaries can be paid.
An admin can change both by hand. Viewing, marking and setting salaries is possible at any time; paying only in the window.
Paying writes a Payslip that freezes the figures and the day-by-day breakdown, locks that person's marks for the month and
sends the employee a "Salary received" notification (the apps also show a popup until they have seen it).

Who: everything admin-side needs payroll.manage (admins hold every permission automatically). An employee sees only their own
paid payslips. Salary amounts are never written to the activity log.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.roles import ADMIN
from app.models.payroll import DayMark, EmployeeSalary, PayrollPeriod, Payslip
from app.models.user import User
from app.services import activity_service, attendance_service, staff_notify

DEFAULT_RELEASE_DAY = 15
DEFAULT_WINDOW_DAYS = 3
MAX_WINDOW_DAYS = 31
MAX_SALARY = Decimal("10000000")
MARK_VALUE = {"FULL": Decimal("1"), "HALF": Decimal("0.5"), "ABSENT": Decimal("0")}
FIRST_MONTH = date(2024, 1, 1)
_PAID_LEAVES_OFF = {"UNPAID"}


def _label(month: date) -> str:
    return f"{calendar.month_name[month.month]} {month.year}"


def _money(v: Decimal | None) -> float | None:
    return None if v is None else float(v)


def _round(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _dim(month: date) -> int:
    return calendar.monthrange(month.year, month.month)[1]


def _next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def _today() -> date:
    return attendance_service.today_local()


# ---------------------------------------------------------------- months and the pay window

def parse_month(value: str | None) -> date:
    """A finished month (payroll is for months that are over). Default: last month."""
    this = _today().replace(day=1)
    if not value:
        return date(this.year - (this.month == 1), (this.month - 2) % 12 + 1, 1)
    try:
        y, m = (int(x) for x in value.split("-"))
        month = date(y, m, 1)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-09.") from None
    if month >= this:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payroll is for a month that has finished.")
    if month < FIRST_MONTH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That month is too far back.")
    return month


def available_months(limit: int = 12) -> list[str]:
    out, cur = [], _today().replace(day=1)
    for _ in range(limit):
        cur = date(cur.year - (cur.month == 1), (cur.month - 2) % 12 + 1, 1)
        out.append(f"{cur:%Y-%m}")
    return out


def _period(db: Session, org_id: uuid.UUID, month: date) -> PayrollPeriod:
    """This month's payout settings, created with the defaults the first time anyone looks."""
    p = db.execute(select(PayrollPeriod).where(PayrollPeriod.organization_id == org_id, PayrollPeriod.month == month)).scalar_one_or_none()
    if p is None:
        p = PayrollPeriod(
            organization_id=org_id, month=month, window_days=DEFAULT_WINDOW_DAYS,
            release_date=_next_month(month).replace(day=DEFAULT_RELEASE_DAY),
        )
        db.add(p)
        try:
            db.commit()
        except IntegrityError:   # two people opened the month at once
            db.rollback()
            p = db.execute(select(PayrollPeriod).where(PayrollPeriod.organization_id == org_id, PayrollPeriod.month == month)).scalar_one()
    return p


def window_state(period: PayrollPeriod, today: date | None = None) -> str:
    today = today or _today()
    closes = period.release_date + timedelta(days=period.window_days - 1)
    return "UPCOMING" if today < period.release_date else "OPEN" if today <= closes else "CLOSED"


def _period_out(p: PayrollPeriod) -> dict:
    return {
        "release_date": p.release_date, "window_days": p.window_days,
        "closes_on": p.release_date + timedelta(days=p.window_days - 1), "state": window_state(p),
    }


def update_period(db: Session, admin: User, month_str: str | None, release_date: date, window_days: int) -> dict:
    month = parse_month(month_str)
    end = date(month.year, month.month, _dim(month))
    if release_date <= end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Salary for {_label(month)} cannot be released before the month has ended.")
    if release_date > end + timedelta(days=120):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That release date is too far away.")
    if not 1 <= window_days <= MAX_WINDOW_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The window must be 1 to {MAX_WINDOW_DAYS} days.")
    p = _period(db, admin.organization_id, month)
    p.release_date, p.window_days, p.updated_by_user_id = release_date, window_days, admin.id
    activity_service.record(
        db, actor=admin, action="payroll.period_changed", entity_type="payroll", entity_id=p.id,
        metadata={"month": f"{month:%Y-%m}", "release_date": release_date.isoformat(), "window_days": window_days},
    )
    db.commit()
    return _period_out(p)


# ---------------------------------------------------------------- counting a month

def _kind(entry: dict | None, d: date, joined: date) -> str:
    if entry is not None:
        return "LEAVE" if entry["status"] == "ON_LEAVE" else "PRESENT"
    if d.weekday() == attendance_service.WEEKLY_OFF:
        return "OFF" if d >= joined else "BEFORE_JOINING"
    return "BEFORE_JOINING" if d < joined else "ABSENT"


def _default_value(kind: str, entry: dict | None) -> Decimal:
    if kind in ("PRESENT", "OFF"):
        return Decimal("1")
    if kind == "LEAVE" and entry is not None and entry.get("leave_type") not in _PAID_LEAVES_OFF:
        return Decimal("0.5") if entry.get("half_day") else Decimal("1")
    return Decimal("0")


def build_days(month: date, entries: dict[str, dict], joined: date, marks: dict[date, str]) -> list[dict]:
    """Every date of the month: what attendance shows, the admin's mark if any, and how much of a day it counts for."""
    out = []
    for i in range(1, _dim(month) + 1):
        d = date(month.year, month.month, i)
        entry = entries.get(d.isoformat())
        kind = _kind(entry, d, joined)
        mark = marks.get(d)
        counted = MARK_VALUE[mark] if mark else _default_value(kind, entry)
        out.append({
            "date": d.isoformat(), "weekday": d.weekday(), "kind": kind, "mark": mark, "counted": float(counted),
            "default": float(_default_value(kind, entry)),    # what the day counts for with no mark (lets the screen preview a change)
            "check_in_at": entry["check_in_at"].isoformat() if entry and entry.get("check_in_at") else None,
            "check_out_at": entry["check_out_at"].isoformat() if entry and entry.get("check_out_at") else None,
            "minutes": entry["minutes"] if entry else 0, "late": bool(entry and entry.get("late")),
            "no_checkout": bool(entry and entry["status"] == "NO_CHECKOUT"),
            "location": entry["location"]["label"] if entry and entry.get("location") else None,
            "leave_type": entry.get("leave_type") if entry and kind == "LEAVE" else None,
            "half_day": bool(entry and kind == "LEAVE" and entry.get("half_day")),
        })
    return out


def compute_amount(salary: Decimal | None, days: list[dict], dim: int) -> tuple[Decimal, Decimal | None]:
    """(paid days, amount). Amount is None while there is no salary."""
    paid = sum((Decimal(str(d["counted"])) for d in days), Decimal("0"))
    return paid, (None if salary is None else _round(salary * paid / dim))


def _marks(db: Session, user_ids: list[uuid.UUID], month: date) -> dict[uuid.UUID, dict[date, str]]:
    out: dict[uuid.UUID, dict[date, str]] = {}
    end = date(month.year, month.month, _dim(month))
    for m in db.execute(select(DayMark).where(DayMark.user_id.in_(user_ids or [uuid.uuid4()]), DayMark.work_date >= month, DayMark.work_date <= end)).scalars():
        out.setdefault(m.user_id, {})[m.work_date] = m.mark
    return out


def _salaries(db: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    return {s.user_id: s.monthly_salary for s in db.execute(select(EmployeeSalary).where(EmployeeSalary.user_id.in_(user_ids or [uuid.uuid4()]))).scalars()}


def _joined(u: User, month: date) -> date:
    return attendance_service.local_date(u.created_at) if u.created_at else month


def _payslips(db: Session, period: PayrollPeriod) -> dict[uuid.UUID, Payslip]:
    return {p.user_id: p for p in db.execute(select(Payslip).where(Payslip.period_id == period.id)).scalars()}


# ---------------------------------------------------------------- admin: the month's list

def overview(db: Session, admin: User, month_str: str | None) -> dict:
    month = parse_month(month_str)
    period = _period(db, admin.organization_id, month)
    data = attendance_service._month_rows(db, admin.organization_id, month, only_user=None, detail=False)  # noqa: SLF001 - same figures as the Monthly tab
    ids = [r["user_id"] for r in data["rows"]]
    users = {u.id: u for u in db.execute(select(User).where(User.id.in_(ids or [uuid.uuid4()]))).scalars()}
    salaries, marks, slips = _salaries(db, ids), _marks(db, ids, month), _payslips(db, period)
    dim = _dim(month)

    rows, payable, paid_total = [], Decimal("0"), Decimal("0")
    for r in data["rows"]:
        uid = r["user_id"]
        u = users.get(uid)
        if u is None or ADMIN in r["roles"]:
            continue
        slip = slips.get(uid)
        if slip is not None:
            salary, paid_days, amount, state = slip.monthly_salary, slip.paid_days, slip.amount, "PAID"
            paid_total += amount
        else:
            salary = salaries.get(uid)
            days = build_days(month, r["days"], _joined(u, month), marks.get(uid, {}))
            paid_days, amount = compute_amount(salary, days, dim)
            state = "NO_SALARY" if salary is None else "READY"
            if amount is not None:
                payable += amount
        rows.append({
            "user_id": uid, "employee_code": r["employee_code"], "full_name": r["full_name"], "category_label": r["category_label"],
            "platform": r["platform"], "region": r["region"], "is_active": u.is_active,
            "monthly_salary": _money(salary), "paid_days": float(paid_days), "amount": _money(amount), "status": state,
            "marked_days": len(marks.get(uid, {})), "absent_days": r["absent_days"], "days_present": r["days_present"],
            "paid_at": slip.paid_at if slip else None,
        })
    return {
        "month": f"{month:%Y-%m}", "month_label": _label(month), "months": available_months(), "days_in_month": dim,
        "today": _today(), "period": _period_out(period),
        "summary": {
            "employees": len(rows), "paid": sum(1 for x in rows if x["status"] == "PAID"),
            "ready": sum(1 for x in rows if x["status"] == "READY"), "no_salary": sum(1 for x in rows if x["status"] == "NO_SALARY"),
            "payable_total": float(payable), "paid_total": float(paid_total),
        },
        "rows": rows,
    }


# ---------------------------------------------------------------- admin: one person

def _person(db: Session, admin: User, user_id: uuid.UUID) -> User:
    u = db.get(User, user_id)
    if u is None or u.organization_id != admin.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    roles = set(attendance_service._roles_by_user(db, admin.organization_id).get(u.id, []))  # noqa: SLF001
    if ADMIN in roles or not (attendance_service.ATTENDING_ROLES & roles):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payroll is for employees and accounts staff.")
    return u


def _detail_out(db: Session, u: User, month: date, period: PayrollPeriod, slip: Payslip | None, paid_by: str | None = None) -> dict:
    dim = _dim(month)
    if slip is not None:
        days, salary, paid_days, amount = slip.breakdown, slip.monthly_salary, slip.paid_days, slip.amount
    else:
        month_data = attendance_service._month_rows(db, u.organization_id, month, only_user=u.id, detail=True)  # noqa: SLF001
        entries = month_data["rows"][0]["days"] if month_data["rows"] else {}
        days = build_days(month, entries, _joined(u, month), _marks(db, [u.id], month).get(u.id, {}))
        salary = _salaries(db, [u.id]).get(u.id)
        paid_days, amount = compute_amount(salary, days, dim)
    return {
        "month": f"{month:%Y-%m}", "month_label": _label(month), "period": _period_out(period), "days_in_month": dim,
        "person": {"user_id": u.id, "employee_code": u.employee_code, "full_name": u.full_name},
        "monthly_salary": _money(salary), "per_day": None if salary is None else float(_round(salary / dim)),
        "days": days, "paid_days": float(paid_days), "amount": _money(amount),
        "status": "PAID" if slip else ("NO_SALARY" if salary is None else "READY"),
        "payslip": {"id": slip.id, "paid_at": slip.paid_at, "paid_by": paid_by} if slip else None,
    }


def detail(db: Session, admin: User, month_str: str | None, user_id: uuid.UUID) -> dict:
    month = parse_month(month_str)
    u = _person(db, admin, user_id)
    period = _period(db, admin.organization_id, month)
    slip = _payslips(db, period).get(u.id)
    by = db.get(User, slip.paid_by_user_id).full_name if slip and slip.paid_by_user_id else None
    return _detail_out(db, u, month, period, slip, by)


def set_salary(db: Session, admin: User, user_id: uuid.UUID, amount: Decimal | None) -> dict:
    """Set (or clear, with None) the monthly salary used for unpaid months. Months already paid keep what they were paid."""
    u = _person(db, admin, user_id)
    if amount is not None and not (Decimal("0") <= amount <= MAX_SALARY):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The salary must be from 0 to {MAX_SALARY:,.0f}.")
    row = db.execute(select(EmployeeSalary).where(EmployeeSalary.user_id == u.id)).scalar_one_or_none()
    if amount is None:
        if row is not None:
            db.delete(row)
    else:
        amount = _round(amount)
        if row is None:
            db.add(EmployeeSalary(user_id=u.id, monthly_salary=amount, updated_by_user_id=admin.id))
        else:
            row.monthly_salary, row.updated_by_user_id = amount, admin.id
    activity_service.record(   # the amount itself stays out of the activity log
        db, actor=admin, action="payroll.salary_set" if amount is not None else "payroll.salary_cleared", entity_type="user", entity_id=u.id,
        metadata={"employee": u.employee_code},
    )
    db.commit()
    return {"user_id": u.id, "monthly_salary": _money(amount)}


def save_marks(db: Session, admin: User, month_str: str | None, user_id: uuid.UUID, marks: list[tuple[date, str | None]]) -> dict:
    """Save the admin's day marks (None clears a mark). Refused once that person is paid for the month."""
    month = parse_month(month_str)
    u = _person(db, admin, user_id)
    period = _period(db, admin.organization_id, month)
    if u.id in _payslips(db, period):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{u.full_name} is already paid for {_label(month)}; the days can no longer be changed.")
    end = date(month.year, month.month, _dim(month))
    existing = {m.work_date: m for m in db.execute(select(DayMark).where(DayMark.user_id == u.id, DayMark.work_date >= month, DayMark.work_date <= end)).scalars()}
    changed = 0
    for d, mark in marks:
        if not (month <= d <= end):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{d.isoformat()} is not in {_label(month)}.")
        cur = existing.get(d)
        if mark is None:
            if cur is not None:
                db.delete(cur)
                changed += 1
        elif cur is None:
            db.add(DayMark(user_id=u.id, work_date=d, mark=mark, marked_by_user_id=admin.id))
            changed += 1
        elif cur.mark != mark:
            cur.mark, cur.marked_by_user_id = mark, admin.id
            changed += 1
    if changed:
        activity_service.record(
            db, actor=admin, action="payroll.days_marked", entity_type="user", entity_id=u.id,
            metadata={"employee": u.employee_code, "month": f"{month:%Y-%m}", "days_changed": changed},
        )
    db.commit()
    return _detail_out(db, u, month, period, None)


def pay(db: Session, admin: User, month_str: str | None, user_id: uuid.UUID) -> dict:
    """Pay one employee for the month: freeze the figures into a Payslip and tell them. Only inside the pay window."""
    month = parse_month(month_str)
    u = _person(db, admin, user_id)
    period = _period(db, admin.organization_id, month)
    state = window_state(period)
    if state == "UPCOMING":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Salary for {_label(month)} can be paid from {period.release_date:%d %b %Y}. Change the release date if it is being paid earlier.")
    if state == "CLOSED":
        raise HTTPException(status.HTTP_409_CONFLICT, f"The pay window for {_label(month)} closed on {period.release_date + timedelta(days=period.window_days - 1):%d %b %Y}. Change the release date or the window to pay now.")
    if u.id in _payslips(db, period):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{u.full_name} is already paid for {_label(month)}.")
    cur = _detail_out(db, u, month, period, None)
    if cur["monthly_salary"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Set {u.full_name}'s monthly salary first.")
    salary = _salaries(db, [u.id])[u.id]
    paid_days, amount = compute_amount(salary, cur["days"], cur["days_in_month"])
    if amount is None or amount <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{u.full_name} has no paid days in {_label(month)}, so there is nothing to pay.")
    slip = Payslip(
        organization_id=admin.organization_id, period_id=period.id, user_id=u.id, monthly_salary=salary, days_in_month=cur["days_in_month"],
        paid_days=paid_days, amount=amount, breakdown=cur["days"], paid_at=datetime.now(timezone.utc), paid_by_user_id=admin.id,
    )
    db.add(slip)
    try:
        db.flush()
    except IntegrityError:   # another admin paid them a moment ago
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"{u.full_name} is already paid for {_label(month)}.") from None
    activity_service.record(
        db, actor=admin, action="payroll.paid", entity_type="user", entity_id=u.id,
        metadata={"employee": u.employee_code, "month": f"{month:%Y-%m}"},
    )
    staff_notify.notify_users(
        db, [u.id], kind="salary", ref_id=slip.id, title="Salary received",
        body=f"Your salary for {_label(month)} (Rs {amount:,.2f}) has been paid.",
    )
    db.commit()
    return _detail_out(db, u, month, period, slip, admin.full_name)


# ---------------------------------------------------------------- the employee's own payslips

def _slip_out(p: Payslip, period: PayrollPeriod, *, with_days: bool) -> dict:
    out = {
        "id": p.id, "month": f"{period.month:%Y-%m}", "month_label": _label(period.month), "release_date": period.release_date,
        "monthly_salary": _money(p.monthly_salary), "days_in_month": p.days_in_month, "paid_days": float(p.paid_days),
        "amount": _money(p.amount), "paid_at": p.paid_at, "seen": p.seen_at is not None,
    }
    if with_days:
        out["days"] = p.breakdown
    return out


def my_payslips(db: Session, user: User) -> dict:
    rows = db.execute(
        select(Payslip, PayrollPeriod).join(PayrollPeriod, PayrollPeriod.id == Payslip.period_id)
        .where(Payslip.user_id == user.id).order_by(PayrollPeriod.month.desc())
    ).all()
    return {"items": [_slip_out(p, per, with_days=True) for p, per in rows]}


def my_unseen(db: Session, user: User) -> dict:
    """Paid payslips whose 'salary received' popup has not been shown yet (oldest first)."""
    rows = db.execute(
        select(Payslip, PayrollPeriod).join(PayrollPeriod, PayrollPeriod.id == Payslip.period_id)
        .where(Payslip.user_id == user.id, Payslip.seen_at.is_(None)).order_by(Payslip.paid_at)
    ).all()
    return {"items": [_slip_out(p, per, with_days=False) for p, per in rows]}


def mark_seen(db: Session, user: User, payslip_id: uuid.UUID) -> dict:
    p = db.get(Payslip, payslip_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payslip not found.")
    if p.seen_at is None:
        p.seen_at = datetime.now(timezone.utc)
        db.commit()
    return {"id": p.id, "seen": True}
