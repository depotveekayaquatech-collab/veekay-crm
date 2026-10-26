"""Zepto monthly capping (who may use it, the alert rules, editing, loading from a sheet) and city-wise vendor rates."""
import csv
import io
import uuid
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

def test_the_monthly_limit_is_the_daily_cap_times_30():
    assert capping_service.monthly_limit(10) == 300 and capping_service.monthly_limit(0) == 0 and capping_service.monthly_limit(None) is None


@pytest.mark.parametrize("used,daily,level", [        # a daily cap of 10 = a monthly limit of 300; NEAR from 240 (80%)
    (10, 10, "OK"), (239, 10, "OK"), (240, 10, "NEAR"), (299, 10, "NEAR"), (300, 10, "NEAR"), (301, 10, "OVER"),
    (0, 0, "OK"), (1, 0, "OVER"), (5, None, "NO_CAP"), (0, None, "NO_CAP"),
])
def test_alert_levels(used, daily, level):
    assert capping_service.alert_for(used, daily) == level


@pytest.mark.parametrize("used,daily,day,level", [
    (160, 10, 15, "AHEAD"),     # 150 allowed by day 15, 160 marked: slow down
    (150, 10, 15, "OK"),        # exactly on pace, under the 80% line
    (100, 10, 15, "OK"),
    (250, 10, 25, "NEAR"),      # on pace (250 allowed), but past 80% of the monthly limit
    (301, 10, 15, "OVER"),      # over beats ahead
    (11, 10, 1, "AHEAD"),       # 10 allowed on day 1
    (300, 10, 31, "NEAR"),      # day 31 still allows only 30 days' worth: the monthly limit
    (301, 10, 31, "OVER"),
    (5, None, 15, "NO_CAP"),
    (0, 0, 15, "OK"), (1, 0, 15, "OVER"),
])
def test_alert_levels_follow_the_pace_of_the_month(used, daily, day, level):
    assert capping_service.alert_for(used, daily, day) == level


def test_pace_only_applies_to_the_month_in_progress():
    month = date(2026, 10, 1)
    assert capping_service.pace_for(10, month, date(2026, 10, 15)) == (15, 150)
    assert capping_service.pace_for(10, month, date(2026, 10, 31)) == (31, 300)                      # never more than 30 days' worth
    assert capping_service.pace_for(10, date(2026, 9, 1), date(2026, 10, 15)) == (None, None)       # a finished month: the full monthly limit
    assert capping_service.pace_for(None, month, date(2026, 10, 15)) == (None, None)                # no cap, no pace


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

def test_report_sums_the_selected_month_only_and_orders_over_first(client, zepto_emp, make_store, db, monkeypatch):
    nxt = date.today().replace(day=28) + timedelta(days=4)
    monkeypatch.setattr(capping_service, "_today", lambda: nxt - timedelta(days=nxt.day))   # last day of the month: the whole cap is allowed
    over = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    near = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    nocap = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    first = date.today().replace(day=1)
    prev = first - timedelta(days=3)
    _entry(db, over, first, 200)
    _entry(db, over, first + timedelta(days=1), 110)     # 310 > the monthly limit 300 (daily cap 10 x 30)
    _entry(db, over, prev, 500)                           # last month: must not count
    _entry(db, near, first, 250)
    _entry(db, nocap, first, 9)
    db.add_all([StoreCap(store_id=over.id, daily_cap=10), StoreCap(store_id=near.id, daily_cap=10)])
    db.commit()
    rep = client.get(f"{API}/capping", headers=zepto_emp).json()
    assert rep["warn_percent"] == 80 and rep["success"]
    r_over, r_near, r_no = _row(rep, over), _row(rep, near), _row(rep, nocap)
    assert (r_over["used"], r_over["alert"], r_over["excess"], r_over["remaining"], r_over["daily_cap"], r_over["monthly_cap"]) == (310, "OVER", 10, 0, 10, 300)
    assert (r_near["used"], r_near["alert"], r_near["remaining"]) == (250, "NEAR", 50)
    assert r_no["alert"] == "NO_CAP" and r_no["daily_cap"] is None and r_no["monthly_cap"] is None and r_no["percent"] is None
    levels = [x["alert"] for x in rep["rows"]]
    assert levels == sorted(levels, key=lambda a: ["OVER", "AHEAD", "NEAR", "OK", "NO_CAP"].index(a))   # over first, then near, ok, no cap
    assert rep["summary"]["over"] >= 1 and rep["summary"]["total"] == len(rep["rows"])
    # last month's report counts last month's entries instead
    old = client.get(f"{API}/capping", params={"month": f"{prev:%Y-%m}"}, headers=zepto_emp).json()
    assert _row(old, over)["used"] == 500


def test_report_flags_a_store_ahead_of_its_pace_this_month_but_not_in_a_finished_month(client, zepto_emp, make_store, db, monkeypatch):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    first = date.today().replace(day=1)
    monkeypatch.setattr(capping_service, "_today", lambda: first.replace(day=15))
    _entry(db, s, first, 160)
    db.add(StoreCap(store_id=s.id, daily_cap=10))          # sheet says 10 a day: 150 are on pace by the 15th
    db.commit()
    row = _row(client.get(f"{API}/capping", headers=zepto_emp).json(), s)
    assert row["alert"] == "AHEAD" and row["allowed_to_date"] == 150 and row["ahead_by"] == 10 and row["monthly_cap"] == 300
    # the same bottles in a finished month are measured against the full cap
    prev = first - timedelta(days=1)
    _entry(db, s, prev.replace(day=2), 160)
    old = _row(client.get(f"{API}/capping", params={"month": f"{prev:%Y-%m}"}, headers=zepto_emp).json(), s)
    assert old["alert"] == "OK" and old["allowed_to_date"] is None and old["ahead_by"] is None


def test_future_and_malformed_months_are_rejected(client, zepto_emp):
    nxt = (date.today().replace(day=1) + timedelta(days=40)).strftime("%Y-%m")
    assert client.get(f"{API}/capping", params={"month": nxt}, headers=zepto_emp).status_code == 422
    assert client.get(f"{API}/capping", params={"month": "soon"}, headers=zepto_emp).status_code == 422


# ---------------------------------------------------------------- editing

def test_an_employee_sets_changes_and_clears_a_cap_one_store_at_a_time(client, zepto_emp, make_store, db):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    url = f"{API}/capping/stores/{s.id}"
    assert client.put(url, headers=zepto_emp, json={"daily_cap": 0}).json()["changed"] is True          # 0 is a real cap
    assert db.query(StoreCap).filter_by(store_id=s.id).one().daily_cap == 0
    assert client.put(url, headers=zepto_emp, json={"daily_cap": 0}).json()["changed"] is False
    assert client.put(url, headers=zepto_emp, json={"daily_cap": 250}).status_code == 200
    assert client.put(url, headers=zepto_emp, json={"daily_cap": -1}).status_code == 422
    assert client.put(url, headers=zepto_emp, json={"daily_cap": None}).status_code == 200
    assert db.query(StoreCap).filter_by(store_id=s.id).count() == 0


def test_an_old_page_sending_monthly_cap_is_refused_instead_of_clearing_the_cap(client, zepto_emp, make_store, db):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    db.add(StoreCap(store_id=s.id, daily_cap=10))
    db.commit()
    r = client.put(f"{API}/capping/stores/{s.id}", headers=zepto_emp, json={"monthly_cap": 250})
    assert r.status_code == 422
    assert db.query(StoreCap).filter_by(store_id=s.id).one().daily_cap == 10


def test_blinkit_employees_cannot_edit_and_blinkit_stores_cannot_get_a_cap(client, emp, admin, make_store):
    z = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    b = make_store(platform="blinkit")
    assert client.put(f"{API}/capping/stores/{z.id}", headers=emp, json={"daily_cap": 5}).status_code == 403
    assert client.put(f"{API}/capping/stores/{b.id}", headers=admin, json={"daily_cap": 5}).status_code == 404


def test_a_cap_change_is_in_the_activity_log(client, zepto_emp, admin, make_store):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    client.put(f"{API}/capping/stores/{s.id}", headers=zepto_emp, json={"daily_cap": 40})
    client.put(f"{API}/capping/stores/{s.id}", headers=zepto_emp, json={"daily_cap": 60})
    log = client.get(f"{API}/activity", headers=admin, params={"page_size": 50}).json()
    items = log["items"] if isinstance(log, dict) else log
    assert any("cap_changed" in str(i) for i in items)


# ---------------------------------------------------------------- loading caps from the sheet / a file

def test_importing_caps_keeps_existing_ones_unless_overwrite(client, dev, make_store, db):
    a = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", code="CAP-A")
    b = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", code="CAP-B")
    db.add(StoreCap(store_id=a.id, daily_cap=10))
    db.commit()
    sheet = _csv(["Outlet ID", "Outlet Name", "Monthly Capping"], [["CAP-A", "x", "99"], ["CAP-B", "x", "0"], ["NOPE", "x", "5"], ["CAP-C", "x", "abc"], ["CAP-D", "x", ""]])

    def load(overwrite):
        return client.post(f"{API}/capping/import", headers=dev, data={"overwrite": str(overwrite).lower()}, files={"file": ("c.csv", sheet, "text/csv")})

    r = load(False).json()
    assert (r["added"], r["updated"], r["kept"], r["unknown_stores"], r["invalid"]) == (1, 0, 1, 1, 1)
    assert db.query(StoreCap).filter_by(store_id=a.id).one().daily_cap == 10     # not overwritten
    assert db.query(StoreCap).filter_by(store_id=b.id).one().daily_cap == 0      # 0 is stored, not treated as blank
    r = load(True).json()
    assert r["updated"] == 1
    db.expire_all()
    assert db.query(StoreCap).filter_by(store_id=a.id).one().daily_cap == 99


def test_a_sheet_with_outlet_names_and_no_ids_loads_by_name(client, admin, make_store, db):
    tag = uuid.uuid4().hex[:6].upper()
    a = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", name=f"Zepto - Alpha {tag}")
    b = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", name=f"Zepto Beta {tag}")
    d1 = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", name=f"Zepto Twin {tag}")
    d2 = make_store(platform="zepto", region=None, state="Delhi", city="Delhi", name=f"zepto twin {tag}")
    sheet = _csv(["Outlet Name", "Capping"], [
        [f"  ZEPTO  alpha {tag} ", "10"],          # case, punctuation and spacing do not matter
        [f"Zepto Beta {tag}", "0"],               # 0 is a real cap
        [f"Zepto Twin {tag}", "7"],               # two stores have this name: skipped and reported, never guessed
        [f"No Such Store {tag}", "5"],
        [f"Zepto Gamma {tag}", "abc"],
    ])
    r = client.post(f"{API}/capping/import", headers=admin, data={"overwrite": "true"}, files={"file": ("c.csv", sheet, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["added"], body["unknown_stores"], body["ambiguous"], body["invalid"]) == (2, 1, 1, 1)
    assert db.query(StoreCap).filter_by(store_id=a.id).one().daily_cap == 10
    assert db.query(StoreCap).filter_by(store_id=b.id).one().daily_cap == 0
    assert db.query(StoreCap).filter(StoreCap.store_id.in_([d1.id, d2.id])).count() == 0
    assert any("more than one store" in w and f"Zepto Twin {tag}" in w for w in body["warnings"])
    # an ID still wins when the sheet has both
    both = _csv(["Outlet ID", "Outlet Name", "Capping"], [[d1.external_code, f"Zepto Twin {tag}", "4"]])
    r = client.post(f"{API}/capping/import", headers=admin, data={"overwrite": "true"}, files={"file": ("c.csv", both, "text/csv")})
    assert r.json()["added"] == 1 and db.query(StoreCap).filter_by(store_id=d1.id).one().daily_cap == 4
    # no store column at all is an error
    r = client.post(f"{API}/capping/import", headers=admin, data={"overwrite": "true"}, files={"file": ("c.csv", _csv(["Capping"], [["5"]]), "text/csv")})
    assert r.status_code == 422


def _upload(client, admin, name, data, ctype="text/csv"):
    return client.post(f"{API}/capping/import", headers=admin, data={"overwrite": "true"}, files={"file": (name, data, ctype)})


def _three_stores(make_store):
    tag = uuid.uuid4().hex[:6].upper()
    return tag, [make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", name=f"Zepto Shop{i} {tag}", code=f"CAPX-{tag}-{i}") for i in (1, 2, 3)]


def test_the_upload_finds_its_columns_whatever_the_sheet_looks_like(client, admin, make_store, db):
    tag, (s1, s2, s3) = _three_stores(make_store)
    cap = lambda s: db.query(StoreCap).filter_by(store_id=s.id).one().daily_cap  # noqa: E731
    # a title and a blank line above the header; headings that are not the usual words; numbers with commas and decimals
    sheet = _csv(["Zepto capping - October", ""], [
        ["", ""],
        ["Store Location", "Cap/Day"],
        [f"Zepto Shop1 {tag}", "12"], [f"Zepto Shop2 {tag}", "1,5"], [f"Zepto Shop3 {tag}", "7.0"],
    ])
    r = _upload(client, admin, "c.csv", sheet)
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 3 and r.json()["invalid"] == 0
    assert (cap(s1), cap(s2), cap(s3)) == (12, 15, 7)                   # commas are thousand separators; "7.0" is 7


def test_a_sheet_with_no_headings_at_all_still_loads(client, admin, make_store, db):
    tag, (s1, s2, s3) = _three_stores(make_store)
    sheet = _csv([f"Zepto Shop1 {tag}", "3"], [[f"Zepto Shop2 {tag}", "4"], [f"zepto shop3 {tag}", "5"]])
    r = _upload(client, admin, "c.csv", sheet)
    assert r.status_code == 200 and r.json()["added"] == 3, r.text
    assert sorted(c.daily_cap for c in db.query(StoreCap).filter(StoreCap.store_id.in_([s1.id, s2.id, s3.id]))) == [3, 4, 5]


def test_outlet_ids_match_whatever_their_case_or_spacing(client, admin, make_store, db):
    tag, (s1, s2, s3) = _three_stores(make_store)
    sheet = _csv(["Sr", "ID", "Capping"], [["1", f" capx-{tag.lower()}-1 ", "6"], ["2", f"CAPX - {tag} - 2".replace(" - ", "-"), "8"]])
    r = _upload(client, admin, "c.csv", sheet)
    assert r.status_code == 200 and r.json()["added"] == 2, r.text


def test_an_excel_file_is_read_from_whichever_sheet_has_the_stores(client, admin, make_store, db):
    from openpyxl import Workbook

    tag, (s1, s2, s3) = _three_stores(make_store)
    wb = Workbook()
    wb.active.title = "Notes"
    wb.active.append(["Read me: the caps are on the next tab"])
    ws = wb.create_sheet("Capping")
    ws.append(["Outlet Name", "City", "Capping"])
    ws.append([f"Zepto Shop1 {tag}", "Bengaluru", 9])
    ws.append([f"Zepto Shop2 {tag}", "Bengaluru", 0])
    buf = io.BytesIO()
    wb.save(buf)
    r = _upload(client, admin, "caps.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.status_code == 200 and r.json()["added"] == 2, r.text
    assert db.query(StoreCap).filter_by(store_id=s1.id).one().daily_cap == 9 and db.query(StoreCap).filter_by(store_id=s2.id).one().daily_cap == 0


def test_a_file_with_nothing_usable_is_refused_with_a_reason(client, admin):
    r = _upload(client, admin, "c.csv", _csv(["Colour", "Size"], [["red", "big"]]))
    assert r.status_code == 422 and "No stores" in r.json()["detail"]


def test_only_developers_may_read_the_google_sheet(client, zepto_emp, admin):
    assert client.post(f"{API}/capping/sync", headers=zepto_emp).status_code == 403
    assert client.post(f"{API}/capping/sync", headers=admin).status_code == 403


def test_admins_and_developers_upload_the_sheet_but_employees_cannot(client, zepto_emp, emp, admin, dev, make_store, db):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", code="CAP-UP")
    sheet = _csv(["Outlet ID", "Monthly Capping"], [["CAP-UP", "120"]])

    def upload(headers):
        return client.post(f"{API}/capping/import", headers=headers, data={"overwrite": "true"}, files={"file": ("c.csv", sheet, "text/csv")})

    assert upload(zepto_emp).status_code == 403 and upload(emp).status_code == 403
    assert db.query(StoreCap).filter_by(store_id=s.id).count() == 0
    r = upload(admin)
    assert r.status_code == 200 and r.json()["added"] == 1
    assert db.query(StoreCap).filter_by(store_id=s.id).one().daily_cap == 120
    assert upload(dev).status_code == 200
    # an employee can still change one store by hand
    assert client.put(f"{API}/capping/stores/{s.id}", headers=zepto_emp, json={"daily_cap": 80}).status_code == 200


# ---------------------------------------------------------------- the alerts permission

def test_capping_alerts_need_the_permission_and_show_only_my_stores(client, make_user, make_store, admin, db, monkeypatch):
    from app.models.organization import Organization
    from app.models.state_assignment import StateAssignment
    from .conftest import auth, login

    mine = make_store(platform="zepto", region=None, state="Alertland", city="Aville")
    theirs = make_store(platform="zepto", region=None, state="Otherland", city="Bville")
    first = date.today().replace(day=1)
    monkeypatch.setattr(capping_service, "_today", lambda: first.replace(day=15))
    for st in (mine, theirs):
        _entry(db, st, first, 160)
        db.add(StoreCap(store_id=st.id, daily_cap=10))
    db.commit()

    def employee(grants):
        code, pw, uid = make_user("employee", platform="zepto", grants=grants)
        return auth(login(client, code, pw).json()["access_token"]), uid

    plain, _ = employee(("orders.view",))
    assert client.get(f"{API}/capping/alerts", headers=plain).status_code == 403      # a Zepto employee without capping.alerts

    h, uid = employee(("orders.view", "capping.alerts"))
    assert client.get(f"{API}/capping/alerts", headers=h).json()["rows"] == []        # no state assigned yet: nothing is theirs
    org = db.query(Organization).filter_by(slug="veekay").one()
    zepto = db.query(Organization).filter_by(slug="zepto").one()
    db.add(StateAssignment(organization_id=org.id, partner_organization_id=zepto.id, state="Alertland", assigned_user_id=uid))
    db.commit()
    try:
        body = client.get(f"{API}/capping/alerts", headers=h).json()
        assert [r["outlet_id"] for r in body["rows"]] == [mine.external_code]
        assert body["rows"][0]["alert"] == "AHEAD" and body["ahead"] == 1 and body["over"] == 0 and body["day"] == 15
        # an administrator sees every store that needs attention
        ids = {r["outlet_id"] for r in client.get(f"{API}/capping/alerts", headers=admin).json()["rows"]}
        assert {mine.external_code, theirs.external_code} <= ids
    finally:
        db.query(StateAssignment).filter_by(assigned_user_id=uid).delete()
        db.commit()


def test_blinkit_employees_get_no_capping_alerts_even_with_the_permission(client, make_user):
    from .conftest import auth, login
    code, pw, _ = make_user("employee", platform="blinkit", region="NORTH", grants=("orders.view", "capping.alerts"))
    h = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/capping/alerts", headers=h).status_code == 403


def test_the_alerts_permission_is_offered_in_the_employee_permission_list(client, admin):
    groups = client.get(f"{API}/permissions", headers=admin).json()
    codes = {p["code"]: g["label"] for g in groups for p in g["permissions"]}
    assert codes.get("capping.alerts") == "Capping"


def test_sheet_sync_needs_the_sheet_to_be_configured_and_reads_it_when_it_is(client, dev, make_store, db, monkeypatch):
    monkeypatch.setattr(settings, "CAPPING_SYNC_SHEETS", [])
    assert client.post(f"{API}/capping/sync", headers=dev).status_code == 422
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", code="CAP-S")
    monkeypatch.setattr(settings, "CAPPING_SYNC_SHEETS", ["zepto=SHEETID:5"])
    monkeypatch.setattr(store_sync_service, "fetch_csv_text", lambda sid, gid: "Outlet ID,Outlet Name,State,City,Monthly Capping,Status\nCAP-S,n,s,c,77,LIVE\n")
    r = client.post(f"{API}/capping/sync", headers=dev)
    assert r.status_code == 200 and r.json()["added"] == 1
    assert db.query(StoreCap).filter_by(store_id=s.id).one().daily_cap == 77


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


def test_a_blinkit_person_never_sees_zepto_capping_even_holding_correct_any_entry(client, make_user, make_store):
    from .conftest import auth, login
    code, pw, _ = make_user("employee", platform="blinkit", region="NORTH", grants=("orders.view", "orders.correct", "capping.alerts"))
    h = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/capping", headers=h).status_code == 403
    assert client.get(f"{API}/capping/alerts", headers=h).status_code == 403
    zepto_store = make_store(platform="zepto", region=None)
    assert client.put(f"{API}/capping/stores/{zepto_store.id}", headers=h, json={"daily_cap": 5}).status_code == 403
