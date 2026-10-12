"""Marking several dates of one store, each with its own count, in a single request."""
from datetime import date, timedelta

from .conftest import API


def _days_this_month(n: int) -> list[date]:
    today = date.today()
    return [today - timedelta(days=i) for i in range(min(n, today.day))]


def _calendar(client, h, store_id, today):
    r = client.get(f"{API}/orders/calendar", params={"store_id": store_id, "year": today.year, "month": today.month}, headers=h)
    assert r.status_code == 200, r.text
    return {d["date"]: d["count"] for d in r.json()["days"] if d["marked"]}


def test_several_dates_are_saved_with_their_own_counts(client, emp, make_store):
    store = make_store()
    days = _days_this_month(3)
    body = {"store_id": str(store.id), "entries": [{"order_date": str(d), "bottle_count": 10 + i} for i, d in enumerate(days)]}
    r = client.post(f"{API}/orders/mark-many", json=body, headers=emp)
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["saved"], out["failed"]) == (len(days), 0) and all(x["ok"] for x in out["results"])
    cal = _calendar(client, emp, str(store.id), date.today())
    assert {d: cal[str(d)] for d in days} == {d: 10 + i for i, d in enumerate(days)}


def test_one_bad_date_does_not_block_the_others(client, emp, make_store):
    store = make_store()
    today = date.today()
    ok_day = today
    first = today.replace(day=1)
    last_month = first - timedelta(days=1)
    body = {"store_id": str(store.id), "entries": [
        {"order_date": str(ok_day), "bottle_count": 7},
        {"order_date": str(today + timedelta(days=1)), "bottle_count": 5},      # future
        {"order_date": str(last_month), "bottle_count": 5},                      # not this month
    ]}
    out = client.post(f"{API}/orders/mark-many", json=body, headers=emp).json()
    by_date = {x["order_date"]: x for x in out["results"]}
    assert (out["saved"], out["failed"]) == (1, 2)
    assert by_date[str(ok_day)]["ok"] and "future" in by_date[str(today + timedelta(days=1))]["error"]
    assert "current month" in by_date[str(last_month)]["error"]
    assert _calendar(client, emp, str(store.id), today)[str(ok_day)] == 7


def test_an_already_marked_date_is_reported_and_left_alone(client, emp, make_store):
    store = make_store()
    d = date.today()
    one = {"store_id": str(store.id), "entries": [{"order_date": str(d), "bottle_count": 12}]}
    assert client.post(f"{API}/orders/mark-many", json=one, headers=emp).json()["saved"] == 1
    again = {"store_id": str(store.id), "entries": [{"order_date": str(d), "bottle_count": 99}]}
    out = client.post(f"{API}/orders/mark-many", json=again, headers=emp).json()
    assert out["saved"] == 0 and "already marked" in out["results"][0]["error"]
    assert _calendar(client, emp, str(store.id), d)[str(d)] == 12


def test_rejected_requests(client, emp, zepto_emp, make_store):
    store = make_store()
    d = str(date.today())
    dup = {"store_id": str(store.id), "entries": [{"order_date": d, "bottle_count": 1}, {"order_date": d, "bottle_count": 2}]}
    assert client.post(f"{API}/orders/mark-many", json=dup, headers=emp).status_code == 422
    assert client.post(f"{API}/orders/mark-many", json={"store_id": str(store.id), "entries": []}, headers=emp).status_code == 422
    too_big = {"store_id": str(store.id), "entries": [{"order_date": d, "bottle_count": 201}]}
    assert client.post(f"{API}/orders/mark-many", json=too_big, headers=emp).status_code == 422
    # a store that is not yours fails the whole request
    mine = {"store_id": str(store.id), "entries": [{"order_date": d, "bottle_count": 3}]}
    assert client.post(f"{API}/orders/mark-many", json=mine, headers=zepto_emp).status_code == 403
    assert client.post(f"{API}/orders/mark-many", json=mine).status_code == 401


def test_admin_can_mark_many_and_overwrite(client, admin, make_store):
    store = make_store()
    d = str(date.today())
    body = {"store_id": str(store.id), "entries": [{"order_date": d, "bottle_count": 4}]}
    assert client.post(f"{API}/orders/mark-many", json=body, headers=admin).json()["saved"] == 1
    body["entries"][0]["bottle_count"] = 9
    assert client.post(f"{API}/orders/mark-many", json=body, headers=admin).json()["saved"] == 1
    assert _calendar(client, admin, str(store.id), date.today())[d] == 9
