"""Vendor payments fed from Busy 21: code extraction, the secured sync endpoint (upsert / replace_period / validation / unmatched),
the month maths (carry-over, Asia/Kolkata boundary), the CSV upload, and who may reach what."""
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.v1.endpoints import busy_sync as busy_sync_endpoint
from app.core.config import settings
from app.models.busy_ledger import BusyLedgerEntry, BusySyncLog, BusyUnmatchedEntry, BusyVendor, BusyVendorAlias
from app.services import busy_ledger_service
from app.services.busy_codes import extract_vendor_code, split_account_name

from .conftest import API

KEY = "test-busy-key-0123456789"
SYNC = f"{API}/busy-sync"
VP = f"{API}/vendor-payments"
KEYED = {"x-api-key": KEY}


@pytest.fixture(autouse=True)
def _busy(db, monkeypatch):
    monkeypatch.setattr(settings, "BUSY_SYNC_API_KEY", KEY)
    busy_sync_endpoint._key_failures.reset()
    yield
    db.rollback()
    for model in (BusyUnmatchedEntry, BusyLedgerEntry, BusyVendorAlias, BusySyncLog, BusyVendor):
        db.query(model).delete()
    db.commit()


def vendor(db, code="V0001", name="Alpha Traders", city="Delhi", opening="0", opening_date=None, active=True):
    v = BusyVendor(vendor_code=code, name=name, city=city, opening_balance=Decimal(opening), opening_date=opening_date, is_active=active)
    db.add(v)
    db.commit()
    return v


def row(code="V0001", day="2026-10-05", kind="BILL", amount="100.00", voucher="B1", narration="", name=None):
    r = {"date": day, "type": kind, "amount": amount, "voucher_no": voucher, "narration": narration}
    if code:
        r["vendor_code"] = code
    if name:
        r["account_name"] = name
    return r


def sync(client, entries, headers=KEYED, **body):
    return client.post(SYNC, headers=headers, json={"entries": entries, **body})


def ledger(db, code=None):
    db.expire_all()
    q = db.query(BusyLedgerEntry)
    return q.filter_by(vendor_code=code).all() if code else q.all()


def detail(client, headers, code, month, **params):
    r = client.get(f"{VP}/vendors/{code}", headers=headers, params={"month": month, **params})
    assert r.status_code == 200, r.text
    return r.json()


# ---- vendor code extraction -----------------------------------------------------------------

def test_code_is_the_last_word_when_it_matches_the_pattern():
    assert extract_vendor_code("Sharma Traders Gurugram V0123") == "V0123"
    assert extract_vendor_code("  sharma traders  v0123  ") == "V0123"
    assert split_account_name("Sharma Traders Gurugram V0123") == ("Sharma Traders Gurugram", "V0123")


def test_code_must_be_the_last_word_and_a_full_match():
    assert extract_vendor_code("V0123 Sharma Traders") is None
    assert extract_vendor_code("Sharma Traders V01234") is None
    assert extract_vendor_code("Sharma Traders (V0123)") is None
    assert extract_vendor_code("") is None and extract_vendor_code(None) is None


def test_code_format_is_one_setting(monkeypatch):
    monkeypatch.setattr(settings, "BUSY_VENDOR_CODE_REGEX", r"^[A-Z]{2}-\d{3}$")
    assert extract_vendor_code("Sharma Traders AB-123") == "AB-123"
    assert extract_vendor_code("Sharma Traders V0123") is None
    assert extract_vendor_code("Sharma Traders", r"^V\d{4}$") is None


# ---- the secured endpoint ------------------------------------------------------------------

def test_wrong_or_missing_key_is_401_and_nothing_is_stored(client, db):
    vendor(db)
    for headers in ({}, {"x-api-key": "nope"}, {"x-api-key": KEY + "x"}):
        assert sync(client, [row()], headers=headers).status_code == 401
    assert ledger(db) == [] and db.query(BusySyncLog).count() == 0


def test_a_bearer_login_token_does_not_open_the_endpoint(client, db, admin):
    vendor(db)
    assert sync(client, [row()], headers=admin).status_code == 401


def test_endpoint_is_off_while_no_key_is_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "BUSY_SYNC_API_KEY", "")
    assert sync(client, [], headers={"x-api-key": ""}).status_code == 503


def test_guessing_keys_gets_an_ip_locked_out(client):
    for _ in range(settings.LOGIN_IP_MAX_FAILURES):
        assert sync(client, [], headers={"x-api-key": "guess"}).status_code == 401
    blocked = sync(client, [], headers={"x-api-key": "guess"})
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_calls_are_rate_limited_per_client(client, db, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "BUSY_SYNC_PER_MIN", 3)
    codes = [sync(client, []).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_an_empty_request_is_a_heartbeat_that_counts_as_a_successful_sync(client, db):
    r = sync(client, [])
    assert r.status_code == 200 and r.json()["status"] == "SUCCESS" and r.json()["received"] == 0
    assert busy_ledger_service.freshness(db).stale is False


# ---- upsert: duplicate-safe, edits update --------------------------------------------------

def test_sending_the_same_data_twice_never_duplicates(client, db):
    vendor(db)
    rows = [row(voucher="B1"), row(kind="PAYMENT", voucher="P1", amount="40.00"), row(voucher="B2", day="2026-10-09", amount="55.50")]
    first = sync(client, rows).json()
    assert (first["inserted"], first["updated"], first["unchanged"]) == (3, 0, 0)
    second = sync(client, rows).json()
    assert (second["inserted"], second["updated"], second["unchanged"]) == (0, 0, 3)
    assert len(ledger(db)) == 3


def test_the_same_voucher_number_can_be_a_bill_and_a_payment(client, db):
    vendor(db)
    r = sync(client, [row(voucher="X1"), row(kind="PAYMENT", voucher="X1")]).json()
    assert r["inserted"] == 2 and r["rejected"] == 0


def test_an_edited_entry_is_updated_in_place(client, db):
    vendor(db)
    sync(client, [row(voucher="B1", amount="100.00", narration="old")])
    r = sync(client, [row(voucher="B1", amount="250.75", narration="new", day="2026-10-07")]).json()
    assert (r["inserted"], r["updated"]) == (0, 1)
    (entry,) = ledger(db)
    assert (entry.amount, entry.narration, entry.entry_date) == (Decimal("250.75"), "new", date(2026, 10, 7))


def test_vendor_code_is_taken_from_the_account_name_when_missing(client, db):
    vendor(db, "V0123", "Sharma Traders")
    r = sync(client, [row(code=None, name="Sharma Traders Gurugram V0123")]).json()
    assert r["inserted"] == 1 and r["unmatched"] == 0
    assert ledger(db)[0].vendor_code == "V0123"


def test_codes_are_matched_ignoring_case_and_spaces(client, db):
    vendor(db, "V0001")
    assert sync(client, [row(code=" v0001 ")]).json()["inserted"] == 1


def test_matching_is_by_code_never_by_name(client, db):
    vendor(db, "V0001", "Alpha Traders")
    r = sync(client, [row(code=None, name="Alpha Traders")]).json()        # right name, no code
    assert r["inserted"] == 0 and r["unmatched"] == 1
    r = sync(client, [row(code="V0999", name="Alpha Traders V0001")]).json()      # code given wins over the name
    assert r["inserted"] == 0 and r["unmatched"] == 1


def test_amounts_keep_exact_cents(client, db):
    vendor(db)
    sync(client, [row(amount="0.10", voucher="A"), row(amount="0.20", voucher="B"), row(amount="1,23,456.70", voucher="C")])
    assert sum(e.amount for e in ledger(db)) == Decimal("123457.00")


# ---- validation ----------------------------------------------------------------------------

def test_bad_rows_are_listed_and_the_good_ones_still_saved(client, db):
    vendor(db)
    rows = [
        row(voucher="OK1"),
        row(day="2026-13-40", voucher="BADDATE"),
        row(amount="-5", voucher="NEG"),
        row(amount="0", voucher="ZERO"),
        row(kind="REFUND", voucher="BADTYPE"),
        row(voucher=""),
        row(amount="10.123", voucher="CENTS"),
        row(amount="abc", voucher="NAN"),
        row(code=None, voucher="NOID"),
        "not an object",
        row(voucher="OK2"),
    ]
    body = sync(client, rows).json()
    assert body["status"] == "PARTIAL"
    assert (body["received"], body["inserted"], body["rejected"]) == (11, 2, 9)
    assert [e["row"] for e in body["errors"]] == [2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert any("BILL or PAYMENT" in e["message"] for e in body["errors"])
    assert {e.voucher_no for e in ledger(db)} == {"OK1", "OK2"}


def test_a_request_where_every_row_is_bad_is_422_and_logged_as_failed(client, db):
    vendor(db)
    r = sync(client, [row(amount="-1"), row(kind="X")])
    assert r.status_code == 422 and r.json()["status"] == "FAILED" and r.json()["rejected"] == 2
    log = db.query(BusySyncLog).one()
    assert log.status == "FAILED" and "rejected" in log.error_message


def test_a_voucher_repeated_inside_one_request_is_rejected_not_silently_merged(client, db):
    vendor(db)
    body = sync(client, [row(voucher="D1", amount="10"), row(voucher="D1", amount="99")]).json()
    assert (body["inserted"], body["rejected"]) == (1, 1) and "duplicate" in body["errors"][0]["message"]
    assert ledger(db)[0].amount == Decimal("10.00")


def test_a_malformed_body_is_a_logged_422(client, db):
    r = client.post(SYNC, headers=KEYED, json={"mode": "replace_period", "entries": []})
    assert r.status_code == 422
    assert db.query(BusySyncLog).one().status == "FAILED"
    assert client.post(SYNC, headers=KEYED, json={"mode": "nonsense", "entries": []}).status_code == 422


def test_too_many_entries_in_one_request_is_refused(client, db, monkeypatch):
    monkeypatch.setattr(settings, "BUSY_SYNC_MAX_ROWS", 2)
    assert sync(client, [row(voucher=str(i)) for i in range(3)]).status_code == 413


# ---- replace_period ---------------------------------------------------------------------------

def _period(frm="2026-10-01", to="2026-10-31"):
    return {"mode": "replace_period", "period": {"from": frm, "to": to}}


def test_replace_period_removes_what_busy_no_longer_has_and_adds_the_rest(client, db):
    vendor(db, "V0001")
    vendor(db, "V0002", "Beta")
    sync(client, [row(voucher="A", amount="10"), row(voucher="B", amount="20"), row(voucher="C", day="2026-11-03", amount="30"), row("V0002", voucher="Z", amount="5")])
    r = sync(client, [row(voucher="A", amount="11"), row(voucher="D", amount="40")], **_period()).json()
    assert (r["inserted"], r["updated"], r["deleted"], r["rejected"]) == (1, 1, 1, 0)
    mine = {e.voucher_no: e.amount for e in ledger(db, "V0001")}
    assert mine == {"A": Decimal("11.00"), "D": Decimal("40.00"), "C": Decimal("30.00")}      # B gone, C (November) untouched
    assert len(ledger(db, "V0002")) == 1                                                       # a vendor not in the request is untouched


def test_replace_period_never_touches_csv_or_manual_entries(client, db):
    vendor(db)
    db.add(BusyLedgerEntry(vendor_code="V0001", entry_date=date(2026, 10, 2), entry_type="BILL", amount=Decimal("7"), voucher_no="CSV1", source="CSV",
                           synced_at=datetime.now(timezone.utc)))
    db.commit()
    sync(client, [row(voucher="A")], **_period())
    assert {e.voucher_no for e in ledger(db)} == {"CSV1", "A"}


def test_replace_period_can_clear_a_vendor_that_has_no_rows_left(client, db):
    vendor(db)
    sync(client, [row(voucher="A")])
    r = sync(client, [], vendor_codes=["V0001"], **_period()).json()
    assert r["deleted"] == 1 and ledger(db) == []


def test_replace_period_without_vendor_codes_and_no_rows_deletes_nothing(client, db):
    vendor(db)
    sync(client, [row(voucher="A")])
    assert sync(client, [], **_period()).json()["deleted"] == 0 and len(ledger(db)) == 1


def test_rows_outside_the_period_are_rejected_and_nothing_is_deleted_for_a_bad_batch(client, db):
    vendor(db)
    sync(client, [row(voucher="A")])
    body = sync(client, [row(voucher="OUT", day="2026-11-02")], vendor_codes=["V0001"], **_period())
    assert body.status_code == 422 and "outside the period" in body.json()["errors"][0]["message"]
    assert [e.voucher_no for e in ledger(db)] == ["A"]


def test_a_failure_part_way_rolls_everything_back_and_is_logged(client, db, monkeypatch):
    vendor(db)
    sync(client, [row(voucher="A")])
    from app.services import busy_sync_service

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(busy_sync_service, "_delete_stale_api_rows", boom)
    with pytest.raises(RuntimeError):
        sync(client, [row(voucher="NEW")], **_period())
    assert [e.voucher_no for e in ledger(db)] == ["A"]                           # the new row was rolled back too
    last = db.query(BusySyncLog).order_by(BusySyncLog.started_at.desc()).first()
    assert last.status == "FAILED" and "RuntimeError" in last.error_message and "disk on fire" not in last.error_message


# ---- unmatched ---------------------------------------------------------------------------------

def test_unknown_codes_are_parked_with_the_raw_row_and_never_duplicated(client, db):
    vendor(db)
    rows = [row("V0777", voucher="U1", name="Ghost Traders V0777"), row(code=None, voucher="U2", name="No Code Co")]
    body = sync(client, rows).json()
    assert (body["unmatched"], body["inserted"]) == (2, 0)
    assert set(body["unmatched_codes"]) == {"V0777", "(no code)"}
    sync(client, rows)
    parked = db.query(BusyUnmatchedEntry).order_by(BusyUnmatchedEntry.voucher_no).all()
    assert [p.voucher_no for p in parked] == ["U1", "U2"] and parked[0].raw["voucher_no"] == "U1" and parked[1].vendor_code is None
    assert ledger(db) == []


def test_creating_the_vendor_moves_its_parked_rows_into_the_ledger(client, db, admin):
    sync(client, [row("V0777", voucher="U1", amount="300", name="Ghost Traders V0777"), row("V0777", kind="PAYMENT", voucher="U2", amount="100")])
    groups = client.get(f"{VP}/admin/unmatched", headers=admin).json()
    assert groups[0]["vendor_code"] == "V0777" and groups[0]["rows"] == 2 and groups[0]["suggested_name"] == "Ghost Traders"
    r = client.post(f"{VP}/admin/unmatched/create-vendor", headers=admin,
                    json={"vendor_code": "V0777", "new_vendor": {"vendor_code": "V0777", "name": "Ghost Traders", "city": "Pune"}})
    assert r.status_code == 200 and r.json()["moved"] == 2 and r.json()["inserted"] == 2
    assert client.get(f"{VP}/admin/unmatched", headers=admin).json() == []
    assert detail(client, admin, "V0777", "2026-10")["month"]["closing"] == "200.00"


def test_mapping_to_an_existing_vendor_also_fixes_future_syncs(client, db, admin):
    vendor(db, "V0001")
    sync(client, [row("V0888", voucher="U1", amount="90")])
    r = client.post(f"{VP}/admin/unmatched/map", headers=admin, json={"vendor_code": "V0888", "map_to_vendor_code": "V0001"})
    assert r.status_code == 200 and r.json()["moved"] == 1
    assert [e.vendor_code for e in ledger(db)] == ["V0001"]
    later = sync(client, [row("V0888", voucher="U2", amount="10")]).json()
    assert later["inserted"] == 1 and later["unmatched"] == 0
    assert {e.vendor_code for e in ledger(db)} == {"V0001"}


def test_mapping_refuses_a_code_that_is_already_a_vendor(client, db, admin):
    vendor(db, "V0001")
    vendor(db, "V0002", "Beta")
    db.add(BusyUnmatchedEntry(dedupe_key="k", vendor_code="V0002", account_name="", entry_date=date(2026, 10, 1), entry_type="BILL", amount=Decimal("1"),
                              voucher_no="Q", source="API", raw={}))
    db.commit()
    assert client.post(f"{VP}/admin/unmatched/map", headers=admin, json={"vendor_code": "V0002", "map_to_vendor_code": "V0001"}).status_code == 409


# ---- the month maths ------------------------------------------------------------------------------

def _seed_three_months(db):
    """Opening 10,000 owed as of 1 Aug. Aug: bill 5,000, paid 2,000. Sep: bill 1,000, paid 4,000 (payments exceed bills). Oct: bill 3,000, paid 500."""
    vendor(db, "V0100", "Maths Co", "Delhi", opening="10000", opening_date=date(2026, 8, 1))
    entries = [
        ("2026-07-20", "BILL", "999"), ("2026-07-25", "PAYMENT", "111"),                       # before the opening date: already inside the opening balance
        ("2026-08-03", "BILL", "5000"), ("2026-08-30", "PAYMENT", "2000"),
        ("2026-09-05", "BILL", "1000"), ("2026-09-28", "PAYMENT", "4000"),
        ("2026-10-31", "BILL", "3000"), ("2026-10-15", "PAYMENT", "500"),
    ]
    return [row("V0100", day=d, kind=k, amount=a, voucher=f"{k[0]}{i}") for i, (d, k, a) in enumerate(entries)]


def test_month_figures_and_carry_over_across_months(client, db, admin):
    sync(client, _seed_three_months(db))
    aug, sep, oct_ = (detail(client, admin, "V0100", m)["month"] for m in ("2026-08", "2026-09", "2026-10"))
    assert (aug["opening"], aug["month_total"], aug["paid"], aug["pending"], aug["closing"]) == ("10000.00", "5000.00", "2000.00", "3000.00", "13000.00")
    assert (sep["opening"], sep["month_total"], sep["paid"], sep["pending"], sep["closing"]) == ("13000.00", "1000.00", "4000.00", "-3000.00", "10000.00")
    assert (oct_["opening"], oct_["month_total"], oct_["paid"], oct_["pending"], oct_["closing"]) == ("10000.00", "3000.00", "500.00", "2500.00", "12500.00")


def test_history_is_oldest_first_and_chains_opening_to_the_previous_closing(client, db, admin):
    sync(client, _seed_three_months(db))
    hist = detail(client, admin, "V0100", "2026-10", months=4)["history"]
    assert [h["month"] for h in hist] == ["2026-07", "2026-08", "2026-09", "2026-10"]
    assert hist[0]["opening"] == "0.00"                     # July is before the opening date: the opening balance does not exist yet
    for before, after in zip(hist[1:], hist[2:]):
        assert after["opening"] == before["closing"]
    assert len(detail(client, admin, "V0100", "2026-10")["history"]) == 12


def test_the_all_vendors_table_matches_the_single_vendor_view_and_totals_cover_every_vendor(client, db, admin):
    sync(client, _seed_three_months(db))
    vendor(db, "V0101", "Other Co", "Pune", opening="500", opening_date=date(2026, 10, 1))
    sync(client, [row("V0101", day="2026-10-02", amount="100", voucher="O1")])
    page = client.get(f"{VP}/summary", headers=admin, params={"month": "2026-10", "page_size": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert page["totals"] == {"vendors": 2, "month_total": "3100.00", "paid": "500.00", "pending": "2600.00", "closing": "13100.00"}
    everyone = client.get(f"{VP}/summary", headers=admin, params={"month": "2026-10"}).json()["items"]
    for item in everyone:
        month = detail(client, admin, item["vendor_code"], "2026-10")["month"]
        assert (item["month_total"], item["paid"], item["pending"], item["closing"]) == (month["month_total"], month["paid"], month["pending"], month["closing"])


def test_a_new_import_changes_the_figures_immediately(client, db, admin):
    vendor(db)
    assert detail(client, admin, "V0001", "2026-10")["month"]["closing"] == "0.00"
    sync(client, [row(amount="75.25")])
    assert detail(client, admin, "V0001", "2026-10")["month"]["closing"] == "75.25"
    sync(client, [row(voucher="P", kind="PAYMENT", amount="75.25")])
    assert detail(client, admin, "V0001", "2026-10")["month"]["closing"] == "0.00"


def test_month_boundaries_use_the_calendar_date_of_the_entry(client, db, admin):
    vendor(db)
    sync(client, [row(day="2026-10-31", voucher="LAST", amount="10"), row(day="2026-11-01", voucher="FIRST", amount="20")])
    assert detail(client, admin, "V0001", "2026-10")["month"]["month_total"] == "10.00"
    nov = detail(client, admin, "V0001", "2026-11")["month"]
    assert (nov["opening"], nov["month_total"], nov["closing"]) == ("10.00", "20.00", "30.00")


def test_this_month_is_read_on_the_india_clock():
    late_oct_utc = datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc)          # 23:30 on 31 Oct in India
    after_midnight_ist = datetime(2026, 10, 31, 18, 31, tzinfo=timezone.utc)   # 00:01 on 1 Nov in India
    assert busy_ledger_service.current_month(late_oct_utc) == "2026-10"
    assert busy_ledger_service.current_month(after_midnight_ist) == "2026-11"
    assert busy_ledger_service.current_month(datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc)) == "2027-01"


def test_the_summary_defaults_to_the_current_month_in_india(client, db, admin, monkeypatch):
    vendor(db)
    this_month = busy_ledger_service.current_month()
    assert client.get(f"{VP}/summary", headers=admin).json()["month"] == this_month
    assert client.get(f"{VP}/summary", headers=admin, params={"month": "2026-13"}).status_code == 422


def test_summary_sorting_and_paging(client, db, admin):
    for i, (name, city) in enumerate([("Charlie", "Agra"), ("Alpha", "Zoya"), ("Bravo", "Mumbai")], start=1):
        vendor(db, f"V000{i}", name, city)
    sync(client, [row("V0001", amount="5", voucher="a"), row("V0002", amount="50", voucher="b"), row("V0003", amount="500", voucher="c")])
    names = lambda **p: [i["name"] for i in client.get(f"{VP}/summary", headers=admin, params={"month": "2026-10", **p}).json()["items"]]
    assert names() == ["Alpha", "Bravo", "Charlie"]
    assert names(sort="month_total", direction="desc") == ["Bravo", "Alpha", "Charlie"]
    assert names(sort="city") == ["Charlie", "Bravo", "Alpha"]
    assert names(sort="name", page=2, page_size=2) == ["Charlie"]


def test_vendor_search_by_name_city_or_code(client, db, emp):
    vendor(db, "V0001", "Sharma Traders", "Gurugram")
    vendor(db, "V0002", "Gupta Stores", "Noida")
    vendor(db, "V0003", "Hidden", "Noida", active=False)
    find = lambda q: [v["vendor_code"] for v in client.get(f"{VP}/vendors", headers=emp, params={"q": q}).json()]
    assert find("sharma") == ["V0001"] and find("noida") == ["V0002"] and find("v0002") == ["V0002"] and find("") == ["V0002", "V0001"]
    assert find("%") == [] and find("hidden") == []


def test_entries_of_the_month_are_listed_by_date(client, db, emp):
    vendor(db)
    sync(client, [row(day="2026-10-09", voucher="B2", amount="2", narration="second"), row(day="2026-10-02", voucher="B1", amount="1", narration="first"),
                  row(day="2026-09-30", voucher="OLD")])
    entries = detail(client, emp, "V0001", "2026-10")["entries"]
    assert [(e["entry_date"], e["voucher_no"], e["entry_type"], e["amount"], e["narration"]) for e in entries] == [
        ("2026-10-02", "B1", "BILL", "1.00", "first"), ("2026-10-09", "B2", "BILL", "2.00", "second")]


# ---- freshness --------------------------------------------------------------------------------------

def test_freshness_never_synced_fresh_then_stale(client, db, emp):
    status = lambda: client.get(f"{VP}/status", headers=emp).json()
    assert status()["never_synced"] is True and status()["stale"] is True
    sync(client, [])
    assert status()["stale"] is False and status()["last_source"] == "API" and status()["stale_hours"] == settings.BUSY_STALE_HOURS
    db.query(BusySyncLog).update({"finished_at": datetime.now(timezone.utc) - timedelta(hours=settings.BUSY_STALE_HOURS, minutes=5)})
    db.commit()
    assert status()["stale"] is True and status()["never_synced"] is False


def test_failed_syncs_do_not_refresh_the_last_updated_time(client, db, emp):
    vendor(db)
    sync(client, [row(amount="-1")])
    assert client.get(f"{VP}/status", headers=emp).json()["never_synced"] is True


def test_every_authenticated_call_is_logged_with_its_counts(client, db, admin):
    vendor(db)
    sync(client, [row(voucher="A"), row("V0999", voucher="U")])
    log = db.query(BusySyncLog).one()
    assert (log.source, log.status, log.rows_received, log.rows_inserted, log.rows_unmatched) == ("API", "SUCCESS", 2, 1, 1)
    page = client.get(f"{VP}/admin/sync-logs", headers=admin).json()
    assert page["total"] == 1 and page["items"][0]["rows_inserted"] == 1


# ---- who may do what -----------------------------------------------------------------------------------

ADMIN_GETS = ["/admin/vendors", "/admin/vendors/check-code?code=V1", "/admin/sync-logs", "/admin/unmatched", "/admin/key-info", "/admin/csv/template"]
ADMIN_WRITES = [("post", "/admin/vendors", {"vendor_code": "V9", "name": "X"}), ("patch", "/admin/vendors/V0001", {"name": "Y"}),
                ("post", "/admin/unmatched/create-vendor", {"vendor_code": "V1", "new_vendor": {"vendor_code": "V1", "name": "X"}}),
                ("post", "/admin/unmatched/map", {"vendor_code": "V1", "map_to_vendor_code": "V0001"}), ("post", "/admin/key-info/generate", None)]


def test_an_employee_can_read_but_nothing_in_the_admin_area_is_open_to_them(client, db, emp):
    vendor(db)
    for path in ("/status", "/vendors", "/summary", "/vendors/V0001"):
        assert client.get(f"{VP}{path}", headers=emp).status_code == 200, path
    for path in ADMIN_GETS:
        assert client.get(f"{VP}{path}", headers=emp).status_code == 403, path
    for method, path, body in ADMIN_WRITES:
        assert client.request(method, f"{VP}{path}", headers=emp, **({"json": body} if body else {})).status_code == 403, path
    for path in ("/admin/csv/preview", "/admin/csv/import"):
        r = client.post(f"{VP}{path}", headers=emp, files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
        assert r.status_code == 403, path
    assert db.query(BusyVendor).count() == 1


def test_the_read_endpoints_have_no_way_to_write(client, db, emp, admin):
    vendor(db)
    for headers in (emp, admin):
        for path in ("/status", "/vendors", "/summary", "/vendors/V0001"):
            for method in ("post", "put", "patch", "delete"):
                assert client.request(method, f"{VP}{path}", headers=headers, json={}).status_code == 405, (method, path)


def test_everyone_signed_out_is_refused(client, db):
    vendor(db)
    for path in ("/status", "/vendors", "/summary", "/vendors/V0001", "/admin/vendors", "/admin/sync-logs"):
        assert client.get(f"{VP}{path}").status_code == 401, path


def test_partner_logins_cannot_see_vendor_payments(client, db, make_user):
    from .conftest import auth, login

    vendor(db)
    code, pw, _ = make_user("partner", platform="zepto")
    token = login(client, code, pw).json()["access_token"]
    assert client.get(f"{VP}/summary", headers=auth(token)).status_code == 403


def test_administrators_can_use_the_admin_area(client, db, admin):
    for path in ADMIN_GETS:
        assert client.get(f"{VP}{path}", headers=admin).status_code == 200, path


# ---- vendor management -----------------------------------------------------------------------------------

def test_admin_creates_edits_and_deactivates_a_vendor(client, db, admin, emp):
    r = client.post(f"{VP}/admin/vendors", headers=admin, json={"vendor_code": " v0500 ", "name": "  New   Vendor ", "city": "Jaipur", "opening_balance": "1500.50", "opening_date": "2026-09-01"})
    assert r.status_code == 201 and r.json()["vendor_code"] == "V0500" and r.json()["name"] == "New Vendor"
    assert client.post(f"{VP}/admin/vendors", headers=admin, json={"vendor_code": "V0500", "name": "Dup"}).status_code == 409
    assert client.patch(f"{VP}/admin/vendors/V0500", headers=admin, json={"name": "Renamed", "city": None, "opening_balance": "2000"}).json()["name"] == "Renamed"
    assert client.patch(f"{VP}/admin/vendors/V0500", headers=admin, json={"is_active": False}).json()["is_active"] is False
    assert client.get(f"{VP}/vendors/V0500", headers=emp).status_code == 404                    # hidden from employees
    assert client.get(f"{VP}/vendors/V0500", headers=admin).status_code == 200


def test_the_vendor_code_can_never_be_changed(client, db, admin):
    vendor(db, "V0001")
    assert client.patch(f"{VP}/admin/vendors/V0001", headers=admin, json={"vendor_code": "V0002"}).status_code == 422
    with pytest.raises(DBAPIError, match="cannot be changed"):
        db.execute(text("UPDATE busy_vendors SET vendor_code = 'V0002' WHERE vendor_code = 'V0001'"))
    db.rollback()
    assert db.query(BusyVendor).one().vendor_code == "V0001"


def test_vendor_input_is_validated(client, db, admin):
    bad = [{"vendor_code": "", "name": "X"}, {"vendor_code": "V 1", "name": "X"}, {"vendor_code": "V" * 40, "name": "X"}, {"vendor_code": "V1", "name": "   "},
           {"vendor_code": "V1", "name": "X", "opening_date": "2026-09-15"}, {"vendor_code": "V1", "name": "X", "opening_balance": "1.234"}]
    for body in bad:
        assert client.post(f"{VP}/admin/vendors", headers=admin, json=body).status_code == 422, body
    assert db.query(BusyVendor).count() == 0


def test_duplicate_code_check(client, db, admin):
    vendor(db, "V0001")
    check = lambda c: client.get(f"{VP}/admin/vendors/check-code", headers=admin, params={"code": c}).json()
    assert check("v0001")["exists"] is True and check("V0002")["exists"] is False and check("V 2")["valid"] is False


def test_key_info_never_reveals_the_key(client, admin):
    info = client.get(f"{VP}/admin/key-info", headers=admin).json()
    assert info["configured"] is True and KEY not in str(info)
    fresh = client.post(f"{VP}/admin/key-info/generate", headers=admin).json()["key"]
    assert len(fresh) >= 32 and fresh != KEY


# ---- CSV upload -------------------------------------------------------------------------------------------------

def csv_file(text_: str, name="busy.csv"):
    return {"file": (name, io.BytesIO(text_.encode("utf-8")), "text/csv")}


def test_the_sample_template_is_itself_a_valid_upload(client, db, admin):
    vendor(db, "V0123", "Sharma")
    vendor(db, "V0456", "Other")
    template = client.get(f"{VP}/admin/csv/template", headers=admin)
    assert template.headers["content-type"].startswith("text/csv")
    preview = client.post(f"{VP}/admin/csv/preview", headers=admin, files=csv_file(template.text)).json()
    assert preview["missing_fields"] == [] and preview["result"]["inserted"] == 3 and preview["result"]["rejected"] == 0


def test_preview_changes_nothing_and_matches_the_real_import(client, db, admin):
    vendor(db)
    sync(client, [row(voucher="B1", amount="10")])
    data = "Party,Voucher Date,Vch No,Vch Type,Amt,Remarks,Code\nAlpha,05/10/2026,B1,Bill,11.00,edited,V0001\nAlpha,06/10/2026,P1,PAYMENT,4,,V0001\nGhost,06/10/2026,G1,BILL,9,,V0999\nAlpha,xx,B9,BILL,1,,V0001\n"
    logs_before = db.query(BusySyncLog).count()
    pre = client.post(f"{VP}/admin/csv/preview", headers=admin, files=csv_file(data)).json()
    assert pre["mapping"] == {"account_name": "Party", "vendor_code": "Code", "date": "Voucher Date", "type": "Vch Type", "amount": "Amt", "voucher_no": "Vch No", "narration": "Remarks"}
    res = pre["result"]
    assert (res["inserted"], res["updated"], res["unmatched"], res["rejected"], res["dry_run"]) == (1, 1, 1, 1, True)
    assert len(ledger(db)) == 1 and db.query(BusySyncLog).count() == logs_before and db.query(BusyUnmatchedEntry).count() == 0
    done = client.post(f"{VP}/admin/csv/import", headers=admin, files=csv_file(data)).json()
    assert all(done[k] == res[k] for k in ("inserted", "updated", "unchanged", "unmatched", "rejected")) and done["dry_run"] is False
    assert {e.voucher_no: e.source for e in ledger(db)} == {"B1": "CSV", "P1": "CSV"}
    log = db.query(BusySyncLog).order_by(BusySyncLog.started_at.desc()).first()
    assert log.source == "CSV" and log.status == "PARTIAL" and "ADMIN001" in log.triggered_by
    assert busy_ledger_service.freshness(db).last_source == "CSV"


def test_the_admin_can_correct_the_column_mapping(client, db, admin):
    vendor(db)
    data = "a,b,c,d,e\n05/10/2026,BILL,100,V0001,INV-7\n"
    pre = client.post(f"{VP}/admin/csv/preview", headers=admin, files=csv_file(data)).json()
    assert pre["result"] is None and set(pre["missing_fields"]) >= {"date", "type", "amount", "voucher_no"}
    mapping = '{"date": "a", "type": "b", "amount": "c", "vendor_code": "d", "voucher_no": "e"}'
    pre = client.post(f"{VP}/admin/csv/preview", headers=admin, files=csv_file(data), data={"mapping": mapping}).json()
    assert pre["missing_fields"] == [] and pre["result"]["inserted"] == 1
    assert client.post(f"{VP}/admin/csv/import", headers=admin, files=csv_file(data)).status_code == 422          # still unmapped: refused
    assert client.post(f"{VP}/admin/csv/import", headers=admin, files=csv_file(data), data={"mapping": mapping}).json()["inserted"] == 1
    assert client.post(f"{VP}/admin/csv/preview", headers=admin, files=csv_file(data), data={"mapping": '{"date": "nope"}'}).status_code == 422


def test_csv_edge_cases(client, db, admin):
    vendor(db)
    assert client.post(f"{VP}/admin/csv/preview", headers=admin, files=csv_file("")).status_code == 422
    semi = "vendor_code;date;type;amount;voucher_no\nV0001;2026-10-01;BILL;1.5;S1\n\nV0001;2026-10-02;PAYMENT;1;S2\n"
    assert client.post(f"{VP}/admin/csv/preview", headers=admin, files=csv_file(semi)).json()["result"]["inserted"] == 2
    latin = "vendor_code,date,type,amount,voucher_no,narration\nV0001,2026-10-01,BILL,1,L1,Caf\xe9\n".encode("cp1252")
    r = client.post(f"{VP}/admin/csv/import", headers=admin, files={"file": ("l.csv", io.BytesIO(latin), "text/csv")})
    assert r.json()["inserted"] == 1 and ledger(db)[0].narration == "Café"
