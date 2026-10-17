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
