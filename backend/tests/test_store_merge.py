"""Merging a temporary-ID store into the store created with the real Outlet ID (developer only)."""
from datetime import date, timedelta

from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.ticket import Ticket  # noqa: F401  (import keeps the table registered)

from .conftest import API


def _mark(db, store, day, n):
    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=day, bottle_count=n, source="manual"))
    db.commit()


def _body(old, new, **kw):
    return {"platform": "blinkit", "pairs": [{"old_code": old.external_code, "new_code": new.external_code}], **kw}


def test_orders_move_to_the_new_store_and_the_temporary_one_is_removed(client, db, dev, make_store):
    old = make_store(code="TMP-1", name="Merge Mart", status="LIVE")
    new = make_store(code="REAL-1", name="Merge Mart", status="PENDING", vendor=None, state="Delhi", city=None)
    old.city, old.start_date = "Noida", date.today() - timedelta(days=40)
    db.commit()
    d1, d2 = date.today() - timedelta(days=2), date.today() - timedelta(days=1)
    _mark(db, old, d1, 4)
    _mark(db, old, d2, 6)
    old_id, new_id = old.id, new.id

    prev = client.post(f"{API}/stores/merge", json=_body(old, new), headers=dev).json()
    assert prev["dry_run"] is True and prev["merged"] == 1 and prev["results"][0]["moved"]["order days"] == 2
    db.expire_all()
    assert db.get(Store, old_id) is not None                                    # a preview changes nothing

    done = client.post(f"{API}/stores/merge", json=_body(old, new, dry_run=False), headers=dev).json()
    assert done["merged"] == 1 and done["results"][0]["ok"] is True
    db.expire_all()
    assert db.get(Store, old_id) is None
    kept = db.get(Store, new_id)
    assert kept.external_code == "REAL-1"
    assert sorted((e.order_date, e.bottle_count) for e in db.query(OrderEntry).filter_by(store_id=new_id)) == [(d1, 4), (d2, 6)]
    assert kept.city == "Noida" and kept.start_date == date.today() - timedelta(days=40)   # blanks filled from the old store
    assert kept.status == "LIVE"                                                            # a fresh Pending store takes the old status


def test_a_pair_that_would_overwrite_data_is_refused_and_left_alone(client, db, dev, make_store):
    old = make_store(code="TMP-2", name="Clash Mart")
    new = make_store(code="REAL-2", name="Clash Mart")
    day = date.today() - timedelta(days=1)
    _mark(db, old, day, 3)
    _mark(db, new, day, 9)
    old_id = old.id
    r = client.post(f"{API}/stores/merge", json=_body(old, new, dry_run=False), headers=dev).json()
    assert r["merged"] == 0 and "both stores" in r["results"][0]["reason"]
    db.expire_all()
    assert db.get(Store, old_id) is not None
    assert db.query(OrderEntry).filter_by(store_id=old_id).count() == 1


def test_unknown_ids_and_repeats_are_reported_not_fatal(client, dev, make_store):
    a = make_store(code="TMP-3", name="Pair A")
    b = make_store(code="REAL-3", name="Pair A")
    body = {"platform": "blinkit", "dry_run": True, "pairs": [
        {"old_code": a.external_code, "new_code": b.external_code},
        {"old_code": "NOPE", "new_code": b.external_code},
        {"old_code": a.external_code, "new_code": a.external_code},
    ]}
    r = client.post(f"{API}/stores/merge", json=body, headers=dev).json()
    assert [x["ok"] for x in r["results"]] == [True, False, False]
    assert "not found" in r["results"][1]["reason"] and "same" in r["results"][2]["reason"]


def test_suggestions_pair_stores_that_share_a_name(client, dev, make_store):
    make_store(code="TMP-4", name="Twin Outlet")
    make_store(code="REAL-4", name="Twin Outlet")
    make_store(code="SOLO-4", name="Only One Outlet")
    got = [s for s in client.get(f"{API}/stores/merge-suggestions", params={"platform": "blinkit"}, headers=dev).json() if s["name"] == "Twin Outlet"]
    assert len(got) == 1 and got[0]["old_code"] == "TMP-4" and got[0]["new_code"] == "REAL-4"


def test_only_the_developer_can_merge(client, admin, make_store):
    a, b = make_store(name="X1"), make_store(name="X1")
    assert client.post(f"{API}/stores/merge", json=_body(a, b), headers=admin).status_code == 403
    assert client.get(f"{API}/stores/merge-suggestions", params={"platform": "blinkit"}, headers=admin).status_code == 403
