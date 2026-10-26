"""Company holidays: who may set them, what they change, and the one place every calculation asks "is this date a holiday?"."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.models.payroll import PayrollPeriod, Payslip
from app.models.user import User
from app.services import activity_service


def between(db: Session, org_id: uuid.UUID, start: date, end: date) -> dict[date, str]:
    """{date: name} for every holiday from `start` to `end` inclusive."""
    return {h.holiday_date: h.name for h in db.execute(
        select(Holiday).where(Holiday.organization_id == org_id, Holiday.holiday_date >= start, Holiday.holiday_date <= end)).scalars()}


def listing(db: Session, org_id: uuid.UUID, year: int) -> list[dict]:
    return [{"date": d, "name": n} for d, n in sorted(between(db, org_id, date(year, 1, 1), date(year, 12, 31)).items())]


def _salary_locked(db: Session, org_id: uuid.UUID, day: date) -> bool:
    """A month whose salary has been paid is final: a holiday can't be added or removed inside it."""
    return db.execute(
        select(Payslip.id).join(PayrollPeriod, PayrollPeriod.id == Payslip.period_id)
        .where(PayrollPeriod.month == day.replace(day=1), Payslip.organization_id == org_id).limit(1)
    ).first() is not None


def add(db: Session, actor: User, day: date, name: str) -> dict:
    name = " ".join((name or "").split())
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the holiday a name, for example Diwali.")
    if _salary_locked(db, actor.organization_id, day):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{day:%B %Y}'s salary is already paid, so its days are locked.")
    existing = db.execute(select(Holiday).where(Holiday.organization_id == actor.organization_id, Holiday.holiday_date == day)).scalar_one_or_none()
    if existing is not None:
        existing.name = name[:128]
    else:
        db.add(Holiday(organization_id=actor.organization_id, holiday_date=day, name=name[:128], created_by_user_id=actor.id))
    activity_service.record(db, actor=actor, action="holiday.set", entity_type="holiday", entity_id=day.isoformat(), metadata={"date": day.isoformat(), "name": name[:128]})
    db.commit()
    return {"date": day, "name": name[:128]}


def remove(db: Session, actor: User, day: date) -> None:
    row = db.execute(select(Holiday).where(Holiday.organization_id == actor.organization_id, Holiday.holiday_date == day)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That date is not a holiday.")
    if _salary_locked(db, actor.organization_id, day):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{day:%B %Y}'s salary is already paid, so its days are locked.")
    activity_service.record(db, actor=actor, action="holiday.removed", entity_type="holiday", entity_id=day.isoformat(), metadata={"date": day.isoformat(), "name": row.name})
    db.delete(row)
    db.commit()
