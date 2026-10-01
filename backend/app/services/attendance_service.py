"""
Attendance from sign-in / sign-out, with where the person signed in from.
See models/attendance.py for the data model and its caveats.

Hooks (called from the auth layer):
  record_login   — a successful sign-in starts a session. This is the ONLY place a location is read and
                   classified; nothing re-checks it while the person is signed in.
  touch          — a signed-in person is still around (throttled; one cheap UPDATE per few minutes)
  close_family   — sign-out / revoked session ends it
"""
from __future__ import annotations

import calendar
import math
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import ADMIN, CATEGORY_LABELS, staff_category
from app.models.attendance import AttendanceSession, Office
from app.models.role import Role
from app.models.user import User, UserRole

# Attendance is for employees and accounts staff. Admins are never tracked: no attendance row, no location check.
ATTENDING_ROLES = {"employee", "accountant"}
_TOUCH_EVERY_SECONDS = 300
_last_touch: dict[uuid.UUID, float] = {}


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


# --------------------------------------------------------------------------
# recording (called from the auth layer — callers commit)
# --------------------------------------------------------------------------

def attends(db: Session, user: User) -> bool:
    """Does this person's sign-in count as attendance? Employees and accounts staff do; admins never do."""
    codes = {
        c for (c,) in db.execute(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id))
    }
    return ADMIN not in codes and bool(ATTENDING_ROLES & codes)


LOCATION_WINDOW_MINUTES = 10


def set_login_location(
    db: Session, user: User, family_id: uuid.UUID, latitude: float | None, longitude: float | None, accuracy: float | None,
) -> dict:
    """
    Attach the sign-in location to the attendance row the person just created by signing in. This is how the
    location gets recorded after a successful login (so admins are never asked). It is allowed ONCE per sign-in,
    and only in the minutes right after it — so location is checked at login and at no other time.
    """
    if not valid_coords(latitude, longitude):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That location isn't valid.")
    row = db.execute(
        select(AttendanceSession)
        .where(AttendanceSession.family_id == family_id, AttendanceSession.user_id == user.id)
        .order_by(AttendanceSession.login_at.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No attendance sign-in to attach a location to.")
    if row.latitude is not None or row.location_status != "unknown":
        raise HTTPException(status.HTTP_409_CONFLICT, "The location for this sign-in is already recorded.")
    if (_now() - row.login_at) > timedelta(minutes=LOCATION_WINDOW_MINUTES):
        raise HTTPException(status.HTTP_409_CONFLICT, "Location can only be recorded when you sign in.")
    st, office, dist = classify(db, user.organization_id, latitude, longitude)
    row.location_status, row.latitude, row.longitude = st, latitude, longitude
    row.accuracy_m = accuracy if accuracy is not None and math.isfinite(accuracy) and accuracy >= 0 else None
    row.distance_m = dist
    if office is not None:
        row.office_id, row.location_label = office.id, office.name
    db.commit()
    return _location(row)


def record_login(
    db: Session, user: User, family_id: uuid.UUID, *, ip: str | None, user_agent: str | None,
    latitude: float | None = None, longitude: float | None = None, accuracy: float | None = None,
) -> AttendanceSession:
    now = _now()
    row = AttendanceSession(
        organization_id=user.organization_id, user_id=user.id, work_date=local_date(now), family_id=family_id,
        login_at=now, last_seen_at=now, ip=ip, user_agent=(user_agent or "")[:255] or None,
    )
    if valid_coords(latitude, longitude):
        st, office, dist = classify(db, user.organization_id, latitude, longitude)
        row.location_status, row.latitude, row.longitude = st, latitude, longitude
        row.accuracy_m = accuracy if accuracy is not None and math.isfinite(accuracy) and accuracy >= 0 else None
        row.distance_m = dist
        if office is not None:
            row.office_id, row.location_label = office.id, office.name
    db.add(row)
    db.flush()
    return row


def rekey_family(db: Session, old_family: uuid.UUID, new_family: uuid.UUID) -> None:
    """The auth session was re-issued (password change). Keep the SAME attendance row — it is not a new
    sign-in, so it is not a new location check; it just follows the new session."""
    db.execute(
        update(AttendanceSession)
        .where(AttendanceSession.family_id == old_family, AttendanceSession.logout_at.is_(None))
        .values(family_id=new_family)
    )


def touch(db: Session, family_id: uuid.UUID) -> None:
    """Mark the session as seen now — at most once every few minutes per process."""
    mono = time.monotonic()
    if mono - _last_touch.get(family_id, -1e9) < _TOUCH_EVERY_SECONDS:
        return
    if len(_last_touch) > 5000:
        _last_touch.clear()
    _last_touch[family_id] = mono
    db.execute(
        update(AttendanceSession)
        .where(AttendanceSession.family_id == family_id, AttendanceSession.logout_at.is_(None))
        .values(last_seen_at=_now())
    )
    db.commit()


def close_family(db: Session, family_id: uuid.UUID, ended_by: str) -> None:
    db.execute(
        update(AttendanceSession)
        .where(AttendanceSession.family_id == family_id, AttendanceSession.logout_at.is_(None))
        .values(logout_at=_now(), ended_by=ended_by)
    )


def close_user(db: Session, user_id: uuid.UUID, ended_by: str, *, except_family: uuid.UUID | None = None) -> None:
    stmt = update(AttendanceSession).where(AttendanceSession.user_id == user_id, AttendanceSession.logout_at.is_(None))
    if except_family is not None:
        stmt = stmt.where(AttendanceSession.family_id != except_family)
    db.execute(stmt.values(logout_at=_now(), ended_by=ended_by))


# --------------------------------------------------------------------------
# summaries
# --------------------------------------------------------------------------

def _location(s: AttendanceSession) -> dict:
    if s.location_status == "unknown" or s.latitude is None or s.longitude is None:
        return {"status": "unknown", "label": "Location not shared"}
    base = {
        "latitude": round(s.latitude, 6), "longitude": round(s.longitude, 6),
        "accuracy_m": round(s.accuracy_m) if s.accuracy_m is not None else None,
        "distance_m": round(s.distance_m) if s.distance_m is not None else None,
        "map_url": map_url(s.latitude, s.longitude),
    }
    if s.location_status == "office":
        return {"status": "office", "label": s.location_label or "Office", **base}
    return {"status": "outside", "label": f"{s.latitude:.6f}, {s.longitude:.6f}", **base}


def _end_at(s: AttendanceSession) -> datetime:
    return s.logout_at or s.last_seen_at


def _state(s: AttendanceSession, now: datetime) -> str:
    if s.logout_at is not None:
        return "signed_out"
    if (now - s.last_seen_at) <= timedelta(minutes=settings.ATTENDANCE_ACTIVE_WINDOW_MINUTES):
        return "active"
    return "idle"  # closed the tab without signing out; counted until last seen


def _session_dict(s: AttendanceSession, now: datetime) -> dict:
    return {
        "id": s.id, "login_at": s.login_at, "logout_at": s.logout_at, "last_seen_at": s.last_seen_at,
        "ended_by": s.ended_by, "state": _state(s, now), "ip": s.ip, "location": _location(s),
        "minutes": max(0, round((_end_at(s) - s.login_at).total_seconds() / 60)),
    }


def _active_minutes(sessions: list[AttendanceSession]) -> int:
    """Total time signed in, merging overlaps (the same person on two devices counts once)."""
    spans = sorted((s.login_at, max(s.login_at, _end_at(s))) for s in sessions)
    total, cur_s, cur_e = timedelta(), None, None
    for a, b in spans:
        if cur_e is None or a > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = a, b
        else:
            cur_e = max(cur_e, b)
    if cur_e is not None:
        total += cur_e - cur_s
    return round(total.total_seconds() / 60)


def _day(sessions: list[AttendanceSession], now: datetime) -> dict:
    ordered = sorted(sessions, key=lambda s: s.login_at)
    explicit = [s.logout_at for s in ordered if s.logout_at and s.ended_by == "logout"]
    states = [_state(s, now) for s in ordered]
    # ACTIVE: seen recently. IDLE: a tab was left open and went quiet. SIGNED_OUT: every session was ended.
    status_ = "ACTIVE" if "active" in states else ("IDLE" if "idle" in states else "SIGNED_OUT")
    return {
        "status": status_,
        "first_login": ordered[0].login_at,
        "last_logout": max(explicit) if explicit else None,
        "last_active": max(_end_at(s) for s in ordered),
        "minutes": _active_minutes(ordered),
        "sign_ins": len(ordered),
        # where they first signed in that day — skipping sign-ins that shared no location
        "location": _location(next((x for x in ordered if x.location_status != "unknown"), ordered[0])),
    }


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


def _attendees(db: Session, org_id: uuid.UUID, roles: dict[uuid.UUID, list[str]]) -> list[User]:
    """Active people who are expected to sign in daily."""
    users = db.execute(select(User).where(User.organization_id == org_id, User.is_active.is_(True))).scalars().all()
    return [u for u in users if ATTENDING_ROLES & set(roles.get(u.id, [])) and ADMIN not in roles.get(u.id, [])]


def day_overview(db: Session, admin: User, day: date) -> dict:
    now = _now()
    org = admin.organization_id
    roles = _roles_by_user(db, org)
    sessions = db.execute(
        select(AttendanceSession).where(AttendanceSession.organization_id == org, AttendanceSession.work_date == day)
    ).scalars().all()
    by_user: dict[uuid.UUID, list[AttendanceSession]] = {}
    for s in sessions:
        by_user.setdefault(s.user_id, []).append(s)

    people = {u.id: u for u in _attendees(db, org, roles)}
    for uid in by_user:  # someone who signed in but is no longer 'active' still shows for that day — but never an admin
        if uid not in people and ADMIN not in roles.get(uid, []):
            u = db.get(User, uid)
            if u is not None and ATTENDING_ROLES & set(roles.get(uid, [])):
                people[uid] = u

    rows = []
    for uid, u in people.items():
        base = _person(u, roles.get(uid, []))
        if uid in by_user:
            d = _day(by_user[uid], now)
            rows.append({**base, **d, "sessions": [_session_dict(s, now) for s in sorted(by_user[uid], key=lambda s: s.login_at)]})
        else:
            rows.append({**base, "status": "ABSENT", "first_login": None, "last_logout": None, "last_active": None,
                         "minutes": 0, "sign_ins": 0, "location": {"status": "unknown", "label": "—"}, "sessions": []})
    order = {"ACTIVE": 0, "SIGNED_OUT": 1, "IDLE": 1, "ABSENT": 2}
    cat_order = {c: i for i, c in enumerate(["accounts", "blinkit", "zepto", "other", "admin"])}
    rows.sort(key=lambda r: (cat_order[r["category"]], order[r["status"]], r["first_login"] or now, r["full_name"].lower()))

    present = [r for r in rows if r["status"] != "ABSENT"]
    expected = [r for r in rows if ATTENDING_ROLES & set(r["roles"])]
    return {
        "date": day,
        "summary": {
            "expected": len(expected),
            "present": sum(1 for r in expected if r["status"] != "ABSENT"),
            "active_now": sum(1 for r in rows if r["status"] == "ACTIVE"),
            "absent": sum(1 for r in expected if r["status"] == "ABSENT"),
            "outside_office": sum(1 for r in present if r["location"]["status"] == "outside"),
            "location_unknown": sum(1 for r in present if r["location"]["status"] == "unknown"),
        },
        "rows": rows,
    }


def _month_bounds(month: date) -> tuple[date, date]:
    return month, date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def parse_month(value: str | None) -> date:
    if not value:
        t = today_local()
        return t.replace(day=1)
    try:
        y, m = (int(x) for x in value.split("-"))
        return date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Month must look like 2026-10.") from exc


def _month_rows(db: Session, org_id: uuid.UUID, month: date, *, only_user: uuid.UUID | None, detail: bool) -> dict:
    now = _now()
    start, end = _month_bounds(month)
    stmt = select(AttendanceSession).where(
        AttendanceSession.organization_id == org_id, AttendanceSession.work_date >= start, AttendanceSession.work_date <= end
    )
    if only_user:
        stmt = stmt.where(AttendanceSession.user_id == only_user)
    grouped: dict[uuid.UUID, dict[date, list[AttendanceSession]]] = {}
    for s in db.execute(stmt).scalars():
        grouped.setdefault(s.user_id, {}).setdefault(s.work_date, []).append(s)

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

    rows = []
    for uid, u in people.items():
        days = {}
        for d, sess in sorted(grouped.get(uid, {}).items()):
            info = _day(sess, now)
            entry = {
                "first_login": info["first_login"], "last_logout": info["last_logout"], "last_active": info["last_active"],
                "minutes": info["minutes"], "sign_ins": info["sign_ins"], "status": info["status"], "location": info["location"],
            }
            if detail:
                entry["sessions"] = [_session_dict(s, now) for s in sorted(sess, key=lambda s: s.login_at)]
            days[d.isoformat()] = entry
        rows.append({
            **_person(u, roles.get(uid, [])), "days": days, "days_present": len(days),
            "total_minutes": sum(x["minutes"] for x in days.values()),
            "outside_days": sum(1 for x in days.values() if x["location"]["status"] == "outside"),
        })
    cat_order = {c: i for i, c in enumerate(["accounts", "blinkit", "zepto", "other", "admin"])}
    rows.sort(key=lambda r: (cat_order[r["category"]], r["full_name"].lower()))
    n_days = calendar.monthrange(month.year, month.month)[1]
    return {
        "month": f"{month:%Y-%m}",
        "dates": [date(month.year, month.month, i).isoformat() for i in range(1, n_days + 1)],
        "today": today_local(),
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
    db.delete(o)  # past sign-ins keep their stored label
    db.commit()

