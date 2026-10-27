"""Capping history: the effective-date rule, changing a capping (backdated, duplicate dates, who may), the capping sheet and its downloads, and the
average-vs-limit alert (average above the limit, one day above it, exactly the limit is fine)."""
import csv
import io
import uuid
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook
from sqlalchemy import event

from app.core.config import settings
from app.db.session import engine
from app.models.capping_history import CappingHistory
from app.models.store_cap import StoreCap
from app.services import capping_history_service as svc

from .conftest import API, plant_entry


@pytest.fixture()
def zstore(make_store):
    return make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")


@pytest.fixture(autouse=True)
def _forget_history(db):
    """Rows of the stores a test made go with the stores (cascade); the seeded Zepto stores keep none."""
    yield
    db.rollback()


def _today():
    return svc.today_ist()


def _change(client, headers, store, capping, day):
    return client.post(f"{API}/capping/change", json={"storeId": str(store.id), "capping": capping, "effectiveFrom": day.isoformat()}, headers=headers)


def _seed(db, store, *rows):
    for eff, cap in rows:
        db.add(CappingHistory(store_id=store.id, capping=cap, effective_from=eff))
    db.commit()


def _sheet_row(body, store):
    return next(r for r in body["rows"] if r["store_id"] == str(store.id))


# ---------------------------------------------------------------- the effective-date rule (pure)

def test_the_capping_on_a_day_is_the_one_with_the_greatest_effective_from_on_or_before_it():
    history = [(date(2026, 10, 1), 10), (date(2026, 10, 15), 11)]
    assert svc.effective_capping(history, date(2026, 9, 30)) is None             # before the first entry
    assert [svc.effective_capping(history, date(2026, 10, d)) for d in (1, 2, 14)] == [10, 10, 10]
    assert [svc.effective_capping(history, date(2026, 10, d)) for d in (15, 16, 31)] == [11, 11, 11]
    assert svc.effective_capping([], date(2026, 10, 1)) is None


def test_a_backdated_entry_slots_into_the_timeline_without_moving_the_later_ones():
    history = sorted([(date(2026, 10, 1), 10), (date(2026, 10, 15), 11), (date(2026, 10, 8), 12)])      # added last, dated in the middle
    assert [svc.effective_capping(history, date(2026, 10, d)) for d in (7, 8, 14, 15)] == [10, 12, 12, 11]


# ---------------------------------------------------------------- the alert rules (pure)

def test_average_above_the_limit_is_an_alert():
    # average 12.5 over two days: the average and both days are above 11
    a = svc.assess(total=25, days=2, breaches=[(date(2026, 10, 1), 12), (date(2026, 10, 2), 13)], limit=11)
    assert a["alert"] and a["average_breach"] and a["day_breach"] and a["reasons"] == ["average", "day"] and a["status"] == "over"
    # the average rule on its own, without being given the days: 11.1 is above 11, 11.0 is not
    assert svc.assess(total=111, days=10, breaches=[], limit=11)["average_breach"] is True
    assert svc.assess(total=110, days=10, breaches=[], limit=11)["average_breach"] is False


def test_one_day_above_the_limit_is_an_alert_even_when_the_average_is_fine():
    a = svc.assess(total=27, days=4, breaches=[(date(2026, 10, 2), 12)], limit=11)       # 5, 12, 6, 4: average 6.75
    assert a["alert"] and a["day_breach"] and not a["average_breach"] and a["reasons"] == ["day"] and a["status"] == "over"


def test_exactly_the_limit_is_not_a_breach():
    a = svc.assess(total=11 * 5, days=5, breaches=[], limit=11)                  # every day 11: average exactly 11 and no day above
    assert not a["alert"] and a["reasons"] == [] and a["status"] == "warn"       # within 1 of the limit: amber, not red
    assert svc.assess(total=100, days=10, breaches=[], limit=11)["status"] == "ok"           # 10.0 is not within the margin
    assert svc.assess(total=101, days=10, breaches=[], limit=11)["status"] == "warn"          # 10.1 is
    assert svc.assess(total=0, days=0, breaches=[], limit=11)["status"] == "none"            # no entries: nothing to compare


def test_the_capping_average_counts_only_days_with_a_capping_in_force():
    hist = [(date(2026, 10, 1), 10), (date(2026, 10, 15), 11)]
    assert svc.capping_totals(hist, date(2026, 10, 1), date(2026, 10, 31)) == (10 * 14 + 11 * 17, 31)
    assert svc.capping_totals(hist, date(2026, 10, 10), date(2026, 10, 16)) == (10 * 5 + 11 * 2, 7)
    assert svc.capping_totals(hist, date(2026, 9, 28), date(2026, 10, 2)) == (20, 2)          # nothing in force before the 1st: those days are left out
    assert svc.capping_totals(hist, date(2026, 9, 1), date(2026, 9, 30)) == (0, 0)
    assert svc.capping_totals([], date(2026, 10, 1), date(2026, 10, 31)) == (0, 0)
    assert svc.capping_totals(hist, date(2026, 10, 5), date(2026, 10, 4)) == (0, 0)


def test_a_capping_average_above_the_limit_is_an_alert_on_its_own():
    a = svc.assess(total=50, days=5, breaches=[], limit=11, capping_total=12 * 10, capping_days=10)       # entries average 10, capping averages 12
    assert a["alert"] and a["capping_breach"] and not a["average_breach"] and a["reasons"] == ["capping"] and a["status"] == "over"
    exact = svc.assess(total=50, days=5, breaches=[], limit=11, capping_total=11 * 10, capping_days=10)   # exactly 11 is fine
    assert not exact["alert"] and exact["reasons"] == [] and exact["status"] == "warn"
    assert svc.assess(total=0, days=0, breaches=[], limit=11, capping_total=90, capping_days=10)["status"] == "ok"      # capping alone, 9.0


def test_the_limit_is_one_setting():
    assert settings.MAX_DAILY_LIMIT == 11 and svc.max_daily_limit() == settings.MAX_DAILY_LIMIT


# ---------------------------------------------------------------- changing a capping

def test_a_change_today_is_saved_and_becomes_the_current_capping(client, admin, zstore, db):
    r = _change(client, admin, zstore, 10, _today())
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["capping"], body["backdated"], body["current_capping"], body["effective_from"]) == (10, False, 10, _today().isoformat())
    db.expire_all()
    assert db.query(StoreCap).filter_by(store_id=zstore.id).one().daily_cap == 10           # the old field is kept in step
    h = client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=admin).json()
    assert [(x["capping"], x["effective_from"]) for x in h["rows"]] == [(10, _today().isoformat())]
    assert h["rows"][0]["changed_by"] and h["rows"][0]["created_at"]


def test_the_example_of_10_from_the_first_and_11_from_the_fifteenth(client, admin, zstore, db):
    first, mid = date(2026, 10, 1), date(2026, 10, 15)
    assert _change(client, admin, zstore, 10, first).status_code == 201
    assert _change(client, admin, zstore, 11, mid).status_code == 201
    sheet = client.get(f"{API}/capping/sheet", params={"from": "2026-10-01", "to": "2026-10-31", "storeId": str(zstore.id)}, headers=admin).json()
    cells = _sheet_row(sheet, zstore)["cells"]
    assert cells[:14] == [10] * 14 and cells[14:] == [11] * 17 and len(sheet["dates"]) == 31


def test_a_backdated_change_is_allowed_and_flagged_and_does_not_move_the_current_capping(client, admin, zstore, db):
    today = _today()
    assert _change(client, admin, zstore, 11, today - timedelta(days=2)).json()["backdated"] is True
    r = _change(client, admin, zstore, 9, today - timedelta(days=20))               # older than the existing one
    assert r.status_code == 201 and r.json()["backdated"] is True
    assert r.json()["current_capping"] == 11                                         # the later change still rules today
    db.expire_all()
    assert db.query(StoreCap).filter_by(store_id=zstore.id).one().daily_cap == 11
    dates = [x["effective_from"] for x in client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=admin).json()["rows"]]
    assert dates == sorted(dates, reverse=True) and len(dates) == 2                  # newest first


def test_a_second_change_for_the_same_date_is_refused_with_a_clear_message(client, admin, zstore, db):
    day = _today() - timedelta(days=3)
    assert _change(client, admin, zstore, 10, day).status_code == 201
    r = _change(client, admin, zstore, 12, day)
    assert r.status_code == 409 and "already exists" in r.json()["detail"] and f"{day:%d-%b-%Y}" in r.json()["detail"]
    db.expire_all()
    assert db.query(CappingHistory).filter_by(store_id=zstore.id).count() == 1       # the first stays as it was


@pytest.mark.parametrize("capping", [0, -3, 1.5, "7", True, None])
def test_the_capping_must_be_a_whole_number_of_at_least_one(client, admin, zstore, capping):
    r = client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": capping, "effectiveFrom": _today().isoformat()}, headers=admin)
    assert r.status_code == 422, r.text


def test_the_date_and_the_store_are_checked(client, admin, zstore):
    assert _change(client, admin, zstore, 10, _today() + timedelta(days=1)).status_code == 422          # no future dates
    bad = client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": 10, "effectiveFrom": "31-02-2026"}, headers=admin)
    assert bad.status_code == 422
    ghost = client.post(f"{API}/capping/change", json={"storeId": str(uuid.uuid4()), "capping": 10, "effectiveFrom": _today().isoformat()}, headers=admin)
    assert ghost.status_code == 404
    assert client.post(f"{API}/capping/change", json={"storeId": str(zstore.id), "capping": 10, "effectiveFrom": _today().isoformat(), "extra": 1}, headers=admin).status_code == 422


def test_a_store_of_another_platform_is_not_found(client, admin, make_store):
    blinkit = make_store(platform="blinkit")
    assert _change(client, admin, blinkit, 10, _today()).status_code == 404


def test_only_someone_holding_capping_change_may_change_and_everyone_who_sees_capping_may_view(client, zepto_emp, emp, admin, zstore, make_user):
    assert _change(client, zepto_emp, zstore, 10, _today()).status_code == 403                    # a Zepto employee can view, not change
    assert _change(client, emp, zstore, 10, _today()).status_code == 403
    assert client.post(f"{API}/capping/change", json={}).status_code in (401, 403)
    for url in ("/capping/sheet", "/capping/summary", "/capping/sheet/download"):
        assert client.get(f"{API}{url}", headers=zepto_emp).status_code == 200, url
        assert client.get(f"{API}{url}", headers=emp).status_code == 403, url                     # a Blinkit employee sees no Zepto capping
    assert client.get(f"{API}/capping/history", params={"storeId": str(zstore.id)}, headers=zepto_emp).status_code == 200

    from .conftest import auth, login
    code, pw, _ = make_user("employee", platform="zepto", grants=("orders.view", "capping.change"))   # ticked for one person, like a manager
    ticked = auth(login(client, code, pw).json()["access_token"])
    assert _change(client, ticked, zstore, 10, _today()).status_code == 201
    assert _change(client, admin, zstore, 12, _today() - timedelta(days=1)).status_code == 201


def test_the_admin_role_holds_the_permission(db):
    from app.models.permission import Permission, RolePermission
    from app.models.role import Role

    n = (db.query(RolePermission).join(Role, Role.id == RolePermission.role_id).join(Permission, Permission.id == RolePermission.permission_id)
         .filter(Role.code == "admin", Permission.code == "capping.change").count())
    assert n == 1


def test_there_is_no_way_to_edit_or_delete_a_history_row(client, admin, zstore):
    row = _change(client, admin, zstore, 10, _today()).json()
    for method in ("put", "patch", "delete"):
        for url in (f"{API}/capping/change", f"{API}/capping/history", f"{API}/capping/history/{row['id']}", f"{API}/capping/change/{row['id']}"):
            assert getattr(client, method)(url, headers=admin).status_code in (404, 405), (method, url)


def test_the_older_single_store_edit_keeps_the_history_in_step(client, zepto_emp, zstore, db):
    r = client.put(f"{API}/capping/stores/{zstore.id}", json={"daily_cap": 9}, headers=zepto_emp)
    assert r.status_code == 200, r.text
    assert client.put(f"{API}/capping/stores/{zstore.id}", json={"daily_cap": 10}, headers=zepto_emp).status_code == 200      # the same day again: corrected, not a clash
    db.expire_all()
    rows = db.query(CappingHistory).filter_by(store_id=zstore.id).all()
    assert [(x.capping, x.effective_from) for x in rows] == [(10, _today())]
    assert client.put(f"{API}/capping/stores/{zstore.id}", json={"daily_cap": None}, headers=zepto_emp).status_code == 200      # "no cap" cannot be history; nothing breaks
    db.expire_all()
    assert db.query(CappingHistory).filter_by(store_id=zstore.id).count() == 1


# ---------------------------------------------------------------- the sheet and its downloads

def test_the_sheet_has_one_row_per_store_and_one_column_per_date_and_empty_before_the_first_change(client, admin, zstore, db):
    _seed(db, zstore, (date(2026, 10, 3), 10))
    r = client.get(f"{API}/capping/sheet", params={"from": "2026-10-01", "to": "2026-10-05"}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dates"] == [f"2026-10-0{d}" for d in range(1, 6)]
    assert _sheet_row(body, zstore)["cells"] == [None, None, 10, 10, 10]
    assert len({x["store_id"] for x in body["rows"]}) == len(body["rows"])


def test_the_sheet_defaults_to_this_month_and_refuses_a_bad_period(client, admin):
    body = client.get(f"{API}/capping/sheet", headers=admin).json()
    today = _today()
    assert body["from"] == today.replace(day=1).isoformat() and body["to"] >= today.isoformat()
    assert client.get(f"{API}/capping/sheet", params={"from": "2026-10-05", "to": "2026-10-01"}, headers=admin).status_code == 422
    assert client.get(f"{API}/capping/sheet", params={"from": "2020-01-01", "to": "2020-01-31"}, headers=admin).status_code == 422
    assert client.get(f"{API}/capping/sheet", params={"from": "2025-01-01", "to": "2026-10-01"}, headers=admin).status_code == 422     # over a year
    assert client.get(f"{API}/capping/sheet", params={"storeId": str(uuid.uuid4())}, headers=admin).status_code == 404


def test_the_sheet_costs_the_same_number_of_queries_however_many_stores_there_are(client, admin, make_store, db):
    def queries() -> int:
        n = []
        listener = lambda *a, **k: n.append(1)  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            for url in ("/capping/sheet", "/capping/summary"):
                assert client.get(f"{API}{url}", params={"from": "2026-10-01", "to": "2026-10-31"}, headers=admin).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        return len(n)

    def add_stores(k):
        for _ in range(k):
            s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
            _seed(db, s, (date(2026, 10, 1), 10), (date(2026, 10, 15), 11))
            plant_entry(db, s, date(2026, 10, 2), 5)

    add_stores(2)
    few = queries()
    add_stores(8)
    assert queries() == few and few <= 20            # ten times the stores, the same queries


def test_the_csv_download_has_store_then_dd_mmm_dates(client, admin, zstore, db):
    _seed(db, zstore, (date(2026, 10, 1), 10), (date(2026, 10, 3), 11))
    r = client.get(f"{API}/capping/sheet/download", params={"from": "2026-10-01", "to": "2026-10-04", "storeId": str(zstore.id), "format": "csv"}, headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and r.headers["content-disposition"].endswith('_2026-10-01_to_2026-10-04.csv"')
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["Store", "01-Oct", "02-Oct", "03-Oct", "04-Oct"]
    assert rows[1] == [zstore.name, "10", "10", "11", "11"] and len(rows) == 2


def test_the_excel_download_matches_and_the_format_is_checked(client, admin, zstore, db):
    _seed(db, zstore, (date(2026, 10, 2), 10))
    r = client.get(f"{API}/capping/sheet/download", params={"from": "2026-10-01", "to": "2026-10-03", "storeId": str(zstore.id), "format": "xlsx"}, headers=admin)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    ws = load_workbook(io.BytesIO(r.content)).active
    assert [c.value for c in ws[1]] == ["Store", "01-Oct", "02-Oct", "03-Oct"]
    assert [c.value for c in ws[2]] == [zstore.name, None, 10, 10] and ws.freeze_panes == "B2"
    assert client.get(f"{API}/capping/sheet/download", params={"format": "pdf"}, headers=admin).status_code == 422


def test_a_store_name_that_looks_like_a_formula_is_defused_in_the_file(client, admin, make_store, db):
    s = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", name="=SUM(A1)")
    r = client.get(f"{API}/capping/sheet/download", params={"from": "2026-10-01", "to": "2026-10-01", "storeId": str(s.id)}, headers=admin)
    assert list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))[1][0] == "'=SUM(A1)"


# ---------------------------------------------------------------- the average-vs-limit summary

def _summary(client, headers, store, start="2026-10-01", end="2026-10-31"):
    r = client.get(f"{API}/capping/summary", params={"from": start, "to": end}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json(), _sheet_row(r.json(), store)


def test_summary_average_is_over_the_days_that_have_an_entry_and_a_zero_counts(client, admin, zstore, db):
    for i, n in enumerate((10, 0, 8)):
        plant_entry(db, zstore, date(2026, 10, 1) + timedelta(days=i), n)
    plant_entry(db, zstore, date(2026, 9, 30), 200)             # outside the period
    body, row = _summary(client, admin, zstore)
    assert (row["average"], row["entry_days"], row["max_day"], row["total"]) == (6.0, 3, 10, 18)
    assert row["alert"] is False and row["breach_days"] == [] and row["status"] == "ok"
    assert body["limit"] == 11 and body["from"] == "2026-10-01" and body["totals"]["stores"] == len(body["rows"])


def test_summary_flags_the_average_above_the_limit_and_names_the_breach_days(client, admin, zstore, db):
    for i, n in enumerate((12, 13)):
        plant_entry(db, zstore, date(2026, 10, 1) + timedelta(days=i), n)
    _, row = _summary(client, admin, zstore)
    assert row["average"] == 12.5 and row["alert"] and row["average_breach"] and row["reasons"] == ["average", "day"]
    assert row["breach_days"] == [{"date": "2026-10-01", "value": 12}, {"date": "2026-10-02", "value": 13}]


def test_summary_flags_a_single_day_above_the_limit_even_when_the_average_is_fine(client, admin, zstore, db):
    for i, n in enumerate((5, 12, 6, 4)):
        plant_entry(db, zstore, date(2026, 10, 1) + timedelta(days=i), n)
    _, row = _summary(client, admin, zstore)
    assert row["average"] == 6.75 and row["alert"] and row["day_breach"] and not row["average_breach"] and row["reasons"] == ["day"]
    assert row["breach_days"] == [{"date": "2026-10-02", "value": 12}] and row["status"] == "over"


def test_summary_gives_both_averages_to_two_decimals_and_alerts_on_the_capping_average(client, admin, zstore, db):
    today = _today()
    start = today.replace(day=1)
    _seed(db, zstore, (start - timedelta(days=40), 12))                  # a capping of 12 in force the whole period
    for i, n in enumerate((10, 9, 9)):
        plant_entry(db, zstore, start + timedelta(days=i), n)         # entries average 9.33
    body = client.get(f"{API}/capping/summary", params={"from": start.isoformat(), "to": today.isoformat()}, headers=admin).json()
    row = _sheet_row(body, zstore)
    assert row["average"] == 9.33 and row["capping_average"] == 12.0 and row["capping_days"] == (today - start).days + 1
    assert row["alert"] and row["capping_breach"] and not row["average_breach"] and row["reasons"] == ["capping"] and row["status"] == "over"
    assert row["breach_days"] == []


def test_summary_capping_average_stops_at_today_for_a_period_that_runs_on(client, admin, zstore, db):
    today = _today()
    _seed(db, zstore, (today.replace(day=1) - timedelta(days=5), 10))
    end = today + timedelta(days=10)
    row = _sheet_row(client.get(f"{API}/capping/summary", params={"from": today.replace(day=1).isoformat(), "to": end.isoformat()}, headers=admin).json(), zstore)
    assert row["capping_days"] == today.day and row["capping_average"] == 10.0 and not row["alert"]


def test_summary_exactly_the_limit_is_not_a_breach(client, admin, zstore, db):
    for i in range(3):
        plant_entry(db, zstore, date(2026, 10, 1) + timedelta(days=i), 11)
    _, row = _summary(client, admin, zstore)
    assert row["average"] == 11.0 and row["max_day"] == 11
    assert row["alert"] is False and row["reasons"] == [] and row["breach_days"] == []
    assert row["status"] == "warn"                                        # amber: within 1 of the limit, not over


def test_summary_a_store_with_no_entries_has_no_average_and_no_alert(client, admin, zstore):
    _, row = _summary(client, admin, zstore)
    assert row["average"] is None and row["max_day"] is None and row["alert"] is False and row["status"] == "none"


def test_summary_gives_the_capping_in_force_today_and_lists_alerts_first(client, admin, zstore, make_store, db):
    calm = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    plant_entry(db, calm, date(2026, 10, 1), 3)
    plant_entry(db, zstore, date(2026, 10, 1), 15)
    _seed(db, zstore, (date(2026, 9, 1), 10), (_today() - timedelta(days=1), 11), (_today() - timedelta(days=30), 9))
    body, row = _summary(client, admin, zstore)
    assert row["current_capping"] == 11
    rows = [r["store_id"] for r in body["rows"]]
    assert rows.index(str(zstore.id)) < rows.index(str(calm.id))          # in alert before not
    assert body["totals"]["in_alert"] == sum(1 for r in body["rows"] if r["alert"])


def test_summary_period_is_checked_and_defaults_to_this_month(client, admin):
    body = client.get(f"{API}/capping/summary", headers=admin).json()
    assert body["from"] == _today().replace(day=1).isoformat()
    assert client.get(f"{API}/capping/summary", params={"from": "2026-10-09", "to": "2026-10-01"}, headers=admin).status_code == 422
