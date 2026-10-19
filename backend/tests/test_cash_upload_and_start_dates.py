"""Upload a cash purchase sheet into the review list; developer 'Sync start dates' from the order sheet; a new store
must have a start date."""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.models.cash_adjustment import CashAdjustment, CashSyncRecord, CashSyncRun
from app.models.cash_purchase import CashPurchase
from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.user import User

from .conftest import API

CASH = f"{API}/developer/cash-adjustments"
TODAY = date.today()
HEADER = ["Date", "Type", "Store / Place", "Store code", "State", "Item", "Reason", "Details", "Proof attached",
          "Amount (INR)", "Added by", "Added on"]


@pytest.fixture(autouse=True)
def _wipe(db):
    yield
    for model in (CashAdjustment, CashSyncRecord, CashSyncRun, CashPurchase):
        db.query(model).delete()
    db.commit()


def _sheet(rows, header=HEADER) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(day, store, amount, kind="Store", code=None):
    return [day, kind, store.name if store else "Office", code if code is not None else (store.external_code if store else None),
            None, "Water bottles", None, None, "No", amount, "Someone", None]


def _upload(client, dev, content, name="cash.xlsx"):
    return client.post(f"{CASH}/sync/upload", headers=dev, files={"file": (name, content, "application/octet-stream")})


def _purchase(db, store, amount, day):
    u = db.query(User).filter_by(employee_code="EMP001").one()
    db.add(CashPurchase(organization_id=store.organization_id, kind="STORE", store_id=store.id, purchase_date=day,
                        category="SUPPLY_DELAYED", amount=Decimal(str(amount)), created_by_user_id=u.id))
    db.commit()


# ---- upload a cash purchase sheet ---------------------------------------------------------------------------------

def test_upload_is_developer_only(client, admin, emp):
    for who in (admin, emp):
        assert _upload(client, who, _sheet([])).status_code == 403


def test_upload_brings_rows_in_for_review_and_changes_nothing_else(client, dev, db, make_store):
    a, b = make_store(code="UP-A"), make_store(code="UP-B")
    d1, d2 = date(2026, 3, 10), TODAY - timedelta(days=3)
    rows = [
        _row(d1, a, 150),
        _row(d2, b, 200.5),
        _row(d2, b, 200.5),                                     # a second, identical purchase the same day is legitimate
        _row(d1, None, 90, kind="Office"),                      # office purchases are not bottles
        _row(d1, None, 40, code="NOPE-1"),                      # a store that isn't in the CRM: added, store to be picked
        _row(TODAY + timedelta(days=2), a, 10),                 # future
        _row(d1, a, "abc"),                                     # bad amount
        ["TOTAL", None, None, None, None, None, None, None, None, 500],
    ]
    r = _upload(client, dev, _sheet(rows))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["added"], body["office_rows"], body["invalid_rows"], body["unmatched_store"]) == (4, 1, 2, 1)
    assert body["summary"]["pending_review"] == 4 and body["summary"]["new_records"] == 4
    assert any("NOPE-1" in w for w in body["warnings"])

    recs = client.get(f"{CASH}/sync/records?status=PENDING", headers=dev).json()["items"]
    assert len(recs) == 4 and {x["status"] for x in recs} == {"PENDING"}
    unmatched = next(x for x in recs if x["store_id"] is None)
    assert unmatched["outlet_code"] == "NOPE-1"                 # the sheet's own text is shown until a store is picked
    assert db.query(OrderEntry).filter(OrderEntry.store_id.in_([a.id, b.id])).count() == 0   # the order sheet is untouched
    assert db.query(CashPurchase).count() == 0                  # and nothing was added to the app's own purchases

    # uploading the same file again adds nothing
    again = _upload(client, dev, _sheet(rows)).json()
    assert again["added"] == 0 and again["already_uploaded"] == 4


def test_the_downloaded_sheet_can_be_uploaded_back_without_double_counting(client, dev, db, make_store):
    a = make_store(code="UP-C")
    _purchase(db, a, 120, TODAY - timedelta(days=2))
    _purchase(db, a, 120, TODAY - timedelta(days=2))
    sheet = client.get(f"{CASH}/purchase-sheet", headers=dev)
    assert sheet.status_code == 200
    r = _upload(client, dev, sheet.content).json()
    assert r["added"] == 0 and r["already_in_app"] >= 2

    # a sheet that has one MORE of the same purchase than the app does: only the extra one is new
    extra = _upload(client, dev, _sheet([_row(TODAY - timedelta(days=2), a, 120)] * 3)).json()
    assert extra["already_in_app"] == 2 and extra["added"] == 1


def test_an_uploaded_row_goes_through_review_and_apply_like_any_other(client, dev, db, make_store):
    a = make_store(code="UP-D")
    day = TODAY - timedelta(days=1)
    db.add(OrderEntry(organization_id=a.organization_id, store_id=a.id, order_date=day, bottle_count=10))
    db.commit()
    assert _upload(client, dev, _sheet([_row(day, a, 100)])).json()["added"] == 1
    rec = client.get(f"{CASH}/sync/records", headers=dev).json()["items"][0]
    assert client.patch(f"{CASH}/sync/records/{rec['id']}", headers=dev, json={"price_per_item": "30"}).status_code == 200
    ok = client.post(f"{CASH}/sync/apply", headers=dev, json={"record_ids": [rec["id"]]})
    assert ok.status_code == 200, ok.text
    db.expire_all()
    assert db.query(OrderEntry).filter_by(store_id=a.id, order_date=day).one().bottle_count == 14   # 10 + ceil(100 / 30)
    # a later sync of the app's purchases must leave the uploaded record alone
    assert client.post(f"{CASH}/sync", headers=dev).status_code == 200
    assert client.get(f"{CASH}/sync/records?status=APPLIED", headers=dev).json()["total"] == 1


def test_upload_rejects_a_sheet_without_the_needed_columns_and_wrong_file_types(client, dev):
    bad = _upload(client, dev, _sheet([[1, 2]], header=["Foo", "Bar"]))
    assert bad.status_code == 422 and "columns" in bad.json()["detail"]
    assert _upload(client, dev, b"hello", name="cash.pdf").status_code == 422
    assert _upload(client, dev, _sheet([]), name="empty.xlsx").status_code == 422


def test_upload_accepts_csv_with_a_price_column(client, dev, db, make_store):
    a = make_store(code="UP-E")
    day = (TODAY - timedelta(days=4)).strftime("%d-%b-%Y")
    csv = f"Date,Store code,Amount,Price\n{day},UP-E,\"1,000\",25\n".encode()
    r = _upload(client, dev, csv, name="cash.csv")
    assert r.status_code == 200 and r.json()["added"] == 1, r.text
    rec = client.get(f"{CASH}/sync/records", headers=dev).json()["items"][0]
    assert Decimal(rec["amount"]) == 1000 and Decimal(rec["price_per_item"]) == 25 and rec["store_id"] == str(a.id)


# ---- sync store start dates from the order sheet ------------------------------------------------------------------

SYNC = f"{API}/stores/sync-start-dates"


def _entry(db, store, day, n):
    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=day, bottle_count=n))
    db.commit()


def test_start_date_sync_is_developer_only(client, admin, emp):
    for who in (admin, emp):
        assert client.post(SYNC, headers=who, json={}).status_code == 403


def test_start_dates_are_filled_or_moved_back_to_the_first_supply_and_hand_dates_kept_unless_replacing(client, dev, db, make_store):
    empty, hand, right, nothing, late = (make_store(code=f"SDS-{i}") for i in range(5))
    first = date(2026, 3, 5)
    for s in (empty, hand, right, late):
        _entry(db, s, first + timedelta(days=9), 4)
        _entry(db, s, first, 7)
    _entry(db, empty, first - timedelta(days=2), 0)           # 0 bottles is not a supply
    _entry(db, nothing, first, 0)
    hand.start_date, right.start_date, late.start_date = date(2026, 1, 1), first, date(2026, 9, 1)
    db.commit()

    def refresh():
        db.expire_all()
        return [s.start_date for s in (empty, hand, right, nothing, late)]

    mine = {"platform": "blinkit"}
    preview = client.post(SYNC, headers=dev, json=mine).json()
    assert preview["dry_run"] and preview["to_fill"] >= 1 and preview["move_earlier"] >= 1 and preview["keep_hand_dates"] >= 1
    assert preview["no_orders_by_status"]["LIVE"] >= 1                       # `nothing` (only 0-bottle days) is a live store without supply
    assert refresh() == [None, date(2026, 1, 1), first, None, date(2026, 9, 1)]   # a preview changes nothing

    done = client.post(SYNC, headers=dev, json={**mine, "dry_run": False}).json()
    assert done["to_change"] == done["to_fill"] + done["move_earlier"]
    # empty filled; September moved back to March; a hand date EARLIER than our first order is kept
    assert refresh() == [first, date(2026, 1, 1), first, None, first]

    done = client.post(SYNC, headers=dev, json={**mine, "overwrite": True, "dry_run": False}).json()
    assert done["to_change"] == done["keep_hand_dates"] >= 1
    assert refresh() == [first, first, first, None, first]           # now replaced; a store with no supply stays empty

    again = client.post(SYNC, headers=dev, json={**mine, "overwrite": True, "dry_run": False}).json()
    assert again["to_change"] == 0


def test_importing_older_orders_moves_a_september_start_back_to_march_and_the_first_vendor_follows(client, dev, db, make_store):
    from app.models.store_vendor_period import StoreVendorPeriod
    from app.services import vendor_history_service

    s = make_store(code="SDS-MV", vendor="V1")
    hand = make_store(code="SDS-HAND", vendor="V2")
    sept, march = date(2026, 9, 3), date(2026, 3, 9)
    s.start_date, hand.start_date = sept, date(2026, 2, 1)
    db.commit()
    vendor_history_service.record_vendors(db, [s, hand], source="backfill", today=sept)
    db.commit()
    for st in (s, hand):
        _entry(db, st, sept, 5)
    # the March sheet arrives later
    csv = "\n".join([f"Outlet ID,Outlet Name,{march},{sept}", "SDS-MV,x,6,5", "SDS-HAND,x,6,5"]).encode()
    r = client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert s.start_date == march                                       # was September
    assert hand.start_date == date(2026, 2, 1)                         # typed by hand, earlier than our data: kept
    assert db.query(StoreVendorPeriod).filter_by(store_id=s.id).one().start_date == march    # the first vendor began with the store
    assert db.query(StoreVendorPeriod).filter_by(store_id=hand.id).one().start_date == date(2026, 2, 1)
    # a later import never pushes it forward again
    csv = "\n".join([f"Outlet ID,Outlet Name,{sept}", "SDS-MV,x,5"]).encode()
    client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")})
    db.expire_all()
    assert s.start_date == march


def test_a_vendor_change_records_who_made_it(client, admin, db, make_store):
    s = make_store(code="SDS-WHO", vendor="FIRST")
    from app.services import vendor_history_service

    vendor_history_service.record_vendors(db, [s], source="backfill", today=date(2026, 1, 1))
    db.commit()
    assert client.patch(f"{API}/stores/{s.id}", headers=admin, json={"vendor_name": "SECOND"}).status_code == 200
    hist = client.get(f"{API}/stores/{s.id}/vendors", headers=admin).json()
    assert [h["vendor_name"] for h in hist] == ["SECOND", "FIRST"]
    assert hist[0]["changed_by"] and hist[0]["source"] == "manual" and hist[0]["recorded_on"]
    assert hist[1]["changed_by"] is None and hist[1]["source"] == "backfill"


def test_start_date_sync_rejects_an_unknown_platform(client, dev):
    assert client.post(SYNC, headers=dev, json={"platform": "nope"}).status_code == 404


# ---- a new store must have a start date --------------------------------------------------------------------------

def test_a_new_store_needs_a_start_date_and_it_cannot_be_removed_later(client, admin, db):
    from app.models.organization import Organization

    pid = str(db.query(Organization).filter_by(slug="blinkit").one().id)
    body = {"name": "Needs Date", "external_code": "SD-REQ-1", "partner_organization_id": pid, "status": "LIVE"}
    r = client.post(f"{API}/stores", json=body, headers=admin)
    assert r.status_code == 422 and "start_date" in r.text
    assert client.post(f"{API}/stores", json={**body, "start_date": None}, headers=admin).status_code == 422
    ok = client.post(f"{API}/stores", json={**body, "start_date": "2026-03-01"}, headers=admin)
    assert ok.status_code == 201, ok.text
    sid = ok.json()["id"]
    assert ok.json()["start_date"] == "2026-03-01"
    assert client.patch(f"{API}/stores/{sid}", json={"start_date": "2026-03-05"}, headers=admin).status_code == 200
    assert client.patch(f"{API}/stores/{sid}", json={"start_date": None}, headers=admin).status_code == 422
    assert client.patch(f"{API}/stores/{sid}", json={"city": "Noida"}, headers=admin).status_code == 200   # other edits unaffected
    db.query(Store).filter_by(id=sid).delete()
    db.commit()


def test_file_import_adds_new_stores_without_a_start_date_but_flags_them(client, dev, db, make_store):
    existing = make_store(code="SD-IMP-1", name="Old Name")
    csv = "\n".join([
        "Outlet ID,Outlet Name,STATUS,Start date",
        "SD-IMP-1,New Name,Live,",                      # existing store, blank date: fine
        "SD-IMP-2,Brand New With Date,Live,2026-03-01",
        "SD-IMP-3,Brand New No Date,Live,",
        "SD-IMP-4,Brand New Bad Date,Live,not a date",
    ]).encode()
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("s.csv", csv, "text/csv")}, headers=dev)
    assert r.status_code == 200, r.text
    body = r.json()
    # nothing is dropped: employees must still see every live store
    assert (body["created"], body["updated"], body["without_start_date"]) == (3, 1, 2)
    assert "no start date" in body["warnings"][0] and "still added" in body["warnings"][0]
    db.expire_all()
    assert existing.name == "New Name"
    rows = {s.external_code: s for s in db.query(Store).filter(Store.external_code.like("SD-IMP-%"))}
    assert rows["SD-IMP-2"].start_date == date(2026, 3, 1) and rows["SD-IMP-3"].start_date is None and rows["SD-IMP-3"].status == "LIVE"
    db.query(Store).filter(Store.external_code.in_(["SD-IMP-2", "SD-IMP-3", "SD-IMP-4"])).delete(synchronize_session=False)
    db.commit()


def test_an_import_never_turns_live_stores_into_pending_by_accident(client, dev, db, make_store):
    """A sheet with no STATUS column, a blank status or unrecognised text must leave an existing store's status alone
    (a PENDING store is invisible to employees); a recognised status still applies; a new store defaults to PENDING."""
    a, b, c = (make_store(code=f"ST-KEEP-{i}") for i in range(3))
    no_col = "Outlet ID,Outlet Name\nST-KEEP-0,A\nST-NEW-1,Brand New\n".encode()
    assert client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("a.csv", no_col, "text/csv")}, headers=dev).status_code == 200
    odd = "Outlet ID,Outlet Name,STATUS\nST-KEEP-0,A,\nST-KEEP-1,B,Supplying nicely\nST-KEEP-2,C,Close\n".encode()
    r = client.post(f"{API}/stores/import", data={"platform": "blinkit"}, files={"file": ("b.csv", odd, "text/csv")}, headers=dev)
    assert r.status_code == 200, r.text
    assert any("doesn't recognise" in w for w in r.json()["warnings"])
    db.expire_all()
    assert (a.status, b.status, c.status) == ("LIVE", "LIVE", "CLOSE")
    assert db.query(Store).filter_by(external_code="ST-NEW-1").one().status == "PENDING"
    db.query(Store).filter_by(external_code="ST-NEW-1").delete()
    db.commit()


# ---- matching the sheet's store to a store in the CRM ---------------------------------------------------------------

def _records(db):
    return {r.current_source["store_code"] or r.current_source.get("store_name"): r for r in db.query(CashSyncRecord).all()}


def test_a_sheet_store_id_is_found_however_it_is_written_and_the_name_is_filled_in(client, dev, db, make_store):
    tag = "7" + __import__("uuid").uuid4().hex[:5].upper()
    a = make_store(code=f"KS-{tag}", name=f"Store Alpha {tag}")
    b = make_store(code="8" + tag.lower(), name=f"Store Beta {tag}")
    c = make_store(code="00" + tag.replace("A", "1").replace("B", "2").replace("C", "3").replace("D", "4").replace("E", "5").replace("F", "6"), name=f"Store Gamma {tag}")
    d = make_store(code=f"ZZ{tag}9", name=f"KS Bengaluru JP Nagar {tag} KS105")
    day = TODAY - timedelta(days=2)
    rows = [
        [day, "Store", None, f" ks {tag.lower()} ", None, "Water bottles", None, None, "No", 100, "x", None],        # case, spaces and a dash-less code
        [day, "Store", None, "8" + tag, None, "Water bottles", None, None, "No", 110, "x", None],                    # upper case
        [day, "Store", None, c.external_code.lstrip("0") + ".0", None, "Water bottles", None, None, "No", 120, "x", None],   # "8696.0", no leading zeros
        [day, "Store", f"KS Bengaluru JP Nagar {tag} KS105 (ZZ{tag}9)", None, None, "Water bottles", None, None, "No", 130, "x", None],   # a label with the code inside
    ]
    r = _upload(client, dev, _sheet(rows))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["added"] == 4 and body["unmatched_store"] == 0, body
    by_store = {x.store_id: x for x in db.query(CashSyncRecord).all()}
    assert set(by_store) == {a.id, b.id, c.id, d.id}                      # every row found its store; the CRM's name is shown, not the sheet's
    assert by_store[a.id].current_source["store_name"] == a.name and by_store[d.id].current_source["store_code"] == d.external_code


def test_the_store_columns_are_found_by_what_they_contain_when_the_headings_are_unusual(client, dev, db, make_store):
    tag = "9" + __import__("uuid").uuid4().hex[:5].upper()
    a, b = make_store(code=f"HD-{tag}-1", name=f"Head A {tag}"), make_store(code=f"HD-{tag}-2", name=f"Head B {tag}")
    day = TODAY - timedelta(days=1)
    header = ["Date", "Type", "Shop", "Payment", "Reason", "Amount (INR)"]
    rows = [[day, "Store", f"HD-{tag}-1", "Cash", None, 55], [day, "Store", f"head b {tag}", "Cash", None, 66]]
    r = _upload(client, dev, _sheet(rows, header=header))
    assert r.status_code == 200 and r.json()["added"] == 2 and r.json()["unmatched_store"] == 0, r.text
    assert {x.store_id for x in db.query(CashSyncRecord).all()} == {a.id, b.id}


def test_uploading_the_same_sheet_again_fills_in_rows_that_were_left_without_a_store(client, dev, db, make_store):
    code = "LATE-" + __import__("uuid").uuid4().hex[:5].upper()
    day = TODAY - timedelta(days=2)
    sheet = _sheet([[day, "Store", None, code, None, "Water bottles", None, None, "No", 75, "x", None]])
    first = _upload(client, dev, sheet).json()
    assert first["added"] == 1 and first["unmatched_store"] == 1
    assert db.query(CashSyncRecord).one().store_id is None
    store = make_store(code=code, name="Added Later " + code)             # the store reaches the CRM afterwards
    second = _upload(client, dev, sheet).json()
    assert second["added"] == 0 and second["already_uploaded"] == 1 and second["rematched"] == 1
    db.expire_all()
    rec = db.query(CashSyncRecord).one()
    assert rec.store_id == store.id and rec.current_source["store_name"] == store.name and rec.baseline["store_code"] == code
    assert any("matched this time" in w for w in second["warnings"])


def test_two_stores_with_the_same_id_are_never_guessed_between(client, dev, db, make_store):
    code = "DUP-" + __import__("uuid").uuid4().hex[:5].upper()
    make_store(code=code, name="Twin One " + code, platform="blinkit")
    make_store(code=code, name="Twin Two " + code, platform="zepto", region=None)
    day = TODAY - timedelta(days=1)
    r = _upload(client, dev, _sheet([[day, "Store", None, code, None, "Water bottles", None, None, "No", 40, "x", None]]))
    assert r.status_code == 200 and r.json()["added"] == 1 and r.json()["unmatched_store"] == 1
    # the name settles it when the sheet has it
    r = _upload(client, dev, _sheet([[day, "Store", "Twin Two " + code, code, None, "Water bottles", None, None, "No", 41, "x", None]]))
    assert r.json()["added"] == 1 and r.json()["unmatched_store"] == 0


# ---- deleting the selected rows from the review list (any tab, for good) -----------------------------------------------

def _ids(db):
    return {r.current_source["store_code"] or r.current_source.get("store_name"): str(r.id) for r in db.query(CashSyncRecord).all()}


def _records_api(client, dev, status=None):
    params = {"page_size": 200, **({"status": status} if status else {})}
    return client.get(f"{CASH}/sync/records", headers=dev, params=params).json()


def test_selected_uploaded_rows_can_be_deleted_and_uploading_again_brings_them_back(client, dev, db, make_store):
    a, b = make_store(code="DEL-A"), make_store(code="DEL-B")
    day = TODAY - timedelta(days=2)
    sheet = _sheet([_row(day, a, 100), _row(day, b, 200)])
    assert _upload(client, dev, sheet).json()["added"] == 2
    ids = _ids(db)
    r = client.post(f"{CASH}/sync/delete", headers=dev, json={"record_ids": [ids["DEL-A"]]})
    assert r.status_code == 200 and r.json() == {"deleted": 1, "refused": 0}
    assert db.query(CashSyncRecord).count() == 1
    again = _upload(client, dev, sheet).json()                            # only the deleted row is new
    assert again["added"] == 1 and again["already_uploaded"] == 1
    assert "cash_sync.rows_deleted" in str(client.get(f"{API}/activity", headers=dev, params={"page_size": 50}).json())


def test_rows_can_be_deleted_from_the_skipped_and_changed_tabs_too(client, dev, db, make_store):
    a, b = make_store(code="DEL-SK"), make_store(code="DEL-CH")
    day = TODAY - timedelta(days=2)
    assert _upload(client, dev, _sheet([_row(day, a, 100), _row(day, b, 200)])).json()["added"] == 2
    ids = _ids(db)
    assert client.post(f"{CASH}/sync/records/{ids['DEL-SK']}/resolve", headers=dev, json={"action": "skip"}).status_code == 200
    assert _records_api(client, dev, "SKIPPED")["counts"]["SKIPPED"] == 1
    r = client.post(f"{CASH}/sync/delete", headers=dev, json={"record_ids": [ids["DEL-SK"], ids["DEL-CH"]]})
    assert r.json() == {"deleted": 2, "refused": 0}
    assert db.query(CashSyncRecord).count() == 0


def test_a_deleted_app_purchase_stays_deleted_and_is_hidden_everywhere(client, dev, db, make_store):
    s = make_store(code="DEL-APP")
    _purchase(db, s, 150, TODAY - timedelta(days=1))
    client.post(f"{CASH}/sync", headers=dev)
    rec = db.query(CashSyncRecord).one()
    client.post(f"{CASH}/sync/records/{rec.id}/resolve", headers=dev, json={"action": "skip"})
    r = client.post(f"{CASH}/sync/delete", headers=dev, json={"record_ids": [str(rec.id)]})
    assert r.json() == {"deleted": 1, "refused": 0}
    db.expire_all()
    assert db.query(CashSyncRecord).one().status == "DELETED"            # only a hidden marker is left, so a Sync cannot add it again
    for tab in (None, "PENDING", "SKIPPED", "CHANGED", "APPLIED"):
        assert _records_api(client, dev, tab)["items"] == []
    assert sum(_records_api(client, dev)["counts"].values()) == 0
    client.post(f"{CASH}/sync", headers=dev)                              # syncing again does not bring it back...
    assert _records_api(client, dev)["items"] == [] and db.query(CashSyncRecord).count() == 1
    assert client.patch(f"{CASH}/sync/records/{rec.id}", headers=dev, json={"price_per_item": "30"}).status_code == 404   # ...and it can no longer be edited
    assert client.post(f"{CASH}/sync/delete", headers=dev, json={"record_ids": [str(rec.id)]}).json() == {"deleted": 0, "refused": 1}


def test_an_applied_row_and_unknown_ids_are_left_alone(client, dev, db, make_store):
    import uuid as _uuid
    s = make_store(code="DEL-APPLIED")
    day = TODAY - timedelta(days=2)
    assert _upload(client, dev, _sheet([_row(day, s, 120)])).json()["added"] == 1
    rid = str(db.query(CashSyncRecord).one().id)
    assert client.patch(f"{CASH}/sync/records/{rid}", headers=dev, json={"price_per_item": "30"}).status_code == 200
    assert client.post(f"{CASH}/sync/apply", headers=dev, json={"record_ids": [rid]}).status_code == 200
    r = client.post(f"{CASH}/sync/delete", headers=dev, json={"record_ids": [rid, str(_uuid.uuid4())]})
    assert r.json() == {"deleted": 0, "refused": 2}
    assert db.query(CashSyncRecord).count() == 1


def test_only_the_developer_can_delete_rows(client, admin, emp):
    import uuid as _uuid
    for who in (admin, emp):
        assert client.post(f"{CASH}/sync/delete", headers=who, json={"record_ids": [str(_uuid.uuid4())]}).status_code == 403
