"""Cash purchases: who may add / see, validation of reasons and stores, and the Excel sheet."""
import io
from datetime import date, timedelta

import pytest

from app.models.cash_purchase import CashPurchase

from .conftest import API, PDF_BYTES, auth, jpeg, login

URL = f"{API}/cash-purchases"


@pytest.fixture(autouse=True)
def _wipe(db):
    yield
    db.query(CashPurchase).delete()
    db.commit()


def _body(**kw):
    return {"kind": "OFFICE", "purchase_date": date.today().isoformat(), "category": "MILK", "amount": "120.50", **kw}


def _post(client, headers, body=None, proof="default", **kw):
    """POST a purchase as multipart with a payment-proof photo (pass proof=None to leave it out)."""
    fields = {k: str(v) for k, v in (body or _body(**kw)).items() if v is not None}
    if proof == "default":
        proof = ("proof.jpg", jpeg(), "image/jpeg")
    return client.post(URL, headers=headers, data=fields, files={"proof": proof} if proof else None)


def _token(client, make_user, role, **kw):
    code, pw, _ = make_user(role, **kw)
    return auth(login(client, code, pw).json()["access_token"])


def test_employee_adds_office_purchase_and_sees_only_their_own(client, admin, emp, zepto_emp):
    r = _post(client, emp)
    assert r.status_code == 201, r.text
    assert r.json()["category_label"] == "Milk" and r.json()["store_name"] is None
    assert _post(client, zepto_emp, category="STATIONERY", amount=40).status_code == 201

    mine = client.get(URL, headers=emp).json()
    assert mine["total"] == 1 and mine["amount_total"] == "120.50"
    everyone = client.get(URL, headers=admin).json()
    assert everyone["total"] == 2 and everyone["office_total"] == "160.50" and everyone["store_total"] == "0.00"


def test_employee_cannot_download_the_sheet(client, emp):
    assert client.get(f"{URL}/export", headers=emp).status_code == 403


def test_accounts_can_see_add_and_download(client, make_user):
    acc = _token(client, make_user, "accountant")
    assert _post(client, acc, category="DRINKING_WATER", amount=300).status_code == 201
    assert client.get(URL, headers=acc).json()["total"] == 1
    assert client.get(f"{URL}/export", headers=acc).status_code == 200


def test_a_user_without_cash_permissions_is_locked_out(client, make_user):
    nobody = _token(client, make_user, "employee", grants=("orders.view",))
    assert client.get(URL, headers=nobody).status_code == 403
    assert client.get(f"{URL}/options", headers=nobody).status_code == 403
    assert _post(client, nobody).status_code == 403


def test_other_needs_a_description_and_known_reasons_are_enforced(client, emp):
    r = _post(client, emp, category="OTHER")
    assert r.status_code == 422 and "Describe" in r.json()["detail"]
    ok = _post(client, emp, category="OTHER", other_reason="  Gift for guest  ")
    assert ok.status_code == 201 and ok.json()["other_reason"] == "Gift for guest" and ok.json()["category_label"] == "Other"
    # a description is dropped when a listed reason is picked
    assert _post(client, emp, other_reason="ignored").json()["other_reason"] is None
    # MILK is an office item, not a store reason
    assert _post(client, emp, kind="STORE", category="MILK").status_code == 422
    assert _post(client, emp, category="NOPE").status_code == 422


def test_amount_and_date_rules(client, emp):
    for amount in (0, -5, "abc"):
        assert _post(client, emp, amount=amount).status_code == 422
    assert _post(client, emp, amount=2_000_000).status_code == 422
    future = (date.today() + timedelta(days=2)).isoformat()
    assert _post(client, emp, purchase_date=future).status_code == 422
    old = (date.today() - timedelta(days=400)).isoformat()
    assert _post(client, emp, purchase_date=old).status_code == 422


def test_store_purchase_is_limited_to_the_employees_own_stores(client, emp, admin, make_store):
    mine = make_store(code="CP-N1", region="NORTH")
    other = make_store(code="CP-S1", platform="zepto", region=None, state="Karnataka")

    assert _post(client, emp, kind="STORE", category="EMERGENCY_REQUIREMENT").status_code == 422  # store missing
    opts = client.get(f"{URL}/options", headers=emp).json()
    ids = {s["id"] for s in opts["stores"]}
    assert str(mine.id) in ids and str(other.id) not in ids and opts["can_view_all"] is False

    ok = _post(client, emp, kind="STORE", category="EMERGENCY_REQUIREMENT", store_id=str(mine.id), amount=700)
    assert ok.status_code == 201 and ok.json()["store_code"] == "CP-N1"
    assert _post(client, emp, kind="STORE", category="EMERGENCY_REQUIREMENT", store_id=str(other.id)).status_code == 403
    # admins may book against any live store
    assert _post(client, admin, kind="STORE", category="EMERGENCY_REQUIREMENT", store_id=str(other.id)).status_code == 201


def test_filters_and_totals(client, admin, make_store):
    s = make_store(code="CP-F1")
    _post(client, admin, amount=100)
    _post(client, admin, kind="STORE", category="SUPPLY_DELAYED", store_id=str(s.id), amount=250)
    _post(client, admin, category="OTHER", other_reason="Birthday cake", amount=500)

    stores_only = client.get(f"{URL}?kind=STORE", headers=admin).json()
    assert stores_only["total"] == 1 and stores_only["amount_total"] == "250.00"
    assert client.get(f"{URL}?q=cake", headers=admin).json()["total"] == 1
    assert client.get(f"{URL}?category=MILK", headers=admin).json()["total"] == 1
    allrows = client.get(URL, headers=admin).json()
    assert allrows["amount_total"] == "850.00" and allrows["store_total"] == "250.00" and allrows["office_total"] == "600.00"


def test_export_sheet_has_every_row_and_a_total(client, admin, make_store):
    from openpyxl import load_workbook

    s = make_store(code="CP-X1", name="Export Store")
    _post(client, admin, amount=100)
    _post(client, admin, kind="STORE", category="OTHER", other_reason="Rope", store_id=str(s.id), amount=50)

    r = client.get(f"{URL}/export", headers=admin)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
    assert rows[0][1] == "Type" and rows[0][9] == "Amount (INR)"
    kinds = {row[1]: row for row in rows[1:3]}
    assert kinds["Store"][2] == "Export Store" and kinds["Store"][5] == "Water bottles" and kinds["Store"][6] == "Other" and kinds["Store"][7] == "Rope" and kinds["Office"][2] == "Office"
    assert rows[-1][0] == "TOTAL" and rows[-1][9] == 150

    only_office = client.get(f"{URL}/export?kind=OFFICE", headers=admin)
    assert "office" in only_office.headers["content-disposition"]
    assert list(load_workbook(io.BytesIO(only_office.content)).active.iter_rows(values_only=True))[-1][9] == 100


def test_payment_proof_is_required_and_checked_by_content(client, emp):
    r = _post(client, emp, proof=None)
    assert r.status_code == 422
    fake = _post(client, emp, proof=("proof.jpg", b"not really an image", "image/jpeg"))
    assert fake.status_code == 422 and "JPG" in fake.json()["detail"]
    assert _post(client, emp, proof=("slip.pdf", PDF_BYTES, "application/pdf")).status_code == 201


def test_proof_can_be_opened_by_the_owner_and_admin_but_not_other_employees(client, emp, zepto_emp, admin):
    made = _post(client, emp).json()
    assert made["has_proof"] is True and made["proof_name"].endswith(".jpg")
    url = f"{URL}/{made['id']}/proof"
    for who in (emp, admin):
        r = client.get(url, headers=who)
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == bytes([0xFF, 0xD8])
    assert client.get(url, headers=zepto_emp).status_code == 404


def test_sheet_says_whether_proof_is_attached(client, admin):
    from openpyxl import load_workbook

    _post(client, admin)
    rows = list(load_workbook(io.BytesIO(client.get(f"{URL}/export", headers=admin).content)).active.iter_rows(values_only=True))
    assert rows[0][8] == "Proof attached" and rows[1][8] == "Yes"
