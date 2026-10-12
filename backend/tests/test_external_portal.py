"""Vendor / POC sign-in: tokens, refresh, logout, lockout, and that a login only ever sees its own stores."""
import uuid

import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.models.external_account import ExternalAccount, ExternalAccountStore
from app.models.organization import Organization
from tests.conftest import API, auth

PW = "123456"


@pytest.fixture()
def make_account(db, make_store):
    created: list[uuid.UUID] = []

    def _make(stores=(), kind="vendor", password=PW, active=True, must_change=True):
        org = db.query(Organization).filter_by(slug="veekay").one()
        a = ExternalAccount(
            organization_id=org.id, kind=kind, email=f"t{uuid.uuid4().hex[:8]}@supplier.com", full_name="Test Vendor",
            password_hash=hash_password(password), must_change_password=must_change, is_active=active, store_count=len(stores),
        )
        db.add(a)
        db.flush()
        for s in stores:
            db.add(ExternalAccountStore(account_id=a.id, store_id=s.id))
        db.commit()
        created.append(a.id)
        return a

    yield _make
    for aid in created:
        db.query(ExternalAccount).filter(ExternalAccount.id == aid).delete()
    db.commit()


def _login(client, email, password=PW, **headers):
    return client.post(f"{API}/external/auth/login", json={"email": email, "password": password}, headers=headers)


def test_login_works_even_with_must_change_flag_and_no_password_change(client, make_account):
    a = make_account(must_change=True)
    r = _login(client, a.email.upper())
    assert r.status_code == 200, r.text
    assert r.json()["access_token"] and r.json()["refresh_token"]
    me = client.get(f"{API}/external/me", headers=auth(r.json()["access_token"]))
    assert me.status_code == 200 and me.json()["email"] == a.email
    assert "must_change_password" not in me.json()


def test_wrong_password_and_unknown_account_get_the_same_error(client, make_account):
    a = make_account()
    bad = _login(client, a.email, "nope")
    unknown = _login(client, "nobody@supplier.com")
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()


def test_lockout_after_repeated_wrong_passwords(client, make_account):
    a = make_account()
    for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
        assert _login(client, a.email, "wrong").status_code == 401
    assert _login(client, a.email, PW).status_code == 403  # even the right password waits out the lock


def test_deactivated_account_cannot_sign_in(client, make_account):
    assert _login(client, make_account(active=False).email).status_code == 403


def test_only_own_stores_are_visible(client, make_account, make_store):
    mine, other = make_store(), make_store()
    a = make_account(stores=[mine])
    b = make_account(stores=[other])
    tok = _login(client, a.email).json()["access_token"]
    got = client.get(f"{API}/external/stores", headers=auth(tok))
    assert [s["id"] for s in got.json()] == [str(mine.id)]
    tok_b = _login(client, b.email).json()["access_token"]
    assert [s["id"] for s in client.get(f"{API}/external/stores", headers=auth(tok_b)).json()] == [str(other.id)]


def test_tokens_do_not_cross_between_staff_and_vendors(client, admin, make_account):
    assert client.get(f"{API}/external/me", headers=admin).status_code == 401
    tok = _login(client, make_account().email).json()["access_token"]
    assert client.get(f"{API}/auth/me", headers=auth(tok)).status_code == 401
    assert client.get(f"{API}/external/stores").status_code == 401


def test_refresh_rotates_and_reuse_kills_the_session(client, make_account, monkeypatch):
    monkeypatch.setattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 0)
    first = _login(client, make_account().email).json()
    second = client.post(f"{API}/external/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200 and second.json()["refresh_token"] != first["refresh_token"]
    # the old token again = copied token: refused, and the whole session ends
    import time; time.sleep(1.1)
    assert client.post(f"{API}/external/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.post(f"{API}/external/auth/refresh", json={"refresh_token": second.json()["refresh_token"]}).status_code == 401
    assert client.get(f"{API}/external/me", headers=auth(second.json()["access_token"])).status_code == 401


def test_logout_ends_the_session_immediately(client, make_account):
    t = _login(client, make_account().email).json()
    assert client.post(f"{API}/external/auth/logout", json={"refresh_token": t["refresh_token"]}).status_code == 204
    assert client.get(f"{API}/external/me", headers=auth(t["access_token"])).status_code == 401
    assert client.post(f"{API}/external/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_cookie_mode_keeps_the_refresh_token_out_of_the_body(client, make_account):
    r = _login(client, make_account().email, **{"X-Auth-Mode": "cookie"})
    assert r.status_code == 200 and r.json()["refresh_token"] is None
    assert "vk_ext_refresh" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    assert client.post(f"{API}/external/auth/refresh", headers={"X-Auth-Mode": "cookie"}).status_code == 200
    client.cookies.clear()


# ------------------------------------------------------------------ Phase 2: read-only data

@pytest.fixture()
def world(client, db, make_account, make_store):
    """Two stores (each with a POC and a vendor), each carrying an order, a ticket (+comment), a bill and a bottle."""
    from datetime import date

    from app.core import storage
    from app.models.bottle import Bottle, BottleStatus
    from app.models.compliance_document import ComplianceDocument
    from app.models.order_entry import OrderEntry
    from app.models.ticket import Ticket, TicketComment

    org = db.query(Organization).filter_by(slug="veekay").one()
    out = {}
    made_bottles = []
    for tag, count in (("a", 7), ("b", 11)):
        st = make_store()
        db.add(OrderEntry(organization_id=org.id, store_id=st.id, order_date=date.today(), bottle_count=count, cash_adjustment=3))
        t = Ticket(organization_id=org.id, store_id=st.id, partner_organization_id=st.partner_organization_id,
                   category="SHORT_SUPPLY", title=f"Short {tag}", description="d")
        db.add(t)
        db.flush()
        db.add(TicketComment(ticket_id=t.id, body=f"note {tag}"))
        key = f"test/{uuid.uuid4().hex}.pdf"
        storage.save(key, b"%PDF-1.4 " + tag.encode())
        doc = ComplianceDocument(organization_id=org.id, store_id=st.id, month=date.today().replace(day=1), kind="bill", file_key=key,
                                 file_name=f"{tag}.pdf", content_type="application/pdf", size_bytes=10, status="PENDING")
        b = Bottle(organization_id=org.id, serial=f"T{uuid.uuid4().hex[:7].upper()}", status=BottleStatus.AT_STORE, current_store_id=st.id)
        db.add_all([doc, b])
        db.commit()
        made_bottles.append(b.id)
        out[tag] = dict(store=st, ticket=t, doc=doc, account=make_account(stores=[st], kind="poc"), vendor=make_account(stores=[st], kind="vendor"))
    yield out
    db.query(Bottle).filter(Bottle.id.in_(made_bottles)).delete()
    db.commit()


def _tok(client, acct):
    return auth(_login(client, acct.email).json()["access_token"])


def test_each_login_reads_only_its_own_data(client, world):
    a, b = world["a"], world["b"]
    h = _tok(client, a["account"])

    o = client.get(f"{API}/external/orders", headers=h).json()
    assert [r["bottle_count"] for r in o["items"]] == [7] and o["total_bottles"] == 7  # bottle_count is already the final number; the adjustment is not exposed
    assert "cash_adjustment" not in o["items"][0]

    t = client.get(f"{API}/external/tickets", headers=h).json()
    assert [x["id"] for x in t["items"]] == [str(a["ticket"].id)]
    d = client.get(f"{API}/external/tickets/{a['ticket'].id}", headers=h).json()
    assert d["comments"][0]["body"] == "note a" and "assigned_to" not in d

    docs = client.get(f"{API}/external/documents", headers=h).json()
    assert [x["id"] for x in docs["items"]] == [str(a["doc"].id)] and docs["items"][0]["status"] == "PENDING"
    f = client.get(f"{API}/external/documents/{a['doc'].id}/file", headers=h)
    assert f.status_code == 200 and f.content.endswith(b" a")

    bt = client.get(f"{API}/external/bottles", headers=h).json()
    assert bt["total"] == 1 and set(bt["per_store"]) == {str(a["store"].id)}

    # the other vendor's things are invisible, whether asked for by store or by id
    assert client.get(f"{API}/external/tickets/{b['ticket'].id}", headers=h).status_code == 404
    assert client.get(f"{API}/external/documents/{b['doc'].id}/file", headers=h).status_code == 404
    for path in ("orders", "tickets", "documents", "bottles"):
        assert client.get(f"{API}/external/{path}", params={"store_id": str(b["store"].id)}, headers=h).status_code == 404


def test_data_routes_need_a_vendor_token(client, admin, world):
    for path in ("orders", "tickets", "documents", "bottles"):
        assert client.get(f"{API}/external/{path}").status_code == 401
        assert client.get(f"{API}/external/{path}", headers=admin).status_code == 401


def test_order_range_is_capped_and_archived_documents_are_hidden(client, db, world):
    from datetime import datetime, timezone
    h = _tok(client, world["a"]["account"])
    assert client.get(f"{API}/external/orders", params={"date_from": "2020-01-01"}, headers=h).status_code == 422
    world["a"]["doc"].deleted_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get(f"{API}/external/documents", headers=h).json()["total"] == 0
    assert client.get(f"{API}/external/documents/{world['a']['doc'].id}/file", headers=h).status_code == 404
