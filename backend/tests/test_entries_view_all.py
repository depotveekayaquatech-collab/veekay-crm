"""entries.view_all: a Level 1 Zepto employee who marks like anyone else (same store scope, one entry per store and day, no corrections) but can SEE every
entry of the stores she can reach, in the order calendar and in the month's bottles."""
from datetime import date

from app.models.organization import Organization
from app.models.employee_scope import EmployeeExclusion

from .conftest import API, auth, login

TODAY = date.today()
STATE = "Viewland"


def _scoped(client, db, make_user, *grants):
    """A Zepto employee who covers STATE (added by hand, so several people can share it) and holds the given extra permissions."""
    code, pw, uid = make_user("employee", platform="zepto", grants=("orders.view", "orders.mark", *grants))
    db.add(EmployeeExclusion(user_id=uid, kind="state", mode="add", value=STATE.lower(), label=STATE))
    db.commit()
    return auth(login(client, code, pw).json()["access_token"])


def _mark(client, who, store, n):
    return client.post(f"{API}/orders/mark", headers=who, json={"store_id": str(store.id), "order_date": TODAY.isoformat(), "bottle_count": n})


def _day(client, who, store):
    r = client.get(f"{API}/orders/calendar", params={"store_id": str(store.id), "year": TODAY.year, "month": TODAY.month}, headers=who)
    assert r.status_code == 200, r.text
    return next(d for d in r.json()["days"] if d["day"] == TODAY.day)


def test_a_view_all_employee_sees_a_colleagues_number_and_a_plain_one_does_not(client, db, make_user, make_store):
    a, b = (make_store(platform="zepto", region=None, state=STATE, city="Viewville") for _ in range(2))
    marker = _scoped(client, db, make_user)
    viewer = _scoped(client, db, make_user, "entries.view_all")
    plain = _scoped(client, db, make_user)
    assert _mark(client, marker, a, 7).status_code == 200

    seen = _day(client, viewer, a)
    assert seen["marked"] and not seen["masked"] and seen["count"] == 7 and seen["mine"] is False        # she sees the colleague's number
    hidden = _day(client, plain, a)
    assert hidden["marked"] and hidden["masked"] and hidden["count"] is None                              # an ordinary Level 1 employee does not

    # she marks like any Level 1 employee: another store of her scope, and the response already shows what she may see
    r = _mark(client, viewer, b, 5)
    assert r.status_code == 200, r.text
    assert next(d for d in r.json()["days"] if d["day"] == TODAY.day)["count"] == 5
    assert _mark(client, viewer, a, 9).status_code == 409                                                   # an already-marked day stays closed to her too


def test_a_view_all_employee_still_cannot_correct_or_reach_stores_outside_her_scope(client, db, make_user, make_store):
    a = make_store(platform="zepto", region=None, state=STATE, city="Viewville")
    outside = make_store(platform="zepto", region=None, state="Elsewhere", city="Nowhere")
    marker = _scoped(client, db, make_user)
    viewer = _scoped(client, db, make_user, "entries.view_all")
    assert _mark(client, marker, a, 7).status_code == 200
    fix = client.patch(f"{API}/orders/entry", headers=viewer, json={"store_id": str(a.id), "order_date": TODAY.isoformat(), "bottle_count": 1})
    assert fix.status_code == 403                                                                           # no corrections
    assert _mark(client, viewer, outside, 3).status_code in (403, 404)                                      # the permission does not widen which stores she can mark
    assert client.get(f"{API}/orders/calendar", params={"store_id": str(outside.id), "year": TODAY.year, "month": TODAY.month}, headers=viewer).status_code in (403, 404)
    assert client.get(f"{API}/entries/attempts", headers=viewer).status_code == 403                          # and it opens no Store Audit / attempts log


def test_the_months_bottles_in_vendors_count_everyones_entries_for_her_only(client, db, make_user, make_store):
    a = make_store(platform="zepto", region=None, state=STATE, city="Viewville")
    marker = _scoped(client, db, make_user)
    viewer = _scoped(client, db, make_user, "entries.view_all")
    plain = _scoped(client, db, make_user)
    assert _mark(client, marker, a, 7).status_code == 200

    def bottles(who):
        items = client.get(f"{API}/orders/inventory", headers=who).json()["items"]
        return next(i["month_bottles"] for i in items if i["id"] == str(a.id))

    assert bottles(viewer) == 7 and bottles(plain) == 0


def test_the_permission_exists_for_an_administrator_to_tick(client, admin):
    r = client.get(f"{API}/permissions", headers=admin)
    assert r.status_code == 200
    codes = {p["code"] for g in r.json() for p in g["permissions"]}
    assert "entries.view_all" in codes


# ---------------------------------------------------------------- "every store of the platform" scope

def _give_all_stores(client, admin, db, uid, org_slug="zepto"):
    pid = str(db.query(Organization).filter_by(slug=org_slug).one().id)
    r = client.put(f"{API}/assignments/scope/{uid}", headers=admin, json={"platform_id": pid, "included_states": ["*"]})
    assert r.status_code == 200, r.text
    return r


def test_the_all_stores_scope_reaches_every_state_including_one_that_did_not_exist_before(client, admin, db, make_user, make_store):
    code, pw, uid = make_user("employee", platform="zepto", grants=("orders.view", "orders.mark", "entries.view_all"))
    she = auth(login(client, code, pw).json()["access_token"])
    brand_new_state = make_store(platform="zepto", region=None, state="Newstate Pradesh", city="Somewhere")
    blank_state = make_store(platform="zepto", region=None, state="", city="Nowhere")
    assert _mark(client, she, brand_new_state, 4).status_code == 403            # no states, no stores: the default

    r = _give_all_stores(client, admin, db, uid)
    assert "*" in r.json()["included_states"]
    assert _mark(client, she, brand_new_state, 4).status_code == 200            # now any state
    assert _mark(client, she, blank_state, 6).status_code == 200                # even a store whose state is empty
    later = make_store(platform="zepto", region=None, state="Another New State", city="X")
    assert _mark(client, she, later, 5).status_code == 200                      # and a state that appears afterwards, with nothing to add


def test_the_all_stores_scope_stays_on_her_platform_and_skipped_places_still_win(client, admin, db, make_user, make_store):
    code, pw, uid = make_user("employee", platform="zepto", grants=("orders.view", "orders.mark"))
    she = auth(login(client, code, pw).json()["access_token"])
    _give_all_stores(client, admin, db, uid)
    blinkit = make_store(platform="blinkit")
    assert _mark(client, she, blinkit, 3).status_code in (403, 404)             # another platform's store is never included
    skipped = make_store(platform="zepto", region=None, state="Skipland", city="Skipville")
    pid = str(db.query(Organization).filter_by(slug="zepto").one().id)
    assert client.put(f"{API}/assignments/scope/{uid}", headers=admin, json={"platform_id": pid, "included_states": ["*"], "excluded_states": ["Skipland"]}).status_code == 200
    assert _mark(client, she, skipped, 3).status_code == 403                    # "skip" beats "all stores"


def test_turning_the_all_stores_scope_off_takes_it_away(client, admin, db, make_user, make_store):
    code, pw, uid = make_user("employee", platform="zepto", grants=("orders.view", "orders.mark"))
    she = auth(login(client, code, pw).json()["access_token"])
    s = make_store(platform="zepto", region=None, state="Offland", city="Offville")
    _give_all_stores(client, admin, db, uid)
    assert _mark(client, she, s, 2).status_code == 200
    pid = str(db.query(Organization).filter_by(slug="zepto").one().id)
    assert client.put(f"{API}/assignments/scope/{uid}", headers=admin, json={"platform_id": pid, "included_states": []}).status_code == 200
    other = make_store(platform="zepto", region=None, state="Offland", city="Offville")
    assert _mark(client, she, other, 2).status_code == 403
