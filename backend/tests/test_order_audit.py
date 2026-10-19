"""Order entry audit: the log of what employees submitted against what is stored and visible, the repair, and the employee's own list."""
from datetime import datetime, timedelta, timezone

from app.models.order_entry import OrderEntry
from app.models.store import Store

from .conftest import API

AUDIT = f"{API}/developer/order-audit"
TODAY = datetime.now(timezone.utc).date()


def _mark(client, who, store, count, day=None):
    r = client.post(f"{API}/orders/mark", headers=who, json={"store_id": str(store.id), "order_date": (day or TODAY).isoformat(), "bottle_count": count})
    assert r.status_code == 200, r.text


def _audit(client, dev, day=None):
    d = (day or TODAY).isoformat()
    r = client.get(AUDIT, headers=dev, params={"start": d, "end": d})
    assert r.status_code == 200, r.text
    return r.json()


def _kinds(report, code):
    return [x["kind"] for x in report["rows"] if x["store_code"] == code]


def _restore(client, dev, dry_run):
    return client.post(f"{AUDIT}/restore", headers=dev, json={"start": TODAY.isoformat(), "end": TODAY.isoformat(), "dry_run": dry_run}).json()


def test_an_intact_entry_is_fine_and_a_lost_one_is_found_and_restored_from_the_log(client, dev, emp, db, make_store):
    a, b = make_store(code="AU-A"), make_store(code="AU-B")
    _mark(client, emp, a, 30)
    _mark(client, emp, b, 40)
    rep = _audit(client, dev)
    assert "MISSING" not in _kinds(rep, "AU-A") + _kinds(rep, "AU-B")
    db.query(OrderEntry).filter(OrderEntry.store_id == b.id).delete()                 # the entry goes missing, whatever the reason
    db.commit()
    rep = _audit(client, dev)
    row = next(x for x in rep["rows"] if x["store_code"] == "AU-B")
    assert row["kind"] == "MISSING" and row["reason"] == "LOST" and row["logged_count"] == 40 and row["restorable"] is True
    assert "MISSING" not in _kinds(rep, "AU-A")
    dry = _restore(client, dev, True)
    assert dry["dry_run"] is True and dry["restorable"] >= 1 and dry["restored"] == 0
    assert db.query(OrderEntry).filter(OrderEntry.store_id == b.id).count() == 0       # a dry run changes nothing
    assert _restore(client, dev, False)["restored"] >= 1
    assert db.query(OrderEntry).filter(OrderEntry.store_id == b.id).one().bottle_count == 40
    assert _restore(client, dev, False)["restored"] == 0                                # once only
    assert "MISSING" not in _kinds(_audit(client, dev), "AU-B")


def test_an_entry_an_admin_cleared_is_reported_as_cleared_and_never_restored(client, dev, emp, admin, db, make_store):
    s = make_store(code="AU-CLR")
    _mark(client, emp, s, 25)
    r = client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(s.id), "order_date": TODAY.isoformat(), "bottle_count": None})
    assert r.status_code == 200
    rep = _audit(client, dev)
    row = next(x for x in rep["rows"] if x["store_code"] == "AU-CLR")
    assert row["kind"] == "CLEARED" and row["restorable"] is False
    _restore(client, dev, False)
    assert db.query(OrderEntry).filter(OrderEntry.store_id == s.id).count() == 0


def test_a_changed_entry_and_a_store_that_is_no_longer_live_are_called_out(client, dev, emp, db, make_store):
    c, h = make_store(code="AU-CHG"), make_store(code="AU-HID")
    _mark(client, emp, c, 10)
    _mark(client, emp, h, 20)
    db.query(OrderEntry).filter(OrderEntry.store_id == c.id).update({"bottle_count": 15, "source": "admin"})   # a sheet import overwrote it (not logged as a correction)
    db.query(Store).filter(Store.id == h.id).update({"status": "PENDING"})              # the sheet sync flips it away from LIVE
    db.commit()
    rep = _audit(client, dev)
    changed = next(x for x in rep["rows"] if x["store_code"] == "AU-CHG" and x["kind"] == "CHANGED")
    assert changed["current_count"] == 15 and changed["logged_count"] == 10
    hid = next(x for x in rep["rows"] if x["store_code"] == "AU-HID" and x["kind"] == "HIDDEN_NOT_LIVE")
    assert hid["store_status"] == "PENDING" and hid["current_count"] == 20 and "PENDING" in hid["detail"]
    assert rep["summary"]["hidden_not_live"] >= 1
    assert db.query(OrderEntry).filter(OrderEntry.store_id == h.id).count() == 1        # the entry itself is intact


def test_a_deleted_and_re_added_store_gets_its_entries_back_on_the_new_store(client, dev, emp, db, make_store):
    old = make_store(code="AU-RE", name="Recreated Store")
    _mark(client, emp, old, 55)
    db.query(Store).filter(Store.id == old.id).delete()                                  # "Remove all stores" then re-import: a new id, the entry is gone
    db.commit()
    new = make_store(code="AU-RE", name="Recreated Store")
    row = next(x for x in _audit(client, dev)["rows"] if x["store_code"] == "AU-RE")
    assert row["kind"] == "MISSING" and row["reason"] == "STORE_RECREATED" and row["restorable"] is True and str(row["store_id"]) == str(new.id)
    _restore(client, dev, False)
    assert db.query(OrderEntry).filter(OrderEntry.store_id == new.id).one().bottle_count == 55


def test_a_store_that_no_longer_exists_is_reported_but_cannot_be_restored(client, dev, emp, db, make_store):
    gone = make_store(code="AU-GONE")
    _mark(client, emp, gone, 12)
    db.query(Store).filter(Store.id == gone.id).delete()
    db.commit()
    row = next(x for x in _audit(client, dev)["rows"] if x["store_code"] == "AU-GONE")
    assert row["reason"] == "STORE_GONE" and row["restorable"] is False


def test_the_audit_is_developer_only_and_limited_to_two_weeks(client, admin, emp, dev):
    for who in (admin, emp):
        assert client.get(AUDIT, headers=who, params={"start": TODAY.isoformat(), "end": TODAY.isoformat()}).status_code == 403
        assert client.post(f"{AUDIT}/restore", headers=who, json={"start": TODAY.isoformat(), "end": TODAY.isoformat()}).status_code == 403
    assert client.get(AUDIT, headers=dev, params={"start": (TODAY - timedelta(days=20)).isoformat(), "end": TODAY.isoformat()}).status_code == 422
    assert client.get(AUDIT, headers=dev, params={"start": TODAY.isoformat(), "end": (TODAY - timedelta(days=1)).isoformat()}).status_code == 422


# ---- the employee's own list ------------------------------------------------------------------------------------------

def test_my_entries_lists_what_the_employee_entered_even_after_the_store_left_live(client, emp, zepto_emp, db, make_store):
    a, b = make_store(code="ME-A"), make_store(code="ME-B")
    _mark(client, emp, a, 31, TODAY)
    _mark(client, emp, b, 42, TODAY - timedelta(days=1))
    db.query(Store).filter(Store.id == b.id).update({"status": "CLOSE"})
    db.commit()
    r = client.get(f"{API}/orders/my-entries", headers=emp, params={"days": 7}).json()
    got = {i["store_code"]: i for i in r["items"]}
    assert got["ME-A"]["bottles"] == 31 and got["ME-A"]["store_status"] == "LIVE"
    assert got["ME-B"]["bottles"] == 42 and got["ME-B"]["store_status"] == "CLOSE"       # still listed, with its status today
    # nobody else sees them
    assert not any(i["store_code"] in ("ME-A", "ME-B") for i in client.get(f"{API}/orders/my-entries", headers=zepto_emp).json()["items"])
    # a day outside the window is not listed
    me = db.query(OrderEntry).filter(OrderEntry.store_id == a.id).one().marked_by_user_id
    old = make_store(code="ME-OLD")
    db.add(OrderEntry(organization_id=old.organization_id, store_id=old.id, order_date=TODAY - timedelta(days=10), bottle_count=9, source="employee", marked_by_user_id=me))
    db.commit()
    assert "ME-OLD" not in {i["store_code"] for i in client.get(f"{API}/orders/my-entries", headers=emp, params={"days": 7}).json()["items"]}
    assert "ME-OLD" in {i["store_code"] for i in client.get(f"{API}/orders/my-entries", headers=emp, params={"days": 14}).json()["items"]}


def test_my_entries_never_shows_a_cash_adjustment_to_the_employee(client, emp, db, make_store):
    s = make_store(code="ME-CASH")
    _mark(client, emp, s, 20)
    e = db.query(OrderEntry).filter(OrderEntry.store_id == s.id).one()
    e.bottle_count, e.cash_adjustment = 26, 6                                           # a developer adjustment of 6 on top of their 20
    db.commit()
    got = next(i for i in client.get(f"{API}/orders/my-entries", headers=emp).json()["items"] if i["store_code"] == "ME-CASH")
    assert got["bottles"] == 20


def test_an_admin_correction_that_is_logged_is_not_flagged_as_a_change(client, dev, emp, admin, make_store):
    s = make_store(code="AU-FIX")
    _mark(client, emp, s, 10)
    client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(s.id), "order_date": TODAY.isoformat(), "bottle_count": 15})
    assert _kinds(_audit(client, dev), "AU-FIX") == []        # the log already says 15, so what is stored matches it


# ---- the admin Inventory page keeps a store that left LIVE while it holds entries this month ---------------------------

def test_inventory_keeps_a_store_that_left_live_but_still_has_entries_this_month(client, admin, emp, db, make_store):
    gone, never = make_store(code="INV-GONE"), make_store(code="INV-NEVER")
    _mark(client, emp, gone, 33)
    db.query(Store).filter(Store.id.in_([gone.id, never.id])).update({"status": "PENDING"}, synchronize_session=False)
    db.commit()
    inv = client.get(f"{API}/orders/inventory", headers=admin).json()
    rows = {i["external_code"]: i for i in inv["items"]}
    assert rows["INV-GONE"]["status"] == "PENDING" and rows["INV-GONE"]["month_bottles"] == 33
    assert rows["INV-GONE"]["pending_days"] == 0                           # a store that is not live is never "behind"
    assert "INV-NEVER" not in rows                                         # no entries this month: not listed, as before
    assert inv["summary"]["stores"] == sum(1 for i in inv["items"] if i["status"] == "LIVE")
