"""Smart Capping Planner engine: priority matching, store choice (both modes) and the target laid over remaining capacity. Pure, no database."""
import pytest

from app.services.capping_planner_engine import consideration_order, match_priority, norm, plan


def row(n, remaining, *, used=0, reason=None, name=None, outlet=None):
    limit = used + remaining
    return {"store_id": f"id{n}", "crm_code": f"ZPT{n:06d}", "outlet_id": outlet or f"OUT-{n}", "name": name or f"Store {n}", "project": "zepto", "state": "Delhi", "city": "Delhi",
            "daily_cap": limit // 30, "monthly_limit": limit, "used": used, "entries": 1 if used else 0, "remaining": remaining, "over_by": 0, "exclude_reason": reason}


def master(rows):
    return [{k: r[k] for k in ("store_id", "crm_code", "outlet_id", "name", "project")} for r in rows]


def lines(rows, *ns):
    return [rows[n - 1]["outlet_id"] for n in ns]


@pytest.fixture()
def stores():
    return [row(1, 100), row(2, 500), row(3, 300), row(4, 0, used=900), row(5, 200), row(6, 50, reason="No capping set")]


def run(stores, *, mode="max_capacity", limit=None, target=0, pasted=(), project="zepto", allowed=True):
    pri = match_priority(list(pasted), master(stores), project)
    return plan(stores, mode=mode, store_limit=limit, target=target, priority=pri, allocation_allowed=allowed)


def chosen(result):
    return [r["name"] for r in sorted((r for r in result["rows"] if r["selected"]), key=lambda r: r["selection_rank"])]


def test_max_capacity_takes_the_biggest_remaining_and_ignores_the_priority_list(stores):
    res = run(stores, limit=2, target=10, pasted=lines(stores, 1))
    assert chosen(res) == ["Store 2", "Store 3"]                                  # 500 and 300; priority store 1 (100) does not override the ranking
    assert res["priority"][0]["outcome"].startswith("Not included: priority does not override")


def test_priority_first_takes_the_pasted_stores_in_order_then_the_biggest(stores):
    res = run(stores, mode="priority_first", limit=3, pasted=lines(stores, 5, 1))
    assert chosen(res) == ["Store 5", "Store 1", "Store 2"]                        # 5 then 1 as pasted, then the biggest of the rest
    assert {r["name"]: r["priority_rank"] for r in res["rows"] if r["priority_rank"]} == {"Store 5": 1, "Store 1": 2}
    assert res["totals"]["priority_included"] == 2


def test_the_target_is_laid_over_the_chosen_stores_in_order_and_never_beyond_a_store_capacity(stores):
    res = run(stores, mode="priority_first", target=450, pasted=lines(stores, 5, 1))
    alloc = {r["name"]: r["proposed"] for r in res["rows"] if r["proposed"]}
    assert alloc == {"Store 5": 200, "Store 1": 100, "Store 2": 150}              # 200 + 100 from the priority stores, 150 from the biggest remaining
    assert all(r["proposed"] <= r["remaining"] for r in res["rows"])
    t = res["totals"]
    assert (t["matchable"], t["unmatched"], t["percent_covered"], t["fits"]) == (450, 0, 100.0, True) and t["proposed_total"] == 450


def test_a_target_larger_than_the_capacity_leaves_the_rest_unmatched_and_is_never_forced(stores):
    res = run(stores, target=5000)                                                 # 100 + 500 + 300 + 200 available (store 4 is full, store 6 unverified)
    t = res["totals"]
    assert t["available_capacity"] == 1100 and t["selected_capacity"] == 1100
    assert (t["matchable"], t["unmatched"], t["unused_capacity"], t["fits"], t["coverable"]) == (1100, 3900, 0, False, False)
    assert t["stores_required"] is None and t["percent_covered"] == 22.0
    assert sum(r["proposed"] for r in res["rows"]) == 1100                        # nothing invented to reach 5000


def test_the_store_limit_can_make_a_target_that_would_fit_unmatched_and_says_how_many_stores_it_needs(stores):
    res = run(stores, limit=2, target=900)                                         # 500 + 300 = 800 < 900, but a third store (200) reaches it
    t = res["totals"]
    assert (t["selected"], t["selected_capacity"], t["matchable"], t["unmatched"], t["coverable"]) == (2, 800, 800, 100, True)
    assert t["stores_required"] == 3


def test_stores_that_are_full_or_unverified_never_get_capacity(stores):
    res = run(stores, target=100_000)
    by = {r["name"]: r for r in res["rows"]}
    assert by["Store 4"]["proposed"] == 0 and by["Store 4"]["capacity"] == 0 and not by["Store 4"]["selected"]      # full
    assert by["Store 6"]["proposed"] == 0 and by["Store 6"]["capacity"] == 0 and not by["Store 6"]["selected"]      # no capping
    assert res["totals"]["excluded"] == 1


def test_priority_stores_with_no_room_are_skipped_with_the_reason_not_dropped(stores):
    res = run(stores, mode="priority_first", limit=5, pasted=lines(stores, 4, 6, 1))
    by = {e["name"]: e for e in res["priority"]}
    assert by["Store 4"]["outcome"] == "Skipped: no remaining capacity (limit 900, used 900)."
    assert by["Store 6"]["outcome"] == "Skipped: No capping set."
    assert by["Store 1"]["included"] is True
    assert len(res["priority"]) == 3                                               # nothing silently removed


def test_a_priority_list_longer_than_the_store_limit_is_explained_not_trimmed(stores):
    res = run(stores, mode="priority_first", limit=2, pasted=lines(stores, 1, 2, 3, 5))
    assert chosen(res) == ["Store 1", "Store 2"]                                   # the first two priority stores, as pasted
    out = [e["outcome"] for e in res["priority"]]
    assert out[:2] == ["Included.", "Included."] and all("store limit (2)" in o for o in out[2:])
    assert res["totals"]["priority_exceeds_limit"] is True and res["totals"]["priority_total"] == 4


def test_unmatched_ambiguous_duplicate_and_other_project_entries_are_flagged_and_excluded():
    a, b = row(1, 100, name="Twin"), row(2, 100, name="Twin")
    other = {**row(3, 100), "project": "blinkit", "outlet_id": "BLK-9", "name": "Blink Store"}
    everything = [a, b, row(4, 100), other]
    pri = match_priority(["", "Nowhere", "Twin", row(4, 0)["outlet_id"], "  out-4 ", "BLK-9", row(4, 0)["crm_code"]], master(everything), "zepto")
    assert [e["status"] for e in pri] == ["unmatched", "ambiguous", "matched", "duplicate", "other_project", "duplicate"]   # the blank line is ignored
    assert [e["position"] for e in pri] == [1, 2, 3, 4, 5, 6]
    assert {c["crm_code"] for c in pri[1]["candidates"]} == {a["crm_code"], b["crm_code"]}
    res = plan(everything, mode="priority_first", store_limit=None, target=0, priority=pri)
    assert res["totals"]["priority_matched"] == 1 and res["totals"]["priority_included"] == 1
    assert all(e["outcome"] in ("Excluded until resolved.", "Duplicate: only the first is used.", "Included.") for e in res["priority"])


def test_the_system_code_settles_a_shared_outlet_id_and_a_project_filter_narrows_it():
    z = row(1, 100, outlet="SAME")
    blk = {**row(2, 100, outlet="SAME"), "project": "blinkit"}
    m = master([z, blk])
    assert match_priority(["SAME"], m, "all")[0]["status"] == "ambiguous"
    assert match_priority(["SAME"], m, "zepto")[0]["crm_code"] == z["crm_code"]
    assert match_priority([blk["crm_code"]], m, "all")[0]["status"] == "matched"


def test_an_empty_priority_list_one_store_and_no_limit_all_work(stores):
    assert run(stores, mode="priority_first", target=10)["totals"]["priority_total"] == 0
    assert chosen(run(stores, mode="priority_first", limit=1, pasted=lines(stores, 3))) == ["Store 3"]
    assert run(stores)["totals"]["selected"] == 4                                  # no limit: every eligible store


def test_a_finished_month_gets_the_capacity_picture_but_no_allocation(stores):
    res = run(stores, target=300, allowed=False)
    assert res["totals"]["proposed_total"] == 0 and res["totals"]["allocation_allowed"] is False
    assert all(r["proposed"] == 0 and r["final_planned"] == r["used"] for r in res["rows"])


def test_ties_are_broken_by_name_then_code_and_the_order_is_stable():
    rows = [row(2, 100, name="B"), row(1, 100, name="A"), row(3, 100, name="A")]
    assert [r["crm_code"] for r in consideration_order(rows, "max_capacity", [])] == ["ZPT000001", "ZPT000003", "ZPT000002"]
    assert norm("  Del  ROHINI\tSector 15 ") == "del rohini sector 15"


def test_a_bad_mode_is_refused(stores):
    with pytest.raises(ValueError):
        plan(stores, mode="bogus", store_limit=None, target=0, priority=[])
