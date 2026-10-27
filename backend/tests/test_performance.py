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


def _vendors(client, admin, **params):
    r = client.get(f"{API}/orders/performance/vendors", params={"partner": "blinkit", "month": TODAY.strftime("%Y-%m"), **params}, headers=admin)
    assert r.status_code == 200, r.text
    return {v["vendor_name"]: v for v in r.json()["vendors"]}


def test_vendor_wise_lists_each_vendors_stores_with_their_bottles(client, db, admin, make_store):
    from .conftest import plant_entry

    a = make_store(vendor="Zed Aqua Vendor", name="Zed Store One")
    b = make_store(vendor="  zed aqua   vendor ", name="Zed Store Two")        # the same vendor, typed differently
    c = make_store(vendor="Solo Vendor Co", name="Solo Store")
    quiet = make_store(vendor="Zed Aqua Vendor", name="Zed Store Quiet")       # live, nothing marked yet
    plant_entry(db, a, TODAY, 12)
    plant_entry(db, b, TODAY, 8)
    plant_entry(db, c, TODAY, 5)

    got = _vendors(client, admin)
    zed = got["Zed Aqua Vendor"]
    assert zed["store_count"] == 3 and zed["bottles"] == 20
    assert [(s["store_name"], s["bottles"]) for s in zed["stores"]] == [("Zed Store One", 12), ("Zed Store Two", 8), ("Zed Store Quiet", 0)]
    solo = got["Solo Vendor Co"]
    assert solo["store_count"] == 1 and solo["bottles"] == 5 and solo["stores"][0]["store_name"] == "Solo Store" and solo["stores"][0]["bottles"] == 5

    assert client.get(f"{API}/orders/performance/vendors", params={"partner": "nope"}, headers=admin).status_code == 404
    emp = client.get(f"{API}/orders/performance/vendors", params={"partner": "blinkit"})
    assert emp.status_code in (401, 403)


def test_vendor_wise_splits_a_store_that_changed_vendor_by_the_dates_each_supplied_it(client, db, admin, make_store):
    from datetime import timedelta
    from app.models.store_vendor_period import StoreVendorPeriod
    from .conftest import plant_entry

    if TODAY.day < 2:
        return                                          # needs yesterday in the same month
    yesterday = TODAY - timedelta(days=1)
    s = make_store(vendor="New Switch Vendor", name="Switch Store")
    db.add(StoreVendorPeriod(store_id=s.id, vendor_name="Old Switch Vendor", start_date=None, end_date=yesterday))
    db.add(StoreVendorPeriod(store_id=s.id, vendor_name="New Switch Vendor", start_date=TODAY, end_date=None))
    db.commit()
    plant_entry(db, s, yesterday, 5)
    plant_entry(db, s, TODAY, 7)

    got = _vendors(client, admin)
    assert got["Old Switch Vendor"]["bottles"] == 5 and got["Old Switch Vendor"]["stores"][0]["store_name"] == "Switch Store"
    assert got["New Switch Vendor"]["bottles"] == 7
    db.query(StoreVendorPeriod).filter(StoreVendorPeriod.store_id == s.id).delete()
    db.commit()


def test_month_parsing_defaults_to_the_month_of_yesterday():
    assert performance_service.parse_month(None, date(2026, 11, 1)) == date(2026, 10, 1)
    assert performance_service.parse_month(None, date(2026, 11, 2)) == date(2026, 11, 1)
    assert performance_service.parse_month("2026-03", date(2026, 11, 2)) == date(2026, 3, 1)
