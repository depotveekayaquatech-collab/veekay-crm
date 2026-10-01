"""Attendance: who is tracked, location checked at sign-in only, the 100 m office rule, day/month views."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import staff_category
from app.models.attendance import AttendanceSession
from app.services import attendance_service as svc

from .conftest import API, auth, login

OFFICE = (12.971599, 77.594566)          # a point in Bengaluru


def _north(metres: float) -> tuple[float, float]:
    """A point `metres` due north of the office (1 degree of latitude is ~111,195 m)."""
    return OFFICE[0] + metres / 111_195.0, OFFICE[1]


@pytest.fixture()
def office(client, admin):
    r = client.post(f"{API}/attendance/offices", headers=admin, json={"name": "Head Office", "latitude": OFFICE[0], "longitude": OFFICE[1]})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- pure rules
def test_haversine_known_distance():
    assert svc.haversine_m(*OFFICE, *_north(100)) == pytest.approx(100, abs=1)
    assert svc.haversine_m(*OFFICE, *OFFICE) == 0


def test_categories_admin_beats_accounts_beats_platform():
    assert staff_category(["admin", "accountant"], "zepto") == "admin"
    assert staff_category(["accountant"], "blinkit") == "accounts"
    assert staff_category(["employee"], "Blinkit") == "blinkit"
    assert staff_category(["employee"], "zepto") == "zepto"
    assert staff_category(["employee"], None) == "other"
    assert staff_category(["employee"], "swiggy") == "other"


# ---------------------------------------------------------------- who is tracked
def test_admin_sign_in_creates_no_attendance_and_no_location_is_stored(client, db):
    r = login(client, "ADMIN001", latitude=OFFICE[0], longitude=OFFICE[1])
    assert r.status_code == 200
    assert db.query(AttendanceSession).count() == 0
    assert client.post(f"{API}/attendance/location", headers=auth(r.json()["access_token"]),
                       json={"latitude": 1, "longitude": 1}).status_code == 404


def test_employee_and_accountant_sign_ins_are_tracked(client, db, make_user):
    login(client, "EMP001")
    code, pw, _ = make_user(role="accountant")
    login(client, code, pw)
    assert db.query(AttendanceSession).count() == 2


def test_admin_never_appears_in_the_day_or_month_views(client, admin, emp):
    day = client.get(f"{API}/attendance/day", headers=admin).json()
    assert all(r["category"] != "admin" for r in day["rows"])
    assert "ADMIN001" not in {r["employee_code"] for r in day["rows"]}
    month = client.get(f"{API}/attendance/month", headers=admin).json()
    assert "ADMIN001" not in {r["employee_code"] for r in month["rows"]}


# ---------------------------------------------------------------- the 100 m rule
def test_inside_100m_shows_the_office_name(client, admin, office):
    lat, lng = _north(60)
    login(client, "EMP001", latitude=lat, longitude=lng)
    row = next(r for r in client.get(f"{API}/attendance/day", headers=admin).json()["rows"] if r["employee_code"] == "EMP001")
    assert row["location"]["status"] == "office" and row["location"]["label"] == "Head Office"


def test_100m_boundary_is_inclusive_and_beyond_it_is_outside(client, db, office):
    org = db.query(__import__("app.models.organization", fromlist=["Organization"]).Organization).filter_by(slug="veekay").one().id
    for metres, expect in ((99, "office"), (101, "outside"), (2000, "outside")):
        lat, lng = _north(metres)
        st, _, dist = svc.classify(db, org, lat, lng)
        assert st == expect and dist == pytest.approx(metres, abs=1.5)


def test_outside_shows_the_exact_coordinates(client, admin, office):
    lat, lng = _north(500)
    login(client, "EMP001", latitude=lat, longitude=lng)
    row = next(r for r in client.get(f"{API}/attendance/day", headers=admin).json()["rows"] if r["employee_code"] == "EMP001")
    loc = row["location"]
    assert loc["status"] == "outside" and loc["label"] == f"{lat:.6f}, {lng:.6f}" and "maps" in loc["map_url"]


def test_no_office_configured_means_outside_not_an_error(client, admin):
    login(client, "EMP001", latitude=OFFICE[0], longitude=OFFICE[1])
    row = next(r for r in client.get(f"{API}/attendance/day", headers=admin).json()["rows"] if r["employee_code"] == "EMP001")
    assert row["location"]["status"] == "outside"


def test_declining_location_still_records_the_sign_in(client, admin):
    login(client, "EMP001")
    row = next(r for r in client.get(f"{API}/attendance/day", headers=admin).json()["rows"] if r["employee_code"] == "EMP001")
    assert row["status"] == "ACTIVE" and row["location"]["status"] == "unknown"


# ---------------------------------------------------------------- location is attached once, at sign-in only
def test_location_can_be_attached_once_after_login(client, admin, office):
    t = login(client, "EMP001").json()
    h = auth(t["access_token"])
    lat, lng = _north(10)
    assert client.post(f"{API}/attendance/location", headers=h, json={"latitude": lat, "longitude": lng}).status_code == 200
    assert client.post(f"{API}/attendance/location", headers=h, json={"latitude": lat, "longitude": lng}).status_code == 409


def test_location_cannot_be_attached_long_after_sign_in(client, db, office):
    t = login(client, "EMP001").json()
    row = db.query(AttendanceSession).one()
    row.login_at = datetime.now(timezone.utc) - timedelta(minutes=svc.LOCATION_WINDOW_MINUTES + 5)
    db.commit()
    r = client.post(f"{API}/attendance/location", headers=auth(t["access_token"]), json={"latitude": OFFICE[0], "longitude": OFFICE[1]})
    assert r.status_code == 409


@pytest.mark.parametrize("body", [{"latitude": 95, "longitude": 0}, {"latitude": 0, "longitude": 181}, {"latitude": "x", "longitude": 0}])
def test_bad_coordinates_are_rejected(client, body):
    t = login(client, "EMP001").json()
    assert client.post(f"{API}/attendance/location", headers=auth(t["access_token"]), json=body).status_code == 422


# ---------------------------------------------------------------- sign-out and views
def test_logout_stamps_the_logout_time(client, admin):
    t = login(client, "EMP001").json()
    client.post(f"{API}/auth/logout", json={"refresh_token": t["refresh_token"]})
    row = next(r for r in client.get(f"{API}/attendance/day", headers=admin).json()["rows"] if r["employee_code"] == "EMP001")
    assert row["status"] == "SIGNED_OUT" and row["last_logout"] is not None and row["sessions"][0]["ended_by"] == "logout"


def test_two_devices_count_time_once(client, admin):
    login(client, "EMP001")
    login(client, "EMP001")
    row = next(r for r in client.get(f"{API}/attendance/day", headers=admin).json()["rows"] if r["employee_code"] == "EMP001")
    assert row["sign_ins"] == 2 and row["minutes"] <= 1


def test_absent_people_are_listed_and_counted(client, admin):
    day = client.get(f"{API}/attendance/day", headers=admin).json()
    s = day["summary"]
    assert s["expected"] >= 2 and s["absent"] == s["expected"] and s["present"] == 0
    assert all(r["status"] == "ABSENT" for r in day["rows"])


def test_month_and_me_views(client, admin, emp):
    login(client, "EMP001")
    month = client.get(f"{API}/attendance/month", headers=admin).json()
    me = next(r for r in month["rows"] if r["employee_code"] == "EMP001")
    assert me["days_present"] == 1
    assert client.get(f"{API}/attendance/month?month=garbage", headers=admin).status_code == 422
    assert client.get(f"{API}/attendance/me", headers=emp).status_code == 200


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
