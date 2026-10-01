"""Monthly compliance: card / invoice / payment proof uploads, file rules, access, repository view, summary PDF."""
import io
import zipfile
from datetime import date

import pytest

from .conftest import API, PDF_BYTES, jpeg, login, auth

MONTH = date.today().strftime("%Y-%m")


def up(client, headers, store, kind="bill", month=MONTH, files=None):
    files = files or [("files", ("a.jpg", jpeg(), "image/jpeg"))]
    return client.post(f"{API}/compliance/upload", headers=headers, data={"store_id": str(store.id), "month": month, "kind": kind}, files=files)


def repo(client, headers, **params):
    r = client.get(f"{API}/compliance/stores", headers=headers, params={"month": MONTH, "page_size": 200, **params})
    assert r.status_code == 200, r.text
    return r.json()


def row_for(data, store):
    return next(r for r in data["items"] if r["store_id"] == str(store.id)) if "items" in data else None


# ---------------------------------------------------------------- upload rules
def test_a_single_photo_is_stored_as_is(client, admin, make_store):
    r = up(client, admin, make_store())
    assert r.status_code == 200
    f = client.get(f"{API}/compliance/{r.json()['id']}/file", headers=admin)
    assert f.status_code == 200 and f.content[:3] == b"\xff\xd8\xff" and f.headers["x-content-type-options"] == "nosniff"


def test_several_photos_are_merged_into_one_pdf(client, admin, make_store):
    r = up(client, admin, make_store(), files=[("files", (f"p{i}.jpg", jpeg(c), "image/jpeg")) for i, c in enumerate(("red", "blue", "green"))])
    assert r.status_code == 200
    assert client.get(f"{API}/compliance/{r.json()['id']}/file", headers=admin).content[:5] == b"%PDF-"


def test_a_pdf_goes_alone_and_not_with_photos(client, admin, make_store):
    s = make_store()
    assert up(client, admin, s, files=[("files", ("x.pdf", PDF_BYTES, "application/pdf"))]).status_code == 200
    mixed = up(client, admin, s, files=[("files", ("x.pdf", PDF_BYTES, "application/pdf")), ("files", ("a.jpg", jpeg(), "image/jpeg"))])
    assert mixed.status_code == 422 and "on its own" in mixed.json()["detail"]


def test_files_are_judged_by_content_not_by_name(client, admin, make_store):
    fake = up(client, admin, make_store(), files=[("files", ("evil.jpg", b"<script>alert(1)</script>", "image/jpeg"))])
    assert fake.status_code == 422 and "JPG, PNG, WEBP" in fake.json()["detail"]
    empty = up(client, admin, make_store(), files=[("files", ("a.jpg", b"", "image/jpeg"))])
    assert empty.status_code == 422


def test_oversized_files_are_refused(client, admin, make_store, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "COMPLIANCE_MAX_FILE_MB", 0)
    assert up(client, admin, make_store()).status_code == 413


def test_only_card_bill_and_payment_exist(client, admin, make_store):
    s = make_store()
    for kind in ("card", "bill", "payment"):
        assert up(client, admin, s, kind=kind).status_code == 200
    for dead in ("weekly", "week1", "invoice-x"):
        assert up(client, admin, s, kind=dead).status_code == 422


@pytest.mark.parametrize("month", ["2020-01", "2999-01", "nonsense", "2026-13"])
def test_months_outside_the_window_are_refused(client, admin, make_store, month):
    assert up(client, admin, make_store(), month=month).status_code == 422


def test_re_uploading_replaces_rather_than_duplicates(client, admin, make_store):
    s = make_store()
    a = up(client, admin, s).json()["id"]
    b = up(client, admin, s).json()["id"]
    assert a == b or client.get(f"{API}/compliance/{a}/file", headers=admin).status_code in (200, 404)
    docs = client.get(f"{API}/compliance/search", headers=admin, params={"month": MONTH, "q": s.external_code, "kind": "bill"}).json()
    assert len(docs["items"]) == 1


# ---------------------------------------------------------------- access
def test_employees_only_touch_their_own_stores(client, emp, zepto_emp, make_store):
    mine = make_store(platform="blinkit", region="NORTH")
    other = make_store(platform="zepto", region="NORTH", state="Karnataka")
    assert up(client, emp, mine).status_code == 200
    r = up(client, emp, other)
    assert r.status_code == 403 and "not assigned" in r.json()["detail"]
    doc = up(client, emp, mine).json()
    assert client.get(f"{API}/compliance/{doc['id']}/file", headers=zepto_emp).status_code == 403


def test_without_the_permission_nothing_works(client, make_user, make_store):
    code, pw, _ = make_user(grants=("orders.view",))
    h = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/compliance/stores", headers=h).status_code == 403
    assert up(client, h, make_store()).status_code == 403


def test_accountant_can_view_and_clear_but_employee_cannot_clear(client, admin, emp, make_user, make_store):
    s = make_store()
    doc = up(client, emp, s).json()
    assert client.post(f"{API}/compliance/{doc['id']}/clear", headers=emp).status_code == 403
    code, pw, _ = make_user(role="accountant")
    acct = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/compliance/{doc['id']}/file", headers=acct).status_code == 200
    r = client.post(f"{API}/compliance/{doc['id']}/clear", headers=acct)
    assert r.status_code == 200
    assert client.post(f"{API}/compliance/{doc['id']}/clear", headers=acct).status_code == 200      # idempotent


def test_only_bills_can_be_cleared(client, admin, make_store):
    doc = up(client, admin, make_store(), kind="card").json()
    assert client.post(f"{API}/compliance/{doc['id']}/clear", headers=admin).status_code == 422


def test_a_cleared_bill_stays_cleared_after_a_re_upload(client, admin, make_store):
    s = make_store()
    doc = up(client, admin, s).json()
    client.post(f"{API}/compliance/{doc['id']}/clear", headers=admin)
    up(client, admin, s)
    found = client.get(f"{API}/compliance/search", headers=admin, params={"month": MONTH, "q": s.external_code, "kind": "bill"}).json()["items"]
    assert len(found) == 1 and "clear" in str(found[0]).lower()


def test_removing_a_document(client, admin, make_store):
    doc = up(client, admin, make_store()).json()
    assert client.delete(f"{API}/compliance/{doc['id']}", headers=admin).status_code == 204
    assert client.get(f"{API}/compliance/{doc['id']}/file", headers=admin).status_code == 404


# ---------------------------------------------------------------- repository view
def test_status_goes_pending_partial_complete(client, admin, make_store):
    s = make_store()
    assert row_for(repo(client, admin), s)["status"].upper() == "PENDING"
    up(client, admin, s, kind="card")
    assert row_for(repo(client, admin), s)["status"].upper() == "PARTIAL"
    up(client, admin, s, kind="bill")
    up(client, admin, s, kind="payment")
    assert row_for(repo(client, admin), s)["status"].upper() == "COMPLETE"


def test_vendor_name_is_the_delivery_manager(client, admin, make_store):
    s = make_store(vendor="Sharma Aqua")
    assert row_for(repo(client, admin), s)["manager"] == "Sharma Aqua"


def test_filters_and_sort_parameters_are_validated(client, admin):
    for bad in ({"sort": "drop table"}, {"missing": "week1"}, {"status": "weird"}, {"range": "1-2"}):
        assert client.get(f"{API}/compliance/stores", headers=admin, params=bad).status_code == 422
    for ok in ({"missing": "payment"}, {"status": "partial"}, {"status": "COMPLETE"}, {"sort": "percent", "dir": "desc"}):
        assert client.get(f"{API}/compliance/stores", headers=admin, params=ok).status_code == 200


def test_the_missing_filter_lists_only_stores_without_that_document(client, admin, make_store):
    done, todo = make_store(), make_store()
    up(client, admin, done, kind="payment")
    ids = {r["store_id"] for r in repo(client, admin, missing="payment")["items"]}
    assert str(todo.id) in ids and str(done.id) not in ids


# ---------------------------------------------------------------- bulk / summary / download
def test_bulk_matches_files_to_stores_by_code_prefix(client, admin, make_store):
    a, b = make_store(code="BULK-1001"), make_store(code="BULK-1002")
    files = [("files", ("BULK-1001.jpg", jpeg(), "image/jpeg")), ("files", ("BULK-1002_page1.jpg", jpeg(), "image/jpeg")),
             ("files", ("BULK-1002_page2.jpg", jpeg("blue"), "image/jpeg")), ("files", ("NOBODY-9.jpg", jpeg(), "image/jpeg"))]
    r = client.post(f"{API}/compliance/bulk", headers=admin, data={"month": MONTH, "kind": "card"}, files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "NOBODY-9.jpg" in str(body) and row_for(repo(client, admin, q="BULK-100"), b)["status"].upper() == "PARTIAL"


def test_summary_pdf(client, admin, make_store):
    s = make_store()
    up(client, admin, s, kind="card")
    r = client.post(f"{API}/compliance/summary-pdf", headers=admin, json={"store_ids": [str(s.id)], "month": MONTH})
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"


def test_download_zip(client, admin, make_store):
    d1, d2 = up(client, admin, make_store()).json(), up(client, admin, make_store(), kind="card").json()
    r = client.post(f"{API}/compliance/download", headers=admin, json={"ids": [d1["id"], d2["id"]]})
    assert r.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 2
    assert client.post(f"{API}/compliance/download", headers=admin, json={"ids": ["00000000-0000-0000-0000-000000000000"]}).status_code == 404


def test_download_needs_the_permission(client, emp, make_user):
    code, pw, _ = make_user(grants=("orders.view",))
    h = auth(login(client, code, pw).json()["access_token"])
    assert client.post(f"{API}/compliance/download", headers=h, json={"ids": []}).status_code in (403, 422)
