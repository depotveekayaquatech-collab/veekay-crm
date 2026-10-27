"""Employee performance recounts from the entries as they are now, 1st of the month to yesterday."""
from datetime import date, timedelta

from app.services import performance_service

from .conftest import API, auth, login

TODAY = date.today()


def _month_start():
    return (TODAY - timedelta(days=1)).replace(day=1)


def test_late_entries_lift_the_earlier_days(client, db, admin, make_user, make_store):
    if TODAY.day < 4:
        return                                           # needs a few finished days in the month
    store = make_store(platform="blinkit", region="NORTH", state="Perf-Land")
    code, pw, uid = make_user(platform="blinkit", region="NORTH", grants=("orders.view", "orders.mark"))
    emp = auth(login(client, code, pw).json()["access_token"])
    first = _month_start()
    n_days = (TODAY - timedelta(days=1) - first).days + 1

    def mine():
        r = client.get(f"{API}/orders/performance", params={"partner": "blinkit"}, headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["as_of"] == (TODAY - timedelta(days=1)).isoformat()
        return next(e for e in r.json()["employees"] if e["employee_id"] == str(uid))

    base = mine()
    assert len(base["daily"]) == n_days and base["stores"] >= 1
    stores, d0, d1 = base["stores"], base["done"], base["daily"][0]["done"]

    # the first finished day is marked: it counts at once
    assert client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(store.id), "order_date": first.isoformat(), "bottle_count": 5}).status_code == 200
    one = mine()
    assert one["done"] == d0 + 1 and one["daily"][0]["done"] == d1 + 1 and one["daily"][0]["percent"] == round((d1 + 1) * 100 / stores, 1)

    # marking a LATER day afterwards changes the totals, and the earlier days keep their numbers
    assert client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(store.id), "order_date": (first + timedelta(days=1)).isoformat(), "bottle_count": 5}).status_code == 200
    two = mine()
    assert two["done"] == d0 + 2 and two["percent"] > one["percent"] and two["daily"][0]["done"] == d1 + 1


def test_someone_with_no_store_is_not_listed(client, db, admin, make_user, make_store):
    make_store(platform="blinkit", region="NORTH", state="Perf-Land")
    _, _, with_store = make_user(platform="blinkit", region="NORTH", grants=("orders.view", "orders.mark"))
    _, _, without = make_user(platform="blinkit", region="SOUTH", grants=("orders.view", "orders.mark"))   # no store in SOUTH
    r = client.get(f"{API}/orders/performance", params={"partner": "blinkit"}, headers=admin)
    assert r.status_code == 200, r.text
    listed = {e["employee_id"] for e in r.json()["employees"]}
    assert str(with_store) in listed and str(without) not in listed
    assert all(e["stores"] > 0 for e in r.json()["employees"])


def test_an_entry_marked_on_a_holiday_does_not_break_the_page(client, db, admin, make_user, make_store):
    if TODAY.day < 4:
        return
    store = make_store(platform="blinkit", region="NORTH", state="Perf-Land")
    code, pw, uid = make_user(platform="blinkit", region="NORTH", grants=("orders.view", "orders.mark"))
    emp = auth(login(client, code, pw).json()["access_token"])
    first = _month_start()
    holiday = first + timedelta(days=1)                  # inside the judged days, with a later day after it
    assert client.post(f"{API}/attendance/holidays", headers=admin, json={"holiday_date": holiday.isoformat(), "name": "Diwali"}).status_code == 200
    try:
        for d in (first, holiday):
            assert client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(store.id), "order_date": d.isoformat(), "bottle_count": 5}).status_code == 200
        r = client.get(f"{API}/orders/performance", params={"partner": "blinkit"}, headers=admin)
        assert r.status_code == 200, r.text
        mine = next(e for e in r.json()["employees"] if e["employee_id"] == str(uid))
        assert holiday.isoformat() not in {d["date"] for d in mine["daily"]}
    finally:
        client.delete(f"{API}/attendance/holidays/{holiday.isoformat()}", headers=admin)


def test_month_parsing_defaults_to_the_month_of_yesterday():
    assert performance_service.parse_month(None, date(2026, 11, 1)) == date(2026, 10, 1)
    assert performance_service.parse_month(None, date(2026, 11, 2)) == date(2026, 11, 1)
    assert performance_service.parse_month("2026-03", date(2026, 11, 2)) == date(2026, 3, 1)
