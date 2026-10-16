"""Zepto monthly capping (who may use it, the alert rules, editing, loading from a sheet) and city-wise vendor rates."""
import csv
import io
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook

from app.core.config import settings
from app.models.order_entry import OrderEntry
from app.models.store_cap import StoreCap
from app.services import capping_service, store_sync_service

from .conftest import API


def _csv(header, rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue().encode()


def _entry(db, store, day, n):
    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=day, bottle_count=n, source="ADMIN"))
    db.commit()


def _row(report, store):
    return next(r for r in report["rows"] if r["outlet_id"] == store.external_code)


# ---------------------------------------------------------------- the alert rules (pure)

@pytest.mark.parametrize("used,cap,level", [
    (10, 100, "OK"), (79, 100, "OK"), (80, 100, "NEAR"), (95, 100, "NEAR"), (100, 100, "NEAR"), (101, 100, "OVER"),
    (0, 0, "OK"), (1, 0, "OVER"), (5, None, "NO_CAP"), (0, None, "NO_CAP"),
])
def test_alert_levels(used, cap, level):
    assert capping_service.alert_for(used, cap) == level


# ---------------------------------------------------------------- who may use it

def test_every_active_zepto_employee_can_view_capping_whatever_their_state(client, make_user, make_store, db):
    code, pw, _ = make_user("employee", platform="zepto", region="SOUTH")
    for_other_state = make_store(platform="zepto", region=None, state="Uttar Pradesh", city="Noida")
    from .conftest import auth, login
    token = login(client, code, pw).json()["access_token"]
    r = client.get(f"{API}/capping", headers=auth(token))
    assert r.status_code == 200, r.text
    assert any(x["outlet_id"] == for_other_state.external_code for x in r.json()["rows"])   # a store in another state is listed


def test_blinkit_employees_and_the_unauthenticated_are_refused(client, emp):
    assert client.get(f"{API}/capping", headers=emp).status_code == 403
    assert client.get(f"{API}/capping").status_code in (401, 403)


def test_admin_can_view_and_a_deactivated_zepto_employee_cannot(client, admin, make_user):
    assert client.get(f"{API}/capping", headers=admin).status_code == 200
    code, pw, _ = make_user("employee", platform="zepto", region="SOUTH", active=False)
    from .conftest import login
    assert login(client, code, pw).status_code in (401, 403)


# ---------------------------------------------------------------- the report

def test_report_sums_the_selected_month_only_and_orders_over_first(client, zepto_emp, make_store, db):
    over = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    near = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    nocap = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    first = date.today().replace(day=1)
    prev = first - timedelta(days=3)
    _entry(db, over, first, 70)
    _entry(db, over, first + timedelta(days=1), 40)      # 110 > cap 100
    _entry(db, over, prev, 500)                           # last month: must not count
    _entry(db, near, first, 85)
    _entry(db, nocap, first, 9)
    db.add_all([StoreCap(store_id=over.id, monthly_cap=100), StoreCap(store_id=near.id, monthly_cap=100)])
    db.commit()
    rep = client.get(f"{API}/capping", headers=zepto_emp).json()
    assert rep["warn_percent"] == 80 and rep["success"]
    r_over, r_near, r_no = _row(rep, over), _row(rep, near), _row(rep, nocap)
    assert (r_over["used"], r_over["alert"], r_over["excess"], r_over["remaining"]) == (110, "OVER", 10, 0)
    assert (r_near["used"], r_near["alert"], r_near["remaining"]) == (85, "NEAR", 15)
    assert r_no["alert"] == "NO_CAP" and r_no["monthly_cap"] is None and r_no["percent"] is None
    levels = [x["alert"] for x in rep["rows"]]
    assert levels == sorted(levels, key=lambda a: ["OVER", "NEAR", "OK", "NO_CAP"].index(a))   # over first, then near, ok, no cap
    assert rep["summary"]["over"] >= 1 and rep["summary"]["total"] == len(rep["rows"])
    # last month's report counts last month's entries instead
    old = client.get(f"{API}/capping", params={"month": f"{prev:%Y-%m}"}, headers=zepto_emp).json()
    assert _row(old, over)["used"] == 500


def test_future_and_malformed_months_are_rejected(client, zepto_emp):
    nxt = (date.today().replace(day=1) + timedelta(days=40)).strftime("%Y-%m")
    assert client.get(f"{API}/capping", params={"month": nxt}, headers=zepto_emp).status_code == 422
    assert client.get(f"{API}/capping", params={"month": "soon"}, headers=zepto_emp).status_code == 422


# ---------------------------------------------------------------- editing

def test_an_employee_sets_changes_and_clears_a_cap_one_store_at_a_time(client, zepto_emp, make_store, db):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    url = f"{API}/capping/stores/{s.id}"
    assert client.put(url, headers=zepto_emp, json={"monthly_cap": 0}).json()["changed"] is True          # 0 is a real cap
    assert db.query(StoreCap).filter_by(store_id=s.id).one().monthly_cap == 0
    assert client.put(url, headers=zepto_emp, json={"monthly_cap": 0}).json()["changed"] is False
    assert client.put(url, headers=zepto_emp, json={"monthly_cap": 250}).status_code == 200
    assert client.put(url, headers=zepto_emp, json={"monthly_cap": -1}).status_code == 422
    assert client.put(url, headers=zepto_emp, json={"monthly_cap": None}).status_code == 200
    assert db.query(StoreCap).filter_by(store_id=s.id).count() == 0


def test_blinkit_employees_cannot_edit_and_blinkit_stores_cannot_get_a_cap(client, emp, admin, make_store):
    z = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    b = make_store(platform="blinkit")
    assert client.put(f"{API}/capping/stores/{z.id}", headers=emp, json={"monthly_cap": 5}).status_code == 403
    assert client.put(f"{API}/capping/stores/{b.id}", headers=admin, json={"monthly_cap": 5}).status_code == 404


def test_a_cap_change_is_in_the_activity_log(client, zepto_emp, admin, make_store):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    client.put(f"{API}/capping/stores/{s.id}", headers=zepto_emp, json={"monthly_cap": 40})
    client.put(f"{API}/capping/stores/{s.id}", headers=zepto_emp, json={"monthly_cap": 60})
    log = client.get(f"{API}/activity", headers=admin, params={"page_size": 50}).json()
    items = log["items"] if isinstance(log, dict) else log
    assert any("cap_changed" in str(i) for i in items)


# ---------------------------------------------------------------- loading caps from the sheet / a file

def test_importing_caps_keeps_existing_ones_unless_overwrite(client, dev, make_store, db):
    a = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", code="CAP-A")
    b = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", code="CAP-B")
    db.add(StoreCap(store_id=a.id, monthly_cap=10))
    db.commit()
    sheet = _csv(["Outlet ID", "Outlet Name", "Monthly Capping"], [["CAP-A", "x", "99"], ["CAP-B", "x", "0"], ["NOPE", "x", "5"], ["CAP-C", "x", "abc"], ["CAP-D", "x", ""]])

    def load(overwrite):
        return client.post(f"{API}/capping/import", headers=dev, data={"overwrite": str(overwrite).lower()}, files={"file": ("c.csv", sheet, "text/csv")})

    r = load(False).json()
    assert (r["added"], r["updated"], r["kept"], r["unknown_stores"], r["invalid"]) == (1, 0, 1, 1, 1)
    assert db.query(StoreCap).filter_by(store_id=a.id).one().monthly_cap == 10     # not overwritten
    assert db.query(StoreCap).filter_by(store_id=b.id).one().monthly_cap == 0      # 0 is stored, not treated as blank
    r = load(True).json()
    assert r["updated"] == 1
    db.expire_all()
    assert db.query(StoreCap).filter_by(store_id=a.id).one().monthly_cap == 99


def test_only_developers_may_load_caps(client, zepto_emp, admin):
    assert client.post(f"{API}/capping/sync", headers=zepto_emp).status_code == 403
    assert client.post(f"{API}/capping/sync", headers=admin).status_code == 403


def test_sheet_sync_needs_the_sheet_to_be_configured_and_reads_it_when_it_is(client, dev, make_store, db, monkeypatch):
    monkeypatch.setattr(settings, "CAPPING_SYNC_SHEETS", [])
    assert client.post(f"{API}/capping/sync", headers=dev).status_code == 422
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", code="CAP-S")
    monkeypatch.setattr(settings, "CAPPING_SYNC_SHEETS", ["zepto=SHEETID:5"])
    monkeypatch.setattr(store_sync_service, "fetch_csv_text", lambda sid, gid: "Outlet ID,Outlet Name,State,City,Monthly Capping,Status\nCAP-S,n,s,c,77,LIVE\n")
    r = client.post(f"{API}/capping/sync", headers=dev)
    assert r.status_code == 200 and r.json()["added"] == 1
    assert db.query(StoreCap).filter_by(store_id=s.id).one().monthly_cap == 77


# ---------------------------------------------------------------- vendor rates

def _rates(client, headers, rows, header=("City", "Rate"), confirm=False, platform="blinkit"):
    return client.post(f"{API}/vendor-rates/upload", headers=headers, data={"platform": platform, "confirm": str(confirm).lower()},
                       files={"file": ("rates.csv", _csv(list(header), rows), "text/csv")})


def test_vendor_rates_need_the_rates_permission(client, emp, zepto_emp):
    assert client.get(f"{API}/vendor-rates", headers=emp).status_code == 403
    assert _rates(client, zepto_emp, [["Delhi", "5"]]).status_code == 403


def test_new_rates_apply_but_a_changed_rate_asks_first(client, admin, make_store):
    make_store(platform="blinkit", city="RateTown", code="RT-1")
    make_store(platform="blinkit", city="RateTown", code="RT-2")
    r = _rates(client, admin, [["RateTown", "9.50"]]).json()
    assert r["applied"] and r["new"] == 1 and not r["needs_confirmation"]
    # same rate again: nothing to do
    assert _rates(client, admin, [["RateTown", "9.50"]]).json()["unchanged"] == 1
    # a different rate: nothing is written until confirmed, and the answer lists the stores affected
    r = _rates(client, admin, [["ratetown", "11"]]).json()
    assert r["needs_confirmation"] and not r["applied"] and r["changed"] == 1 and r["stores_affected"] == 2
    assert r["changes"][0]["old_rate"] == "9.50" and r["changes"][0]["new_rate"] == "11.00"
    listed = {x["city"]: x["rate"] for x in client.get(f"{API}/vendor-rates", headers=admin).json()}
    assert listed["RateTown"] == "9.50"                      # still the old rate
    r = _rates(client, admin, [["RateTown", "11"]], confirm=True).json()
    assert r["applied"]
    listed = {x["city"]: x["rate"] for x in client.get(f"{API}/vendor-rates", headers=admin).json()}
    assert listed["RateTown"] == "11.00"


def test_a_store_rate_overrides_its_city_and_bad_rows_are_reported(client, admin, make_store):
    s = make_store(platform="blinkit", city="OverTown", code="OT-1")
    r = _rates(client, admin, [["OverTown", "8", ""], ["", "12", "OT-1"], ["OverTown", "abc", ""], ["", "5", "MISSING"]], header=("City", "Rate", "Outlet ID")).json()
    assert r["applied"] and r["new"] == 2 and any("skipped" in w for w in r["warnings"])
    rates = client.get(f"{API}/vendor-rates", headers=admin).json()
    assert any(x["outlet_id"] == "OT-1" and x["rate"] == "12.00" for x in rates)


def test_blinkit_report_with_vendor_rate_is_admin_only_and_multiplies_bottles(client, admin, emp, make_store, db):
    s = make_store(platform="blinkit", city="ReportTown", code="RP-1")
    day = date.today() - timedelta(days=1)
    _entry(db, s, day, 10)
    _rates(client, admin, [["ReportTown", "3.5"]])
    params = {"start": day.isoformat(), "end": day.isoformat(), "partner": "blinkit", "include_rate": "true"}
    assert client.get(f"{API}/orders/matrix/export", headers=emp, params=params).status_code in (403,)
    r = client.get(f"{API}/orders/matrix/export", headers=admin, params=params)
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    head = [c.value for c in ws[1]]
    assert "Vendor Rate" in head and "Amount" in head
    row = next(row for row in ws.iter_rows(min_row=2, values_only=True) if row[head.index("Outlet ID")] == "RP-1")
    assert row[head.index("Vendor Rate")] == 3.5 and row[head.index("Amount")] == 35.0
    # the normal report is unchanged
    plain = load_workbook(io.BytesIO(client.get(f"{API}/orders/matrix/export", headers=admin, params={**params, "include_rate": "false"}).content)).active
    assert "Vendor Rate" not in [c.value for c in plain[1]]
