"""Attendance: explicit check in / out, the 100 m office rule, lateness, day/month views, and leave."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.roles import staff_category
from app.models.attendance import AttendanceRecord
from app.services import attendance_service as svc

from .conftest import API, auth, login

OFFICE = (12.971599, 77.594566)          # a point in Bengaluru
IST = ZoneInfo("Asia/Kolkata")


def _north(metres: float) -> tuple[float, float]:
    """A point `metres` due north of the office (1 degree of latitude is ~111,195 m)."""
    return OFFICE[0] + metres / 111_195.0, OFFICE[1]


def _at(lat_lng: tuple[float, float]) -> dict:
    return {"latitude": lat_lng[0], "longitude": lat_lng[1], "accuracy": 12}


@pytest.fixture()
def office(client, admin):
    r = client.post(f"{API}/attendance/offices", headers=admin, json={"name": "Head Office", "latitude": OFFICE[0], "longitude": OFFICE[1]})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def clock(monkeypatch):
    """Pin 'now' (given as local IST wall-clock time on the real today) so lateness is deterministic."""
    def set_time(hour: int, minute: int = 0):
        local_today = datetime.now(IST).date()
        fixed = datetime(local_today.year, local_today.month, local_today.day, hour, minute, tzinfo=IST).astimezone(timezone.utc)
        monkeypatch.setattr(svc, "_now", lambda: fixed)
        return fixed
    return set_time


def _fresh_employee(client, make_user):
    code, pw, uid = make_user()
    return auth(login(client, code, pw).json()["access_token"]), uid


# ---------------------------------------------------------------- pure rules
def test_haversine_known_distance():
    assert svc.haversine_m(*OFFICE, *_north(100)) == pytest.approx(100, abs=1)
    assert svc.haversine_m(*OFFICE, *OFFICE) == 0


def test_categories_admin_beats_accounts_beats_platform():
    assert staff_category(["admin", "accountant"], "zepto") == "admin"
    assert staff_category(["manager"], None) == "admin"          # a custom admin is still an admin on the Team page
    assert staff_category(["partner"], "blinkit") == "partner"
    assert staff_category(["accountant"], "blinkit") == "accounts"
    assert staff_category(["employee"], "Blinkit") == "blinkit"
    assert staff_category(["employee"], "zepto") == "zepto"
    assert staff_category(["employee"], None) == "other"
    assert staff_category(["employee"], "swiggy") == "other"


# ---------------------------------------------------------------- signing in is not attendance
def test_signing_in_records_nothing_and_the_old_location_route_is_gone(client, db, make_user):
    code, pw, uid = make_user()
    r = login(client, code, pw)
    assert r.status_code == 200
    assert db.query(AttendanceRecord).filter_by(user_id=uid).count() == 0
    assert client.post(f"{API}/attendance/location", headers=auth(r.json()["access_token"]), json={"latitude": 1, "longitude": 1}).status_code in (404, 405)
    today = client.get(f"{API}/attendance/today", headers=auth(r.json()["access_token"])).json()
    assert today["eligible"] is True and today["checked_in"] is False


# ---------------------------------------------------------------- who can check in
def test_admins_and_partner_logins_cannot_check_in(client, admin, make_user):
    assert client.post(f"{API}/attendance/check-in", headers=admin, json={}).status_code == 403
    assert client.get(f"{API}/attendance/today", headers=admin).json()["eligible"] is False
    code, pw, _ = make_user(role="partner", platform="blinkit")
    p = auth(login(client, code, pw).json()["access_token"])
    assert client.post(f"{API}/attendance/check-in", headers=p, json={}).status_code == 403


def test_admin_never_appears_in_the_day_or_month_views(client, admin, emp):
    day = client.get(f"{API}/attendance/day", headers=admin).json()
    assert all(r["category"] != "admin" for r in day["rows"])
    assert "ADMIN001" not in {r["employee_code"] for r in day["rows"]}
    month = client.get(f"{API}/attendance/month", headers=admin).json()
    assert "ADMIN001" not in {r["employee_code"] for r in month["rows"]}


# ---------------------------------------------------------------- check in / out
def test_check_in_then_out_once_a_day(client, make_user, clock):
    clock(10, 0)
    h, _ = _fresh_employee(client, make_user)
    r = client.post(f"{API}/attendance/check-in", headers=h, json={})
    assert r.status_code == 200 and r.json()["checked_in"] and not r.json()["checked_out"]
    assert client.post(f"{API}/attendance/check-in", headers=h, json={}).status_code == 409     # only once
    clock(18, 30)
    out = client.post(f"{API}/attendance/check-out", headers=h, json={})
    assert out.status_code == 200 and out.json()["checked_out"] and out.json()["minutes"] == 510
    assert client.post(f"{API}/attendance/check-out", headers=h, json={}).status_code == 409


def test_check_out_needs_a_check_in_first(client, make_user):
    h, _ = _fresh_employee(client, make_user)
    r = client.post(f"{API}/attendance/check-out", headers=h, json={})
    assert r.status_code == 409 and "Check in first" in r.json()["detail"]


def test_late_after_the_grace_period(client, make_user, clock):
    h1, _ = _fresh_employee(client, make_user)
    clock(10, 15)                                                  # exactly at start + grace: still on time
    assert client.post(f"{API}/attendance/check-in", headers=h1, json={}).json()["late"] is False
    h2, _ = _fresh_employee(client, make_user)
    clock(10, 16)
    assert client.post(f"{API}/attendance/check-in", headers=h2, json={}).json()["late"] is True


# ---------------------------------------------------------------- location is read at check in / out, nowhere else
def test_inside_100m_shows_the_office_name(client, admin, office, make_user, clock):
    clock(9, 30)
    h, _ = _fresh_employee(client, make_user)
    loc = client.post(f"{API}/attendance/check-in", headers=h, json=_at(_north(60))).json()["check_in_location"]
    assert loc["status"] == "office" and loc["label"] == "Head Office"


def test_100m_boundary_is_inclusive_and_beyond_it_is_outside(client, office, make_user, clock):
    clock(9, 30)
    h1, _ = _fresh_employee(client, make_user)
    assert client.post(f"{API}/attendance/check-in", headers=h1, json=_at(_north(99))).json()["check_in_location"]["status"] == "office"
    h2, _ = _fresh_employee(client, make_user)
    assert client.post(f"{API}/attendance/check-in", headers=h2, json=_at(_north(150))).json()["check_in_location"]["status"] == "outside"


def test_outside_shows_the_exact_coordinates(client, office, make_user, clock):
    clock(9, 30)
    h, _ = _fresh_employee(client, make_user)
    loc = client.post(f"{API}/attendance/check-in", headers=h, json=_at(_north(5000))).json()["check_in_location"]
    assert loc["status"] == "outside" and "," in loc["label"] and loc["map_url"].startswith("https://www.google.com/maps")
    assert 4900 < loc["distance_m"] < 5100


def test_no_office_configured_means_outside_not_an_error(client, make_user, clock):
    clock(9, 30)
    h, _ = _fresh_employee(client, make_user)
    assert client.post(f"{API}/attendance/check-in", headers=h, json=_at(OFFICE)).json()["check_in_location"]["status"] == "outside"


def test_declining_location_still_checks_you_in(client, make_user, clock):
    clock(9, 30)
    h, _ = _fresh_employee(client, make_user)
    t = client.post(f"{API}/attendance/check-in", headers=h, json={}).json()
    assert t["checked_in"] and t["check_in_location"]["status"] == "unknown"


def test_check_out_records_its_own_location(client, office, make_user, clock):
    clock(9, 30)
    h, _ = _fresh_employee(client, make_user)
    client.post(f"{API}/attendance/check-in", headers=h, json=_at(_north(10)))
    clock(18, 0)
    t = client.post(f"{API}/attendance/check-out", headers=h, json=_at(_north(3000))).json()
    assert t["check_in_location"]["status"] == "office" and t["check_out_location"]["status"] == "outside"


@pytest.mark.parametrize("body", [{"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": 181}, {"latitude": 0, "longitude": 0, "accuracy": -1}])
def test_bad_coordinates_are_rejected(client, emp, body):
    assert client.post(f"{API}/attendance/check-in", headers=emp, json=body).status_code == 422


# ---------------------------------------------------------------- admin views
def test_absent_people_are_listed_and_counted(client, admin, clock):
    clock(12, 0)
    day = client.get(f"{API}/attendance/day?date={datetime.now(IST).date()}", headers=admin).json()
    s = day["summary"]
    if not day["is_weekly_off"]:
        assert s["expected"] >= 2 and s["absent"] == s["expected"] and s["present"] == 0
        assert all(r["status"] == "ABSENT" for r in day["rows"])


def test_sunday_is_the_weekly_off_not_an_absence(client, admin):
    d = date.today()
    sunday = d - timedelta(days=(d.weekday() + 1) % 7)             # the most recent Sunday
    day = client.get(f"{API}/attendance/day?date={sunday}", headers=admin).json()
    assert day["is_weekly_off"] is True and day["summary"]["absent"] == 0
    assert all(r["status"] == "OFF" for r in day["rows"])


def test_day_view_shows_present_late_and_still_in(client, admin, make_user, clock):
    clock(11, 0)
    code, pw, _ = make_user()
    h = auth(login(client, code, pw).json()["access_token"])
    client.post(f"{API}/attendance/check-in", headers=h, json={})
    day = client.get(f"{API}/attendance/day?date={datetime.now(IST).date()}", headers=admin).json()
    row = next(r for r in day["rows"] if r["employee_code"] == code)
    assert row["status"] == "CHECKED_IN" and row["late"] is True
    assert day["summary"]["present"] >= 1 and day["summary"]["late"] >= 1 and day["summary"]["checked_in_now"] >= 1


def test_month_and_me_views(client, admin, make_user, clock):
    clock(9, 30)
    code, pw, _ = make_user()
    h = auth(login(client, code, pw).json()["access_token"])
    client.post(f"{API}/attendance/check-in", headers=h, json={})
    month = client.get(f"{API}/attendance/month", headers=admin).json()
    me = next(r for r in month["rows"] if r["employee_code"] == code)
    assert me["days_present"] == 1 and me["late_days"] == 0
    assert client.get(f"{API}/attendance/month?month=garbage", headers=admin).status_code == 422
    mine = client.get(f"{API}/attendance/me", headers=h).json()
    assert mine["rows"][0]["days_present"] == 1


def test_employees_cannot_see_everyone_or_manage_offices(client, emp):
    assert client.get(f"{API}/attendance/day", headers=emp).status_code == 403
    assert client.get(f"{API}/attendance/offices", headers=emp).status_code == 403
    assert client.post(f"{API}/attendance/offices", headers=emp, json={"name": "x", "latitude": 1, "longitude": 1}).status_code == 403


# ---------------------------------------------------------------- offices
def test_office_crud(client, admin, office):
    assert office["radius_m"] == 100                                    # default radius
    oid = office["id"]
    assert client.patch(f"{API}/attendance/offices/{oid}", headers=admin, json={"radius_m": 250}).json()["radius_m"] == 250
    assert any(o["id"] == oid for o in client.get(f"{API}/attendance/offices", headers=admin).json())
    assert client.patch(f"{API}/attendance/offices/{oid}", headers=admin, json={"radius_m": 5}).status_code == 422
    assert client.delete(f"{API}/attendance/offices/{oid}", headers=admin).status_code == 204
    assert client.delete(f"{API}/attendance/offices/{oid}", headers=admin).status_code == 404


# ---------------------------------------------------------------- leave
def _next_weekday(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7 or 7)


def _leave(client, h, start: date, end: date, **kw):
    body = {"leave_type": "SICK", "start_date": str(start), "end_date": str(end), "reason": "Fever", **kw}
    return client.post(f"{API}/attendance/leaves", headers=h, json=body)


def test_leave_days_skip_sundays(client, make_user):
    h, _ = _fresh_employee(client, make_user)
    monday = _next_weekday(date.today(), 0)
    r = _leave(client, h, monday - timedelta(days=2), monday)          # Sat, Sun, Mon
    assert r.status_code == 201 and r.json()["days"] == 2 and r.json()["status"] == "PENDING"


def test_leave_rules(client, make_user):
    h, _ = _fresh_employee(client, make_user)
    monday = _next_weekday(date.today(), 0)
    assert _leave(client, h, monday + timedelta(days=1), monday).status_code == 422                      # ends before it starts
    assert _leave(client, h, date.today() - timedelta(days=30), date.today() - timedelta(days=30)).status_code == 422  # too far back
    assert _leave(client, h, monday, monday + timedelta(days=1), half_day=True).status_code == 422     # half day = one date
    assert _leave(client, h, monday - timedelta(days=1), monday - timedelta(days=1)).status_code == 422  # a lone Sunday is nothing to apply for
    assert _leave(client, h, monday, monday, reason="  ").status_code == 422


def test_overlapping_leave_is_refused_but_cancelling_frees_the_dates(client, make_user):
    h, _ = _fresh_employee(client, make_user)
    monday = _next_weekday(date.today(), 0)
    first = _leave(client, h, monday, monday + timedelta(days=2))
    assert first.status_code == 201
    assert _leave(client, h, monday + timedelta(days=1), monday + timedelta(days=1)).status_code == 409
    assert client.post(f"{API}/attendance/leaves/{first.json()['id']}/cancel", headers=h).json()["status"] == "CANCELLED"
    assert _leave(client, h, monday + timedelta(days=1), monday + timedelta(days=1)).status_code == 201


def test_only_reviewers_approve_and_never_their_own_request(client, admin, emp, make_user):
    h, _ = _fresh_employee(client, make_user)
    monday = _next_weekday(date.today(), 0)
    lid = _leave(client, h, monday, monday).json()["id"]
    assert client.post(f"{API}/attendance/leaves/{lid}/review", headers=emp, json={"approve": True}).status_code == 403
    assert client.get(f"{API}/attendance/leaves", headers=emp).status_code == 403
    pending = client.get(f"{API}/attendance/leaves?status=PENDING", headers=admin).json()
    assert any(i["id"] == lid for i in pending["items"]) and pending["pending"] >= 1
    ok = client.post(f"{API}/attendance/leaves/{lid}/review", headers=admin, json={"approve": True, "note": "Rest well"})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED" and ok.json()["review_note"] == "Rest well"
    assert client.post(f"{API}/attendance/leaves/{lid}/review", headers=admin, json={"approve": False}).status_code == 409   # decided once


def test_approved_leave_shows_as_on_leave_not_absent(client, admin, make_user):
    code, pw, _ = make_user()
    h = auth(login(client, code, pw).json()["access_token"])
    monday = _next_weekday(date.today(), 0)
    lid = _leave(client, h, monday, monday, leave_type="CASUAL").json()["id"]
    client.post(f"{API}/attendance/leaves/{lid}/review", headers=admin, json={"approve": True})
    day = client.get(f"{API}/attendance/day?date={monday}", headers=admin).json()
    row = next(r for r in day["rows"] if r["employee_code"] == code)
    assert row["status"] == "ON_LEAVE" and row["leave_type"] == "CASUAL" and day["summary"]["on_leave"] >= 1
    mine = client.get(f"{API}/attendance/leaves/me", headers=h).json()
    assert mine["taken"]["CASUAL"] == 1.0
    # an approved leave in the future can still be cancelled by its owner
    assert client.post(f"{API}/attendance/leaves/{lid}/cancel", headers=h).json()["status"] == "CANCELLED"


def test_admins_cannot_apply_for_leave(client, admin):
    monday = _next_weekday(date.today(), 0)
    assert _leave(client, admin, monday, monday).status_code == 403
