"""Monthwise virtual card: months, signed QR + public count page, single PDF, multi-vendor ZIP."""
import io
import zipfile
from datetime import date

import pytest

from app.services import card_service as cards

from .conftest import API, auth, login


def entry(db, store, day: date, bottles: int):
    from app.models.order_entry import OrderEntry
    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=day, bottle_count=bottles))
    db.commit()


# ---------------------------------------------------------------- months
def test_blank_means_no_month_and_the_range_is_enforced():
    assert cards.parse_card_month(None) is None and cards.parse_card_month("") is None
    assert cards.parse_card_month("2026-09") == date(2026, 9, 1)
    for bad in ("2026-08", "2999-01", "garbage", "2026-13"):
        with pytest.raises(Exception):
            cards.parse_card_month(bad)


def test_months_list_starts_at_the_first_active_month(client, admin):
    months = client.get(f"{API}/cards/vendors", headers=admin).json()["months"]
    assert months and months[-1]["value"] == "2026-09"


# ---------------------------------------------------------------- QR signing / public page
def test_signature_is_verifiable_and_not_transferable(make_store):
    a, b = make_store(), make_store()
    sig = cards.sign_store(a.id)
    assert cards.verify_signature(a.id, sig) and cards.verify_signature(a.id, sig.upper())
    assert not cards.verify_signature(b.id, sig) and not cards.verify_signature(a.id, "") and not cards.verify_signature(a.id, "0" * 32)
    assert cards.qr_url(a.id).startswith("http://testserver/count?s=") and sig in cards.qr_url(a.id)


def test_public_count_needs_no_login_but_needs_a_valid_signature(client, db, make_store):
    s = make_store(vendor="Aqua One")
    today = date.today()
    entry(db, s, today.replace(day=1), 7)            # one entry per store per day
    if today.day > 1:
        entry(db, s, today.replace(day=2), 5)
    expected = 7 + (5 if today.day > 1 else 0)
    ok = client.get(f"{API}/public/count", params={"s": str(s.id), "sig": cards.sign_store(s.id)})
    assert ok.status_code == 200
    body = ok.json()
    assert body["store_code"] == s.external_code and body["this_month_bottles"] == expected and body["vendor_name"] == "Aqua One"
    assert set(body) == {"store_name", "store_code", "vendor_name", "platform", "this_month_label", "this_month_bottles",
                         "last_month_label", "last_month_bottles", "as_on"}            # totals only — nothing else is exposed
    for sig in ("bad", cards.sign_store(s.id)[:-1] + "0"):
        assert client.get(f"{API}/public/count", params={"s": str(s.id), "sig": sig}).status_code == 404


def test_public_count_gives_the_same_404_for_unknown_stores(client):
    import uuid
    sid = uuid.uuid4()
    assert client.get(f"{API}/public/count", params={"s": str(sid), "sig": cards.sign_store(sid)}).status_code == 404


# ---------------------------------------------------------------- vendors
def test_vendors_listing_groups_stores(client, admin, make_store):
    make_store(vendor="ZZ Vendor"), make_store(vendor="ZZ Vendor"), make_store(vendor="ZZ Other")
    vendors = {v["vendor"]: v["stores"] for v in client.get(f"{API}/cards/vendors", headers=admin).json()["vendors"]}
    assert vendors["ZZ Vendor"] == 2 and vendors["ZZ Other"] == 1


def test_employees_only_see_vendors_of_their_own_stores(client, emp, make_store):
    make_store(vendor="MINE", platform="blinkit", region="NORTH")
    make_store(vendor="NOT MINE", platform="zepto", region="NORTH", state="Karnataka")
    names = {v["vendor"] for v in client.get(f"{API}/cards/vendors", headers=emp).json()["vendors"]}
    assert "MINE" in names and "NOT MINE" not in names


# ---------------------------------------------------------------- PDFs
def test_blank_and_monthly_pdf_for_a_vendor(client, admin, make_store):
    make_store(vendor="PDF Vendor"), make_store(vendor="PDF Vendor")
    blank = client.get(f"{API}/cards/pdf", headers=admin, params={"partner": "blinkit", "vendor": "PDF Vendor"})
    assert blank.status_code == 200 and blank.content[:5] == b"%PDF-" and blank.headers["x-card-count"] == "2"
    monthly = client.get(f"{API}/cards/pdf", headers=admin, params={"partner": "blinkit", "vendor": "PDF Vendor", "month": "2026-09"})
    assert monthly.status_code == 200 and monthly.content[:5] == b"%PDF-"
    assert "2026" in monthly.headers["content-disposition"] or "SEP" in monthly.headers["content-disposition"].upper()


def test_pdf_with_entries_differs_from_the_blank_card(client, db, admin, make_store):
    s = make_store(vendor="Entries Vendor")
    entry(db, s, date(2026, 9, 3), 4)
    p = {"partner": "blinkit", "store_id": str(s.id)}
    blank = client.get(f"{API}/cards/pdf", headers=admin, params=p).content
    with_month = client.get(f"{API}/cards/pdf", headers=admin, params={**p, "month": "2026-09"}).content
    assert blank != with_month


@pytest.mark.parametrize("params,status", [
    ({"partner": "blinkit", "vendor": "NO SUCH VENDOR"}, 404),
    ({"partner": "blinkit", "vendor": "x", "month": "2026-08"}, 422),
    ({"partner": "blinkit", "vendor": "x", "month": "junk"}, 422),
])
def test_pdf_errors(client, admin, params, status):
    assert client.get(f"{API}/cards/pdf", headers=admin, params=params).status_code == status


# ---------------------------------------------------------------- ZIP
def test_zip_has_one_pdf_per_vendor(client, admin, make_store):
    make_store(vendor="ZIP A"), make_store(vendor="ZIP A"), make_store(vendor="ZIP B")
    r = client.post(f"{API}/cards/zip", headers=admin, json={"vendors": ["ZIP A", "ZIP B"], "partner": "blinkit"})
    assert r.status_code == 200 and r.headers["x-vendor-count"] == "2" and r.headers["x-card-count"] == "3"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(z.namelist()) == 2 and all(n.lower().endswith(".pdf") for n in z.namelist())
    assert all(z.read(n)[:5] == b"%PDF-" for n in z.namelist())


def test_zip_with_a_month_is_named_for_it(client, admin, make_store):
    make_store(vendor="ZIP M")
    r = client.post(f"{API}/cards/zip", headers=admin, json={"vendors": ["ZIP M"], "partner": "blinkit", "month": "2026-09"})
    assert r.status_code == 200 and "2026" in r.headers["content-disposition"] + "".join(zipfile.ZipFile(io.BytesIO(r.content)).namelist())


def test_zip_validation(client, admin, make_store, monkeypatch):
    assert client.post(f"{API}/cards/zip", headers=admin, json={"vendors": []}).status_code == 422
    assert client.post(f"{API}/cards/zip", headers=admin, json={"vendors": ["NOBODY AT ALL"]}).status_code == 404
    assert client.post(f"{API}/cards/zip", headers=admin, json={"vendors": ["x"], "month": "2026-08"}).status_code == 422
    make_store(vendor="CAP")
    monkeypatch.setattr(cards, "MAX_STORES_PER_ZIP", 0)
    assert client.post(f"{API}/cards/zip", headers=admin, json={"vendors": ["CAP"], "partner": "blinkit"}).status_code == 422


def test_zip_never_includes_another_employees_vendors(client, emp, make_store):
    make_store(vendor="SECRET VENDOR", platform="zepto", region="NORTH", state="Karnataka")
    assert client.post(f"{API}/cards/zip", headers=emp, json={"vendors": ["SECRET VENDOR"]}).status_code == 404


def test_cards_require_login_and_permission(client, make_user):
    assert client.post(f"{API}/cards/zip", json={"vendors": ["x"]}).status_code == 401
    code, pw, _ = make_user(grants=("compliance.upload",))
    h = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/cards/vendors", headers=h).status_code == 403
