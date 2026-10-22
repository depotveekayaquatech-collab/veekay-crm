"""Store names are the store's identity: unique per platform, never changed; Outlet IDs can be corrected; duplicates are listed."""
from datetime import date, timedelta

from app.models.order_entry import OrderEntry
from app.models.store import Store

from .conftest import API


def test_a_store_name_cannot_be_changed_by_anyone(client, admin, dev, make_store):
    s = make_store(code="NM-1", name="Fixed Name Mart")
    for who in (admin, dev):
        r = client.patch(f"{API}/stores/{s.id}", json={"name": "Another Name"}, headers=who)
        assert r.status_code == 422 and "can't be changed" in r.json()["detail"]
    same = client.patch(f"{API}/stores/{s.id}", json={"name": "  fixed name   mart ", "city": "Noida"}, headers=admin)
    assert same.status_code == 200 and same.json()["name"] == "Fixed Name Mart" and same.json()["city"] == "Noida"


def test_the_outlet_id_can_be_corrected_and_the_store_keeps_its_orders(client, admin, db, make_store):
    s = make_store(code="NM-TEMP", name="Id Fix Mart")
    db.add(OrderEntry(organization_id=s.organization_id, store_id=s.id, order_date=date.today() - timedelta(days=1), bottle_count=7, source="manual"))
    db.commit()
    r = client.patch(f"{API}/stores/{s.id}", json={"external_code": "NM-REAL"}, headers=admin)
    assert r.status_code == 200 and r.json()["external_code"] == "NM-REAL" and r.json()["name"] == "Id Fix Mart"
    assert db.query(OrderEntry).filter_by(store_id=s.id).count() == 1


def test_an_outlet_id_that_belongs_to_another_store_is_refused_clearly(client, admin, make_store):
    a = make_store(code="NM-A", name="Mart A")
    make_store(code="NM-B", name="Mart B")
    r = client.patch(f"{API}/stores/{a.id}", json={"external_code": "NM-B"}, headers=admin)
    assert r.status_code == 409 and "already belongs to another store" in r.json()["detail"]


def test_a_store_with_an_existing_name_cannot_be_added_by_hand(client, admin, make_store):
    s = make_store(code="NM-C", name="Taken Name Mart")
    body = {"name": "taken name  mart", "external_code": "NM-C2", "start_date": "2026-03-01", "partner_organization_id": str(s.partner_organization_id)}
    r = client.post(f"{API}/stores", json=body, headers=admin)
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


def test_order_import_finds_the_store_by_name_even_with_a_different_outlet_id(client, dev, db, make_store):
    temp = make_store(code="NM-TEMP-9", name="Blinkit - Order Name Mart")
    day = date.today() - timedelta(days=1)
    csv = f"Outlet ID,Outlet Name,{day}\nREAL-ID-9,blinkit - order  name mart,12\nGHOST-1,Blinkit - Nobody,5\n".encode()
    r = client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 1 and out["unknown_stores"] == 1
    assert "by Outlet Name" in out["warnings"][0] and "Blinkit - Nobody" in out["warnings"][0]
    assert db.query(OrderEntry).filter_by(store_id=temp.id, order_date=day).one().bottle_count == 12


def test_order_import_uses_the_id_only_when_the_sheet_has_no_name_column(client, dev, db, make_store):
    s = make_store(code="NM-ONLYID", name="Blinkit - Only Id Mart")
    day = date.today() - timedelta(days=1)
    csv = f"Outlet ID,{day}\nNM-ONLYID,4\n".encode()
    r = client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["created"] == 1
    assert db.query(OrderEntry).filter_by(store_id=s.id).count() == 1


def test_duplicates_are_listed_with_their_order_days(client, admin, db, make_store):
    a = make_store(code="NM-D1", name="Dup List Mart")
    make_store(code="NM-D2", name="Dup List Mart")
    make_store(code="nm d3", name="Id Lookalike A")
    make_store(code="NM-D3", name="Id Lookalike B")
    db.add(OrderEntry(organization_id=a.organization_id, store_id=a.id, order_date=date.today() - timedelta(days=1), bottle_count=3, source="manual"))
    db.commit()
    got = client.get(f"{API}/stores/duplicates", headers=admin).json()
    names = [g for g in got["groups"] if g["kind"] == "name" and g["label"] == "Dup List Mart"]
    assert len(names) == 1 and sorted(s["external_code"] for s in names[0]["stores"]) == ["NM-D1", "NM-D2"]
    assert {s["external_code"]: s["order_days"] for s in names[0]["stores"]} == {"NM-D1": 1, "NM-D2": 0}
    assert any(g["kind"] == "id" and len(g["stores"]) == 2 for g in got["groups"])
    assert got["total_groups"] >= 2 and got["total_stores"] >= 4


def test_merging_a_duplicate_keeps_every_order(client, dev, db, make_store):
    old = make_store(code="NM-M1", name="Merge Keep Mart")
    new = make_store(code="NM-M2", name="Merge Keep Mart")
    d1, d2 = date.today() - timedelta(days=2), date.today() - timedelta(days=1)
    for d, n in ((d1, 2), (d2, 5)):
        db.add(OrderEntry(organization_id=old.organization_id, store_id=old.id, order_date=d, bottle_count=n, source="manual"))
    db.commit()
    nid = new.id
    r = client.post(f"{API}/stores/merge", json={"platform": "blinkit", "dry_run": False, "pairs": [{"old_code": "NM-M1", "new_code": "NM-M2"}]}, headers=dev)
    assert r.status_code == 200 and r.json()["merged"] == 1
    assert sorted((e.order_date, e.bottle_count) for e in db.query(OrderEntry).filter_by(store_id=nid)) == [(d1, 2), (d2, 5)]
    assert db.query(Store).filter(Store.name == "Merge Keep Mart").count() == 1
