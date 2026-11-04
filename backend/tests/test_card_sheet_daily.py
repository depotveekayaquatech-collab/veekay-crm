"""Random Card PDF, "my own daily entries" mode: a sheet of store name + total count + one column per day of a chosen month.
The numbers in the sheet go on the cards exactly as written; the preview reports whether each store's days add up to its total."""
import io

import pytest

from app.services import card_sheet_service as svc

from .conftest import API
from .test_card_sheet import BASE, _files, _unlock


@pytest.fixture(autouse=True)
def _reset():
    svc._fails.clear()
    yield
    svc._fails.clear()


def _daily(client, dev, token, text, month="2026-10", name="daily.csv", expect=200):
    r = client.post(f"{BASE}/daily-preview", data={"token": token, "month": month}, files=_files(text, name), headers=dev)
    assert r.status_code == expect, r.text
    return r.json()


def _by_code(p):
    return {m["code"]: m for m in p["matched"]}


def test_days_and_total_are_read_as_written(client, dev):
    token = _unlock(client, dev).json()["token"]
    sheet = "Store name,Total count,1,2,3,4,5\nBlinkit — Saket,15,5,5,5,,\nBLINKIT - rohini,7,0,3,4,,\n"
    p = _daily(client, dev, token, sheet)
    got = _by_code(p)
    saket, rohini = got["BLK-4821"], got["BLK-4830"]
    assert [(e["date"], e["count"]) for e in saket["entries"]] == [("2026-10-01", 5), ("2026-10-02", 5), ("2026-10-03", 5)]   # a blank day is no entry
    assert (saket["total"], saket["sheet_total"], saket["issues"]) == (15, 15, [])
    assert [e["count"] for e in rohini["entries"]] == [0, 3, 4]                       # a typed 0 is an entry
    assert (rohini["total"], rohini["sheet_total"]) == (7, 7)
    assert p["unmatched"] == [] and p["month"] == "2026-10"


def test_a_total_that_does_not_match_the_days_is_reported_not_changed(client, dev):
    token = _unlock(client, dev).json()["token"]
    p = _daily(client, dev, token, "Store name,Total count,1,2,3\nBlinkit — Saket,20,5,5,5\nBlinkit - Rohini,,1,1,1\n")
    got = _by_code(p)
    assert (got["BLK-4821"]["total"], got["BLK-4821"]["sheet_total"]) == (15, 20)       # the page flags 15 != 20; nothing is adjusted
    assert (got["BLK-4830"]["total"], got["BLK-4830"]["sheet_total"]) == (3, None)      # no total given: nothing to check against


def test_a_day_the_month_does_not_have_is_an_issue_only_when_it_holds_a_number(client, dev):
    token = _unlock(client, dev).json()["token"]
    days = ",".join(str(d) for d in range(1, 32))
    saket = ["5"] + [""] * 30                                                            # 5 on the 1st, 31 left blank
    rohini = ["4"] + [""] * 29 + ["5"]                                                   # 4 on the 1st, 5 under column 31 (November has 30 days)
    sheet = f"Store name,Total count,{days}\nBlinkit — Saket,5,{','.join(saket)}\nBlinkit - Rohini,9,{','.join(rohini)}\n"
    p = _daily(client, dev, token, sheet, month="2026-11")
    got = _by_code(p)
    assert got["BLK-4821"]["issues"] == []                                              # a blank 31 under November is fine
    assert any("31" in i and "November" in i for i in got["BLK-4830"]["issues"])
    assert [e["date"] for e in got["BLK-4830"]["entries"]] == ["2026-11-01"]            # the impossible day is never turned into a date


def test_cells_that_are_not_whole_numbers_are_issues(client, dev):
    token = _unlock(client, dev).json()["token"]
    p = _daily(client, dev, token, "Store name,Total count,1,2,3,4\nBlinkit — Saket,10,5,abc,-3,2.5\n")
    row = _by_code(p)["BLK-4821"]
    assert [e["count"] for e in row["entries"]] == [5]
    assert len(row["issues"]) == 3 and any("2" in i and "abc" in i for i in row["issues"])
    assert _daily(client, dev, token, "Store name,Total count,1,2,3\nBlinkit — Saket,ten,1,1,1\n")["matched"][0]["issues"] != []   # an unreadable total


def test_unknown_stores_keep_their_days_and_get_suggestions(client, dev):
    token = _unlock(client, dev).json()["token"]
    p = _daily(client, dev, token, "Store name,Total count,1,2,3\nBlinkit Gurugram New,6,2,2,2\nNo Such Outlet,3,1,1,1\n")
    by = {u["name"]: u for u in p["unmatched"]}
    assert set(by) == {"Blinkit Gurugram New", "No Such Outlet"} and p["matched"] == []
    assert any(s["code"] == "BLK-4901" for s in by["Blinkit Gurugram New"]["suggestions"])
    assert [e["count"] for e in by["Blinkit Gurugram New"]["entries"]] == [2, 2, 2] and by["Blinkit Gurugram New"]["sheet_total"] == 6


def test_a_repeated_store_adds_up_and_total_rows_and_empty_rows_are_left_out(client, dev):
    token = _unlock(client, dev).json()["token"]
    sheet = "Store name,Total count,1,2,3\nBlinkit — Saket,3,1,1,1\nBlinkit — Saket,5,2,2,1\nBlinkit - Rohini,,,,\nTotal,8,3,3,2\n"
    p = _daily(client, dev, token, sheet)
    assert [m["code"] for m in p["matched"]] == ["BLK-4821"]                            # Rohini had no numbers, "Total" is not a store
    saket = p["matched"][0]
    assert [e["count"] for e in saket["entries"]] == [3, 3, 2] and (saket["total"], saket["sheet_total"]) == (8, 8)
    text = " ".join(p["warnings"])
    assert "more than once" in text and "Blinkit - Rohini" in text


def test_outlet_id_column_title_rows_and_numeric_excel_headers(client, dev):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["October entries"])
    ws.append([])
    ws.append(["Outlet ID", "Total Count", 1, 2, 3])
    ws.append(["BLK-4821", 9, 3, 3, 3])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(f"{BASE}/daily-preview", data={"token": _unlock(client, dev).json()["token"], "month": "2026-10"},
                    files={"file": ("d.xlsx", io.BytesIO(buf.getvalue()), "application/octet-stream")}, headers=dev)
    assert r.status_code == 200, r.text
    assert [e["count"] for e in r.json()["matched"][0]["entries"]] == [3, 3, 3]


def test_the_month_is_required_and_the_sheet_must_have_day_columns(client, dev):
    token = _unlock(client, dev).json()["token"]
    sheet = "Store name,Total count,1,2,3\nBlinkit — Saket,3,1,1,1\n"
    for month in ("", "October", "2026-13"):
        r = client.post(f"{BASE}/daily-preview", data={"token": token, "month": month}, files=_files(sheet), headers=dev)
        assert r.status_code == 422, month
    no_month = client.post(f"{BASE}/daily-preview", data={"token": token}, files=_files(sheet), headers=dev)
    assert no_month.status_code == 422
    bad = _daily(client, dev, token, "Store name,Total count\nBlinkit — Saket,3\n", expect=422)
    assert "day" in bad["detail"].lower()


def test_daily_preview_is_for_the_developer_only_and_needs_the_token(client, emp, admin, dev):
    sheet = "Store name,Total count,1,2,3\nBlinkit — Saket,3,1,1,1\n"
    for h in (emp, admin):
        assert client.post(f"{BASE}/daily-preview", data={"token": "x", "month": "2026-10"}, files=_files(sheet), headers=h).status_code == 403
    assert client.post(f"{BASE}/daily-preview", data={"token": "x", "month": "2026-10"}, files=_files(sheet), headers=dev).status_code == 403


def test_what_the_preview_returns_prints_on_the_cards(client, dev, db):
    import fitz

    token = _unlock(client, dev).json()["token"]
    p = _daily(client, dev, token, "Store name,Total count,1,2,3\nBlinkit — Saket,15,5,5,5\nBlinkit - Rohini,7,0,3,4\n")
    items = [{"store_id": m["store_id"], "rows": [{"date": e["date"], "count": e["count"]} for e in m["entries"]]} for m in p["matched"]]
    r = client.post(f"{BASE}/random-bulk-pdf", json={"token": token, "items": items}, headers=dev)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    pdf = fitz.open(stream=r.content, filetype="pdf")
    assert pdf.page_count == 2 and "OCT-2026" in pdf[0].get_text()


def test_the_sample_sheet_has_a_column_per_day_of_the_month_and_reads_back(client, dev, emp):
    r = client.get(f"{API}/templates/cardsheet-daily", params={"month": "2026-11"}, headers=emp)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(r.content)).worksheets[0]
    head = [c.value for c in ws[1]]
    assert head[:2] == ["Store name", "Total count"] and head[2:] == list(range(1, 31))      # November: 30 days
    token = _unlock(client, dev).json()["token"]
    back = client.post(f"{BASE}/daily-preview", data={"token": token, "month": "2026-11"},
                       files={"file": ("t.xlsx", io.BytesIO(r.content), "application/octet-stream")}, headers=dev)
    assert back.status_code == 200, back.text            # the invented example stores are simply "not found", the layout is understood
