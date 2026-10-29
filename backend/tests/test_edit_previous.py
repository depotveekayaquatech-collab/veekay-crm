"""entries.edit_previous: a Level 1 employee who is given it may change ANY entry of their stores in the dates still open to them, whoever entered it, with the full audit."""
from datetime import date, timedelta

from sqlalchemy import text

from app.core.config import settings
from app.models.order_entry import OrderEntry
from app.services import order_service

from .conftest import API, auth, login, plant_entry

TODAY = date.today()
GRANTS = ("orders.view", "orders.mark")


def _as(client, make_user, *extra, **kw):
    code, pw, uid = make_user(platform="blinkit", region="NORTH", grants=GRANTS + extra, **kw)
    return auth(login(client, code, pw).json()["access_token"]), uid, code


def _events(db, entry_id):
    return db.execute(text("SELECT event_type, actor_user_id, actor_role, old_values, new_values, reason FROM order_entry_events WHERE entry_id = :e ORDER BY seq"),
                      {"e": entry_id}).mappings().all()


def test_the_permission_lets_a_level_one_employee_change_an_entry_a_colleague_made_and_it_is_audited(client, db, make_user, make_store):
    store = make_store(region="NORTH")
    colleague, c_id, _ = _as(client, make_user)
    editor, e_id, _ = _as(client, make_user, "entries.edit_previous")
    plain, _, _ = _as(client, make_user)
    day = TODAY
    assert client.post(f"{API}/orders/mark", headers=colleague, json={"store_id": str(store.id), "order_date": day.isoformat(), "bottle_count": 11}).status_code == 200
    entry = db.query(OrderEntry).filter_by(store_id=store.id, order_date=day).one()

    body = {"store_id": str(store.id), "order_date": day.isoformat(), "bottle_count": 14}
    assert client.patch(f"{API}/orders/my-entry", headers=plain, json=body).status_code == 403          # no permission: someone else's entry stays a senior's job
    r = client.patch(f"{API}/orders/my-entry", headers=editor, json=body)
    assert r.status_code == 200, r.text

    db.expire_all()
    e = db.query(OrderEntry).filter_by(id=entry.id).one()
    assert e.bottle_count == 14 and e.created_by_user_id == c_id                                        # the creator never changes
    assert e.last_modified_by_user_id == e_id and e.version == 2                                        # who changed it last is stamped
    created, edited = _events(db, entry.id)
    assert edited["event_type"] == "EDITED" and edited["actor_user_id"] == e_id
    assert edited["old_values"]["bottle_count"] == 11 and edited["new_values"]["bottle_count"] == 14   # what it was stays in the history
    assert "earlier entries" in (edited["reason"] or "")


def test_it_also_works_on_an_entry_an_admin_made_and_on_one_already_changed_by_someone_else_and_can_clear_it(client, db, admin, make_user, make_store):
    store = make_store(region="NORTH")
    editor, e_id, _ = _as(client, make_user, "entries.edit_previous")
    day = TODAY - timedelta(days=1) if TODAY.day > 1 else TODAY
    assert client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(store.id), "order_date": day.isoformat(), "bottle_count": 20}).status_code == 200      # an admin's entry
    assert client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(store.id), "order_date": day.isoformat(), "bottle_count": 21}).status_code == 200      # changed again
    body = {"store_id": str(store.id), "order_date": day.isoformat(), "bottle_count": 9}
    assert client.patch(f"{API}/orders/my-entry", headers=editor, json=body).status_code == 200
    db.expire_all()
    assert db.query(OrderEntry).filter_by(store_id=store.id, order_date=day).one().bottle_count == 9
    cleared = client.patch(f"{API}/orders/my-entry", headers=editor, json={**body, "bottle_count": None})
    assert cleared.status_code == 200
    db.expire_all()
    assert db.query(OrderEntry).filter_by(store_id=store.id, order_date=day).count() == 0               # cleared: the deleted-rows archive and the history keep it


def test_only_the_open_dates_can_be_changed_this_month_and_last_month_for_five_days(client, db, make_user, make_store):
    assert settings.BACKMONTH_GRACE_DAYS == 5                                                           # the month itself plus 5 days
    store = make_store(region="NORTH")
    editor, _, _ = _as(client, make_user, "entries.edit_previous")
    first = TODAY.replace(day=1)
    last_month_day = first - timedelta(days=3)
    old_day = first - timedelta(days=45)
    plant_entry(db, store, last_month_day, 7)
    plant_entry(db, store, old_day, 7)

    def change(day):
        return client.patch(f"{API}/orders/my-entry", headers=editor, json={"store_id": str(store.id), "order_date": day.isoformat(), "bottle_count": 8})

    assert change(old_day).status_code == 422                                                           # two months back: closed
    open_now = order_service.employee_can_mark_month(last_month_day.year, last_month_day.month, TODAY)
    assert (change(last_month_day).status_code == 200) is open_now                                       # last month is open only through the 5th
    assert order_service.backmonth_open_until(date(2026, 11, 1)) == date(2026, 11, 5)
    assert order_service.employee_can_mark_month(2026, 10, date(2026, 11, 5)) and not order_service.employee_can_mark_month(2026, 10, date(2026, 11, 6))
    assert change(TODAY + timedelta(days=1)).status_code == 422                                          # never the future


def test_the_permission_is_in_the_catalogue_and_the_app_is_told_about_it(client, make_user):
    ticked, _, _ = _as(client, make_user, "entries.edit_previous")
    plain, _, _ = _as(client, make_user)
    assert client.get(f"{API}/auth/me", headers=ticked).json()["can_edit_previous"] is True
    assert client.get(f"{API}/auth/me", headers=plain).json()["can_edit_previous"] is False


def test_after_the_window_a_level_one_employee_can_see_entries_but_not_mark_or_change_them(client, db, make_user, make_store):
    store = make_store(region="NORTH")
    plain, _, _ = _as(client, make_user)
    editor, _, _ = _as(client, make_user, "entries.edit_previous")
    closed = TODAY.replace(day=1) - timedelta(days=40)                                                  # beyond this month + 5 days of the next, always
    plant_entry(db, store, closed, 12)

    for who in (plain, editor):
        cal = client.get(f"{API}/orders/calendar", params={"store_id": str(store.id), "year": closed.year, "month": closed.month}, headers=who)
        assert cal.status_code == 200 and cal.json()["can_mark"] is False                               # the month is shown, marked view-only
        day = next(d for d in cal.json()["days"] if d["date"] == closed.isoformat())
        assert day["marked"] is True                                                                    # they can still see that it was entered
        body = {"store_id": str(store.id), "order_date": closed.isoformat(), "bottle_count": 5}
        assert client.post(f"{API}/orders/mark", headers=who, json=body).status_code == 422
        other = (closed + timedelta(days=1)).isoformat()
        many = client.post(f"{API}/orders/mark-many", headers=who, json={"store_id": str(store.id), "entries": [{"order_date": other, "bottle_count": 5}]})
        assert many.status_code == 200 and many.json()["saved"] == 0 and many.json()["failed"] == 1       # each date is refused on its own
        assert client.patch(f"{API}/orders/my-entry", headers=who, json=body).status_code == (403 if who is plain else 422)    # no permission: refused outright; with it: the dates are closed
    db.expire_all()
    assert db.query(OrderEntry).filter_by(store_id=store.id).count() == 1 and db.query(OrderEntry).filter_by(store_id=store.id).one().bottle_count == 12
