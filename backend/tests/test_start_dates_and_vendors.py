"""Start dates from orders, vendor history, the month filter, and private sheet access."""
import csv
import io
from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.models.store_vendor_period import StoreVendorPeriod
from app.services import store_activity, store_sync_service, vendor_history_service

from .conftest import API

HEADER = ["Outlet ID", "Outlet Name", "STATUS", "State", "City", "Vendor", "Vendor Number"]


def _orders(rows: dict[str, dict[date, object]]) -> bytes:
    days = sorted({d for r in rows.values() for d in r})
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Outlet ID", "Outlet Name", *[d.isoformat() for d in days]])
    for code, r in rows.items():
        w.writerow([code, "x", *[r.get(d, "") for d in days]])
    return out.getvalue().encode()


def _upload_orders(client, dev, content: bytes, platform="blinkit"):
    return client.post(f"{API}/orders/import", headers=dev, data={"platform": platform},
                       files={"file": ("orders.csv", content, "text/csv")})


def _upload_stores(client, dev, rows: list[list[str]], platform="blinkit"):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HEADER)
    w.writerows(rows)
    return client.post(f"{API}/stores/import", headers=dev, data={"platform": platform},
                       files={"file": ("stores.csv", out.getvalue().encode(), "text/csv")})


def test_start_date_is_the_first_day_with_bottles_and_is_never_overwritten(client, dev, db, make_store):
    first = make_store(code="SD-1")
    manual = make_store(code="SD-2")
    manual.start_date = date(2026, 1, 1)
    db.commit()
    zero_only = make_store(code="SD-3")
    d = date.today() - timedelta(days=10)
    r = _upload_orders(client, dev, _orders({
        "SD-1": {d: 0, d + timedelta(days=1): 5, d + timedelta(days=3): 7},   # 0 bottles on day one: not supplied yet
        "SD-2": {d: 9},
        "SD-3": {d: 0},
    }))
    assert r.status_code == 200, r.text
    assert r.json()["start_dates_set"] >= 1   # (seeded demo stores with orders may be dated too)
    for s in (first, manual, zero_only):
        db.refresh(s)
    assert first.start_date == d + timedelta(days=1)
    assert manual.start_date == date(2026, 1, 1)         # set by hand: untouched
    assert zero_only.start_date is None                  # only zeros: not started
    # importing the same sheet again changes nothing
    assert _upload_orders(client, dev, _orders({"SD-1": {d: 0, d + timedelta(days=1): 5}})).json()["start_dates_set"] == 0


def test_a_new_month_of_orders_dates_only_the_new_stores(client, dev, db, make_store):
    old, new = make_store(code="SD-4"), make_store(code="SD-5")
    m1, m2 = date.today() - timedelta(days=40), date.today() - timedelta(days=5)
    _upload_orders(client, dev, _orders({"SD-4": {m1: 3}}))
    _upload_orders(client, dev, _orders({"SD-4": {m2: 3}, "SD-5": {m2: 4}}))
    db.refresh(old)
    db.refresh(new)
    assert old.start_date == m1 and new.start_date == m2


def test_a_vendor_change_keeps_the_old_vendor_and_dates_the_new_one_from_its_first_order(client, dev, db, make_store):
    s = make_store(code="SD-6", vendor="OLD VENDOR")
    vendor_history_service.record_vendors(db, [s], source="backfill", today=date(2026, 1, 1))
    db.commit()
    r = _upload_stores(client, dev, [["SD-6", s.name, "LIVE", "Delhi", "New Delhi", "NEW VENDOR", "9999999999"]])
    assert r.status_code == 200, r.text
    assert r.json()["vendor_changes"] == 1
    hist = client.get(f"{API}/stores/{s.id}/vendors", headers=dev).json()
    assert [h["vendor_name"] for h in hist] == ["NEW VENDOR", "OLD VENDOR"]
    assert hist[0]["current"] and not hist[0]["start_confirmed"] and hist[1]["end_date"] is not None
    # the new vendor's first order fixes its start; the old vendor ends the day before
    start = date.today()
    assert _upload_orders(client, dev, _orders({"SD-6": {start: 4}})).json()["vendor_starts_set"] == 1
    hist = client.get(f"{API}/stores/{s.id}/vendors", headers=dev).json()
    assert hist[0]["start_confirmed"] and hist[0]["start_date"] == start.isoformat()
    assert hist[1]["end_date"] == (start - timedelta(days=1)).isoformat()
    # the store itself shows the current vendor everywhere
    assert client.get(f"{API}/stores/{s.id}", headers=dev).json()["vendor_name"] == "NEW VENDOR"


def test_same_vendor_in_a_new_sync_changes_nothing(client, dev, db, make_store):
    s = make_store(code="SD-7", vendor="ACME")
    vendor_history_service.record_vendors(db, [s], source="backfill", today=date(2026, 1, 1))
    db.commit()
    r = _upload_stores(client, dev, [["SD-7", s.name, "LIVE", "Delhi", "New Delhi", "  acme ", ""]])
    assert r.json()["vendor_changes"] == 0
    assert db.query(StoreVendorPeriod).filter_by(store_id=s.id).count() == 1


def test_month_filter_shows_stores_started_by_the_end_of_that_month(db, make_store):
    early = make_store(code="M-1")
    early.start_date = date(2026, 3, 10)
    late = make_store(code="M-2")
    late.start_date = date(2026, 5, 2)
    unknown = make_store(code="M-3")
    db.commit()
    stores = [early, late, unknown]

    def names(m):
        return {s.external_code for s in store_activity.filter_active_in_month(stores, m)}

    assert names(date(2026, 2, 1)) == {"M-3"}
    assert names(date(2026, 3, 1)) == {"M-1", "M-3"}
    assert names(date(2026, 4, 1)) == {"M-1", "M-3"}
    assert names(date(2026, 5, 31)) == {"M-1", "M-2", "M-3"}
    assert names(None) == {"M-1", "M-2", "M-3"}


def test_a_manual_vendor_edit_is_history_too(client, admin, db, make_store):
    s = make_store(code="SD-8", vendor="FIRST")
    vendor_history_service.record_vendors(db, [s], source="backfill", today=date(2026, 1, 1))
    db.commit()
    assert client.patch(f"{API}/stores/{s.id}", headers=admin, json={"vendor_name": "SECOND"}).status_code == 200
    hist = client.get(f"{API}/stores/{s.id}/vendors", headers=admin).json()
    assert [h["vendor_name"] for h in hist] == ["SECOND", "FIRST"]
    assert hist[0]["start_confirmed"]


def test_private_sheet_access_is_used_only_when_configured(monkeypatch):
    from app.services import google_sheets

    monkeypatch.setattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", "")
    assert not google_sheets.configured() and google_sheets.service_account_email() is None
    monkeypatch.setattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", "not json")
    assert google_sheets.configured() and google_sheets.service_account_email() is None   # bad key: no crash, no leak
    with pytest.raises(google_sheets.SheetsAccessError, match="not a valid"):
        google_sheets._credentials()
    monkeypatch.setattr(google_sheets, "fetch_csv", lambda url: "Outlet ID,Outlet Name\nA,B\n")
    monkeypatch.setattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", '{"client_email":"sa@x.iam","private_key":"k"}')
    assert store_sync_service.fetch_csv_text("SID", "0").startswith("Outlet ID")


def test_scheduled_runs_can_skip_the_sheets_but_sync_now_cannot(monkeypatch):
    from app.core import scheduler
    from app.services import activity_service

    monkeypatch.setattr(settings, "SHEET_AUTO_SYNC", False)
    monkeypatch.setattr(settings, "STORE_SYNC_SHEETS", ["blinkit=ID:0"])
    called = []
    monkeypatch.setattr(store_sync_service, "sync_all", lambda db, actor: called.append("stores") or [])
    monkeypatch.setattr("app.services.reminder_service.send_bill_reminders", lambda db: {"reminders": 0})
    monkeypatch.setattr(activity_service, "record", lambda *a, **k: None)

    class _Db:
        def commit(self): ...
        def rollback(self): ...

    scheduler.execute_sync(_Db(), object(), "scheduled")
    assert called == []                      # the automatic run did not pull the sheet
    scheduler.execute_sync(_Db(), object(), "manual")
    assert called == ["stores"]              # a developer's "Sync now" does
