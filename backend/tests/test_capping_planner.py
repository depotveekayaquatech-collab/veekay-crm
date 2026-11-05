"""Smart Capping Planner over the real database: access, the capacity figures, verification, priority matching, the finished-month rule, the export, and that it writes nothing."""
from datetime import timedelta
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import func, select

from app.models.order_entry import OrderEntry
from app.services import capping_history_service as hist
from app.services import capping_service as cs

from .conftest import API, auth, login, plant_entry


def _cap(client, admin, store, n):
    assert client.post(f"{API}/capping/change", json={"storeId": str(store.id), "capping": n}, headers=admin).status_code == 201


def _plan(client, headers, **body):
    return client.post(f"{API}/capping/planner/plan", json=body, headers=headers)


def _row(res, store):
    return next((r for r in res["rows"] if r["store_id"] == str(store.id)), None)


def _dim() -> int:
    return cs.days_in_month(hist.today_ist().replace(day=1))


def _zepto(make_store, **kw):
    return make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru", **kw)


def test_only_someone_holding_the_permission_may_plan_and_a_zepto_person_only_for_zepto(client, admin, emp, zepto_emp, make_user):
    assert client.post(f"{API}/capping/planner/plan", json={}).status_code in (401, 403)
    for who in (emp, zepto_emp):
        assert _plan(client, who).status_code == 403                                   # nobody is given it by default
        assert client.post(f"{API}/capping/planner/export", json={}, headers=who).status_code == 403
    assert _plan(client, admin).status_code == 200

    code, pw, _ = make_user("employee", platform="zepto", grants=("orders.view", "capping.planner"))     # ticked for one person, like a Team Lead / reviewer
    lead = auth(login(client, code, pw).json()["access_token"])
    assert _plan(client, lead).status_code == 200
    assert _plan(client, lead, project="blinkit").status_code == 403                    # Zepto staff plan Zepto only
    code, pw, _ = make_user("employee", platform="blinkit", region="NORTH", grants=("orders.view", "capping.planner"))
    assert _plan(client, auth(login(client, code, pw).json()["access_token"])).status_code == 403   # a Blinkit person never sees Zepto capping


def test_capacity_comes_from_the_capping_and_the_months_entries(client, admin, make_store, db):
    s = _zepto(make_store)
    first = hist.today_ist().replace(day=1)
    plant_entry(db, s, first, 200)
    _cap(client, admin, s, 10)
    res = _plan(client, admin, mode="max_capacity").json()
    r = _row(res, s)
    limit = 10 * _dim()
    assert (r["daily_cap"], r["monthly_limit"], r["used"], r["remaining"], r["over_by"], r["exclude_reason"]) == (10, limit, 200, limit - 200, 0, None)
    assert r["capacity"] == limit - 200 and res["is_plan"] is True and res["month"] == f"{first:%Y-%m}"


def test_a_full_store_an_over_cap_store_and_a_store_with_no_capping_add_no_capacity(client, admin, make_store, db):
    full, over, nocap = _zepto(make_store), _zepto(make_store), _zepto(make_store)
    first = hist.today_ist().replace(day=1)
    plant_entry(db, full, first, 10 * _dim())
    plant_entry(db, over, first, 10 * _dim() + 50)
    for st in (full, over):
        _cap(client, admin, st, 10)
    res = _plan(client, admin, target=10_000_000).json()
    assert [_row(res, x)["capacity"] for x in (full, over, nocap)] == [0, 0, 0]
    assert _row(res, over)["over_by"] == 50 and _row(res, nocap)["exclude_reason"] == "No capping set"
    codes = {(i["code"], i["crm_code"]) for i in res["issues"]}
    assert ("over_cap", over.crm_code) in codes and ("missing_capping", nocap.crm_code) in codes
    assert all(r["proposed"] == 0 for r in res["rows"] if r["store_id"] in {str(full.id), str(over.id), str(nocap.id)})


def test_priority_stores_are_filled_first_in_the_order_pasted_and_never_beyond_their_capacity(client, admin, make_store, db):
    a, b, c = _zepto(make_store), _zepto(make_store), _zepto(make_store)
    for st, cap in ((a, 10), (b, 5), (c, 20)):
        _cap(client, admin, st, cap)                                                   # remaining 10, 5 and 20 days' worth
    d = _dim()
    res = _plan(client, admin, mode="priority_first", target=5 * d + 100, storeLimit=2, priority=[b.crm_code, a.crm_code, c.name]).json()
    assert _row(res, b)["proposed"] == 5 * d and _row(res, a)["proposed"] == 100       # b filled to its capacity, the rest to a - never beyond a capacity
    assert _row(res, c)["proposed"] == 0 and _row(res, c)["selected"] is False        # the limit of 2 was reached
    assert (_row(res, b)["priority_rank"], _row(res, a)["priority_rank"], _row(res, c)["priority_rank"]) == (1, 2, 3)
    t = res["totals"]
    assert (t["matchable"], t["unmatched"], t["selected"], t["priority_exceeds_limit"]) == (5 * d + 100, 0, 2, True)
    outcomes = [e["outcome"] for e in res["priority"]]
    assert outcomes[:2] == ["Included.", "Included."] and "store limit (2)" in outcomes[2]


def test_maximum_capacity_ignores_the_priority_list(client, admin, make_store):
    small, big = _zepto(make_store), _zepto(make_store)
    _cap(client, admin, small, 1)
    _cap(client, admin, big, 29)
    res = _plan(client, admin, mode="max_capacity", storeLimit=1, priority=[small.crm_code]).json()
    chosen = [r for r in res["rows"] if r["selected"]]
    assert len(chosen) == 1 and chosen[0]["remaining"] >= 29 * _dim()                      # the biggest store in the system, not the pasted one
    assert res["priority"][0]["included"] is False


def test_identical_records_are_excluded_but_a_shared_outlet_id_is_kept_and_never_guessed(client, admin, make_store):
    t1, t2 = _zepto(make_store, code="DUP-1", name="Twin Store"), _zepto(make_store, code="DUP-1", name="Twin Store")
    s1, s2 = _zepto(make_store, code="SHARE-1", name="Alpha Mart"), _zepto(make_store, code="SHARE-1", name="Beta Mart")
    for st in (t1, t2, s1, s2):
        _cap(client, admin, st, 10)
    res = _plan(client, admin, priority=["SHARE-1", "Alpha Mart", "Nowhere At All", "DUP-1", s1.crm_code]).json()
    assert {_row(res, x)["exclude_reason"] for x in (t1, t2)} == {"Duplicate store record"}
    assert _row(res, s1)["exclude_reason"] is None and _row(res, s2)["exclude_reason"] is None
    kinds = {i["code"] for i in res["issues"] if i["crm_code"] in (s1.crm_code, s2.crm_code, t1.crm_code)}
    assert {"shared_outlet_id", "duplicate_record"} <= kinds
    assert [e["status"] for e in res["priority"]] == ["ambiguous", "matched", "unmatched", "ambiguous", "duplicate"]   # the shared ID is not guessed; Alpha by name; the code repeats Alpha
    assert all(e["included"] is False for e in res["priority"] if e["status"] != "matched")


def test_a_finished_month_shows_capacity_but_proposes_no_allocation(client, admin, make_store):
    s = _zepto(make_store)
    _cap(client, admin, s, 10)
    last = hist.today_ist().replace(day=1) - timedelta(days=1)
    res = _plan(client, admin, month=f"{last:%Y-%m}", target=500, priority=[s.crm_code]).json()
    assert res["totals"]["allocation_allowed"] is False and res["allocation_note"]
    assert all(r["proposed"] == 0 and r["final_planned"] == r["used"] for r in res["rows"])
    assert _plan(client, admin, month="2999-01").status_code == 422


def test_blinkit_stores_have_no_capping_and_add_no_capacity(client, admin, make_store):
    b = make_store(platform="blinkit")
    res = _plan(client, admin, project="blinkit", target=100).json()
    r = _row(res, b)
    assert r["exclude_reason"] == "No capping set" and res["totals"]["available_capacity"] == 0
    assert res["totals"]["matchable"] == 0 and res["totals"]["unmatched"] == 100
    assert _row(_plan(client, admin, project="zepto").json(), b) is None


def test_planning_and_exporting_write_nothing(client, admin, make_store, db):
    s = _zepto(make_store)
    plant_entry(db, s, hist.today_ist().replace(day=1), 40)
    _cap(client, admin, s, 10)
    snapshot = lambda: db.execute(select(func.count(OrderEntry.id), func.coalesce(func.sum(OrderEntry.bottle_count), 0))).one()  # noqa: E731
    before = snapshot()
    _plan(client, admin, target=1000, priority=[s.crm_code])
    assert client.post(f"{API}/capping/planner/export", json={"target": 1000, "priority": [s.crm_code]}, headers=admin).status_code == 200
    db.expire_all()
    assert snapshot() == before


def test_the_export_has_the_eight_sheets_keeps_recorded_and_planned_apart_and_reconciles(client, admin, make_store, db):
    s = _zepto(make_store)
    plant_entry(db, s, hist.today_ist().replace(day=1), 100)
    _cap(client, admin, s, 10)
    r = client.post(f"{API}/capping/planner/export", json={"target": 50, "mode": "priority_first", "priority": [s.crm_code, "Missing Store"]}, headers=admin)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"] and r.headers["content-disposition"].startswith("attachment")
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["Configuration Summary", "Selected Stores", "All Store Capacities", "Priority Stores", "Proposed Allocation", "Excluded Stores",
                             "Data Validation Issues", "Reconciliation Audit"]
    sel = list(wb["Selected Stores"].iter_rows(min_row=2, values_only=True))
    head, first = sel[0], sel[1]
    assert "Recorded count (actual)" in head and "Proposed allocation (plan)" in head and "Planned count (plan)" in head
    d = dict(zip(head, first))
    assert (d["Recorded count (actual)"], d["Proposed allocation (plan)"], d["Planned count (plan)"], d["Outlet ID"]) == (100, 50, 150, s.external_code)
    assert "PLAN ONLY" in wb["Selected Stores"]["A1"].value
    audit = [row for row in wb["Reconciliation Audit"].iter_rows(min_row=3, values_only=True) if row[1] in ("PASS", "FAIL")]
    assert audit and all(row[1] == "PASS" for row in audit)
    pri = list(wb["Priority Stores"].iter_rows(min_row=3, values_only=True))
    assert [p[2] for p in pri] == ["Matched", "Unmatched"]                               # the unmatched entry is in the report, not dropped


def test_bad_input_is_refused(client, admin):
    assert _plan(client, admin, storeLimit=0).status_code == 422
    assert _plan(client, admin, target=-1).status_code == 422
    assert _plan(client, admin, mode="bogus").status_code == 422
    assert _plan(client, admin, priority=["x" * 201]).status_code == 422
    assert _plan(client, admin, unknown=1).status_code == 422
