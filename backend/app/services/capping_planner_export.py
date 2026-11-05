"""
Smart Capping Planner - the Excel workbook of one calculation. Recorded values (copied from the CRM) and planning values (this calculation's proposals) sit in
clearly different, labelled columns, and every sheet starts with the line that a proposal is not supply. Built from the SAME result the screen shows.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

NOTE = "PLAN ONLY - proposed allocations are capacity planning, not supply. Recorded counts are copied unchanged from the CRM."
ACTUAL = PatternFill("solid", fgColor="E8F0FE")        # recorded in the CRM
PLANNED = PatternFill("solid", fgColor="FFF4D6")       # this plan's proposal
HEAD = Font(bold=True)
_IST = ZoneInfo("Asia/Kolkata")


def _sheet(wb: Workbook, title: str, headers: list[str], rows: list[list], *, actual: set[int] = frozenset(), planned: set[int] = frozenset()):
    ws = wb.create_sheet(title)
    ws.append([NOTE])
    ws["A1"].font = Font(bold=True, color="9C2B2B")
    ws.append(headers)
    for i, _ in enumerate(headers, start=1):
        c = ws.cell(row=2, column=i)
        c.font = HEAD
        c.alignment = Alignment(wrap_text=True, vertical="top")
        c.fill = ACTUAL if i in actual else PLANNED if i in planned else PatternFill()
    for r in rows:
        ws.append(r)
    for i, h in enumerate(headers, start=1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:300] if i - 1 < len(r)])
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 48)
    ws.freeze_panes = "A3"
    return ws


def _store_row(r: dict) -> list:
    return [r["name"], r["outlet_id"], r["crm_code"], r["project"].title(), r["state"], r["city"], r["daily_cap"], r["monthly_limit"], r["used"], r["remaining"],
            r["priority_rank"], r["selection_rank"], r["proposed"], r["final_planned"], r["exclude_reason"] or ""]


STORE_HEAD = ["Store name", "Outlet ID", "System code", "Project", "State", "City", "Daily capping", "Monthly limit", "Recorded count (actual)", "Remaining capacity",
              "Priority rank", "Selection rank", "Proposed allocation (plan)", "Planned count (plan)", "Excluded because"]
STORE_ACTUAL, STORE_PLANNED = {7, 8, 9, 10}, {11, 12, 13, 14}


def build(result: dict, *, user_name: str, now: datetime | None = None) -> bytes:
    """The workbook bytes for a plan result (capping_planner_service.run)."""
    now = (now or datetime.now(_IST)).astimezone(_IST)
    t = result["totals"]
    rows = result["rows"]
    selected = sorted((r for r in rows if r["selected"]), key=lambda r: r["selection_rank"])
    wb = Workbook()
    wb.remove(wb.active)

    ws = _sheet(wb, "Configuration Summary", ["Item", "Value"], [
        ["Month", result["month_label"]], ["Project", result["project"].title() if result["project"] != "all" else "All projects"],
        ["Calculation mode", "Priority First" if result["mode"] == "priority_first" else "Maximum Capacity"],
        ["Number of stores to use", result["store_limit"] if result["store_limit"] else "No limit (all eligible stores)"],
        ["Target difference", t["target"]], ["Current total (recorded)", t["current_total"]], ["Desired total (current + target)", t["desired_total"]],
        ["Total stores", t["stores"]], ["Eligible stores (verified, with capacity)", t["eligible"]], ["Excluded stores", t["excluded"]],
        ["Total available capacity (eligible stores)", t["available_capacity"]], ["Stores selected", t["selected"]], ["Capacity of selected stores", t["selected_capacity"]],
        ["Matchable difference", t["matchable"]], ["Unmatched difference", t["unmatched"]], ["Unused capacity in selected stores", t["unused_capacity"]],
        ["Target covered %", t["percent_covered"] if t["percent_covered"] is not None else "n/a"],
        ["Stores needed to cover the target", t["stores_required"] if t["stores_required"] else ("Fits in the selection" if t["fits"] else "Cannot be covered by every eligible store")],
        ["Priority entries pasted / matched / included", f"{t['priority_total']} / {t['priority_matched']} / {t['priority_included']}"],
        ["Allocation", "Proposed" if t["allocation_allowed"] else (result["allocation_note"] or "Not proposed")],
        ["Prepared by", user_name], ["Prepared at (IST)", now.strftime("%d-%b-%Y %H:%M")],
    ])
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 44

    _sheet(wb, "Selected Stores", STORE_HEAD, [_store_row(r) for r in selected], actual=STORE_ACTUAL, planned=STORE_PLANNED)
    _sheet(wb, "All Store Capacities", STORE_HEAD, [_store_row(r) for r in sorted(rows, key=lambda r: (-r["capacity"], r["name"].casefold()))], actual=STORE_ACTUAL, planned=STORE_PLANNED)
    _sheet(wb, "Priority Stores", ["Position", "Pasted text", "Match", "Store name", "Outlet ID", "System code", "Outcome"],
           [[e["position"], e["raw"], e["status"].replace("_", " ").title(), e["name"] or "", e["outlet_id"] or "", e["crm_code"] or "", e["outcome"] if "outcome" in e else e["message"]]
            for e in result["priority"]])
    _sheet(wb, "Proposed Allocation", ["Order", "Store name", "Outlet ID", "System code", "Remaining capacity", "Proposed allocation (plan)", "Recorded count (actual)", "Planned count (plan)"],
           [[r["selection_rank"], r["name"], r["outlet_id"], r["crm_code"], r["remaining"], r["proposed"], r["used"], r["final_planned"]] for r in selected if r["proposed"]],
           actual={7}, planned={6, 8})
    _sheet(wb, "Excluded Stores", ["Store name", "Outlet ID", "System code", "Project", "City", "Reason", "Recorded count (actual)"],
           [[r["name"], r["outlet_id"], r["crm_code"], r["project"].title(), r["city"], r["exclude_reason"], r["used"]] for r in rows if r["exclude_reason"]], actual={7})
    _sheet(wb, "Data Validation Issues", ["Severity", "Issue", "Store name", "Outlet ID", "System code", "Project", "Detail"],
           [[i["severity"].title(), i["code"].replace("_", " ").capitalize(), i["name"], i["outlet_id"], i["crm_code"], i["project"].title(), i["message"]] for i in result["issues"]])

    allocated = sum(r["proposed"] for r in rows)
    checks = [
        ("No store is allocated beyond its remaining capacity", all(r["proposed"] <= r["remaining"] for r in rows)),
        ("Planned count = recorded count + proposed allocation, for every store", all(r["final_planned"] == r["used"] + r["proposed"] for r in rows)),
        ("Total allocated does not exceed the target", allocated <= t["target"]),
        ("Total allocated equals the matchable difference (or none was proposed)", allocated == (t["matchable"] if t["allocation_allowed"] else 0)),
        ("Stores selected does not exceed the store limit", not t["store_limit"] or t["selected"] <= t["store_limit"]),
        ("Only eligible stores were selected", all(r["capacity"] > 0 for r in selected)),
        ("Unmatched difference = target - matchable difference", t["unmatched"] == t["target"] - t["matchable"]),
    ]
    _sheet(wb, "Reconciliation Audit", ["Check / item", "Result / value"], [
        ["Source", "CRM stores, capping history and the month's order entries, read only. No record was created, changed or deleted."],
        ["Recorded total of the month (all stores listed)", t["current_total"]], ["Entries counted", sum(r["entries"] for r in rows)],
        ["Total proposed allocation (plan)", allocated],
        *[[name, "PASS" if ok else "FAIL"] for name, ok in checks],
        ["Reminder", "Capacity is not proof of supply. Do not enter or report proposed values as delivered."],
    ])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
