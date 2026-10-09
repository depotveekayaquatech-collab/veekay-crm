"""Bottle QR tracking: unique serials, labels, IN/OUT scans, overdue (possibly lost), replacement, external API."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.bottle import Bottle, BottleBatch, BottleScan
from app.models.store import Store
from app.services.bottle_service import normalize_serial

from .conftest import API

B = f"{API}/bottles"


@pytest.fixture(autouse=True)
def _wipe(db):
    yield
    db.query(BottleScan).delete()
    db.query(Bottle).update({"replaces_id": None, "replaced_by_id": None})
    db.query(Bottle).delete()
    db.query(BottleBatch).delete()
    db.commit()


@pytest.fixture()
def store(db):
    return db.query(Store).filter_by(external_code="BLK-4821").one()


def _generate(client, admin, n=5):
    r = client.post(f"{B}/batches", json={"quantity": n}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _serials(client, admin, n=5):
    batch = _generate(client, admin, n)
    r = client.get(f"{B}/batches/{batch['id']}/serials.csv", headers=admin)
    assert r.status_code == 200
    return batch, [line.split(",")[1] for line in r.text.strip().splitlines()[1:]]


def _scan(client, admin, serial, direction, store=None, **kw):
    body = {"serial": serial, "direction": direction, **kw}
    if store is not None:
        body["store_id"] = str(store.id)
    return client.post(f"{B}/scan", json=body, headers=admin)


def test_generate_unique_serials_and_labels(client, admin):
    batch, serials = _serials(client, admin, 120)
    assert len(serials) == len(set(serials)) == 120
    assert all(s.startswith("VK-") and len(s) == 12 for s in serials)
    assert batch["quantity"] == 120 and batch["first_serial"] == serials[0] and batch["last_serial"] == serials[-1]
    pdf = client.get(f"{B}/batches/{batch['id']}/labels.pdf?start=1&count=45", headers=admin)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"{B}/batches/{batch['id']}/labels.pdf?start=500", headers=admin).status_code == 404
    again = _generate(client, admin, 120)
    assert again["first_serial"] not in serials


def test_serial_normalisation():
    assert normalize_serial("vk-7f3k-9q2m") == "VK-7F3K-9Q2M"
    assert normalize_serial("VK7F3K9Q2M") == "VK-7F3K-9Q2M"
    assert normalize_serial("vk-oi3k-9q2m") == "VK-013K-9Q2M"      # O->0, I->1 when typed by hand
    with pytest.raises(Exception):
        normalize_serial("nonsense12")


def test_in_then_out_and_unused_is_never_overdue(client, admin, store):
    _, serials = _serials(client, admin, 3)
    a = serials[0]
    r = _scan(client, admin, a, "IN", store)
    assert r.status_code == 200, r.text
    assert r.json()["bottle"]["status"] == "AT_STORE" and r.json()["warning"] is None
    assert r.json()["bottle"]["store_name"] == store.name
    r = _scan(client, admin, a.lower(), "OUT")                       # OUT needs no store: it uses the one it is at
    assert r.json()["bottle"]["status"] == "RETURNED" and r.json()["scan"]["store_name"] == store.name
    s = client.get(f"{B}/summary", headers=admin).json()
    assert (s["unused"], s["returned"], s["at_store"], s["overdue"]) == (2, 1, 0, 0)
    hist = client.get(f"{B}/lookup/{a}", headers=admin).json()
    assert [x["direction"] for x in hist["scans"]] == ["OUT", "IN"]


def test_in_without_out_becomes_overdue(client, admin, store, db):
    _, serials = _serials(client, admin, 3)
    long_ago = (datetime.now(timezone.utc) - timedelta(days=settings.BOTTLE_LOST_AFTER_DAYS + 5)).isoformat()
    assert _scan(client, admin, serials[0], "IN", store, scanned_at=long_ago).status_code == 200
    assert _scan(client, admin, serials[1], "IN", store).status_code == 200      # fresh: not overdue yet
    over = client.get(f"{B}?state=OVERDUE", headers=admin).json()
    assert [b["serial"] for b in over["items"]] == [serials[0]] and over["items"][0]["overdue"] is True
    assert over["items"][0]["days_at_store"] >= settings.BOTTLE_LOST_AFTER_DAYS + 5
    assert client.get(f"{B}?state=OVERDUE&overdue_days=0", headers=admin).json()["total"] == 2
    assert client.get(f"{B}/summary", headers=admin).json()["overdue"] == 1
    _scan(client, admin, serials[0], "OUT")                                       # coming back clears it
    assert client.get(f"{B}?state=OVERDUE", headers=admin).json()["total"] == 0


def test_out_of_order_scans_warn_but_are_recorded(client, admin, store):
    _, serials = _serials(client, admin, 1)
    s = serials[0]
    assert "No IN scan" in _scan(client, admin, s, "OUT", store).json()["warning"]
    _scan(client, admin, s, "IN", store)
    assert "Already scanned IN" in _scan(client, admin, s, "IN", store).json()["warning"]
    assert len(client.get(f"{B}/lookup/{s}", headers=admin).json()["scans"]) == 3


def test_in_needs_a_store_and_unknown_code_is_404(client, admin, store):
    _, serials = _serials(client, admin, 1)
    assert _scan(client, admin, serials[0], "IN").status_code == 422
    assert _scan(client, admin, "VK-0000-0000", "IN", store).status_code == 404
    assert _scan(client, admin, "garbage", "IN", store).status_code == 422


def test_scan_id_makes_retries_safe_and_late_scans_dont_rewind(client, admin, store):
    _, serials = _serials(client, admin, 1)
    s = serials[0]
    first = _scan(client, admin, s, "IN", store, scan_id="x-1").json()
    again = _scan(client, admin, s, "IN", store, scan_id="x-1").json()
    assert again["duplicate"] is True and again["scan"]["id"] == first["scan"]["id"]
    assert len(client.get(f"{B}/lookup/{s}", headers=admin).json()["scans"]) == 1
    _scan(client, admin, s, "OUT")
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    late = _scan(client, admin, s, "IN", store, scanned_at=old).json()             # an old offline scan arrives late
    assert late["bottle"]["status"] == "RETURNED"
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert _scan(client, admin, s, "IN", store, scanned_at=future).status_code == 422


def test_replace_damaged_qr_keeps_the_bottle_going(client, admin, store):
    _, serials = _serials(client, admin, 1)
    old = serials[0]
    _scan(client, admin, old, "IN", store)
    r = client.post(f"{B}/{old}/replace", json={"reason": "torn"}, headers=admin)
    assert r.status_code == 200, r.text
    new = r.json()["new"]
    assert new["serial"] != old and new["status"] == "AT_STORE" and new["store_name"] == store.name and new["replaces_serial"] == old
    assert r.json()["old"]["status"] == "RETIRED" and r.json()["old"]["replaced_by_serial"] == new["serial"]
    dead = _scan(client, admin, old, "OUT")
    assert dead.status_code == 409 and new["serial"] in dead.json()["detail"]
    assert _scan(client, admin, new["serial"], "OUT").json()["bottle"]["status"] == "RETURNED"
    assert client.post(f"{B}/{old}/replace", json={}, headers=admin).status_code == 409
    assert client.get(f"{B}/{new['serial']}/label.pdf", headers=admin).content.startswith(b"%PDF")
    # a retired code is not a missing bottle
    assert client.get(f"{B}/summary", headers=admin).json()["overdue"] == 0


def test_retire(client, admin, store):
    _, serials = _serials(client, admin, 1)
    _scan(client, admin, serials[0], "IN", store)
    r = client.post(f"{B}/{serials[0]}/retire", json={"reason": "confirmed lost"}, headers=admin)
    assert r.json()["status"] == "RETIRED" and r.json()["retire_reason"] == "confirmed lost"
    assert _scan(client, admin, serials[0], "OUT").status_code == 409


def test_permissions(client, admin, emp, store):
    assert client.post(f"{B}/batches", json={"quantity": 2}, headers=emp).status_code == 403
    assert client.get(f"{B}/summary", headers=emp).status_code == 403
    _, serials = _serials(client, admin, 1)
    assert _scan(client, emp, serials[0], "IN", store).status_code == 403
    assert client.post(f"{B}/batches", json={"quantity": 0}, headers=admin).status_code == 422
    assert client.post(f"{B}/batches", json={"quantity": 200001}, headers=admin).status_code == 422


def test_external_api(client, admin, store, monkeypatch):
    _, serials = _serials(client, admin, 2)
    url = f"{API}/integrations/bottles"
    body = {"serial": serials[0], "direction": "IN", "store_code": store.external_code, "scan_id": "ext-1", "scanned_by": "Gun 7"}
    monkeypatch.setattr(settings, "BOTTLE_API_KEY", "")
    assert client.post(f"{url}/scan", json=body, headers={"X-Integration-Key": "k"}).status_code == 503
    monkeypatch.setattr(settings, "BOTTLE_API_KEY", "secret-bottle-key")
    assert client.post(f"{url}/scan", json=body).status_code == 401
    assert client.post(f"{url}/scan", json=body, headers={"X-Integration-Key": "wrong"}).status_code == 401
    h = {"X-Integration-Key": "secret-bottle-key"}
    r = client.post(f"{url}/scan", json=body, headers=h)
    assert r.status_code == 200 and r.json()["bottle"]["status"] == "AT_STORE" and r.json()["scan"]["source"] == "api"
    assert client.post(f"{url}/scan", json=body, headers=h).json()["duplicate"] is True
    assert client.post(f"{url}/scan", json={**body, "scan_id": "ext-2", "store_code": "NOPE"}, headers=h).status_code == 422
    d = client.get(f"{url}/{serials[0]}", headers=h).json()
    assert d["bottle"]["store_name"] == store.name and d["scans"][0]["scanned_by_name"] == "Gun 7"
    assert client.get(f"{url}/overdue?days=0", headers=h).json()["total"] == 1


def test_scan_store_list(client, admin, emp):
    r = client.get(f"{B}/stores", headers=admin)
    assert r.status_code == 200 and any(s["code"] == "BLK-4821" for s in r.json())
    assert client.get(f"{B}/stores", headers=emp).status_code == 403


def test_deleted_codes_stop_working_but_keep_their_history(client, admin, dev, store, db):
    batch, serials = _serials(client, admin, 4)
    _scan(client, admin, serials[0], "IN", store)                      # one is in circulation, three were never used
    # admins can't delete; the developer can
    assert client.post(f"{B}/delete", json={"serials": [serials[1]]}, headers=admin).status_code == 403
    assert client.post(f"{B}/batches/{batch['id']}/delete", json={}, headers=admin).status_code == 403
    # one code, with a reason
    r = client.post(f"{B}/delete", json={"serials": [serials[1].lower(), "VK-0000-0000", "junk"], "reason": "misprinted"}, headers=dev).json()
    assert r["deleted"] == 1 and len(r["not_found"]) == 2
    # it can never be scanned again, and it can't be replaced or retired either
    dead = _scan(client, admin, serials[1], "IN", store)
    assert dead.status_code == 409 and "deleted" in dead.json()["detail"]
    assert client.post(f"{B}/{serials[1]}/replace", json={}, headers=admin).status_code == 409
    # ...but the record is still there, with its reason
    d = client.get(f"{B}/lookup/{serials[1]}", headers=admin).json()["bottle"]
    assert d["status"] == "DELETED" and d["retire_reason"] == "misprinted" and d["retired_at"]
    assert client.post(f"{B}/delete", json={"serials": [serials[1]]}, headers=dev).json() == {"deleted": 0, "already_deleted": 1, "skipped_in_use": [], "not_found": []}
    # a batch delete voids the never-used codes and leaves the one in circulation alone
    r = client.post(f"{B}/batches/{batch['id']}/delete", json={}, headers=dev).json()
    assert r["deleted"] == 2 and r["skipped_in_use"] == [serials[0]]
    assert client.get(f"{B}/lookup/{serials[0]}", headers=admin).json()["bottle"]["status"] == "AT_STORE"
    # an in-circulation code can still be deleted on purpose: its scan history survives
    assert client.post(f"{B}/delete", json={"serials": [serials[0]]}, headers=dev).json()["deleted"] == 1
    h = client.get(f"{B}/lookup/{serials[0]}", headers=admin).json()
    assert h["bottle"]["status"] == "DELETED" and [x["direction"] for x in h["scans"]] == ["IN"]
    assert db.query(BottleScan).count() == 1 and db.query(Bottle).count() == 4 and db.query(BottleBatch).count() == 1
    # counted separately, hidden from "all", shown when asked for, never overdue, serial can't come back
    s = client.get(f"{B}/summary", headers=admin).json()
    assert (s["deleted"], s["total_active"], s["overdue"], s["at_store"]) == (4, 0, 0, 0)
    assert client.get(f"{B}", headers=admin).json()["total"] == 0
    assert client.get(f"{B}?state=DELETED", headers=admin).json()["total"] == 4
    assert db.query(Bottle).filter_by(serial=serials[0]).count() == 1
