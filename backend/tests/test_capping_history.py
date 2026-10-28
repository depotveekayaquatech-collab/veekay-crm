"""Capping history: the effective-date rule, changing a capping (backdated, duplicate dates, who may), moving a start date, and the list of latest cappings."""
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


def _change(client, headers, store, capping, day):
    return client.post(f"{API}/capping/change", json={"storeId": str(store.id), "capping": capping, "effectiveFrom": day.isoformat()}, headers=headers)


def _seed(db, store, *rows):
    for eff, cap in rows:
        db.add(CappingHistory(store_id=store.id, capping=cap, effective_from=eff))
    db.commit()


def test_the_capping_on_a_day_is_the_one_with_the_greatest_effective_from_on_or_before_it():
    history = [(date(2026, 10, 1), 10), (date(2026, 10, 15), 11)]
    assert svc.effective_capping(history, date(2026, 9, 30)) is None             # before the first entry
    assert [svc.effective_capping(history, date(2026, 10, d)) for d in (1, 2, 14)] == [10, 10, 10]
    assert [svc.effective_capping(history, date(2026, 10, d)) for d in (15, 16, 31)] == [11, 11, 11]
    assert svc.effective_capping([], date(2026, 10, 1)) is None


def test_a_backdated_entry_slots_into_the_timeline_without_moving_the_later_ones():
    history = sorted([(date(2026, 10, 1), 10), (date(2026, 10, 15), 11), (date(2026, 10, 8), 12)])      # added last, dated in the middle
    assert [svc.effective_capping(history, date(2026, 10, d)) for d in (7, 8, 14, 15)] == [10, 12, 12, 11]


# ---------------------------------------------------------------- the alert rules (pure)


def test_a_change_today_is_saved_and_becomes_the_current_capping(client, admin, zstore, db):
    r = _change(client, admin, zstore, 10, _today())
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["capping"], body["backdated"], body["current_capping"], body["effective_from"]) == (10, False, 10, _today().isoformat())
    db.expire_all()
    assert db.query(StoreCap).filter_by(store_id=zstore.id).one().daily_cap == 10           # the old field is kept in step
    h = client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=admin).json()
    assert [(x["capping"], x["effective_from"]) for x in h["rows"]] == [(10, _today().isoformat())]
    assert h["rows"][0]["changed_by"] and h["rows"][0]["created_at"]


def test_the_example_of_10_from_the_first_and_11_from_the_fifteenth(client, admin, zstore, db):
    first, mid = date(2026, 10, 1), date(2026, 10, 15)
    assert _change(client, admin, zstore, 10, first).status_code == 201
    assert _change(client, admin, zstore, 11, mid).status_code == 201
    on = lambda day: svc.effective_capping(sorted((r.effective_from, r.capping) for r in db.query(CappingHistory).filter_by(store_id=zstore.id)), day)  # noqa: E731
    assert [on(date(2026, 10, d)) for d in (1, 14, 15, 31)] == [10, 10, 11, 11] and on(date(2026, 9, 30)) is None
    listed = next(r for r in client.get(f"{API}/capping", headers=admin).json()["rows"] if r["store_id"] == str(zstore.id))
    assert listed["capping"] == 11 and listed["since"] == "2026-10-15"                         # the list shows the latest capping and when it began


def test_a_backdated_change_is_allowed_and_flagged_and_does_not_move_the_current_capping(client, admin, zstore, db):
    today = _today()
    assert _change(client, admin, zstore, 11, today - timedelta(days=2)).json()["backdated"] is True
    r = _change(client, admin, zstore, 9, today - timedelta(days=20))               # older than the existing one
    assert r.status_code == 201 and r.json()["backdated"] is True
    assert r.json()["current_capping"] == 11                                         # the later change still rules today
    db.expire_all()
    assert db.query(StoreCap).filter_by(store_id=zstore.id).one().daily_cap == 11
    dates = [x["effective_from"] for x in client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=admin).json()["rows"]]
    assert dates == sorted(dates, reverse=True) and len(dates) == 2                  # newest first


def test_a_second_change_for_the_same_date_is_refused_with_a_clear_message(client, admin, zstore, db):
    day = _today() - timedelta(days=3)
    assert _change(client, admin, zstore, 10, day).status_code == 201
    r = _change(client, admin, zstore, 12, day)
    assert r.status_code == 409 and "already exists" in r.json()["detail"] and f"{day:%d-%b-%Y}" in r.json()["detail"]
    db.expire_all()
    assert db.query(CappingHistory).filter_by(store_id=zstore.id).count() == 1       # the first stays as it was


@pytest.mark.parametrize("capping", [0, -3, 1.5, "7", True, None])
def test_the_capping_must_be_a_whole_number_of_at_least_one(client, admin, zstore, capping):
    r = client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": capping, "effectiveFrom": _today().isoformat()}, headers=admin)
    assert r.status_code == 422, r.text


def test_the_date_and_the_store_are_checked(client, admin, zstore):
    assert _change(client, admin, zstore, 10, _today() + timedelta(days=1)).status_code == 422          # no future dates
    bad = client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": 10, "effectiveFrom": "31-02-2026"}, headers=admin)
    assert bad.status_code == 422
    ghost = client.post(f"{API}/capping/change", json={"storeId": str(uuid.uuid4()), "capping": 10, "effectiveFrom": _today().isoformat()}, headers=admin)
    assert ghost.status_code == 404
    assert client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": 10, "effectiveFrom": _today().isoformat(), "extra": 1}, headers=admin).status_code == 422


def test_a_store_of_another_platform_is_not_found(client, admin, make_store):
    blinkit = make_store(platform="blinkit")
    assert _change(client, admin, blinkit, 10, _today()).status_code == 404


def test_only_someone_holding_capping_change_may_change_and_everyone_who_sees_capping_may_view(client, zepto_emp, emp, admin, zstore, make_user):
    assert _change(client, zepto_emp, zstore, 10, _today()).status_code == 403                    # a Zepto employee can view, not change
    assert _change(client, emp, zstore, 10, _today()).status_code == 403
    assert client.post(f"{API}/capping/change", json={}).status_code in (401, 403)
    for url in ("/capping",):
        assert client.get(f"{API}{url}", headers=zepto_emp).status_code == 200, url
        assert client.get(f"{API}{url}", headers=emp).status_code == 403, url                     # a Blinkit employee sees no Zepto capping
    assert client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=zepto_emp).status_code == 200

    from .conftest import auth, login
    code, pw, _ = make_user("employee", platform="zepto", grants=("orders.view", "capping.change"))   # ticked for one person, like a manager
    ticked = auth(login(client, code, pw).json()["access_token"])
    assert _change(client, ticked, zstore, 10, _today()).status_code == 201
    assert _change(client, admin, zstore, 12, _today() - timedelta(days=1)).status_code == 201


def test_the_admin_role_holds_the_permission(db):
    from app.models.permission import Permission, RolePermission
    from app.models.role import Role

    n = (db.query(RolePermission).join(Role, Role.id == RolePermission.role_id).join(Permission, Permission.id == RolePermission.permission_id)
         .filter(Role.code == "admin", Permission.code == "capping.change").count())
    assert n == 1


def test_there_is_no_way_to_edit_or_delete_a_history_row(client, admin, zstore):
    row = _change(client, admin, zstore, 10, _today()).json()
    for method in ("put", "patch", "delete"):
        for url in (f"{API}/capping/change", f"{API}/capping/history", f"{API}/capping/history/{row['id']}", f"{API}/capping/change/{row['id']}"):
            if method == "patch" and url.endswith(f"/history/{row['id']}"):
                continue                                                  # the one allowed edit: the START DATE (see the effective-date tests)
            assert getattr(client, method)(url, headers=admin).status_code in (404, 405), (method, url)


def test_a_start_date_can_be_moved_and_the_current_capping_follows(client, admin, zepto_emp, zstore, db):
    today = _today()
    _seed(db, zstore, (today - timedelta(days=9), 10), (today - timedelta(days=2), 12))
    ids = {r.capping: r.id for r in db.query(CappingHistory).filter_by(store_id=zstore.id)}

    moved = client.patch(f"{API}/capping/history/{ids[12]}", json={"effectiveFrom": (today - timedelta(days=5)).isoformat()}, headers=admin)
    assert moved.status_code == 200, moved.text
    assert moved.json()["effective_from"] == (today - timedelta(days=5)).isoformat() and moved.json()["capping"] == 12 and moved.json()["current_capping"] == 12
    db.expire_all()
    assert {r.capping: r.effective_from for r in db.query(CappingHistory).filter_by(store_id=zstore.id)} == {10: today - timedelta(days=9), 12: today - timedelta(days=5)}

    assert client.patch(f"{API}/capping/history/{ids[12]}", json={"effectiveFrom": (today - timedelta(days=9)).isoformat()}, headers=admin).status_code == 409   # that date is used
    assert client.patch(f"{API}/capping/history/{ids[12]}", json={"effectiveFrom": (today + timedelta(days=1)).isoformat()}, headers=admin).status_code == 422
    assert client.patch(f"{API}/capping/history/{ids[12]}", json={"effectiveFrom": today.isoformat()}, headers=zepto_emp).status_code == 403          # capping.change only
    assert client.patch(f"{API}/capping/history/{uuid.uuid4()}", json={"effectiveFrom": today.isoformat()}, headers=admin).status_code == 404
    assert client.patch(f"{API}/capping/history/{ids[12]}", json={"effectiveFrom": today.isoformat(), "capping": 99}, headers=admin).status_code == 422     # only the date can change
