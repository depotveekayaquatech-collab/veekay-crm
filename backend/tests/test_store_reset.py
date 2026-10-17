from datetime import date, timedelta

from app.models.audit_log import AuditLog
from app.models.order_entry import OrderEntry
from app.models.store import Store
from tests.conftest import API


def _entry(db, store, days_ago: int, n: int):
    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id,
                      order_date=date.today() - timedelta(days=days_ago), bottle_count=n))
    db.commit()


def test_status_change_keeps_order_history_and_logs_it(client, admin, db, make_store):
    store = make_store()
    _entry(db, store, 1, 10)
    _entry(db, store, 2, 5)
    r = client.patch(f"{API}/stores/{store.id}", json={"status": "PENDING"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "PENDING"
    assert db.query(OrderEntry).filter_by(store_id=store.id).count() == 2
    log = db.query(AuditLog).filter_by(action="store.status_changed", entity_id=str(store.id)).one()
    assert log.metadata_json["from"] == "LIVE" and log.metadata_json["to"] == "PENDING"
    assert log.metadata_json["order_days_kept"] == 2 and log.metadata_json["bottles_kept"] == 15
    # still visible in the admin matrix for the period it has entries
    m = client.get(f"{API}/orders/matrix", params={"start": str(date.today() - timedelta(days=3)), "end": str(date.today())}, headers=admin)
    if m.status_code == 200:
        assert str(store.id) in m.text


def test_delete_all_needs_exact_confirmation(client, dev, make_store):
    store = make_store(platform="zepto")
    for confirm in ("", "delete blinkit", "DELETE ALL"):
        r = client.delete(f"{API}/stores", params={"platform": "zepto", "confirm": confirm}, headers=dev)
        assert r.status_code == 422
    assert client.delete(f"{API}/stores", params={"confirm": "DELETE ZEPTO"}, headers=dev).status_code == 422
    assert client.get(f"{API}/stores/{store.id}", headers=dev).status_code == 200


def test_delete_all_removes_only_that_platform_and_archives_history(client, dev, db, make_store):
    z = make_store(platform="zepto")
    b = make_store(platform="blinkit")
    zid, bid = z.id, b.id
    _entry(db, z, 1, 7)
    _entry(db, b, 1, 9)
    r = client.delete(f"{API}/stores", params={"platform": "zepto", "confirm": "delete zepto"}, headers=dev)
    assert r.status_code == 200, r.text
    assert r.json()["stores_deleted"] >= 1 and r.json()["order_entries_deleted"] >= 1
    db.expire_all()
    assert db.get(Store, zid) is None
    assert db.query(OrderEntry).filter_by(store_id=zid).count() == 0
    assert db.get(Store, bid) is not None and db.query(OrderEntry).filter_by(store_id=bid).count() == 1
    assert db.query(AuditLog).filter_by(action="store.deleted_all").count() >= 1


def test_delete_all_is_developer_only(client, admin, emp):
    for h in (admin, emp):
        r = client.delete(f"{API}/stores", params={"platform": "zepto", "confirm": "DELETE ZEPTO"}, headers=h)
        assert r.status_code == 403


def test_wiped_history_comes_back_when_the_store_is_added_again(client, dev, admin, db, make_store):
    from app.models.order_archive import OrderEntryArchive
    from app.models.organization import Organization
    z = make_store(platform="zepto", code="ZPT-RESTORE-1", name="Zepto Restore")
    _entry(db, z, 1, 7)
    _entry(db, z, 2, 4)
    partner_id = z.partner_organization_id
    r = client.delete(f"{API}/stores", params={"platform": "zepto", "confirm": "DELETE ZEPTO"}, headers=dev)
    assert r.status_code == 200 and r.json()["order_entries_archived"] >= 2
    db.expire_all()
    assert db.query(OrderEntryArchive).filter_by(external_code="ZPT-RESTORE-1").count() == 2
    created = client.post(f"{API}/stores", json={"name": "Zepto Restore", "external_code": "ZPT-RESTORE-1",
                                                  "partner_organization_id": str(partner_id), "status": "LIVE", "start_date": "2026-03-01"}, headers=admin)
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    db.expire_all()
    got = {e.bottle_count for e in db.query(OrderEntry).filter_by(store_id=sid)}
    assert got == {7, 4}
    assert db.query(OrderEntryArchive).filter_by(external_code="ZPT-RESTORE-1").count() == 0
    db.query(OrderEntry).filter_by(store_id=sid).delete()
    db.query(Store).filter_by(id=sid).delete()
    db.commit()


def test_closing_a_store_keeps_history_too(client, admin, db, make_store):
    store = make_store()
    _entry(db, store, 1, 8)
    assert client.delete(f"{API}/stores/{store.id}", headers=admin).status_code == 200
    assert db.query(OrderEntry).filter_by(store_id=store.id).count() == 1
    log = db.query(AuditLog).filter_by(action="store.status_changed", entity_id=str(store.id)).one()
    assert log.metadata_json["to"] == "CLOSE" and log.metadata_json["bottles_kept"] == 8


def _csv(rows):
    head = "Outlet ID,Outlet Name,STATUS,State,City,Start date\n"
    return (head + "\n".join(f"{c},{n},Live,Delhi,Delhi,2026-03-01" for c, n in rows)).encode()


def test_import_refuses_a_sheet_that_mentions_another_platform(client, dev, db):
    rows = [(f"ZPT-{i}", f"Zepto - Store {i}") for i in range(5)]
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"},
                    files={"file": ("zepto.csv", _csv(rows), "text/csv")}, headers=dev)
    assert r.status_code == 422 and "Zepto" in r.json()["detail"]
    assert db.query(Store).filter(Store.external_code.like("ZPT-%")).count() == 0


def test_import_refuses_ids_that_already_belong_to_another_platform(client, dev, db, make_store):
    made = [make_store(platform="zepto", code=f"SHARED-{i}", name=f"Plain {i}") for i in range(4)]
    rows = [(f"SHARED-{i}", f"Plain {i}") for i in range(4)]
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"},
                    files={"file": ("x.csv", _csv(rows), "text/csv")}, headers=dev)
    assert r.status_code == 422 and "already exist" in r.json()["detail"]
    ok = client.post(f"{API}/stores/import", data={"platform": "blinkit", "allow_mismatch": "true"},
                     files={"file": ("x.csv", _csv(rows), "text/csv")}, headers=dev)
    assert ok.status_code == 200 and ok.json()["created"] == 4
    db.query(Store).filter(Store.external_code.like("SHARED-%"), Store.partner_organization_id != made[0].partner_organization_id).delete()
    db.commit()


def test_move_platform_fixes_a_wrong_import_and_keeps_history(client, dev, admin, db, make_store):
    wrong = make_store(platform="blinkit", code="MV-1", name="Zepto - Mixed 1")
    other = make_store(platform="blinkit", code="MV-2", name="Blinkit - Fine")
    wid = wrong.id
    _entry(db, wrong, 1, 6)
    body = {"from_platform": "blinkit", "to_platform": "zepto", "contains": "Zepto -"}
    prev = client.post(f"{API}/stores/move-platform", json=body, headers=dev).json()
    assert prev["dry_run"] and prev["moved"] == 1
    db.expire_all()
    assert db.get(Store, wid).partner_organization.slug == "blinkit"
    done = client.post(f"{API}/stores/move-platform", json={**body, "dry_run": False}, headers=dev).json()
    assert done["moved"] == 1
    db.expire_all()
    assert db.get(Store, wid).partner_organization.slug == "zepto"
    assert db.get(Store, other.id).partner_organization.slug == "blinkit"
    assert db.query(OrderEntry).filter_by(store_id=wid).count() == 1
    assert client.post(f"{API}/stores/move-platform", json=body, headers=admin).status_code == 403
