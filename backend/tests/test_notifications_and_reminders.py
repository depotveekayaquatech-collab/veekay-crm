"""Bill-due reminders to vendors / POCs, and alerts for employees and admins (leave, tickets)."""
import uuid
from datetime import date, timedelta

import pytest

from app.models.compliance_document import ComplianceDocument
from app.models.external_activity import BillReminder, StaffNotification
from app.models.organization import Organization
from app.services import reminder_service, ticket_service

from .conftest import API, auth, jpeg, login
from .test_external_portal import _login, _tok, make_account  # noqa: F401  (fixtures)


def test_stage_boundaries():
    s = reminder_service.stage_for
    assert [s(n) for n in (10, 4)] == [None, None]
    assert [s(n) for n in (3, 1)] == ["soon", "soon"]
    assert [s(n) for n in (0, -6)] == ["due", "due"]
    assert [s(n) for n in (-7, -13)] == ["late7", "late7"]
    assert [s(n) for n in (-14, -29)] == ["late14", "late14"]
    assert [s(n) for n in (-30, -400)] == ["late30", "late30"]


def _bill(db, store, due: date, status="PENDING", month: date | None = None):
    org = db.query(Organization).filter_by(slug="veekay").one()
    d = ComplianceDocument(
        organization_id=org.id, store_id=store.id, month=month or due.replace(day=1), kind="bill", file_key=f"test/{uuid.uuid4().hex}.pdf",
        file_name="b.pdf", content_type="application/pdf", size_bytes=1, status=status, due_date=due,
    )
    db.add(d)
    db.commit()
    return d


def test_each_stage_is_sent_once_to_the_stores_people_only(client, db, make_store, make_account):
    store, other = make_store(), make_store()
    poc, vendor = make_account(stores=[store], kind="poc"), make_account(stores=[store], kind="vendor")
    stranger = make_account(stores=[other], kind="vendor")
    today = date.today()
    bill = _bill(db, store, today + timedelta(days=2))

    first = reminder_service.send_bill_reminders(db, today)
    assert first["reminders"] >= 1
    for who in (poc, vendor):
        n = client.get(f"{API}/external/notifications", headers=_tok(client, who)).json()
        assert n["total"] == 1 and n["items"][0]["kind"] == "bill" and n["items"][0]["ref_id"] == str(bill.id)
        assert "due in 2 days" in n["items"][0]["title"]
    assert client.get(f"{API}/external/notifications", headers=_tok(client, stranger)).json()["total"] == 0

    again = reminder_service.send_bill_reminders(db, today)                    # the job running twice repeats nothing
    assert client.get(f"{API}/external/notifications", headers=_tok(client, poc)).json()["total"] == 1 and again["reminders"] == 0

    reminder_service.send_bill_reminders(db, today + timedelta(days=2))        # now it is the due date: a new stage
    titles = [i["title"] for i in client.get(f"{API}/external/notifications", headers=_tok(client, poc)).json()["items"]]
    assert len(titles) == 2 and any("Bill is due" in t for t in titles)
    assert {r.stage for r in db.query(BillReminder).filter_by(document_id=bill.id)} == {"soon", "due"}


def test_old_bills_get_one_message_and_cleared_or_distant_bills_none(client, db, make_store, make_account):
    store = make_store()
    poc = make_account(stores=[store], kind="poc")
    today = date.today()
    very_late = _bill(db, store, today - timedelta(days=50), month=date(2026, 6, 1))
    _bill(db, store, today - timedelta(days=5), status="CLEARED", month=date(2026, 7, 1))     # paid: no reminder
    _bill(db, store, today + timedelta(days=20), month=date(2026, 8, 1))                      # too early
    reminder_service.send_bill_reminders(db, today)
    items = client.get(f"{API}/external/notifications", headers=_tok(client, poc)).json()["items"]
    assert len(items) == 1 and "over a month late" in items[0]["title"] and items[0]["ref_id"] == str(very_late.id)


def _staff(client, make_user, db):
    code, pw, uid = make_user()
    return auth(login(client, code, pw).json()["access_token"]), uid


def test_leave_and_ticket_alerts_reach_the_right_people(client, admin, emp, make_user, db, make_store, make_account):
    # leave: the admin hears about a new request, and the employee about the decision
    h, uid = _staff(client, make_user, db)
    day = str(date.today() + timedelta(days=25))
    lid = client.post(f"{API}/attendance/leaves", json={"leave_type": "CASUAL", "start_date": day, "end_date": day, "half_day": False, "reason": "trip"}, headers=h).json()["id"]
    admin_feed = client.get(f"{API}/me/notifications", headers=admin).json()
    assert any(n["kind"] == "leave" and n["ref_id"] == lid and n["title"] == "New leave request" for n in admin_feed["items"])
    assert client.get(f"{API}/me/notifications", headers=h).json()["total"] == 0           # not to the person who asked
    client.post(f"{API}/attendance/leaves/{lid}/review", json={"approve": True, "note": "ok"}, headers=admin)
    mine = client.get(f"{API}/me/notifications", headers=h).json()
    assert mine["unread"] == 1 and mine["items"][0]["title"] == "Your leave was approved" and "ok" in mine["items"][0]["body"]

    # a ticket raised by a POC from the app alerts whoever manages tickets; assigning it alerts the assignee
    store = make_store()
    poc = _tok(client, make_account(stores=[store], kind="poc"))
    t = client.post(f"{API}/external/tickets", headers=poc, data={"store_id": str(store.id), "category": "OTHER", "title": "Hello there"}, files=[("photos", ("p.jpg", jpeg(), "image/jpeg"))]).json()
    assert any(n["kind"] == "ticket" and n["ref_id"] == t["id"] and "New ticket" in n["title"] for n in client.get(f"{API}/me/notifications", headers=admin).json()["items"])
    assert client.patch(f"{API}/tickets/{t['id']}", json={"assigned_to_id": str(uid)}, headers=admin).status_code == 200
    feed = client.get(f"{API}/me/notifications", headers=h).json()["items"]
    assert any("assigned to you" in n["title"] and n["ref_id"] == t["id"] for n in feed)


def test_my_notifications_read_and_devices(client, emp, make_user, db):
    h, _ = _staff(client, make_user, db)
    assert client.get(f"{API}/me/notifications").status_code == 401
    assert client.post(f"{API}/me/notifications/read", json={}, headers=h).status_code == 204
    tok = "fcm-staff-" + uuid.uuid4().hex
    assert client.post(f"{API}/me/devices", json={"token": tok, "platform": "android"}, headers=h).status_code == 204
    assert client.post(f"{API}/me/devices", json={"token": tok, "platform": "android"}, headers=emp).status_code == 204   # moves to the new login
    from app.models.external_activity import StaffDevice
    assert db.query(StaffDevice).filter_by(token=tok).count() == 1
    assert client.delete(f"{API}/me/devices", params={"token": tok}, headers=h).status_code == 204     # not theirs: ignored
    assert db.query(StaffDevice).filter_by(token=tok).count() == 1


def test_a_new_ticket_reaches_the_employees_who_handle_that_store(client, db, make_user, make_store, make_account):
    store = make_store(platform="blinkit", region="NORTH")
    north, pw, north_id = make_user(platform="blinkit", region="NORTH", grants=("tickets.view",))
    _, _, south_id = make_user(platform="blinkit", region="SOUTH", grants=("tickets.view",))
    _, _, blind_id = make_user(platform="blinkit", region="NORTH", grants=("orders.view",))     # same region, cannot open tickets
    _, _, zepto_id = make_user(platform="zepto", region="NORTH", grants=("tickets.view",))
    heard = lambda uid: [n for n in db.query(StaffNotification).filter_by(user_id=uid, kind="ticket").all() if "New ticket" in n.title]

    poc = _tok(client, make_account(stores=[store], kind="poc"))
    t = client.post(f"{API}/external/tickets", headers=poc, data={"store_id": str(store.id), "category": "OTHER", "title": "No water today"}, files=[("photos", ("p.jpg", jpeg(), "image/jpeg"))]).json()
    assert [n.ref_id for n in heard(north_id)] == [t["id"]]
    assert not heard(south_id) and not heard(blind_id) and not heard(zepto_id)

    # a ticket from the Google form reaches them too
    ticket, created = ticket_service.create_external(
        db, store.organization_id, external_id=f"x-{uuid.uuid4().hex}", store_code=store.external_code, platform="blinkit", store_name=None,
        category="late", priority=None, title="Late delivery", description=None, reporter="Form user", raised_at=None,
    )
    assert created and [n.ref_id for n in heard(north_id)] == [t["id"], str(ticket.id)]
    assert not heard(south_id)
