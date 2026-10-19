"""Nothing valuable is lost: every deleted order entry is kept by the database and can be put back; every change to an entry is kept."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models.cash_purchase import CashPurchase
from app.models.deleted_row import DeletedRow, OrderEntryChange
from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.user import User

from .conftest import API

AUDIT = f"{API}/developer/order-audit"
TODAY = datetime.now(timezone.utc).date()


def _mark(client, who, store, n, day=None):
    r = client.post(f"{API}/orders/mark", headers=who, json={"store_id": str(store.id), "order_date": (day or TODAY).isoformat(), "bottle_count": n})
    assert r.status_code == 200, r.text


def _kept(db, store_id, table="order_entries"):
    db.expire_all()
    return [r for r in db.query(DeletedRow).filter(DeletedRow.table_name == table) if r.data.get("store_id") == str(store_id)]


def test_every_way_of_deleting_an_entry_leaves_a_copy(client, emp, db, make_store):
    a, b, c = make_store(code="DS-A"), make_store(code="DS-B"), make_store(code="DS-C")
    for s, n in ((a, 11), (b, 22), (c, 33)):
        _mark(client, emp, s, n)
    # 1) the ORM, 2) a bulk delete, 3) raw SQL typed by hand
    db.delete(db.query(OrderEntry).filter(OrderEntry.store_id == a.id).one())
    db.commit()
    db.query(OrderEntry).filter(OrderEntry.store_id == b.id).delete()
    db.commit()
    db.execute(text("DELETE FROM order_entries WHERE store_id = :s"), {"s": c.id})
    db.commit()
    for s, n in ((a, 11), (b, 22), (c, 33)):
        copies = _kept(db, s.id)
        assert len(copies) == 1 and copies[0].data["bottle_count"] == n and copies[0].data["order_date"] == TODAY.isoformat()
        assert copies[0].restored_at is None


def test_deleting_a_store_keeps_its_entries_and_the_store(client, emp, db, make_store):
    s = make_store(code="DS-STORE", name="Doomed Store")
    _mark(client, emp, s, 44)
    sid = s.id
    db.execute(text("DELETE FROM stores WHERE id = :s"), {"s": sid})                       # cascades to the store's order entries
    db.commit()
    assert [r.data["bottle_count"] for r in _kept(db, sid)] == [44]
    gone = db.query(DeletedRow).filter(DeletedRow.table_name == "stores", DeletedRow.row_id == str(sid)).one()
    assert gone.data["external_code"] == "DS-STORE" and gone.data["name"] == "Doomed Store"


def test_clearing_a_day_logs_what_was_there_and_can_be_undone(client, dev, emp, admin, db, make_store):
    s = make_store(code="DS-CLR")
    _mark(client, emp, s, 25)
    r = client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(s.id), "order_date": TODAY.isoformat(), "bottle_count": None})
    assert r.status_code == 200 and db.query(OrderEntry).filter(OrderEntry.store_id == s.id).count() == 0
    log = str(client.get(f"{API}/activity", headers=dev, params={"page_size": 50}).json())
    assert "order.cleared" in log and "previous_count" in log
    listed = client.get(f"{AUDIT}/deleted", headers=dev, params={"start": TODAY.isoformat(), "end": TODAY.isoformat()}).json()
    row = next(i for i in listed["items"] if i["store_code"] == "DS-CLR")
    assert row["bottles"] == 25 and row["state"] == "RESTORABLE"
    done = client.post(f"{AUDIT}/deleted/restore", headers=dev, json={"ids": [row["id"]], "dry_run": False}).json()
    assert done["restored"] == 1
    assert db.query(OrderEntry).filter(OrderEntry.store_id == s.id).one().bottle_count == 25
    again = client.get(f"{AUDIT}/deleted", headers=dev, params={"start": TODAY.isoformat(), "end": TODAY.isoformat()}).json()
    assert not [i for i in again["items"] if i["store_code"] == "DS-CLR"]                    # restored copies drop out of the list
    shown = client.get(f"{AUDIT}/deleted", headers=dev, params={"include_restored": "true", "start": TODAY.isoformat(), "end": TODAY.isoformat()}).json()
    assert next(i for i in shown["items"] if i["store_code"] == "DS-CLR")["state"] == "RESTORED"


def test_every_change_to_an_entry_is_kept(client, emp, admin, db, make_store):
    s = make_store(code="DS-CHG")
    _mark(client, emp, s, 10)
    client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(s.id), "order_date": TODAY.isoformat(), "bottle_count": 15})
    client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(s.id), "order_date": TODAY.isoformat(), "bottle_count": 18})
    changes = db.query(OrderEntryChange).filter(OrderEntryChange.store_id == s.id).order_by(OrderEntryChange.changed_at).all()
    assert [(c.old_count, c.new_count) for c in changes] == [(10, 15), (15, 18)]
    assert changes[0].old_source == "employee" and changes[0].new_source == "admin"


def test_a_store_deleted_and_added_again_gets_its_entries_back_on_the_new_store(client, dev, emp, db, make_store):
    old = make_store(code="DS-RE", name="Rebuilt Store")
    _mark(client, emp, old, 55)
    db.execute(text("DELETE FROM stores WHERE id = :s"), {"s": old.id})
    db.commit()
    new = make_store(code="DS-RE", name="Rebuilt Store")
    day = TODAY.isoformat()
    listed = client.get(f"{AUDIT}/deleted", headers=dev, params={"start": day, "end": day}).json()
    row = next(i for i in listed["items"] if i["store_code"] == "DS-RE")
    assert row["state"] == "RESTORABLE" and row["store_name"] == "Rebuilt Store"
    dry = client.post(f"{AUDIT}/deleted/restore", headers=dev, json={"ids": [row["id"]]}).json()
    assert dry["dry_run"] is True and dry["restorable"] == 1 and dry["restored"] == 0
    assert db.query(OrderEntry).filter(OrderEntry.store_id == new.id).count() == 0
    done = client.post(f"{AUDIT}/deleted/restore", headers=dev, json={"ids": [row["id"]], "dry_run": False}).json()
    assert done["restored"] == 1
    assert db.query(OrderEntry).filter(OrderEntry.store_id == new.id).one().bottle_count == 55


def test_a_restore_never_overwrites_an_entry_that_exists_and_skips_a_store_that_is_gone(client, dev, emp, admin, db, make_store):
    s, gone = make_store(code="DS-KEEP"), make_store(code="DS-GONE")
    _mark(client, emp, s, 20)
    _mark(client, emp, gone, 7)
    client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(s.id), "order_date": TODAY.isoformat(), "bottle_count": None})      # cleared
    _mark(client, admin, s, 99)                                                                                                                  # then entered again
    db.execute(text("DELETE FROM stores WHERE id = :s"), {"s": gone.id})
    db.commit()
    day = TODAY.isoformat()
    out = client.post(f"{AUDIT}/deleted/restore", headers=dev, json={"start": day, "end": day, "dry_run": False}).json()
    assert out["already_there"] >= 1 and out["store_gone"] >= 1
    assert db.query(OrderEntry).filter(OrderEntry.store_id == s.id).one().bottle_count == 99               # the newer entry stays
    states = {i["store_code"]: i["state"] for i in client.get(f"{AUDIT}/deleted", headers=dev, params={"start": day, "end": day}).json()["items"]}
    assert states["DS-GONE"] == "STORE_GONE"


def test_other_valuable_records_are_kept_too(client, emp, db):
    me = db.query(User).filter_by(employee_code="EMP001").one()
    p = CashPurchase(organization_id=me.organization_id, kind="OFFICE", purchase_date=TODAY, category="MILK", amount=120, created_by_user_id=me.id)
    db.add(p)
    db.commit()
    pid = str(p.id)
    db.delete(p)
    db.commit()
    kept = db.query(DeletedRow).filter(DeletedRow.table_name == "cash_purchases", DeletedRow.row_id == pid).one()
    assert kept.data["category"] == "MILK" and float(kept.data["amount"]) == 120


def test_every_protected_table_really_has_the_trigger(db):
    protected = ["order_entries", "stores", "cash_purchases", "cash_adjustments", "payslips", "compliance_documents", "tickets", "bottle_scans",
                 "external_accounts", "audit_logs", "attendance_records"]
    have = {r[0] for r in db.execute(text(
        "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE t.tgname = 'trg_keep_deleted' AND NOT t.tgisinternal"))}
    assert set(protected) <= have, set(protected) - have


def test_the_recovery_tools_are_developer_only(client, admin, emp):
    for who in (admin, emp):
        assert client.get(f"{AUDIT}/deleted", headers=who).status_code == 403
        assert client.post(f"{AUDIT}/deleted/restore", headers=who, json={"start": TODAY.isoformat(), "end": TODAY.isoformat()}).status_code == 403
    dev_missing = client.post(f"{AUDIT}/deleted/restore", headers=admin, json={})
    assert dev_missing.status_code == 403
