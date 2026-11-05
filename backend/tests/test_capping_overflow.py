"""Zepto capping overflow: the stores over their capping (month and day by day), the stores with room left, and that looking changes nothing."""
from datetime import date, timedelta

from sqlalchemy import func, select

from app.models.order_entry import OrderEntry
from app.services import capping_history_service as hist
from app.services import capping_service as cs
from app.services.capping_overflow_service import over_days

from .conftest import API, plant_entry


def _cap(client, admin, store, n):
    assert client.post(f"{API}/capping/change", json={"storeId": str(store.id), "capping": n}, headers=admin).status_code == 201


def _overflow(client, headers, month=None):
    r = client.get(f"{API}/capping/overflow", params={"month": month} if month else {}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _row(body, store):
    return next((x for x in body["rows"] if x["store_id"] == str(store.id)), None)


def test_a_day_is_over_only_against_the_capping_in_force_that_day():
    days = [(date(2026, 10, 3), 12), (date(2026, 10, 10), 12), (date(2026, 10, 20), 12), (date(2026, 10, 21), 0)]
    changed = [(date(2026, 10, 1), 10), (date(2026, 10, 15), 15)]                 # 10 until the 14th, 15 from the 15th
    late = over_days(days, changed, legacy=None)
    assert [d["date"] for d in late] == [date(2026, 10, 3), date(2026, 10, 10)]    # 12 is fine once the capping is 15
    assert late[0] == {"date": date(2026, 10, 3), "bottles": 12, "cap": 10, "over_by": 2}
    assert over_days(days, [(date(2026, 10, 1), None)], legacy=5) == []             # a removed capping can never be exceeded
    assert [d["over_by"] for d in over_days(days, [], legacy=10)] == [2, 2, 2]      # no history: the current capping
    assert over_days(days, [], legacy=None) == []


def test_the_overflow_lists_stores_over_and_stores_with_room(client, admin, make_store, db):
    today = hist.today_ist()
    if today.day < 3:
        return
    first = today.replace(day=1)
    over = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    roomy = make_store(platform="zepto", region=None, state="Karnataka", city="Mysuru")
    d = cs.days_in_month(first)
    plant_entry(db, over, first, 40)                                                # cap 1 -> limit d: 40 - d over for the month, 39 over on the day
    plant_entry(db, roomy, first, 6)
    plant_entry(db, roomy, first + timedelta(days=1), 15)                           # cap 10 -> 5 over on one day, but 10 x d - 21 left
    _cap(client, admin, over, 1)
    _cap(client, admin, roomy, 10)
    body = _overflow(client, admin)
    a, b = _row(body, over), _row(body, roomy)
    assert (a["monthly_cap"], a["used"], a["excess"], a["room"]) == (d, 40, 40 - d, 0)
    assert (a["days_over"], a["daily_excess"]) == (1, 39) and a["over_days"][0]["date"] == first.isoformat()
    assert (b["monthly_cap"], b["used"], b["excess"], b["room"]) == (10 * d, 21, 0, 10 * d - 21)
    assert (b["days_over"], b["daily_excess"]) == (1, 5)
    s = body["summary"]
    assert s["stores_over_month"] >= 1 and s["month_excess"] >= 40 - d and s["stores_with_room"] >= 1 and s["room"] >= 10 * d - 21
    assert body["rows"][0]["excess"] >= body["rows"][-1]["excess"]                  # worst first


def test_a_store_with_no_capping_and_one_with_no_entries_are_handled(client, admin, make_store, db):
    today = hist.today_ist()
    nocap = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    quiet = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    plant_entry(db, nocap, today.replace(day=1), 500)
    _cap(client, admin, quiet, 8)
    body = _overflow(client, admin)
    assert _row(body, nocap) is None                                                # no capping: nothing to be over, no room to speak of
    q = _row(body, quiet)
    assert q["used"] == 0 and q["excess"] == 0 and q["room"] == 8 * cs.days_in_month(hist.today_ist().replace(day=1)) and q["days_over"] == 0


def test_looking_at_the_overflow_changes_no_entry(client, admin, make_store, db):
    today = hist.today_ist()
    store = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    plant_entry(db, store, today.replace(day=1), 99)
    _cap(client, admin, store, 1)
    before = db.execute(select(func.count(OrderEntry.id), func.coalesce(func.sum(OrderEntry.bottle_count), 0))).one()
    _overflow(client, admin)
    db.expire_all()
    assert db.execute(select(func.count(OrderEntry.id), func.coalesce(func.sum(OrderEntry.bottle_count), 0))).one() == before
    assert client.post(f"{API}/capping/overflow", headers=admin).status_code == 405   # there is no write route at all


# ---------------------------------------------------------------- a finished month is read against the capping it had then

def _history(db, store, *rows):
    from app.models.capping_history import CappingHistory
    for eff, cap in rows:
        db.add(CappingHistory(store_id=store.id, capping=cap, effective_from=eff))
    db.commit()


def test_the_capping_list_for_a_month_shows_the_capping_of_that_month(client, admin, make_store, db):
    today = hist.today_ist()
    this = today.replace(day=1)
    last_end = this - timedelta(days=1)
    last_first = last_end.replace(day=1)
    store = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    _history(db, store, (last_first - timedelta(days=40), 10), (last_first + timedelta(days=14), 12), (this + timedelta(days=0), 15))
    now = next(r for r in client.get(f"{API}/capping", headers=admin).json()["rows"] if r["store_id"] == str(store.id))
    assert now["capping"] == 15 and now["start_capping"] == 15
    r = client.get(f"{API}/capping", params={"month": f"{last_end:%Y-%m}"}, headers=admin)
    assert r.status_code == 200 and r.json()["is_current"] is False and r.json()["month"] == f"{last_end:%Y-%m}"
    row = next(x for x in r.json()["rows"] if x["store_id"] == str(store.id))
    assert (row["start_capping"], row["capping"]) == (10, 12)                         # 10 at the start of the month, 12 by its last day
    assert client.get(f"{API}/capping", params={"month": "2999-01"}, headers=admin).status_code == 422


def test_usage_and_overflow_of_a_finished_month_use_the_capping_it_had(client, admin, make_store, db):
    today = hist.today_ist()
    last_end = today.replace(day=1) - timedelta(days=1)
    last_first = last_end.replace(day=1)
    store = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    _history(db, store, (last_first - timedelta(days=40), 10), (today.replace(day=1), 20))   # 10 all last month, 20 from this month
    plant_entry(db, store, last_first, 25)
    month = f"{last_end:%Y-%m}"
    usage = next(x for x in client.get(f"{API}/capping/usage", params={"month": month}, headers=admin).json()["rows"] if x["store_id"] == str(store.id))
    dim = cs.days_in_month(last_first)
    assert usage["daily_cap"] == 10 and usage["monthly_cap"] == 10 * dim              # not today's 20, and last month's own number of days
    row = _row(_overflow(client, admin, month), store)
    assert row["days_over"] == 1 and row["over_days"][0]["cap"] == 10 and row["room"] == 10 * dim - 25
    alert = client.get(f"{API}/capping/alert", params={"from": last_first.isoformat(), "to": last_end.isoformat()}, headers=admin)
    assert alert.status_code == 200 and alert.json()["to"] == last_end.isoformat()   # the alert can be asked for a finished month
