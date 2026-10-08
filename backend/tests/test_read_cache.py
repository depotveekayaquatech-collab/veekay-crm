"""The dashboard read cache: shared work, but never stale after a write — on this worker or another."""
from datetime import date

import pytest
from sqlalchemy import text

from app.core import cache as cache_mod
from app.core.cache import TTLCache
from app.db.session import engine

from .conftest import API


@pytest.fixture()
def fresh(monkeypatch):
    monkeypatch.setattr(cache_mod, "_VERSION_MEMO_SECONDS", 0.0)   # re-read the shared counter every time
    return TTLCache()


def test_a_value_is_computed_once_until_it_expires_or_data_changes(fresh):
    calls = []
    compute = lambda: calls.append(1) or len(calls)  # noqa: E731
    assert fresh.get_or_set("k", 60, compute) == 1
    assert fresh.get_or_set("k", 60, compute) == 1          # served from cache
    assert len(calls) == 1
    fresh.invalidate()
    assert fresh.get_or_set("k", 60, compute) == 2          # a write happened: recomputed


def test_a_write_on_another_worker_invalidates_this_workers_cache(fresh):
    calls = []
    compute = lambda: calls.append(1) or len(calls)  # noqa: E731
    fresh.get_or_set("k", 60, compute)
    with engine.begin() as conn:                              # what a different worker's invalidate() does
        conn.execute(text("SELECT nextval('app_data_version')"))
    assert fresh.get_or_set("k", 60, compute) == 2


def test_concurrent_requests_share_one_computation(fresh):
    import threading, time

    calls = []

    def slow():
        calls.append(1)
        time.sleep(0.2)
        return "done"

    results = []
    threads = [threading.Thread(target=lambda: results.append(fresh.get_or_set("k", 60, slow))) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == ["done"] * 8 and len(calls) == 1


def test_marking_an_order_shows_up_in_the_cached_dashboard_and_store_list_at_once(client, admin, make_store, db):
    store = make_store(code="CACHE-1", platform="zepto", region=None, state="Testland-C")
    today = date.today().isoformat()

    def insights():
        return client.get(f"{API}/orders/insights", headers=admin).json()

    def my(code):
        return next(s for s in client.get(f"{API}/orders/my-stores", headers=admin).json() if s["external_code"] == code)

    before = insights()["bottles_today"]
    assert my("CACHE-1")["today_count"] is None
    assert client.post(f"{API}/orders/mark", headers=admin, json={"store_id": str(store.id), "order_date": today, "bottle_count": 17}).status_code == 200
    assert insights()["bottles_today"] == before + 17        # not the stale cached number
    assert my("CACHE-1")["today_count"] == 17

    # Correcting it later is also reflected straight away.
    assert client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(store.id), "order_date": today, "bottle_count": 5}).status_code == 200
    assert insights()["bottles_today"] == before + 5
    assert my("CACHE-1")["today_count"] == 5


def test_all_stores_comes_in_one_request_and_follows_store_edits(client, admin, make_store):
    make_store(code="ALL-1", platform="zepto", region=None, state="Testland-A")
    r = client.get(f"{API}/stores/all", headers=admin)
    assert r.status_code == 200
    codes = {s["external_code"] for s in r.json()}
    assert {"ALL-1", "BLK-4821", "ZEP-1187"} <= codes                      # new store + the seeded demo stores, in one response
    assert client.get(f"{API}/stores/all").status_code == 401

    sid = next(s["id"] for s in r.json() if s["external_code"] == "ALL-1")
    assert client.patch(f"{API}/stores/{sid}", headers=admin, json={"city": "Cachetown"}).status_code == 200
    again = next(s for s in client.get(f"{API}/stores/all", headers=admin).json() if s["id"] == sid)
    assert again["city"] == "Cachetown"                                  # the edit invalidated the shared copy


def test_big_cached_lists_are_served_pre_compressed_and_identical_either_way(client, admin, make_store):
    make_store(code="GZ-1", platform="blinkit", region="NORTH", state="Testland-G")
    for path in ("/orders/my-stores", "/stores/all", "/orders/inventory"):
        plain = client.get(f"{API}{path}", headers={**admin, "Accept-Encoding": "identity"})
        zipped = client.get(f"{API}{path}", headers={**admin, "Accept-Encoding": "gzip"})
        assert plain.status_code == zipped.status_code == 200, path
        assert "content-encoding" not in plain.headers
        assert zipped.headers.get("content-encoding") == "gzip" and zipped.headers["vary"].lower() == "accept-encoding"
        assert plain.json() == zipped.json()                                  # httpx inflates the gzip body for us


def test_employees_cannot_get_the_admin_lists_even_if_an_admin_just_cached_them(client, admin, emp):
    client.get(f"{API}/orders/my-stores", headers=admin)                       # primes the shared admin copy
    mine = client.get(f"{API}/orders/my-stores", headers=emp).json()
    admin_all = client.get(f"{API}/orders/my-stores", headers=admin).json()
    assert len(mine) < len(admin_all) or len(admin_all) <= 1                   # an employee only ever sees their own stores
    assert client.get(f"{API}/stores/all", headers=emp).status_code == 403     # stores.view is not granted to employees by default
