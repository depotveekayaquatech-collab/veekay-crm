"""Cards from a sheet: developer-only + access code, preview / PDF, source footer, audit log, nothing written to orders."""
import io

import pytest

from app.models.audit_log import AuditLog
from app.models.order_entry import OrderEntry
from app.services import card_sheet_service as svc

from .conftest import API

BASE = f"{API}/developer/card-sheet"


@pytest.fixture(autouse=True)
def _reset():
    svc._fails.clear()
    yield
    svc._fails.clear()


def _csv(rows):
    return "store code,date,filled bottles\n" + "\n".join(rows) + "\n"


def _unlock(client, dev, code="2580"):
    return client.post(f"{BASE}/unlock", json={"code": code}, headers=dev)


def _files(text, name="entries.csv"):
    return {"file": (name, io.BytesIO(text.encode()), "text/csv")}


def test_permission_and_access_code(client, admin, emp, dev, db):
    for who in (admin, emp):                                           # the permission is reserved to the developer
        assert _unlock(client, who).status_code == 403
    bad = _unlock(client, dev, "0000")
    assert bad.status_code == 403 and "isn't right" in bad.json()["detail"]
    ok = _unlock(client, dev)
    assert ok.status_code == 200 and ok.json()["token"]
    # no token / a made-up token / someone else's token can't use the tool
    sheet = _csv(["BLK-4821,2026-09-03,12"])
    assert client.post(f"{BASE}/preview", data={"token": "x"}, files=_files(sheet), headers=dev).status_code == 403
    assert client.post(f"{BASE}/preview", data={"token": ok.json()["token"] + "A"}, files=_files(sheet), headers=dev).status_code == 403
    acts = {a for (a,) in db.query(AuditLog.action).filter(AuditLog.entity_type == "card_sheet")}
    assert {"card_sheet.unlock_failed", "card_sheet.unlocked"} <= acts


def test_five_wrong_codes_lock_the_user_out(client, dev):
    for _ in range(5):
        assert _unlock(client, dev, "1111").status_code == 403
    r = _unlock(client, dev)                                           # even the right code waits
    assert r.status_code == 429 and "minutes" in r.json()["detail"]


def test_preview_and_download(client, dev, db):
    token = _unlock(client, dev).json()["token"]
    sheet = _csv(["BLK-4821,2026-09-03,12", "BLK-4821,04/09/2026,8", "BLK-4821,2026-09-03,2", "BLK-4830,2026-09-05,30", "NOPE-1,2026-09-05,5", "BLK-4830,not-a-date,5"])
    before = db.query(OrderEntry).count()
    pv = client.post(f"{BASE}/preview", data={"token": token}, files=_files(sheet), headers=dev)
    assert pv.status_code == 200, pv.text
    p = pv.json()
    assert (p["rows"], p["cards"], p["stores"], p["entries"], p["bottles"]) == (6, 2, 2, 3, 12 + 2 + 8 + 30)
    assert p["unmatched_count"] == 2 and any("more than once" in w for w in p["warnings"])
    dl = client.post(f"{BASE}/download", data={"token": token}, files=_files(sheet), headers=dev)
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF") and "attachment" in dl.headers["content-disposition"]
    import fitz

    pdf = fitz.open(stream=dl.content, filetype="pdf")
    assert pdf.page_count == 2
    text = pdf[0].get_text()
    assert "Source: uploaded sheet 'entries.csv'" in text and "Not generated from the order records" in text and "SEP-2026" in text
    assert "TOTAL" in text.upper()
    assert db.query(OrderEntry).count() == before                       # nothing was written to the orders
    meta = [m for (m,) in db.query(AuditLog.metadata_json).filter(AuditLog.action == "card_sheet.download")][-1]
    assert meta["file"] == "entries.csv" and meta["cards"] == 2 and meta["bottles"] == 52 and len(meta["sha256"]) == 64
    # the entries themselves are never stored: the log keeps only the file name, a fingerprint and totals
    assert set(meta) == {"file", "sha256", "cards", "stores", "entries", "bottles"}
    logged = " ".join(str(m) for (m,) in db.query(AuditLog.metadata_json).filter(AuditLog.entity_type == "card_sheet"))
    assert "2026-09-03" not in logged and "BLK-4821" not in logged


def test_bad_sheets_are_refused(client, dev):
    token = _unlock(client, dev).json()["token"]
    no_cols = client.post(f"{BASE}/preview", data={"token": token}, files=_files("a,b\n1,2\n"), headers=dev)
    assert no_cols.status_code == 422 and "date column" in no_cols.json()["detail"]
    none_match = client.post(f"{BASE}/download", data={"token": token}, files=_files(_csv(["NOPE-1,2026-09-05,5"])), headers=dev)
    assert none_match.status_code == 422 and "nothing to print" in none_match.json()["detail"]
    assert client.post(f"{BASE}/preview", data={"token": token}, files=_files("x", "notes.pdf"), headers=dev).status_code == 422


# ---- the wide layout: one row per store, one column per day -------------------------------------------------------

WIDE_HEAD = "Entity,ZONE,State,City,Outlet ID,Outlet Name,POC Name,POC Number,Vendor Name,Vendor Number," + ",".join(f"{d}-Oct" for d in range(1, 32))


def _wide_row(code, values, name=""):
    days = [str(values.get(d, "")) for d in range(1, 32)]
    return f"BCPL,NORTH,Delhi,New Delhi,{code},{name},Poc,9999999999,Vendor,8888888888," + ",".join(days)


def _preview(client, dev, token, text, name="oct.csv"):
    r = client.post(f"{BASE}/preview", data={"token": token}, files=_files(text, name), headers=dev)
    assert r.status_code == 200, r.text
    return r.json()


def test_wide_sheet_in_the_standard_format(client, dev, db):
    token = _unlock(client, dev).json()["token"]
    sheet = WIDE_HEAD + "\n" + "\n".join([
        _wide_row("BLK-4821", {1: 10, 2: 0, 3: 12, 31: 5}),         # a 0 is an entry, an empty day is not
        _wide_row("BLK-4830", {1: 7, 5: "NA", 6: "-", 7: 3}),        # text in a day cell is skipped, not fatal
        _wide_row("NOPE-9", {1: 1}),
    ])
    p = _preview(client, dev, token, sheet)
    assert (p["rows"], p["cards"], p["stores"], p["entries"], p["bottles"]) == (3, 2, 2, 6, 10 + 0 + 12 + 5 + 7 + 3)
    assert p["unmatched_count"] == 1 and p["unmatched"][0]["store"] == "NOPE-9"
    assert any("OCT" in w.upper() and "Dates read as" in w for w in p["warnings"]) and any("2 cell(s)" in w for w in p["warnings"])
    dl = client.post(f"{BASE}/download", data={"token": token}, files=_files(sheet), headers=dev)
    import fitz

    pdf = fitz.open(stream=dl.content, filetype="pdf")
    assert pdf.page_count == 2 and "OCT-" in pdf[0].get_text().upper()


def test_changed_headers_columns_and_extra_rows_still_work(client, dev, db):
    token = _unlock(client, dev).json()["token"]
    # title rows above the header, different order and spelling, store id as a float, totals line, other date styles
    sheet = "\n".join([
        "Monthly report,,,,",
        ",,,,",
        "Store Name,  OUTLET_ID ,Zone,01-Oct-2026,Oct 2,3/10,2026-10-04,5.10.2026",
        "Blinkit Saket,BLK-4821,North,1,2,3,4,5",
        "Total,,,1,2,3,4,5",
    ])
    p = _preview(client, dev, token, sheet)
    assert (p["rows"], p["cards"], p["entries"], p["bottles"]) == (1, 1, 5, 15)
    # matched by store name when the id column is empty or unknown
    named = "Outlet Name,Outlet ID,1-Oct,2-Oct\nBlinkit — Saket,,4,6\n"
    p2 = _preview(client, dev, token, named)
    assert p2["cards"] == 1 and p2["bottles"] == 10


def test_long_layout_still_works_and_unreadable_headers_say_why(client, dev):
    token = _unlock(client, dev).json()["token"]
    assert _preview(client, dev, token, _csv(["BLK-4821,2026-09-03,12"]))["bottles"] == 12
    r = client.post(f"{BASE}/preview", data={"token": token}, files=_files("foo,bar\n1,2\n"), headers=dev)
    assert r.status_code == 422 and "header row" in r.json()["detail"]


def test_wide_xlsx_with_real_date_headers(client, dev):
    from datetime import date

    from openpyxl import Workbook

    token = _unlock(client, dev).json()["token"]
    wb = Workbook()
    ws = wb.active
    ws.append(["Outlet ID", "Outlet Name", date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)])
    ws.append(["BLK-4821", "Blinkit - Saket", 5, 6, 7])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(f"{BASE}/preview", data={"token": token}, files={"file": ("m.xlsx", io.BytesIO(buf.getvalue()), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers=dev)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["cards"] == 2 and p["entries"] == 3 and p["bottles"] == 18        # September and October get a card each


# ---- random count card: render-only ---------------------------------------------------------------------------------

def _store_id(db):
    from app.models.store import Store

    return str(db.query(Store).filter(Store.external_code == "BLK-4821").one().id)


def _random(client, dev, token, store_id, rows):
    return client.post(f"{BASE}/random-pdf", json={"token": token, "store_id": store_id, "rows": rows}, headers=dev)


def test_random_pdf_is_render_only_and_gated(client, admin, dev, db):
    import fitz

    from app.models.audit_log import AuditLog

    token = _unlock(client, dev).json()["token"]
    sid = _store_id(db)
    rows = [{"date": "2026-09-29", "count": 4}, {"date": "2026-09-30", "count": 0}, {"date": "2026-10-01", "count": 9}]
    assert _random(client, admin, token, sid, rows).status_code == 403                    # permission
    assert _random(client, dev, "bogus", sid, rows).status_code == 403                    # token
    before_orders, before_audit = db.query(OrderEntry).count(), db.query(AuditLog).count()
    r = _random(client, dev, token, sid, rows)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert "BLK-4821_Random_Count_Card_2026-09-29_to_2026-10-01.pdf" in r.headers["content-disposition"]
    pdf = fitz.open(stream=r.content, filetype="pdf")
    assert pdf.page_count == 2                                                            # a card per month
    sep, octo = pdf[0].get_text(), pdf[1].get_text()
    assert "SEP-2026" in sep.upper() and "29-Sep-2026" in sep and "30-Sep-2026" in sep and "random count generator" not in sep
    assert "1-Oct-2026" in octo and "TOTAL" in octo.upper()
    assert db.query(OrderEntry).count() == before_orders and db.query(AuditLog).count() == before_audit   # nothing stored or logged


def test_random_pdf_rejects_bad_input(client, dev, db):
    token = _unlock(client, dev).json()["token"]
    sid = _store_id(db)
    ok = {"date": "2026-10-01", "count": 3}
    assert _random(client, dev, token, sid, []).status_code == 422
    assert _random(client, dev, token, sid, [ok, ok]).status_code == 422
    assert _random(client, dev, token, sid, [{"date": "2026-10-01", "count": -1}]).status_code == 422
    assert _random(client, dev, token, "00000000-0000-0000-0000-000000000000", [ok]).status_code == 404


def test_random_card_is_pixel_identical_to_the_store_cards_page(client, dev, db):
    """The random card is drawn by the Store Cards renderer: the whole page is identical, with no extra footer."""
    import fitz

    from app.models.store import Store
    from app.services import card_service

    token = _unlock(client, dev).json()["token"]
    store = db.query(Store).filter(Store.external_code == "BLK-4821").one()
    from datetime import date

    entries = [(date(2026, 10, d), d % 4) for d in range(1, 11)]
    r = _random(client, dev, token, str(store.id), [{"date": d.isoformat(), "count": n} for d, n in entries])
    assert r.status_code == 200
    contacts = card_service._Contacts(db, store.organization_id)
    ref = card_service._render([store], card_service._vendor_key(store), date(2026, 10, 1), contacts, {store.id: entries})

    def shot(data):
        page = fitz.open(stream=data, filetype="pdf")[0]
        return page.get_pixmap(dpi=100).samples

    assert shot(r.content) == shot(ref)
    total = sum(n for _, n in entries)
    assert str(total) in fitz.open(stream=r.content, filetype="pdf")[0].get_text()


def _month_preview(client, dev, token, text, month, name="m.csv"):
    r = client.post(f"{BASE}/preview", data={"token": token, "month": month}, files=_files(text, name), headers=dev)
    assert r.status_code == 200, r.text
    return r.json()


def test_chosen_month_keeps_only_that_months_days(client, dev):
    token = _unlock(client, dev).json()["token"]
    sheet = "Outlet ID,28-Sep,30-Sep,1-Oct,2-Oct\nBLK-4821,5,6,7,8\n"
    both = _preview(client, dev, token, sheet)
    assert both["bottles"] == 26 and both["cards"] == 2                       # no month chosen: everything, as before
    only = _month_preview(client, dev, token, sheet, "2026-10")
    assert (only["cards"], only["entries"], only["bottles"]) == (1, 2, 15)
    assert any("other months" in w for w in only["warnings"])
    none = _month_preview(client, dev, token, sheet, "2026-01")
    assert none["cards"] == 0 and any("Nothing in the sheet falls in" in w for w in none["warnings"])


def test_day_number_columns_are_days_of_the_chosen_month(client, dev):
    token = _unlock(client, dev).json()["token"]
    sheet = "Outlet Name,1,2,3rd,Day 4\nBlinkit — Saket,10,20,30,40\n"
    p = _month_preview(client, dev, token, sheet, "2026-09")
    assert (p["cards"], p["entries"], p["bottles"]) == (1, 4, 100)
    assert any("SEP-2026" in w.upper() for w in p["warnings"])
    # without a month a bare number is not a date, so the sheet can't be read
    r = client.post(f"{BASE}/preview", data={"token": token}, files=_files(sheet), headers=dev)
    assert r.status_code == 422
    bad = client.post(f"{BASE}/preview", data={"token": token, "month": "October"}, files=_files(sheet), headers=dev)
    assert bad.status_code == 422 and "2026-10" in bad.json()["detail"]


def test_any_column_that_identifies_the_store_is_used(client, dev):
    token = _unlock(client, dev).json()["token"]
    # punctuation / spacing / case differ from the stored name
    loose = "Outlet Name,1-Oct,2-Oct\nblinkit saket,4,6\nBLINKIT - ROHINI,1,2\n"
    p = _preview(client, dev, token, loose)
    assert (p["cards"], p["unmatched_count"], p["bottles"]) == (2, 0, 13)
    # no 'Outlet ID' / 'Outlet Name' header at all: the column full of known stores is found by its content
    unnamed = "Region,Shop,Notes,1-Oct,2-Oct\nNORTH,BLK-4821,ok,5,5\nNORTH,BLK-4830,ok,2,2\nNORTH,BLK-4901,ok,1,1\n"
    q = _preview(client, dev, token, unnamed)
    assert (q["cards"], q["bottles"], q["unmatched_count"]) == (3, 16, 0)
    # the store only appears in some other cell of the row, under a header we don't know
    buried = "Outlet ID,Remark,1-Oct\n,Saket outlet BLK-4821,9\nunknown-1,Blinkit — Rohini,3\n"
    r = _preview(client, dev, token, buried)
    assert r["cards"] == 1 and r["bottles"] == 3 and r["unmatched_count"] == 1


# ------------------------------------------------------------ random generator from a sheet (store + total, no dates)

def _totals(client, dev, token, text, name="totals.csv"):
    r = client.post(f"{BASE}/totals-preview", data={"token": token}, files=_files(text, name), headers=dev)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_headerless_name_and_total_sheet_is_read_and_near_misses_get_suggestions(client, dev):
    token = _unlock(client, dev).json()["token"]
    sheet = "Blinkit — Saket,150\nBLINKIT - rohini,455\nBlinkit Gurugram New,340\nNo Such Outlet,12\n"
    p = _totals(client, dev, token, sheet)
    assert p["rows"] == 4
    got = {m["code"]: m["total"] for m in p["matched"]}
    assert got == {"BLK-4821": 150, "BLK-4830": 455}                       # punctuation and case don't matter
    by_name = {u["name"]: u for u in p["unmatched"]}
    assert set(by_name) == {"Blinkit Gurugram New", "No Such Outlet"}
    assert any(s["code"] == "BLK-4901" for s in by_name["Blinkit Gurugram New"]["suggestions"])   # "did you mean ..."
    assert by_name["No Such Outlet"]["suggestions"] == []


def test_headers_codes_repeats_and_junk_rows(client, dev):
    token = _unlock(client, dev).json()["token"]
    sheet = "Outlet ID,Outlet Name,Notes,Total Count\nBLK-4821,,hello,100\nBLK-4821,,again,20\nBLK-4830,,,5\n,Grand Total,,125\n"
    p = _totals(client, dev, token, sheet)
    assert {m["code"]: m["total"] for m in p["matched"]} == {"BLK-4821": 120, "BLK-4830": 5}      # a repeated store adds up
    assert p["unmatched"] == [] and any("more than once" in w for w in p["warnings"])
    bad = client.post(f"{BASE}/totals-preview", data={"token": token}, files=_files("just,words\nhere,there\n"), headers=dev)
    assert bad.status_code == 422


def test_bulk_random_pdf_draws_one_card_per_store_and_month(client, dev, db):
    import fitz

    token = _unlock(client, dev).json()["token"]
    from app.models.store import Store

    a = db.query(Store).filter_by(external_code="BLK-4821").one()
    b = db.query(Store).filter_by(external_code="BLK-4830").one()
    body = {"token": token, "items": [
        {"store_id": str(a.id), "rows": [{"date": "2026-10-01", "count": 10}, {"date": "2026-10-02", "count": 5}]},
        {"store_id": str(b.id), "rows": [{"date": "2026-09-30", "count": 3}, {"date": "2026-10-01", "count": 4}]},   # spans two months
    ]}
    r = client.post(f"{BASE}/random-bulk-pdf", json=body, headers=dev)
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "attachment" in r.headers["content-disposition"]
    assert fitz.open(stream=r.content, filetype="pdf").page_count == 3                  # 1 + 2 months
    assert "2026-09-30_to_2026-10-02" in r.headers["content-disposition"]

    def post(**over):
        return client.post(f"{BASE}/random-bulk-pdf", json={**body, **over}, headers=dev)

    one = body["items"][0]
    assert post(items=[one, one]).status_code == 422                                     # same store twice
    assert post(items=[{**one, "rows": [one["rows"][0], one["rows"][0]]}]).status_code == 422   # same date twice
    assert post(items=[{**one, "rows": [{"date": "2026-10-01", "count": -1}]}]).status_code == 422
    assert post(items=[{"store_id": "00000000-0000-0000-0000-000000000000", "rows": one["rows"]}]).status_code == 404
    assert post(token="bad").status_code == 403
    assert post(items=[]).status_code == 422


def test_bulk_random_is_for_the_developer_only(client, emp, admin):
    for h in (emp, admin):
        assert client.post(f"{BASE}/totals-preview", data={"token": "x"}, files=_files("a,1\n"), headers=h).status_code == 403
        assert client.post(f"{BASE}/random-bulk-pdf", json={"token": "x", "items": []}, headers=h).status_code == 403
