"""Store import: a store made under a temporary Outlet ID is found again by its Outlet Name and gets the real ID."""
from datetime import date, timedelta

from app.models.order_entry import OrderEntry
from app.models.store import Store
from tests.conftest import API

from .test_store_import_limits import _xlsx


def _import(client, dev, rows):
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.xlsx", _xlsx(rows), "application/octet-stream")}, headers=dev)
    assert r.status_code == 200, r.text
    return r.json()


def test_real_outlet_id_replaces_the_temporary_one_and_keeps_the_orders(client, dev, db, make_store):
    temp = make_store(code="TEMP-77", name="Blinkit - Rename Mart", state="Delhi")
    day = date.today() - timedelta(days=1)
    db.add(OrderEntry(organization_id=temp.organization_id, store_id=temp.id, order_date=day, bottle_count=5, source="manual"))
    db.commit()
    tid = temp.id

    out = _import(client, dev, [["REAL-77", "Blinkit - Rename Mart", "Live", "Delhi", "Delhi", "2026-03-01"]])
    assert out["created"] == 0 and out["updated"] == 1
    assert "matched by Outlet Name" in out["warnings"][0] and "TEMP-77 → REAL-77" in out["warnings"][0]

    db.expire_all()
    s = db.get(Store, tid)
    assert s.external_code == "REAL-77"                                   # same store, new Outlet ID
    assert db.query(OrderEntry).filter_by(store_id=tid).count() == 1      # its orders stayed
    assert db.query(Store).filter(Store.name == "Blinkit - Rename Mart").count() == 1

    again = _import(client, dev, [["REAL-77", "Blinkit - Rename Mart", "Live", "Delhi", "Delhi", "2026-03-01"]])
    assert again["created"] == 0 and again["unchanged"] == 1              # a repeat changes nothing


def test_name_match_ignores_case_and_spacing(client, dev, db, make_store):
    temp = make_store(code="TEMP-78", name="Blinkit -  Spacing   Mart")
    _import(client, dev, [["REAL-78", "blinkit - spacing mart", "Live", "Delhi", "Delhi", "2026-03-01"]])
    db.expire_all()
    assert db.get(Store, temp.id).external_code == "REAL-78"


def test_ambiguous_names_are_not_guessed(client, dev, db, make_store):
    a = make_store(code="TEMP-79A", name="Blinkit - Twin Mart")
    b = make_store(code="TEMP-79B", name="Blinkit - Twin Mart")           # two stores share the name
    out = _import(client, dev, [["REAL-79", "Blinkit - Twin Mart", "Live", "Delhi", "Delhi", "2026-03-01"]])
    assert out["created"] == 1                                            # added as new instead of renaming the wrong one
    db.expire_all()
    assert db.get(Store, a.id).external_code == "TEMP-79A" and db.get(Store, b.id).external_code == "TEMP-79B"
    db.query(Store).filter(Store.external_code == "REAL-79").delete()
    db.commit()


def test_a_store_whose_id_is_still_in_the_sheet_is_never_renamed(client, dev, db, make_store):
    keep = make_store(code="KEEP-80", name="Blinkit - Same Name")
    out = _import(client, dev, [
        ["KEEP-80", "Blinkit - Same Name", "Live", "Delhi", "Delhi", "2026-03-01"],
        ["NEW-80", "Blinkit - Same Name", "Live", "Delhi", "Delhi", "2026-03-01"],     # another outlet that shares the name
    ])
    assert out["created"] == 1
    db.expire_all()
    assert db.get(Store, keep.id).external_code == "KEEP-80"
    db.query(Store).filter(Store.external_code == "NEW-80").delete()
    db.commit()
