"""
Attendance: an explicit Check in / Check out once a day, with where the person was each time.
See models/attendance.py for the data model and its caveats.

  check_in / check_out — the only places a location is read. The browser asks for it when the person taps the
                         button; it is classified here, on the server, against the active offices.
  day_overview / month_summary / my_month — what admins and each person see. Approved leave and the weekly
                         off (Sunday) are shown as such rather than as "absent".

Leave requests live in leave_service.
"""
from __future__ import annotations

import calendar
import math
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import ADMIN, CATEGORY_LABELS, staff_category
from app.models.attendance import AttendanceRecord, Office
from app.models.role import Role
from app.models.user import User, UserRole

# Attendance is for employees and accounts staff. Admins and partner logins are never tracked.
ATTENDING_ROLES = {"employee", "accountant"}
WEEKLY_OFF = 6  # Sunday (date.weekday())


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _tz() -> ZoneInfo:
    return ZoneInfo(settings.ATTENDANCE_TIMEZONE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def local_date(dt: datetime) -> date:
    return dt.astimezone(_tz()).date()


def today_local() -> date:
    return local_date(_now())


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def valid_coords(lat: float | None, lng: float | None) -> bool:
    return (
        lat is not None and lng is not None
        and math.isfinite(lat) and math.isfinite(lng)
        and -90 <= lat <= 90 and -180 <= lng <= 180
    )


def map_url(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps?q={lat:.6f},{lng:.6f}"


def classify(db: Session, org_id: uuid.UUID, lat: float, lng: float) -> tuple[str, Office | None, float | None]:
    """('office' | 'outside', matched office, distance in metres to the nearest active office)."""
    offices = db.execute(select(Office).where(Office.organization_id == org_id, Office.is_active.is_(True))).scalars().all()
    if not offices:
        return "outside", None, None
    nearest = min(offices, key=lambda o: haversine_m(lat, lng, o.latitude, o.longitude))
    dist = haversine_m(lat, lng, nearest.latitude, nearest.longitude)
    return ("office", nearest, dist) if dist <= nearest.radius_m else ("outside", None, dist)


def attends(db: Session, user: User) -> bool:
    """Is this person expected to check in? Employees and accounts staff are; admins and partner logins never are."""
    codes = {
        c for (c,) in db.execute(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id))
    }
    return ADMIN not in codes and bool(ATTENDING_ROLES & codes)


def _work_start() -> time:
    try:
        h, m = (int(x) for x in settings.ATTENDANCE_WORK_START.split(":"))
        return time(h, m)
    except (ValueError, AttributeError):
        return time(10, 0)


def _is_late(checked_in: datetime) -> bool:
    local = checked_in.astimezone(_tz())
    limit = datetime.combine(local.date(), _work_start(), tzinfo=_tz()) + timedelta(minutes=settings.ATTENDANCE_GRACE_MINUTES)
    return local > limit


# --------------------------------------------------------------------------
# location (shared by check in / check out)
# --------------------------------------------------------------------------

def _read_location(db: Session, user: User, lat: float | None, lng: float | None, accuracy: float | None) -> dict:
    """Classify a reading. No (or invalid) coordinates is allowed — it is recorded as 'location not shared'."""
    if not valid_coords(lat, lng):
        return {"status": "unknown", "lat": None, "lng": None, "accuracy": None, "distance": None, "label": None}
    st, office, dist = classify(db, user.organization_id, lat, lng)
    return {
        "status": st, "lat": lat, "lng": lng,
        "accuracy": accuracy if accuracy is not None and math.isfinite(accuracy) and accuracy >= 0 else None,
        "distance": dist, "label": office.name if office is not None else None,
    }


def _loc_dict(st: str | None, lat, lng, acc, dist, label) -> dict:
    if not st or st == "unknown" or lat is None or lng is None:
        return {"status": "unknown", "label": "Location not shared"}
    base = {
        "latitude": round(lat, 6), "longitude": round(lng, 6),
        "accuracy_m": round(acc) if acc is not None else None,
        "distance_m": round(dist) if dist is not None else None,
        "map_url": map_url(lat, lng),
    }
    if st == "office":
        return {"status": "office", "label": label or "Office", **base}
    return {"status": "outside", "label": f"{lat:.6f}, {lng:.6f}", **base}


def _in_loc(r: AttendanceRecord) -> dict:
    return _loc_dict(r.check_in_status, r.check_in_lat, r.check_in_lng, r.check_in_accuracy_m, r.check_in_distance_m, r.check_in_label)


def _out_loc(r: AttendanceRecord) -> dict | None:
    if r.check_out_at is None:
        return None
    return _loc_dict(r.check_out_status, r.check_out_lat, r.check_out_lng, r.check_out_accuracy_m, r.check_out_distance_m, r.check_out_label)


# --------------------------------------------------------------------------
# check in / check out (callers: the person themself)
# --------------------------------------------------------------------------

def _require_attendee(db: Session, user: User) -> None:
    if not attends(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Check in is for employees and accounts staff.")


def _today_record(db: Session, user: User) -> AttendanceRecord | None:
    return db.execute(
        select(AttendanceRecord).where(AttendanceRecord.user_id == user.id, AttendanceRecord.work_date == today_local())
    ).scalar_one_or_none()


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone(_tz()).strftime("%I:%M %p").lstrip("0")


def check_in(db: Session, user: User, lat: float | None, lng: float | None, accuracy: float | None) -> dict:
    _require_attendee(db, user)
    existing = _today_record(db, user)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already checked in today at {_fmt_time(existing.check_in_at)}.")
    now = _now()
    loc = _read_location(db, user, lat, lng, accuracy)
    db.add(AttendanceRecord(
        organization_id=user.organization_id, user_id=user.id, work_date=local_date(now), check_in_at=now,
        check_in_status=loc["status"], check_in_lat=loc["lat"], check_in_lng=loc["lng"], check_in_accuracy_m=loc["accuracy"],
        check_in_distance_m=loc["distance"], check_in_label=loc["label"], late=_is_late(now), source="checkin",
    ))
    db.commit()
    return today_status(db, user)


def check_out(db: Session, user: User, lat: float | None, lng: float | None, accuracy: float | None) -> dict:
    _require_attendee(db, user)
    rec = _today_record(db, user)
    if rec is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Check in first — you haven't checked in today.")
    if rec.check_out_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already checked out today at {_fmt_time(rec.check_out_at)}.")
    loc = _read_location(db, user, lat, lng, accuracy)
    rec.check_out_at = _now()
    rec.check_out_status, rec.check_out_lat, rec.check_out_lng = loc["status"], loc["lat"], loc["lng"]
    rec.check_out_accuracy_m, rec.check_out_distance_m, rec.check_out_label = loc["accuracy"], loc["distance"], loc["label"]
    db.commit()
    return today_status(db, user)


def today_status(db: Session, user: User) -> dict:
    from app.services import leave_service

    now = _now()
    today = today_local()
    eligible = attends(db, user)
    rec = _today_record(db, user) if eligible else None
    leave = leave_service.approved_leave_on(db, user, today) if eligible else None
    minutes = None
    if rec is not None:
        minutes = max(0, round((((rec.check_out_at) or now) - rec.check_in_at).total_seconds() / 60))
    return {
        "eligible": eligible,
        "date": today,
        "work_start": settings.ATTENDANCE_WORK_START,
        "grace_minutes": settings.ATTENDANCE_GRACE_MINUTES,
        "is_weekly_off": today.weekday() == WEEKLY_OFF,
        "checked_in": rec is not None,
        "checked_out": bool(rec and rec.check_out_at),
        "check_in_at": rec.check_in_at if rec else None,
        "check_out_at": rec.check_out_at if rec else None,
        "late": bool(rec and rec.late),
        "minutes": minutes,
        "check_in_location": _in_loc(rec) if rec else None,
        "check_out_location": _out_loc(rec) if rec else None,
        "on_leave": leave,
    }


# --------------------------------------------------------------------------
# summaries
# --------------------------------------------------------------------------

def _roles_by_user(db: Session, org_id: uuid.UUID) -> dict[uuid.UUID, list[str]]:
    out: dict[uuid.UUID, list[str]] = {}
    for uid, code in db.execute(
        select(UserRole.user_id, Role.code).join(Role, Role.id == UserRole.role_id).join(User, User.id == UserRole.user_id)
        .where(User.organization_id == org_id)
    ):
        out.setdefault(uid, []).append(code)
    return out


def _person(u: User, roles: list[str]) -> dict:
    cat = staff_category(roles, u.platform_organization.slug if u.platform_organization else None)
    return {
        "user_id": u.id, "employee_code": u.employee_code, "full_name": u.full_name, "roles": sorted(roles),
        "platform": u.platform_organization.name if u.platform_organization else None,
        "region": u.region.name if u.region else None,
        "category": cat, "category_label": CATEGORY_LABELS[cat],
    }


_CAT_ORDER = {c: i for i, c in enumerate(["accounts", "blinkit", "zepto", "other", "admin"])}


def _attendees(db: Session, org_id: uuid.UUID, roles: dict[uuid.UUID, list[str]]) -> list[User]:
    """Active people who are expected to check in daily."""
    users = db.execute(select(User).where(User.organization_id == org_id, User.is_active.is_(True))).scalars().all()
    return [u for u in users if ATTENDING_ROLES & set(roles.get(u.id, [])) and ADMIN not in roles.get(u.id, [])]


def _minutes(r: AttendanceRecord, now: datetime) -> int:
    if r.check_out_at is not None:
        return max(0, round((r.check_out_at - r.check_in_at).total_seconds() / 60))
    if r.work_date == local_date(now):
        return max(0, round((now - r.check_in_at).total_seconds() / 60))
    return 0  # a past day nobody checked out of: no honest figure


def _record_status(r: AttendanceRecord, now: datetime) -> str:
    if r.check_out_at is not None:
        return "CHECKED_OUT"
    return "CHECKED_IN" if r.work_date == local_date(now) else "NO_CHECKOUT"


def _entry(r: AttendanceRecord, now: datetime) -> dict:
    return {
        "status": _record_status(r, now), "check_in_at": r.check_in_at, "check_out_at": r.check_out_at,
        "minutes": _minutes(r, now), "late": r.late, "location": _in_loc(r), "check_out_location": _out_loc(r),
        "source": r.source,
    }


def day_overview(db: Session, admin: User, day: date) -> dict:
    from app.services import leave_service

    now = _now()
    org = admin.organization_id
    roles = _roles_by_user(db, org)
    records = {r.user_id: r for r in db.execute(
        select(AttendanceRecord).where(AttendanceRecord.organization_id == org, AttendanceRecord.work_date == day)
    ).scalars()}
    leaves = leave_service.approved_between(db, org, day, day)

    people = {u.id: u for u in _attendees(db, org, roles)}
    for uid in records:  # someone who checked in but is no longer 'active' still shows for that day — never an admin
        if uid not in people and ADMIN not in roles.get(uid, []) and ATTENDING_ROLES & set(roles.get(uid, [])):
            u = db.get(User, uid)
            if u is not None:
                people[uid] = u

    off = day.weekday() == WEEKLY_OFF
    rows = []
    for uid, u in people.items():
        base = _person(u, roles.get(uid, []))
        rec = records.get(uid)
        if rec is not None:
            rows.append({**base, **_entry(rec, now), "leave_type": None})
        else:
            lv = leaves.get(uid, [None])[0]
            st = "ON_LEAVE" if lv else ("OFF" if off else "ABSENT")
            rows.append({
                **base, "status": st, "check_in_at": None, "check_out_at": None, "minutes": 0, "late": False,
                "location": {"status": "unknown", "label": "—"}, "check_out_location": None, "source": None,
                "leave_type": lv["leave_type"] if lv else None,
            })
    order = {"CHECKED_IN": 0, "CHECKED_OUT": 1, "NO_CHECKOUT": 1, "ON_LEAVE": 2, "OFF": 3, "ABSENT": 4}
    rows.sort(key=lambda r: (_CAT_ORDER.get(r["category"], 9), order[r["status"]], r["check_in_at"] or now, r["full_name"].lower()))

    present = [r for r in rows if r["status"] in ("CHECKED_IN", "CHECKED_OUT", "NO_CHECKOUT")]
    expected = [r for r in rows if r["status"] not in ("OFF",)]
    return {
        "date": day,
        "is_weekly_off": off,
        "summary": {
            "expected": len(expected),
            "present": len(present),
            "checked_in_now": sum(1 for r in rows if r["status"] == "CHECKED_IN"),
            "late": sum(1 for r in present if r["late"]),
            "on_leave": sum(1 for r in rows if r["status"] == "ON_LEAVE"),
            "absent": sum(1 for r in rows if r["status"] == "ABSENT"),
            "outside_office": sum(1 for r in present if r["location"]["status"] == "outside"),
            "location_unknown": sum(1 for r in present if r["location"]["status"] == "unknown"),
        },
        "rows": rows,
    }


def _month_bounds(month: date) -> tuple[date, date]:
    return month, date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def parse_month(value: str | None) -> date:
    if not value:
        return today_local().replace(day=1)
    try:
        y, m = (int(x) for x in value.split("-"))
        return date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-10.") from exc


def _month_rows(db: Session, org_id: uuid.UUID, month: date, *, only_user: uuid.UUID | None, detail: bool) -> dict:
    from app.services import leave_service

    now = _now()
    today = today_local()
    start, end = _month_bounds(month)
    stmt = select(AttendanceRecord).where(
        AttendanceRecord.organization_id == org_id, AttendanceRecord.work_date >= start, AttendanceRecord.work_date <= end
    )
    if only_user:
        stmt = stmt.where(AttendanceRecord.user_id == only_user)
    grouped: dict[uuid.UUID, dict[date, AttendanceRecord]] = {}
    for r in db.execute(stmt).scalars():
        grouped.setdefault(r.user_id, {})[r.work_date] = r
    leaves = leave_service.approved_between(db, org_id, start, end)

    roles = _roles_by_user(db, org_id)
    if only_user:
        people = {only_user: db.get(User, only_user)}
    else:
        people = {u.id: u for u in _attendees(db, org_id, roles)}
        for uid in grouped:
            if uid not in people and ADMIN not in roles.get(uid, []) and ATTENDING_ROLES & set(roles.get(uid, [])):
                u = db.get(User, uid)
                if u is not None:
                    people[uid] = u

    n_days = calendar.monthrange(month.year, month.month)[1]
    all_dates = [date(month.year, month.month, i) for i in range(1, n_days + 1)]
    rows = []
    for uid, u in people.items():
        recs = grouped.get(uid, {})
        joined = local_date(u.created_at) if u.created_at else start
        days: dict[str, dict] = {}
        leave_days = 0.0
        absent = 0
        for d in all_dates:
            rec = recs.get(d)
            if rec is not None:
                days[d.isoformat()] = _entry(rec, now)
                continue
            if d.weekday() == WEEKLY_OFF:
                continue
            lv = next((x for x in leaves.get(uid, []) if x["start_date"] <= d <= x["end_date"]), None)
            if lv:
                half = lv["half_day"]
                leave_days += 0.5 if half else 1
                days[d.isoformat()] = {"status": "ON_LEAVE", "leave_type": lv["leave_type"], "half_day": half, "minutes": 0, "late": False,
                                       "check_in_at": None, "check_out_at": None, "location": {"status": "unknown", "label": "—"}}
            elif d < today and d >= joined:
                absent += 1
        present = [e for e in days.values() if e["status"] != "ON_LEAVE"]
        row = {
            **_person(u, roles.get(uid, [])), "days": days, "days_present": len(present),
            "total_minutes": sum(e["minutes"] for e in present),
            "outside_days": sum(1 for e in present if e["location"]["status"] == "outside"),
            "late_days": sum(1 for e in present if e["late"]),
            "leave_days": leave_days, "absent_days": absent,
        }
        rows.append(row)
    rows.sort(key=lambda r: (_CAT_ORDER.get(r["category"], 9), r["full_name"].lower()))
    return {
        "month": f"{month:%Y-%m}",
        "dates": [d.isoformat() for d in all_dates],
        "today": today,
        "rows": rows,
    }


def month_summary(db: Session, admin: User, month: date) -> dict:
    return _month_rows(db, admin.organization_id, month, only_user=None, detail=False)


def my_month(db: Session, user: User, month: date) -> dict:
    return _month_rows(db, user.organization_id, month, only_user=user.id, detail=True)


# --------------------------------------------------------------------------
# offices
# --------------------------------------------------------------------------

def office_dict(o: Office) -> dict:
    return {
        "id": o.id, "name": o.name, "latitude": o.latitude, "longitude": o.longitude,
        "radius_m": o.radius_m, "is_active": o.is_active, "map_url": map_url(o.latitude, o.longitude),
    }


def list_offices(db: Session, admin: User) -> list[dict]:
    rows = db.execute(select(Office).where(Office.organization_id == admin.organization_id).order_by(Office.name)).scalars().all()
    return [office_dict(o) for o in rows]


def _check_office(name: str | None, lat: float | None, lng: float | None, radius: int | None) -> None:
    if name is not None and not name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the office a name.")
    if (lat is not None or lng is not None) and not valid_coords(lat, lng):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That location isn't valid (latitude -90..90, longitude -180..180).")
    if radius is not None and not (10 <= radius <= 5000):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The radius must be between 10 and 5000 metres.")


def create_office(db: Session, admin: User, name: str, lat: float, lng: float, radius: int | None) -> dict:
    _check_office(name, lat, lng, radius)
    o = Office(organization_id=admin.organization_id, name=name.strip()[:128], latitude=lat, longitude=lng,
               radius_m=radius or settings.OFFICE_DEFAULT_RADIUS_M, is_active=True)
    db.add(o)
    db.commit()
    return office_dict(o)


def update_office(db: Session, admin: User, office_id: uuid.UUID, data: dict) -> dict:
    o = db.get(Office, office_id)
    if o is None or o.organization_id != admin.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Office not found.")
    _check_office(data.get("name"), data.get("latitude"), data.get("longitude"), data.get("radius_m"))
    for k in ("name", "latitude", "longitude", "radius_m", "is_active"):
        if k in data and data[k] is not None:
            setattr(o, k, data[k].strip()[:128] if k == "name" else data[k])
    db.commit()
    return office_dict(o)


def delete_office(db: Session, admin: User, office_id: uuid.UUID) -> None:
    o = db.get(Office, office_id)
    if o is None or o.organization_id != admin.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Office not found.")
    db.delete(o)  # past check-ins keep their stored label
    db.commit()
