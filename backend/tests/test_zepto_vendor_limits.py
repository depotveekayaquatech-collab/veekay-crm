"""Zepto vendor performance and capping usage carry the numbers behind the copy-paste message: capping, monthly limit, supplied till date and the pending limit."""
from app.services import capping_history_service as hist
from app.services import capping_service as cs

from .conftest import API, plant_entry


def _cap(client, admin, store, n):
    assert client.post(f"{API}/capping/change", json={"storeId": str(store.id), "capping": n}, headers=admin).status_code == 201


def _vendors(client, admin, partner):
    r = client.get(f"{API}/orders/performance/vendors", params={"partner": partner, "month": f"{hist.today_ist():%Y-%m}"}, headers=admin)
    assert r.status_code == 200, r.text
    return {v["vendor_name"]: v for v in r.json()["vendors"]}


def test_a_zepto_vendor_store_shows_its_limit_what_was_supplied_and_what_is_pending(client, admin, make_store, db):
    today = hist.today_ist()
    a = make_store(platform="zepto", region=None, state="Karnataka", vendor="Zl Aqua Vendor", name="Zl Store One")
    b = make_store(platform="zepto", region=None, state="Karnataka", vendor="Zl Aqua Vendor", name="Zl Store Two")
    c = make_store(platform="zepto", region=None, state="Karnataka", vendor="Zl Aqua Vendor", name="Zl Store No Cap")
    _cap(client, admin, a, 10)
    _cap(client, admin, b, 2)
    plant_entry(db, a, today, 120)
    d = cs.days_in_month(today.replace(day=1))
    plant_entry(db, b, today, 2 * d + 10)                          # ten more than 2 x the month's days
    plant_entry(db, c, today, 5)

    stores = {s["store_name"]: s for s in _vendors(client, admin, "zepto")["Zl Aqua Vendor"]["stores"]}
    one = stores["Zl Store One"]
    assert (one["daily_cap"], one["monthly_limit"], one["bottles"], one["pending"], one["over_by"]) == (10, 10 * d, 120, 10 * d - 120, 0)
    two = stores["Zl Store Two"]
    assert (two["monthly_limit"], two["bottles"], two["pending"], two["over_by"]) == (2 * d, 2 * d + 10, 0, 10)       # used up: pending stops at 0
    nocap = stores["Zl Store No Cap"]
    assert nocap["daily_cap"] is None and nocap["monthly_limit"] is None and nocap["pending"] is None and nocap["bottles"] == 5


def test_other_platforms_have_no_limit_figures(client, admin, make_store, db):
    store = make_store(vendor="Zl Blinkit Vendor", name="Zl Blinkit Store")
    plant_entry(db, store, hist.today_ist(), 7)
    s = _vendors(client, admin, "blinkit")["Zl Blinkit Vendor"]["stores"][0]
    assert s["monthly_limit"] is None and s["pending"] is None and s["bottles"] == 7


def test_the_capping_usage_rows_name_the_vendor(client, admin, make_store, db):
    store = make_store(platform="zepto", region=None, state="Karnataka", vendor="  Zl   Usage Vendor ", name="Zl Usage Store")
    _cap(client, admin, store, 4)
    r = client.get(f"{API}/capping/usage", headers=admin)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["rows"] if x["store_id"] == str(store.id))
    assert row["vendor_name"] == "Zl Usage Vendor" and row["monthly_cap"] == 120
