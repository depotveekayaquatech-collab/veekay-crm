"""
Leave requests: a person applies, someone holding `leave.review` approves or rejects.

  - Working days exclude Sundays (the weekly off); a single day can be a half day.
  - Requests may not overlap another pending/approved request of the same person.
  - Past dates are accepted only up to 7 days back (sick leave is often recorded after the fact).
  - Approved leave shows on the attendance views as "On leave" instead of "Absent".
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.attendance import LeaveRequest
from app.models.user import User
from app.services import activity_service, attendance_service

LEAVE_TYPES = ("CASUAL", "SICK", "PAID", "UNPAID")
STATUSES = ("PENDING", "APPROVED", "REJECTED", "CANCELLED")
MAX_BACKDATE_DAYS = 7
MAX_SPAN_DAYS = 60
BLOCKING = ("PENDING", "APPROVED")


def working_days(start: date, end: date, half_day: bool) -> float:
    n = sum(1 for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() != attendance_service.WEEKLY_OFF)
    return 0.5 if half_day and n == 1 else float(n)


def _person(u: User | None) -> dict | None:
    if u is None:
        return None
    return {
        "user_id": u.id, "name": u.full_name, "code": u.employee_code,
        "platform": u.platform_organization.name if u.platform_organization else None,
        "region": u.region.name if u.region else None,
    }


def _dict(lr: LeaveRequest, db: Session, *, with_person: bool, today: date) -> dict:
    reviewer = db.get(User, lr.reviewed_by_user_id) if lr.reviewed_by_user_id else None
    return {
        "id": lr.id, "leave_type": lr.leave_type, "start_date": lr.start_date, "end_date": lr.end_date, "half_day": lr.half_day,
        "days": lr.days, "reason": lr.reason, "status": lr.status, "created_at": lr.created_at,
        "reviewed_by_name": reviewer.full_name if reviewer else None, "reviewed_at": lr.reviewed_at, "review_note": lr.review_note,
        "can_cancel": lr.status == "PENDING" or (lr.status == "APPROVED" and lr.start_date > today),
        "person": _person(db.get(User, lr.user_id)) if with_person else None,
    }


# --------------------------------------------------------------------------
# lookups used by the attendance views
# --------------------------------------------------------------------------

def approved_between(db: Session, org_id: uuid.UUID, start: date, end: date) -> dict[uuid.UUID, list[dict]]:
    rows = db.execute(
        select(LeaveRequest).where(
            LeaveRequest.organization_id == org_id, LeaveRequest.status == "APPROVED",
            LeaveRequest.start_date <= end, LeaveRequest.end_date >= start,
        )
    ).scalars().all()
    out: dict[uuid.UUID, list[dict]] = {}
    for r in rows:
        out.setdefault(r.user_id, []).append(
            {"start_date": r.start_date, "end_date": r.end_date, "leave_type": r.leave_type, "half_day": r.half_day}
        )
    return out


def approved_leave_on(db: Session, user: User, day: date) -> dict | None:
    r = db.execute(
        select(LeaveRequest).where(
            LeaveRequest.user_id == user.id, LeaveRequest.status == "APPROVED",
            LeaveRequest.start_date <= day, LeaveRequest.end_date >= day,
        )
    ).scalars().first()
    return {"leave_type": r.leave_type, "half_day": r.half_day, "end_date": r.end_date} if r else None


# --------------------------------------------------------------------------
# the person's side
# --------------------------------------------------------------------------

def apply(db: Session, user: User, leave_type: str, start: date, end: date, half_day: bool, reason: str) -> dict:
    if not attendance_service.attends(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Leave requests are for employees and accounts staff.")
    today = attendance_service.today_local()
    if leave_type not in LEAVE_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a leave type.")
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The end date can't be before the start date.")
    if start < today - timedelta(days=MAX_BACKDATE_DAYS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Leave can be applied for at most {MAX_BACKDATE_DAYS} days back.")
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"A single request can cover at most {MAX_SPAN_DAYS} days.")
    if half_day and start != end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A half day must be a single date.")
    if not reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please give a reason.")
    days = working_days(start, end, half_day)
    if days == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Those dates are all weekly offs — no leave needed.")

    clash = db.execute(
        select(LeaveRequest).where(
            LeaveRequest.user_id == user.id, LeaveRequest.status.in_(BLOCKING),
            LeaveRequest.start_date <= end, LeaveRequest.end_date >= start,
        )
    ).scalars().first()
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You already have a {clash.status.lower()} request for {clash.start_date:%d %b} – {clash.end_date:%d %b}.",
        )

    lr = LeaveRequest(
        organization_id=user.organization_id, user_id=user.id, leave_type=leave_type, start_date=start, end_date=end,
        half_day=half_day, days=days, reason=reason.strip()[:500], status="PENDING",
    )
    db.add(lr)
    db.flush()
    activity_service.record(
        db, actor=user, action="leave.applied", entity_type="leave", entity_id=lr.id,
        metadata={"type": leave_type, "from": start.isoformat(), "to": end.isoformat(), "days": days},
    )
    db.commit()
    return _dict(lr, db, with_person=False, today=today)


def my_leaves(db: Session, user: User, year: int | None) -> dict:
    today = attendance_service.today_local()
    year = year or today.year
    rows = db.execute(
        select(LeaveRequest).where(
            LeaveRequest.user_id == user.id,
            LeaveRequest.start_date <= date(year, 12, 31), LeaveRequest.end_date >= date(year, 1, 1),
        ).order_by(LeaveRequest.start_date.desc())
    ).scalars().all()
    taken = {t: 0.0 for t in LEAVE_TYPES}
    for r in rows:
        if r.status == "APPROVED":
            taken[r.leave_type] += r.days
    return {
        "year": year,
        "items": [_dict(r, db, with_person=False, today=today) for r in rows],
        "taken": taken,
        "pending": sum(1 for r in rows if r.status == "PENDING"),
    }


def cancel(db: Session, user: User, leave_id: uuid.UUID) -> dict:
    lr = db.get(LeaveRequest, leave_id)
    today = attendance_service.today_local()
    if lr is None or lr.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave request not found.")
    if not (lr.status == "PENDING" or (lr.status == "APPROVED" and lr.start_date > today)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This request can no longer be cancelled.")
    lr.status = "CANCELLED"
    activity_service.record(db, actor=user, action="leave.cancelled", entity_type="leave", entity_id=lr.id)
    db.commit()
    return _dict(lr, db, with_person=False, today=today)


# --------------------------------------------------------------------------
# the reviewer's side
# --------------------------------------------------------------------------

def list_all(db: Session, reviewer: User, status_filter: str | None, q: str | None) -> dict:
    today = attendance_service.today_local()
    stmt = select(LeaveRequest).where(LeaveRequest.organization_id == reviewer.organization_id)
    if status_filter and status_filter.upper() in STATUSES:
        stmt = stmt.where(LeaveRequest.status == status_filter.upper())
    rows = db.execute(stmt.order_by(
        (LeaveRequest.status != "PENDING"), LeaveRequest.start_date.desc()
    ).limit(300)).scalars().all()
    items = [_dict(r, db, with_person=True, today=today) for r in rows]
    if q and q.strip():
        needle = q.strip().lower()
        items = [i for i in items if i["person"] and needle in f"{i['person']['name']} {i['person']['code']}".lower()]
    pending = db.execute(
        select(LeaveRequest.id).where(LeaveRequest.organization_id == reviewer.organization_id, LeaveRequest.status == "PENDING")
    ).all()
    return {"items": items, "pending": len(pending)}


def review(db: Session, reviewer: User, leave_id: uuid.UUID, approve: bool, note: str | None) -> dict:
    lr = db.get(LeaveRequest, leave_id)
    if lr is None or lr.organization_id != reviewer.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave request not found.")
    if lr.user_id == reviewer.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't review your own leave request.")
    if lr.status != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request is already {lr.status.lower()}.")
    lr.status = "APPROVED" if approve else "REJECTED"
    lr.reviewed_by_user_id = reviewer.id
    lr.reviewed_at = datetime.now(timezone.utc)
    lr.review_note = (note or "").strip()[:500] or None
    activity_service.record(
        db, actor=reviewer, action="leave.approved" if approve else "leave.rejected", entity_type="leave", entity_id=lr.id,
        metadata={"for": str(lr.user_id)},
    )
    db.commit()
    return _dict(lr, db, with_person=True, today=attendance_service.today_local())
