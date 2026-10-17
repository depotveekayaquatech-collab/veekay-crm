"""The Android app uses the EXISTING compliance routes. These tests pin down what it relies on: an employee sees only their own stores,
the web CRM and the phone share the same records, a retried upload never makes a second version, and access is enforced by the
server (not by which tab the app shows)."""
import uuid
from datetime import date

from .conftest import API, PDF_BYTES, auth, jpeg, login

MONTH = date.today().strftime("%Y-%m")
STORES = f"{API}/compliance/stores"


def put(client, headers, store, kind="card", files=None, key=None, month=MONTH):
    files = files or [("files", ("IMG.jpg", jpeg(size=(900, 700)), "image/jpeg"))]
    h = {**headers, **({"Idempotency-Key": key} if key else {})}
    return client.post(f"{API}/compliance/upload", headers=h, data={"store_id": str(store.id), "month": month, "kind": kind}, files=files)


def row(client, headers, store, **params):
    r = client.get(STORES, headers=headers, params={"month": MONTH, "q": store.external_code, "page_size": 30, **params})
    assert r.status_code == 200, r.text
    return next((x for x in r.json()["items"] if x["store_id"] == str(store.id)), None), r.json()


def test_an_employee_sees_only_their_own_stores_and_an_admin_sees_all(client, admin, emp, make_store):
    mine = make_store(platform="blinkit", region="NORTH")
    other = make_store(platform="zepto", region=None, state="Karnataka")
    assert row(client, emp, mine)[0] is not None
    assert row(client, emp, other)[0] is None                       # the server scopes the list: the phone cannot ask for more
    assert row(client, admin, mine)[0] is not None and row(client, admin, other)[0] is not None


def test_the_tab_is_only_for_people_with_the_compliance_permission_and_the_server_agrees(client, make_user, make_store):
    code, pw, _ = make_user(grants=("orders.view",))                # no compliance permission
    h = auth(login(client, code, pw).json()["access_token"])
    assert client.get(STORES, headers=h).status_code == 403
    assert put(client, h, make_store()).status_code == 403
    assert client.get(STORES).status_code == 401
    assert client.get(f"{API}/auth/me", headers=h).json()["permissions"].count("compliance.upload") == 0   # what the app reads to hide the tab


def test_the_list_gives_the_phone_what_it_needs(client, emp, make_store):
    s = make_store()
    r = client.get(STORES, headers=emp, params={"page_size": 1})
    body = r.json()
    assert r.status_code == 200 and body["month"] == MONTH and MONTH in body["months"] and body["page_size"] == 1
    assert {"compliance_percent", "card_logged", "invoice_logged", "payment_logged", "total"} <= set(body["kpis"])
    one, _ = row(client, emp, s)
    assert {"store_id", "name", "external_code", "status", "percent", "card", "bill", "payment", "city"} <= set(one)
    assert one["card"] is None and one["status"].upper() == "PENDING"
    assert row(client, emp, s, missing="card")[0] is not None        # "Missing card" filter lists it
    assert row(client, emp, s, status="complete")[0] is None


def test_web_and_phone_share_the_same_records_both_ways(client, admin, emp, make_store):
    s = make_store()
    mine = put(client, emp, s, "card")                              # uploaded from the phone
    assert mine.status_code == 200
    seen_by_web = row(client, admin, s)[0]
    assert seen_by_web["card"]["id"] == mine.json()["id"] and seen_by_web["card"]["uploaded_at"]     # the date is on the record
    # The upload answer names the uploader; the list route does not fill that field in today (it comes back null). The phone shows
    # "by <name>" whenever the server supplies it, so nothing changes in the app if the list route ever does.
    assert mine.json()["uploaded_by"]
    assert "uploaded_by" in seen_by_web["card"]
    assert put(client, admin, s, "bill", [("files", ("b.pdf", PDF_BYTES, "application/pdf"))]).status_code == 200   # uploaded on the web
    seen_by_phone = row(client, emp, s)[0]
    assert seen_by_phone["bill"] is not None and seen_by_phone["bill"]["content_type"] == "application/pdf"
    assert seen_by_phone["percent"] == round(2 / 3 * 100)           # the same percentage the web page shows


def test_a_retried_upload_with_the_same_key_never_makes_a_second_version(client, emp, make_store):
    s = make_store()
    key = uuid.uuid4().hex
    first, again = put(client, emp, s, key=key), put(client, emp, s, key=key)
    assert first.status_code == again.status_code == 200 and first.json()["id"] == again.json()["id"]
    versions = client.get(f"{API}/compliance/{first.json()['id']}/versions", headers=emp).json()
    assert len(versions) == 1 and versions[0]["current"] is True
    assert {"version", "file_name", "size_bytes", "content_type", "uploaded_at", "source_files", "current"} <= set(versions[0])


def test_a_new_upload_keeps_the_earlier_file_in_the_history_and_both_open(client, emp, make_store):
    s = make_store()
    doc = put(client, emp, s, files=[("files", ("a.jpg", jpeg("red", (900, 700)), "image/jpeg"))]).json()
    again = put(client, emp, s, files=[("files", ("b.jpg", jpeg("blue", (900, 700)), "image/jpeg"))]).json()
    assert again["id"] == doc["id"]
    versions = client.get(f"{API}/compliance/{doc['id']}/versions", headers=emp).json()
    assert [(v["version"], v["current"]) for v in versions] == [(2, True), (1, False)]
    for v in (1, 2):
        r = client.get(f"{API}/compliance/{doc['id']}/file", headers=emp, params={"version": v})
        assert r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff"
        assert client.get(f"{API}/compliance/{doc['id']}/url", headers=emp, params={"version": v}).status_code == 200
    assert client.get(f"{API}/compliance/{doc['id']}/file", headers=emp, params={"version": 9}).status_code == 404


def test_another_stores_documents_stay_out_of_reach_even_with_the_right_id(client, admin, emp, make_store):
    other = make_store(platform="zepto", region=None, state="Karnataka")
    doc = put(client, admin, other, "card").json()
    for path in (f"{doc['id']}/versions", f"{doc['id']}/url", f"{doc['id']}/file"):
        assert client.get(f"{API}/compliance/{path}", headers=emp).status_code in (403, 404), path
    assert put(client, emp, other, "card").status_code == 403
    assert client.delete(f"{API}/compliance/{doc['id']}", headers=emp).status_code in (403, 404)
    assert client.get(f"{API}/compliance/{doc['id']}/file", headers=admin).status_code == 200      # and the owner side is untouched


def test_removing_archives_like_the_web_and_uploading_again_brings_it_back(client, emp, make_store):
    s = make_store()
    doc = put(client, emp, s).json()
    assert client.delete(f"{API}/compliance/{doc['id']}", headers=emp).status_code == 204
    assert row(client, emp, s)[0]["card"] is None                    # hidden from the list
    back = put(client, emp, s).json()
    assert back["id"] == doc["id"]                                   # the same record is restored, not duplicated
    assert row(client, emp, s)[0]["card"]["id"] == doc["id"]
    assert len(client.get(f"{API}/compliance/{doc['id']}/versions", headers=emp).json()) == 2     # nothing was lost


def test_the_upload_policy_is_readable_by_an_employee_and_matches_what_the_server_enforces(client, emp, make_store):
    p = client.get(f"{API}/uploads/policy", headers=emp).json()
    assert p["photo_max_stored_kb"] == 1024 and p["pdf_max_mb"] == 2 and p["photo_max_upload_mb"] == 12 and p["max_dimension"] == 1600
    big_pdf = PDF_BYTES + b"0" * (3 * 1024 * 1024)
    refused = put(client, emp, make_store(), files=[("files", ("scan.pdf", big_pdf, "application/pdf"))])
    assert refused.status_code == 413 and "2 MB" in refused.json()["detail"]
    assert put(client, emp, make_store(), files=[("files", ("n.txt", b"hello", "text/plain"))]).status_code == 422
