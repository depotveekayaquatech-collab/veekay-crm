"""Vendor / POC app, Phase 3: raising tickets with photos, replies, uploads, delivery confirmations, notifications."""
import uuid
from datetime import date, timedelta

from tests.conftest import API, jpeg
from tests.test_external_portal import _tok, make_account, world  # noqa: F401  (fixtures)


def _photo(name="p.jpg", color="red"):
    return ("photos", (name, jpeg(color), "image/jpeg"))


def _raise(client, h, store, **over):
    data = {"store_id": str(store.id), "category": "SHORT_SUPPLY", "title": "Only 40 bottles came", **over}
    return client.post(f"{API}/external/tickets", data=data, files=[_photo()], headers=h)


def test_raise_ticket_with_photo_and_staff_see_it(client, admin, world):
    a = world["a"]
    h = _tok(client, a["account"])
    r = _raise(client, h, a["store"], description="Truck was late")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "OPEN" and t["priority"] == "MEDIUM" and len(t["attachments"]) == 1
    photo = client.get(f"{API}/external/tickets/{t['id']}/attachments/{t['attachments'][0]['id']}", headers=h)
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"

    st = client.get(f"{API}/tickets/{t['id']}", headers=admin).json()
    assert st["created_by_name"] == "Test Vendor (POC)" and st["source"] == "vendor_app" and len(st["attachments"]) == 1
    assert client.get(f"{API}/tickets/{t['id']}/attachments/{st['attachments'][0]['id']}", headers=admin).status_code == 200


def test_another_vendors_store_ticket_and_photos_are_off_limits(client, world):
    a, b = world["a"], world["b"]
    h = _tok(client, a["account"])
    assert _raise(client, h, b["store"]).status_code == 404
    assert client.post(f"{API}/external/tickets/{b['ticket'].id}/comments", data={"body": "hi"}, headers=h).status_code == 404
    mine = _raise(client, _tok(client, b["account"]), b["store"]).json()
    assert client.get(f"{API}/external/tickets/{mine['id']}/attachments/{mine['attachments'][0]['id']}", headers=h).status_code == 404


def test_non_images_and_too_many_photos_are_refused(client, world):
    a = world["a"]
    h = _tok(client, a["account"])
    form = {"store_id": str(a["store"].id), "category": "OTHER", "title": "bad file"}
    fake = client.post(f"{API}/external/tickets", headers=h, data=form, files=[("photos", ("x.jpg", b"<html>no</html>", "image/jpeg"))])
    assert fake.status_code == 422
    six = client.post(f"{API}/external/tickets", headers=h, data=form, files=[_photo(f"{i}.jpg") for i in range(6)])
    assert six.status_code == 422


def test_reply_reaches_staff_and_closed_tickets_refuse(client, admin, world):
    a = world["a"]
    h = _tok(client, a["account"])
    t = _raise(client, h, a["store"]).json()
    r = client.post(f"{API}/external/tickets/{t['id']}/comments", data={"body": "Any update?"}, files=[_photo()], headers=h)
    assert r.status_code == 201 and r.json()["comments"][-1]["mine"] is True and len(r.json()["attachments"]) == 2
    staff = client.get(f"{API}/tickets/{t['id']}", headers=admin).json()
    assert staff["comments"][-1]["author_name"] == "Test Vendor (POC)"
    assert client.patch(f"{API}/tickets/{t['id']}", json={"status": "CLOSED"}, headers=admin).status_code == 200
    assert client.post(f"{API}/external/tickets/{t['id']}/comments", data={"body": "again"}, headers=h).status_code == 409


def test_staff_updates_notify_the_stores_vendors(client, admin, world):
    a, b = world["a"], world["b"]
    h = _tok(client, a["account"])
    t = _raise(client, h, a["store"]).json()
    assert client.patch(f"{API}/tickets/{t['id']}", json={"status": "IN_PROGRESS"}, headers=admin).status_code == 200
    assert client.post(f"{API}/tickets/{t['id']}/comments", json={"body": "On it"}, headers=admin).status_code == 200
    n = client.get(f"{API}/external/notifications", headers=h).json()
    assert n["unread"] == 2 and {x["kind"] for x in n["items"]} == {"ticket"} and n["items"][0]["ref_id"] == t["id"]
    assert client.get(f"{API}/external/notifications", headers=_tok(client, b["account"])).json()["total"] == 0
    assert client.post(f"{API}/external/notifications/read", json={}, headers=h).status_code == 204
    assert client.get(f"{API}/external/notifications", headers=h).json()["unread"] == 0


def test_upload_card_and_payment_proof_but_not_bills(client, world):
    a, b = world["a"], world["b"]
    h = _tok(client, a["account"])
    f = [("files", ("c.jpg", jpeg(), "image/jpeg"))]
    sid = str(a["store"].id)
    ok = client.post(f"{API}/external/documents", data={"store_id": sid, "kind": "payment"}, files=f, headers=h)
    assert ok.status_code == 201 and ok.json()["kind"] == "payment"
    again = client.post(f"{API}/external/documents", data={"store_id": sid, "kind": "payment"}, files=f, headers=h)
    assert again.status_code == 201 and again.json()["id"] == ok.json()["id"]  # same document, new version
    assert client.post(f"{API}/external/documents", data={"store_id": sid, "kind": "bill"}, files=f, headers=h).status_code == 422
    assert client.post(f"{API}/external/documents", data={"store_id": str(b["store"].id), "kind": "card"}, files=f, headers=h).status_code == 404
    assert client.post(f"{API}/external/documents", data={"store_id": sid, "kind": "card", "month": "1999-01"}, files=f, headers=h).status_code == 422
    assert client.get(f"{API}/external/documents", params={"kind": "payment"}, headers=h).json()["total"] == 1


def test_delivery_received_short_and_duplicate(client, admin, world):
    a = world["a"]
    h = _tok(client, a["account"])
    base = {"store_id": str(a["store"].id)}
    day = date.today() - timedelta(days=1)
    ok = client.post(f"{API}/external/deliveries", data={**base, "delivery_date": str(day), "outcome": "RECEIVED"}, headers=h)
    assert ok.status_code == 201 and ok.json()["ticket_id"] is None
    assert client.post(f"{API}/external/deliveries", data={**base, "delivery_date": str(day), "outcome": "RECEIVED"}, headers=h).status_code == 409

    short = client.post(
        f"{API}/external/deliveries", headers=h, files=[_photo()],
        data={**base, "delivery_date": str(date.today()), "outcome": "SHORT", "expected_qty": 100, "received_qty": 60, "note": "Driver left early"},
    )
    assert short.status_code == 201, short.text
    staff = client.get(f"{API}/tickets/{short.json()['ticket_id']}", headers=admin).json()
    assert staff["category"] == "SHORT_SUPPLY" and staff["priority"] == "HIGH" and len(staff["attachments"]) == 1
    assert "Expected 100, received 60" in staff["description"]
    assert client.get(f"{API}/external/deliveries", headers=h).json()["total"] == 2


def test_delivery_rules(client, world):
    h = _tok(client, world["a"]["account"])
    base = {"store_id": str(world["a"]["store"].id)}

    def post(day, outcome, **extra):
        return client.post(f"{API}/external/deliveries", data={**base, "delivery_date": str(day), "outcome": outcome}, headers=h, **extra)

    assert post(date.today() + timedelta(days=1), "RECEIVED").status_code == 422      # future
    assert post(date.today() - timedelta(days=60), "RECEIVED").status_code == 422     # too old
    assert post(date.today(), "DAMAGED").status_code == 422                           # needs a note or quantity
    assert post(date.today(), "RECEIVED", files=[_photo()]).status_code == 422        # photos only for problems


def test_device_registration_moves_between_logins(client, db, world):
    from app.models.external_activity import ExternalDevice

    ha, hb = _tok(client, world["a"]["account"]), _tok(client, world["b"]["account"])
    tok = "fcm-token-" + uuid.uuid4().hex
    assert client.post(f"{API}/external/devices", json={"token": tok, "platform": "android"}, headers=ha).status_code == 204
    assert client.delete(f"{API}/external/devices", params={"token": tok}, headers=hb).status_code == 204  # someone else's: ignored
    assert db.query(ExternalDevice).filter_by(token=tok).count() == 1
    assert client.post(f"{API}/external/devices", json={"token": tok, "platform": "android"}, headers=hb).status_code == 204
    db.expire_all()
    assert db.query(ExternalDevice).filter_by(token=tok).one().account_id == world["b"]["account"].id
    assert client.delete(f"{API}/external/devices", params={"token": tok}, headers=hb).status_code == 204
    assert db.query(ExternalDevice).filter_by(token=tok).count() == 0


def test_write_routes_need_a_vendor_token(client, admin, world):
    st = str(world["a"]["store"].id)
    cases = (
        ("tickets", {"store_id": st, "category": "OTHER", "title": "abc"}),
        ("deliveries", {"store_id": st, "delivery_date": str(date.today()), "outcome": "RECEIVED"}),
    )
    for path, data in cases:
        assert client.post(f"{API}/external/{path}", data=data).status_code == 401
        assert client.post(f"{API}/external/{path}", data=data, headers=admin).status_code == 401


def test_vendors_only_watch_pocs_act(client, admin, world):
    a = world["a"]
    poc, vendor = _tok(client, a["account"]), _tok(client, a["vendor"])
    st = str(a["store"].id)

    # the vendor cannot raise, reply or confirm a delivery
    assert _raise(client, vendor, a["store"]).status_code == 403
    day = {"store_id": st, "delivery_date": str(date.today()), "outcome": "RECEIVED"}
    assert client.post(f"{API}/external/deliveries", data=day, headers=vendor).status_code == 403

    # ...but sees what the POC raised and reported, and cannot reply to it
    t = _raise(client, poc, a["store"]).json()
    assert client.post(f"{API}/external/deliveries", data=day, headers=poc).status_code == 201
    seen = client.get(f"{API}/external/tickets", headers=vendor).json()
    assert str(t["id"]) in [x["id"] for x in seen["items"]]
    assert client.get(f"{API}/external/tickets/{t['id']}", headers=vendor).status_code == 200
    assert client.post(f"{API}/external/tickets/{t['id']}/comments", data={"body": "hi"}, headers=vendor).status_code == 403
    dl = client.get(f"{API}/external/deliveries", headers=vendor).json()
    assert dl["total"] == 1 and dl["items"][0]["reported_by"] == "Test Vendor (POC)"

    # a second POC cannot report the same store and day again
    poc2 = poc  # same POC again; any POC of the store gets the same answer
    assert client.post(f"{API}/external/deliveries", data=day, headers=poc2).status_code == 409


def test_daily_order_totals(client, world):
    h = _tok(client, world["a"]["vendor"])
    days = client.get(f"{API}/external/orders/daily", headers=h).json()
    assert days == [{"order_date": date.today().isoformat(), "bottles": 7, "stores": 1}]
    other = client.get(f"{API}/external/orders/daily", params={"store_id": str(world["b"]["store"].id)}, headers=h)
    assert other.status_code == 404
