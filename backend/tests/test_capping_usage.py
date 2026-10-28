"""Zepto capping usage: every store against its monthly limit (daily capping x 30), counting every entry, with the alert levels, and the dashboard alerts."""
from datetime import date, timedelta

import pytest

from app.services import capping_history_service as hist
from app.services import capping_service as cs

from .conftest import API, auth, login, plant_entry


@pytest.fixture()
def zstore(make_store):
    return make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")


def _cap(client, admin, store, n):
    assert client.post(f"{API}/capping/change", json={"storeId": str(store.id), "capping": n}, headers=admin).status_code == 201


def _row(client, headers, store, month=None):
    r = client.get(f"{API}/capping/usage", params={"month": month} if month else {}, headers=headers)
    assert r.status_code == 200, r.text
    return next(x for x in r.json()["rows"] if x["store_id"] == str(store.id)), r.json()


def test_the_levels_follow_the_monthly_limit_the_pace_and_the_warning_line():
    assert cs.monthly_limit(10) == 300 and cs.monthly_limit(None) is None and cs.monthly_limit(0) == 0
    assert cs.alert_for(5, None) == "NO_CAP"
    assert cs.alert_for(301, 10) == "OVER" and cs.alert_for(300, 10) == "NEAR"                 # exactly the limit is not over it
    assert cs.alert_for(0, 0) == "OK" and cs.alert_for(1, 0) == "OVER"                         # a capping of 0 is a real capping
    assert cs.alert_for(250, 10) == "NEAR" and cs.alert_for(239, 10) == "OK"                   # 80% of 300 is 240
    assert cs.alert_for(160, 10, day=15) == "AHEAD" and cs.alert_for(150, 10, day=15) == "OK"  # ahead of 10 x 15
    assert cs.pace_for(10, date(2026, 10, 1), date(2026, 10, 15)) == (15, 150)
    assert cs.pace_for(10, date(2026, 9, 1), date(2026, 10, 15)) == (None, None)               # a finished month has no pace


def test_the_usage_report_counts_every_entry_of_the_month_against_the_limit(client, admin, zstore, db):
    today = hist.today_ist()
    if today.day < 3:
        return
    first = today.replace(day=1)
    plant_entry(db, zstore, first, 200)                                                        # an employee's entry
    plant_entry(db, zstore, first + timedelta(days=1), 150, source="admin")                    # an admin's / a sheet's entry counts too
    _cap(client, admin, zstore, 10)
    row, body = _row(client, admin, zstore)
    assert row["daily_cap"] == 10 and row["monthly_cap"] == 300
    assert row["used"] == 350 and row["entries"] == 2 and row["highest_day"] == 200 and row["last_entry"] == (first + timedelta(days=1)).isoformat()
    assert row["alert"] == "OVER" and row["excess"] == 50 and row["remaining"] == 0 and row["percent"] == 116.7
    assert body["summary"]["over"] >= 1 and body["summary"]["total"] == len(body["rows"]) and body["month"] == f"{first:%Y-%m}"
    assert body["rows"][0]["alert"] == "OVER"                                                  # worst first


def test_a_store_with_no_capping_and_a_store_that_is_not_live_are_handled(client, admin, zstore, make_store, db):
    today = hist.today_ist()
    plant_entry(db, zstore, today.replace(day=1), 40)
    row, body = _row(client, admin, zstore)
    assert row["alert"] == "NO_CAP" and row["daily_cap"] is None and row["monthly_cap"] is None and row["used"] == 40 and row["percent"] is None
    closed = make_store(platform="zepto", region=None, status="CLOSE")
    assert all(x["store_id"] != str(closed.id) for x in body["rows"])                          # only live stores are measured


def test_the_ahead_of_pace_level_shows_in_the_current_month(client, admin, zstore, db):
    today = hist.today_ist()
    need = 10 * today.day + 5                                                                  # a few bottles more than a capping of 10 allows so far
    if need > 200 or need > 240:
        return
    plant_entry(db, zstore, today.replace(day=1), need)
    _cap(client, admin, zstore, 10)
    row, _ = _row(client, admin, zstore)
    assert row["alert"] == "AHEAD" and row["ahead_by"] == 5 and row["allowed_to_date"] == 10 * today.day


def test_an_earlier_month_has_no_pace_and_the_month_is_checked(client, admin, zstore):
    assert client.get(f"{API}/capping/usage", params={"month": "2999-01"}, headers=admin).status_code == 422
    assert client.get(f"{API}/capping/usage", params={"month": "2023-12"}, headers=admin).status_code == 422
    assert client.get(f"{API}/capping/usage", params={"month": "garbage"}, headers=admin).status_code == 422
    last = hist.today_ist().replace(day=1) - timedelta(days=1)
    row, body = _row(client, admin, zstore, f"{last:%Y-%m}")
    assert row["allowed_to_date"] is None and body["months"][0] == f"{hist.today_ist():%Y-%m}"


def test_who_may_see_the_usage_and_the_alerts(client, admin, zepto_emp, emp, zstore, make_user, db):
    today = hist.today_ist()
    plant_entry(db, zstore, today.replace(day=1), 200)
    if today.day > 1:
        plant_entry(db, zstore, today.replace(day=1) + timedelta(days=1), 150)
    _cap(client, admin, zstore, 10)
    assert client.get(f"{API}/capping/usage", headers=zepto_emp).status_code == 200
    assert client.get(f"{API}/capping/usage", headers=emp).status_code == 403                  # a Blinkit employee sees no Zepto capping
    assert client.get(f"{API}/capping/usage").status_code in (401, 403)

    assert client.get(f"{API}/capping/alerts", headers=zepto_emp).status_code == 403           # the alert needs capping.alerts
    assert client.get(f"{API}/capping/alerts", headers=emp).status_code == 403
    code, pw, _ = make_user(role="partner", platform="zepto", region=None)                      # the platform's own login always gets it
    partner = auth(login(client, code, pw).json()["access_token"])
    a = client.get(f"{API}/capping/alerts", headers=partner)
    assert a.status_code == 200, a.text
    if today.day > 1:
        assert any(r["store_id"] == str(zstore.id) and r["alert"] == "OVER" for r in a.json()["rows"]) and a.json()["over"] >= 1

    ccode, cpw, _ = make_user("employee", platform="zepto", grants=("orders.view", "capping.alerts"))
    ticked = auth(login(client, ccode, cpw).json()["access_token"])
    assert client.get(f"{API}/capping/alerts", headers=ticked).status_code == 200              # ticked for one person
