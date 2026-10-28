"""Zepto capping: setting and removing a store's capping (no dates to choose), its history, the list with each store's actual entry start date, and the
"Reduce capping" alert on the collective averages."""
import uuid
from datetime import date, timedelta

import pytest

from app.models.capping_history import CappingHistory
from app.models.store_cap import StoreCap
from app.services import capping_history_service as svc

from .conftest import API, plant_entry


@pytest.fixture()
def zstore(make_store):
    return make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")


@pytest.fixture(autouse=True)
def _forget_history(db):
    """Rows of the stores a test made go with the stores (cascade); the seeded Zepto stores keep none."""
    yield
    db.rollback()


def _today():
    return svc.today_ist()


def _change(client, headers, store, capping):
    return client.post(f"{API}/capping/change", json={"storeId": str(store.id), "capping": capping}, headers=headers)


def _remove(client, headers, store):
    return client.post(f"{API}/capping/remove", json={"storeId": str(store.id)}, headers=headers)


def _seed(db, store, *rows):
    for eff, cap in rows:
        db.add(CappingHistory(store_id=store.id, capping=cap, effective_from=eff))
    db.commit()


def _rows(db, store):
    db.expire_all()
    return sorted((r.effective_from, r.capping) for r in db.query(CappingHistory).filter_by(store_id=store.id))


def _listed(client, headers, store):
    return next(r for r in client.get(f"{API}/capping", headers=headers).json()["rows"] if r["store_id"] == str(store.id))


# ---------------------------------------------------------------- the rule (pure)

def test_the_capping_on_a_day_is_the_one_with_the_greatest_effective_from_on_or_before_it():
    h = [(date(2026, 10, 1), 10), (date(2026, 10, 15), 11)]
    assert svc.effective_capping(h, date(2026, 9, 30)) is None
    assert [svc.effective_capping(h, date(2026, 10, d)) for d in (1, 14, 15, 31)] == [10, 10, 11, 11]


# ---------------------------------------------------------------- setting a capping

def test_a_change_applies_from_today_and_a_second_change_the_same_day_corrects_it(client, admin, zstore, db):
    today = _today()
    first = _change(client, admin, zstore, 10)
    assert first.status_code == 201, first.text
    assert first.json()["capping"] == 10 and first.json()["current_capping"] == 10 and first.json()["effective_from"] == today.isoformat()
    assert db.query(StoreCap).filter_by(store_id=zstore.id).one().daily_cap == 10                    # the old field is kept in step
    again = _change(client, admin, zstore, 12)                                                       # a correction on the same day: the same row, not a second one
    assert again.status_code == 201 and again.json()["current_capping"] == 12
    assert _rows(db, zstore) == [(today, 12)]
    h = client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=admin).json()
    assert [r["capping"] for r in h["rows"]] == [12] and h["rows"][0]["changed_by"] and h["rows"][0]["created_at"]


def test_a_later_change_is_a_new_row_and_the_earlier_capping_stays_on_record(client, admin, zstore, db):
    today = _today()
    _seed(db, zstore, (today - timedelta(days=9), 10))
    assert _change(client, admin, zstore, 11).status_code == 201
    assert _rows(db, zstore) == [(today - timedelta(days=9), 10), (today, 11)]
    h = client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=admin).json()
    assert [r["capping"] for r in h["rows"]] == [11, 10]                                             # newest first
    assert _listed(client, admin, zstore)["capping"] == 11


def test_the_first_capping_of_a_store_starts_on_the_day_its_entries_started(client, admin, make_store, db):
    from app.models.store import Store

    today = _today()
    with_start = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    db.query(Store).filter_by(id=with_start.id).update({"start_date": today - timedelta(days=9)})
    from_entries = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    plant_entry(db, from_entries, today - timedelta(days=6), 0)                                      # a zero is not supply
    plant_entry(db, from_entries, today - timedelta(days=5), 8)
    never_supplied = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    db.commit()

    assert _change(client, admin, with_start, 10).json()["effective_from"] == (today - timedelta(days=9)).isoformat()      # its start date
    assert _change(client, admin, from_entries, 10).json()["effective_from"] == (today - timedelta(days=5)).isoformat()    # its first day with bottles
    assert _change(client, admin, never_supplied, 10).json()["effective_from"] == today.isoformat()                         # nothing yet: today
    assert _change(client, admin, with_start, 12).json()["effective_from"] == today.isoformat()                            # a later change applies from today
    assert _rows(db, with_start) == [(today - timedelta(days=9), 10), (today, 12)]


@pytest.mark.parametrize("capping", [0, -3, 1.5, "7", True, None])
def test_the_capping_must_be_a_whole_number_of_at_least_one(client, admin, zstore, capping):
    r = client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": capping}, headers=admin)
    assert r.status_code == 422


def test_a_start_date_cannot_be_sent_any_more(client, admin, zstore):
    r = client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": 10, "effectiveFrom": _today().isoformat()}, headers=admin)
    assert r.status_code == 422


def test_a_store_of_another_platform_is_not_found(client, admin, make_store):
    blinkit = make_store(platform="blinkit")
    assert _change(client, admin, blinkit, 10).status_code == 404
    assert _remove(client, admin, blinkit).status_code == 404


def test_only_someone_holding_capping_change_may_change_and_everyone_who_sees_capping_may_view(client, zepto_emp, emp, admin, zstore, make_user):
    assert _change(client, zepto_emp, zstore, 10).status_code == 403                              # a Zepto employee can view, not change
    assert _change(client, emp, zstore, 10).status_code == 403
    assert _remove(client, zepto_emp, zstore).status_code == 403
    assert client.post(f"{API}/capping/change", json={}).status_code in (401, 403)
    assert client.get(f"{API}/capping", headers=zepto_emp).status_code == 200
    assert client.get(f"{API}/capping", headers=emp).status_code == 403                            # a Blinkit employee sees no Zepto capping
    assert client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=zepto_emp).status_code == 200

    from .conftest import auth, login
    code, pw, _ = make_user("employee", platform="zepto", grants=("orders.view", "capping.change"))   # ticked for one person, like a manager
    ticked = auth(login(client, code, pw).json()["access_token"])
    assert _change(client, ticked, zstore, 10).status_code == 201


def test_the_admin_role_holds_the_permission(db):
    from app.models.permission import Permission, RolePermission
    from app.models.role import Role

    n = (db.query(RolePermission).join(Role, Role.id == RolePermission.role_id).join(Permission, Permission.id == RolePermission.permission_id)
         .filter(Role.code == "admin", Permission.code == "capping.change").count())
    assert n == 1


def test_there_is_no_way_to_edit_or_delete_a_history_row(client, admin, zstore):
    row = _change(client, admin, zstore, 10).json()
    for method in ("put", "patch", "delete"):
        for url in (f"{API}/capping/change", f"{API}/capping/history", f"{API}/capping/history/{row['id']}", f"{API}/capping/change/{row['id']}"):
            assert getattr(client, method)(url, headers=admin).status_code in (404, 405), (method, url)


# ---------------------------------------------------------------- removing a capping

def test_a_capping_can_be_removed_and_the_record_keeps_what_it_was(client, admin, zepto_emp, zstore, db):
    today = _today()
    _seed(db, zstore, (today - timedelta(days=9), 10), (today - timedelta(days=4), 12))
    db.add(StoreCap(store_id=zstore.id, daily_cap=12, source="manual"))
    db.commit()

    gone = _remove(client, admin, zstore)
    assert gone.status_code == 201, gone.text
    assert gone.json()["capping"] is None and gone.json()["current_capping"] is None
    db.expire_all()
    assert db.query(StoreCap).filter_by(store_id=zstore.id).count() == 0                          # the store has no current capping now
    assert _rows(db, zstore) == [(today - timedelta(days=9), 10), (today - timedelta(days=4), 12), (today, None)]    # the earlier cappings are still on record
    assert _listed(client, admin, zstore)["capping"] is None
    h = client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=admin).json()
    assert [r["capping"] for r in h["rows"]] == [None, 12, 10]                                    # newest first: the removal, then what it replaced

    assert _remove(client, admin, zstore).status_code == 422                                      # nothing left to remove
    assert _change(client, admin, zstore, 9).status_code == 201                                   # setting one again the same day replaces the removal
    assert _rows(db, zstore)[-1] == (today, 9) and _listed(client, admin, zstore)["capping"] == 9


def test_a_store_that_never_had_a_capping_has_nothing_to_remove(client, admin, zstore):
    assert _remove(client, admin, zstore).status_code == 422


# ---------------------------------------------------------------- the list shows each store's actual entry start date

def test_the_list_shows_the_latest_capping_and_no_start_dates(client, admin, zstore, db):
    today = _today()
    plant_entry(db, zstore, today - timedelta(days=4), 6)
    _seed(db, zstore, (today - timedelta(days=4), 10), (today - timedelta(days=1), 11))
    row = _listed(client, admin, zstore)
    assert row["capping"] == 11
    assert "start_date" not in row and "since" not in row                                           # a store's start date is shown in the store's details, not here
    assert client.get(f"{API}/capping", headers=admin).json()["without_capping"] >= 0


# ---------------------------------------------------------------- the "Reduce capping" alert (collective averages)

def test_the_alert_rules_are_on_the_two_collective_averages():
    # a limit of 11: average entry 12.0 -> alert; exactly 11 -> not; the capping average can raise it alone; nothing to average -> no alert
    assert svc.assess(120, 10, 11)["alert"] is True and svc.assess(120, 10, 11)["reasons"] == ["average"]
    assert svc.assess(110, 10, 11)["alert"] is False
    assert svc.assess(50, 10, 11, capping_total=125, capping_days=10)["reasons"] == ["capping"]
    assert svc.assess(0, 0, 11)["alert"] is False and svc.assess(0, 0, 11)["status"] == "none"
    assert svc.assess(105, 10, 11)["status"] == "warn"                                             # within the margin of the limit


def test_the_capping_average_counts_only_store_days_with_a_capping_in_force_and_stops_at_a_removal():
    d = lambda n: date(2026, 10, n)  # noqa: E731
    history = [(d(5), 12), (d(10), None), (d(20), 8)]                                              # 12 from the 5th, removed on the 10th, 8 from the 20th
    assert svc.capping_totals(history, d(1), d(31)) == (12 * 5 + 8 * 12, 17)                       # days 5-9 and 20-31 only
    assert svc.capping_totals(history, d(1), d(4)) == (0, 0)
    assert svc.capping_totals(history, d(12), d(15)) == (0, 0)


def test_the_alert_measures_a_stores_capping_from_the_day_its_entries_started(client, admin, zepto_emp, emp, make_store, db):
    from app.models.store import Store

    today = _today()
    first = today.replace(day=1)
    if today.day < 6:
        return
    started = first + timedelta(days=2)                                                             # supplied from the 3rd
    a = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    db.query(Store).filter_by(id=a.id).update({"start_date": started})
    plant_entry(db, a, started, 5)
    db.commit()
    base = client.get(f"{API}/capping/alert", headers=admin).json()["overall"]
    assert _change(client, admin, a, 90).status_code == 201                                         # a very high capping, set today: it counts from the 3rd, not from today
    o = client.get(f"{API}/capping/alert", headers=admin).json()
    days = (today - started).days + 1
    assert o["overall"]["capping_days"] == base["capping_days"] + days
    assert o["limit"] == 11 and o["from"] == first.isoformat()
    assert o["overall"]["capping_breach"] is (o["overall"]["capping_average"] > 11) and o["overall"]["alert"] is (o["overall"]["entry_breach"] or o["overall"]["capping_breach"])
    assert client.get(f"{API}/capping/alert", headers=zepto_emp).status_code == 200                # whoever may see Zepto capping
    assert client.get(f"{API}/capping/alert", headers=emp).status_code == 403                      # a Blinkit employee may not
    assert client.get(f"{API}/capping/alert", params={"from": "2026-10-05", "to": "2026-10-01"}, headers=admin).status_code == 422


def test_a_store_that_was_never_supplied_adds_no_capping_days(client, admin, zstore, db):
    before = client.get(f"{API}/capping/alert", headers=admin).json()["overall"]["capping_days"]
    assert _change(client, admin, zstore, 10).status_code == 201                                   # capping set, but no entry has ever started
    assert client.get(f"{API}/capping/alert", headers=admin).json()["overall"]["capping_days"] == before
