"""Idempotency keys: a retry with the same Idempotency-Key returns the original result and creates nothing new."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.cash_purchase import CashPurchase
from app.models.compliance_document import ComplianceDocumentVersion
from app.models.idempotency_key import IdempotencyKey
from app.models.ticket import Ticket, TicketComment

from .conftest import API, jpeg
from .test_external_actions import _photo, _raise
from .test_external_portal import _tok, make_account, world  # noqa: F401  (fixtures)

KEY = "retry-key-0001"


@pytest.fixture(autouse=True)
def _wipe(db):
    yield
    db.query(IdempotencyKey).delete()
    db.query(CashPurchase).delete()
    db.commit()


def _h(h, key=KEY):
    return {**h, "Idempotency-Key": key}


def _count_tickets(db):
    db.expire_all()
    return db.query(Ticket).count()


def test_ticket_retry_with_same_key_returns_original_and_makes_one_ticket(client, db, world):
    a = world["a"]
    h = _tok(client, a["account"])
    before = _count_tickets(db)
    first = _raise(client, _h(h), a["store"])
    again = _raise(client, _h(h), a["store"])
    assert first.status_code == 201 and again.status_code == 201
    assert again.json()["id"] == first.json()["id"]
    assert _count_tickets(db) == before + 1


def test_without_a_key_or_with_a_new_key_behaviour_is_unchanged(client, db, world):
    a = world["a"]
    h = _tok(client, a["account"])
    before = _count_tickets(db)
    assert _raise(client, h, a["store"]).status_code == 201           # no header: as before
    assert _raise(client, h, a["store"]).status_code == 201
    assert _raise(client, _h(h, "another-key-001"), a["store"]).status_code == 201
    assert _count_tickets(db) == before + 3


def test_reply_retry_adds_one_comment(client, db, world):
    a = world["a"]
    h = _tok(client, a["account"])
    t = _raise(client, h, a["store"]).json()
    url = f"{API}/external/tickets/{t['id']}/comments"
    r1 = client.post(url, data={"body": "Any update?"}, files=[_photo()], headers=_h(h))
    r2 = client.post(url, data={"body": "Any update?"}, files=[_photo()], headers=_h(h))
    assert r1.status_code == 201 and r2.status_code == 201 and r2.json() == r1.json()
    db.expire_all()
    assert db.query(TicketComment).filter_by(ticket_id=t["id"]).count() == 1


def test_document_retry_adds_no_extra_version(client, db, world):
    a = world["a"]
    h = _tok(client, a["account"])
    f = [("files", ("c.jpg", jpeg(), "image/jpeg"))]
    data = {"store_id": str(a["store"].id), "kind": "payment"}
    r1 = client.post(f"{API}/external/documents", data=data, files=f, headers=_h(h))
    db.expire_all()
    versions = db.query(ComplianceDocumentVersion).count()
    r2 = client.post(f"{API}/external/documents", data=data, files=f, headers=_h(h))
    assert r1.status_code == 201 and r2.status_code == 201 and r2.json()["id"] == r1.json()["id"]
    db.expire_all()
    assert db.query(ComplianceDocumentVersion).count() == versions     # a plain re-upload WOULD have added one


def _purchase(client, h, key=None):
    body = {"kind": "OFFICE", "purchase_date": date.today().isoformat(), "category": "MILK", "amount": "120.50"}
    return client.post(f"{API}/cash-purchases", data=body, files={"proof": ("p.jpg", jpeg(), "image/jpeg")},
                       headers=_h(h, key) if key else h)


def test_cash_purchase_retry_records_it_once(client, db, emp):
    r1 = _purchase(client, emp, KEY)
    r2 = _purchase(client, emp, KEY)
    assert r1.status_code == 201 and r2.status_code == 201 and r2.json()["id"] == r1.json()["id"]
    assert db.query(CashPurchase).count() == 1
    assert _purchase(client, emp).status_code == 201                    # without a key it is a new purchase, as before
    assert db.query(CashPurchase).count() == 2


def test_keys_do_not_collide_between_people(client, db, emp, admin):
    r1 = _purchase(client, emp, KEY)
    r2 = _purchase(client, admin, KEY)
    assert r1.status_code == 201 and r2.status_code == 201 and r1.json()["id"] != r2.json()["id"]


def test_a_failed_request_frees_its_key_for_the_retry(client, db, emp):
    bad = {"kind": "OFFICE", "purchase_date": date.today().isoformat(), "category": "NOT_A_CATEGORY", "amount": "5"}
    r = client.post(f"{API}/cash-purchases", data=bad, files={"proof": ("p.jpg", jpeg(), "image/jpeg")}, headers=_h(emp))
    assert r.status_code >= 400
    assert db.query(IdempotencyKey).count() == 0
    assert _purchase(client, emp, KEY).status_code == 201               # same key, now valid: runs normally


def test_a_malformed_key_is_rejected(client, emp):
    assert _purchase(client, emp, "short").status_code == 422
    assert _purchase(client, emp, "has spaces in it!!").status_code == 422


def test_in_progress_key_gets_409_and_an_abandoned_one_is_taken_over(client, db, emp):
    owner_id = client.get(f"{API}/auth/me", headers=emp).json()["id"]
    db.add(IdempotencyKey(owner=str(owner_id), endpoint="cash.purchase.create", key=KEY, state="pending"))
    db.commit()
    assert _purchase(client, emp, KEY).status_code == 409               # first request still running
    db.query(IdempotencyKey).update({"created_at": datetime.now(timezone.utc) - timedelta(minutes=10)})
    db.commit()
    assert _purchase(client, emp, KEY).status_code == 201               # abandoned: processed normally
    assert db.query(CashPurchase).count() == 1
