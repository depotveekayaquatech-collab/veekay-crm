"""
One store followed through every surface (web admin, employee app, POC app, vendor app) to prove they all read and write
the same CRM: whatever one side does is what the others see, with no copy to keep in step.
"""
from datetime import date

import pytest

from app.models.bottle import Bottle, BottleBatch, BottleScan

from .conftest import API, auth, jpeg
from .test_external_portal import _login, make_account  # noqa: F401  (fixture)


@pytest.fixture()
def _bottles_cleanup(db):
    yield
    db.query(BottleScan).delete()
    db.query(Bottle).update({"replaces_id": None, "replaced_by_id": None})
    db.query(Bottle).delete()
    db.query(BottleBatch).delete()
    db.commit()


def _tok(client, account):
    return auth(_login(client, account.email).json()["access_token"])


def test_one_store_seen_the_same_way_everywhere(client, admin, emp, make_store, make_account, _bottles_cleanup):
    store = make_store()                                    # a Blinkit / North store: EMP001's, and the POC's and vendor's
    poc = _tok(client, make_account(stores=[store], kind="poc"))
    vendor_account = make_account(stores=[store], kind="vendor")
    vendor = _tok(client, vendor_account)
    today = date.today()
    sid = str(store.id)

    # 1. The employee marks orders from the phone (several dates at once)...
    before = client.get(f"{API}/orders/insights", headers=admin).json()["bottles_today"]
    marked = client.post(f"{API}/orders/mark-many", json={"store_id": sid, "entries": [{"order_date": str(today), "bottle_count": 24}]}, headers=emp)
    assert marked.status_code == 200 and marked.json()["saved"] == 1
    # ...and the admin dashboard, the web calendar and the vendor's app all show that same number.
    assert client.get(f"{API}/orders/insights", headers=admin).json()["bottles_today"] == before + 24
    cal = client.get(f"{API}/orders/calendar", params={"store_id": sid}, headers=emp).json()
    assert next(d for d in cal["days"] if d["date"] == str(today))["count"] == 24
    assert client.get(f"{API}/external/orders/daily", headers=vendor).json()[0]["bottles"] == 24
    assert client.get(f"{API}/external/orders", headers=poc).json()["total_bottles"] == 24

    # 2. The POC raises a ticket with a photo: staff see it in the normal Tickets list, tagged as coming from the app.
    t = client.post(
        f"{API}/external/tickets", headers=poc, data={"store_id": sid, "category": "SHORT_SUPPLY", "title": "Only 20 arrived"},
        files=[("photos", ("p.jpg", jpeg(), "image/jpeg"))],
    ).json()
    staff_view = client.get(f"{API}/tickets/{t['id']}", headers=admin).json()
    assert staff_view["source"] == "vendor_app" and len(staff_view["attachments"]) == 1
    assert t["id"] in [x["id"] for x in client.get(f"{API}/external/tickets", headers=vendor).json()["items"]]   # the vendor follows it

    # 3. Staff move it along: the POC and the vendor are both told, and the status matches everywhere.
    assert client.patch(f"{API}/tickets/{t['id']}", json={"status": "IN_PROGRESS"}, headers=admin).status_code == 200
    for who in (poc, vendor):
        assert client.get(f"{API}/external/tickets/{t['id']}", headers=who).json()["status"] == "IN_PROGRESS"
        notes = client.get(f"{API}/external/notifications", headers=who).json()
        assert notes["unread"] >= 1 and notes["items"][0]["ref_id"] == t["id"]

    # 4. The POC flags a short delivery: it becomes a high-priority ticket staff see, and the vendor sees the report.
    d = client.post(f"{API}/external/deliveries", headers=poc, data={"store_id": sid, "delivery_date": str(today), "outcome": "SHORT", "note": "left early"}).json()
    assert client.get(f"{API}/tickets/{d['ticket_id']}", headers=admin).json()["priority"] == "HIGH"
    assert client.get(f"{API}/external/deliveries", headers=vendor).json()["items"][0]["ticket_id"] == d["ticket_id"]

    # 5. An employee scans a bottle IN at that store: the vendor sees it there, and the admin's counts move.
    batch = client.post(f"{API}/bottles/batches", json={"quantity": 2}, headers=admin).json()
    serial = client.get(f"{API}/bottles/batches/{batch['id']}/serials.csv", headers=admin).text.splitlines()[1].split(",")[1]
    assert client.post(f"{API}/bottles/scan", json={"serial": serial, "direction": "IN", "store_id": sid, "scan_id": "e2e-1"}, headers=admin).status_code == 200
    again = client.post(f"{API}/bottles/scan", json={"serial": serial, "direction": "IN", "store_id": sid, "scan_id": "e2e-1"}, headers=admin).json()
    assert again["duplicate"] is True                                                   # an offline re-send never double counts
    vb = client.get(f"{API}/external/bottles", headers=vendor).json()
    assert vb["total"] == 1 and vb["items"][0]["serial"] == serial and vb["per_store"][sid] == 1
    assert client.get(f"{API}/bottles/summary", headers=admin).json()["at_store"] == 1

    # 6. The POC uploads a payment proof: the vendor sees it, and staff reading compliance see the same document.
    up = client.post(f"{API}/external/documents", headers=poc, data={"store_id": sid, "kind": "payment"}, files=[("files", ("c.jpg", jpeg(), "image/jpeg"))]).json()
    assert client.get(f"{API}/external/documents", headers=vendor).json()["items"][0]["id"] == up["id"]
    assert client.get(f"{API}/compliance/{up['id']}/file", headers=admin).status_code == 200

    # 7. Nothing leaks sideways: a vendor of another store sees none of this.
    other = _tok(client, make_account(stores=[make_store()], kind="vendor"))
    assert client.get(f"{API}/external/tickets", headers=other).json()["total"] == 0
    assert client.get(f"{API}/external/orders/daily", headers=other).json() == []
    assert client.get(f"{API}/external/bottles", headers=other).json()["total"] == 0
