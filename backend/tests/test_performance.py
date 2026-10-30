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


def test_someone_with_no_store_who_made_entries_is_listed_with_how_many(client, db, admin, make_user, make_store):
    from .conftest import plant_entry

    store = make_store(platform="blinkit", region="NORTH", state="Perf-Land")
    _, _, helper = make_user(platform="blinkit", region="SOUTH", grants=("orders.view", "orders.mark"))    # no store in SOUTH of their own
    _, _, idle = make_user(platform="blinkit", region="SOUTH", grants=("orders.view", "orders.mark"))      # no store, no entries
    first = TODAY.replace(day=1)
    plant_entry(db, store, first, 7, creator=helper)
    if TODAY.day > 1:
        plant_entry(db, store, first + timedelta(days=1), 3, creator=helper)

    r = client.get(f"{API}/orders/performance", params={"partner": "blinkit", "month": first.strftime("%Y-%m")}, headers=admin)
    assert r.status_code == 200, r.text
    got = {e["employee_id"]: e for e in r.json()["employees"]}
    assert str(idle) not in got                                                  # still hidden when they entered nothing
    me = got[str(helper)]
    assert me["no_stores"] is True and me["stores"] == 0 and me["entries_made"] == (2 if TODAY.day > 1 else 1)
    assert me["expected"] == 0 and me["done"] == 0 and me["daily"] == []
    assert r.json()["employees"][-1]["employee_id"] in {k for k, v in got.items() if v["no_stores"]}   # listed after everyone who has stores
    assert r.json()["summary"]["employees"] == sum(1 for e in got.values() if not e["no_stores"])      # and not counted in the summary


def test_the_platform_overall_counts_each_store_day_once_whoever_entered_it(client, db, admin, make_user, make_store):
    from .conftest import plant_entry

    if TODAY.day < 3:
        return                                                   # needs a finished day in the month
    store = make_store(platform="blinkit", region="NORTH", state="Perf-Land")
    _, _, helper = make_user(platform="blinkit", region="SOUTH", grants=("orders.view", "orders.mark"))        # no store of their own
    _, _, owner = make_user(platform="blinkit", region="NORTH", grants=("orders.view", "orders.mark"))
    day = TODAY.replace(day=1)

    def summary():
        r = client.get(f"{API}/orders/performance", params={"partner": "blinkit", "month": TODAY.strftime("%Y-%m")}, headers=admin)
        assert r.status_code == 200, r.text
        return r.json()["summary"]

    base = summary()
    assert 0 < base["expected"] <= base["stores"] * (TODAY - timedelta(days=1)).day      # every live store on every finished day (holidays included: they are attendance's business)
    plant_entry(db, store, day, 8, creator=helper)               # entered by someone with no store of their own: it still counts, once
    assert summary()["done"] == base["done"] + 1
    assert summary()["expected"] == base["expected"]


def test_a_team_lead_shows_how_many_entries_they_corrected(client, db, admin, make_user, make_store):
    from app.models.role import Role
    from app.models.user import User, UserRole

    store = make_store(platform="blinkit", region="NORTH", state="Perf-Land")
    _, _, lead = make_user(platform="blinkit", region="SOUTH", grants=("orders.view", "orders.mark"))       # no store of their own
    db.add(UserRole(user_id=lead, role_id=db.query(Role).filter_by(code="team_lead").one().id))
    code, pw, member = make_user(platform="blinkit", region="NORTH", grants=("orders.view", "orders.mark"))
    db.query(User).filter(User.id == member).update({"reports_to_user_id": lead})
    db.commit()
    lead_code = db.query(User).filter(User.id == lead).one().employee_code
    emp = auth(login(client, code, pw).json()["access_token"])
    boss = auth(login(client, lead_code, "Pass@123").json()["access_token"])

    other = make_store(platform="blinkit", region="NORTH", state="Perf-Land")
    for st in (store, other):
        r = client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(st.id), "order_date": TODAY.isoformat(), "bottle_count": 11})
        assert r.status_code == 200, r.text
    for item in client.get(f"{API}/entries/search", headers=boss).json()["items"]:                       # the Team Lead corrects both entries
        c = client.patch(f"{API}/entries/{item['entry_id']}", headers=boss, json={"bottle_count": 14, "reason": "delivery note", "expected_version": 1})
        assert c.status_code == 200, c.text

    rows = {e["employee_id"]: e for e in client.get(f"{API}/orders/performance", params={"partner": "blinkit", "month": TODAY.strftime("%Y-%m")}, headers=admin).json()["employees"]}
    assert rows[str(lead)]["corrected"] == 2 and rows[str(lead)]["is_team_lead"] is True and rows[str(lead)]["no_stores"] is True   # listed for the corrections alone
    assert rows[str(member)]["corrected"] == 0 and rows[str(member)]["is_team_lead"] is False and rows[str(member)]["entries_made"] == 2


def test_an_entry_dated_on_a_holiday_counts_like_any_other(client, db, admin, make_user, make_store):
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
        on_holiday = next(d for d in mine["daily"] if d["date"] == holiday.isoformat())        # the holiday is a judged day like any other...
        assert on_holiday["done"] >= 1 and on_holiday["expected"] == mine["stores"]            # ...and the entry made on it counts
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


def test_an_employee_sees_only_the_vendors_of_their_own_stores_and_only_themselves_in_the_employee_performance(client, db, admin, make_user, make_store):
    from .conftest import plant_entry

    code, pw, uid = make_user(platform="blinkit", region="NORTH", grants=("orders.view", "orders.mark"))
    emp = auth(login(client, code, pw).json()["access_token"])
    mine = make_store(region="NORTH", vendor="Near Aqua Vendor", name="Near Store")
    far = make_store(region="SOUTH", vendor="Far Aqua Vendor", name="Far Store")
    plant_entry(db, mine, TODAY, 9, cash_adjustment=4)                      # 9 entered, a developer's 4 on top
    plant_entry(db, far, TODAY, 6)

    r = client.get(f"{API}/orders/performance/vendors", params={"partner": "blinkit", "month": TODAY.strftime("%Y-%m")}, headers=emp)
    assert r.status_code == 200, r.text
    got = {v["vendor_name"]: v for v in r.json()["vendors"]}
    assert "Near Aqua Vendor" in got and "Far Aqua Vendor" not in got        # only the stores in their scope
    assert got["Near Aqua Vendor"]["bottles"] == 9                           # never the developer's adjustment
    assert [s["store_name"] for s in got["Near Aqua Vendor"]["stores"]] == ["Near Store"]
    # the administrator sees the whole platform, adjustment included, as the other pages do
    full = _vendors(client, admin)
    assert "Far Aqua Vendor" in full and full["Near Aqua Vendor"]["bottles"] == 13
    # and the employee-by-employee performance shows only themselves, never a colleague
    own = client.get(f"{API}/orders/performance", params={"partner": "blinkit"}, headers=emp)
    assert own.status_code == 200 and own.json()["view"] == "self" and [e["employee_id"] for e in own.json()["employees"]] == [str(uid)]


def test_a_platform_login_is_not_shown_the_vendors(client, db, make_user):
    code, pw, uid = make_user(role="partner", platform="blinkit", grants=("orders.view",))
    who = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/orders/performance/vendors", params={"partner": "blinkit"}, headers=who).status_code == 403


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
