"""
Load capping, with the DATE each capping starts, from a sheet people already keep.

Two layouts are read (the header may sit under a title; columns are found by their words; a store is named by Outlet Name or Outlet ID):

  * DATES across the top (the same shape as the downloaded capping sheet): Store | 01-Oct | 02-Oct | ... with the capping in force in each cell.
    For every store the dates are walked in order: the first date that has a number is when its capping STARTS, and every date where the number changes
    is a new change. A blank cell carries the capping on; a 0 is a day marked 0 (not a change of capping). So "10 on every date from the 1st" is one change
    from day 1, and "10 until the 14th, 12 from the 15th" is two.
  * ONE capping per store: Store | Capping [| Effective from]. The start is the row's date when the sheet has an "Effective from" style column, otherwise the
    `default_start` the person chose (the 1st of this month unless they say otherwise).

Nothing is written until the person applies the preview (`dry_run` false). Dates are Asia/Kolkata days, never in the future. By default a date a store already
has a capping row for is kept (and reported when the sheet disagrees); with `replace` the sheet is the truth from each store's first date in it: the store's
rows from that date on are made to match it (rows the sheet does not have are removed, every removed row is listed in the activity log).
"""
from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.capping_history import CappingHistory, CappingZeroDay
from app.models.store import Store, StoreStatus
from app.models.user import User
from app.services import activity_service, capping_history_service as hist, capping_service

_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_START_HEADERS = {capping_service._norm_name(x) for x in (  # noqa: SLF001
    "effective from", "effective date", "effective", "start date", "start", "from date", "from", "applicable from", "w.e.f", "wef", "date")}
SAMPLE = 40


def parse_header_date(text: str, today: date) -> date | None:
    """A date column heading: 2026-10-01, 01/10/2026, 1-Oct, 01-Oct-26, 1 October 2026, or a bare day number 1..31 (this month). The year of a heading
    that has none is this year, or last year when the month is still ahead (a sheet kept since last December)."""
    t = (text or "").strip()
    if not t:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", t)
    if m:
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", t)
    if m:
        y = int(m[3]) + (2000 if int(m[3]) < 100 else 0)
        return _safe(y, int(m[2]), int(m[1]))
    m = re.fullmatch(r"(\d{1,2})[\s/.-]*([A-Za-z]{3,9})[\s/.,-]*(\d{2,4})?", t)
    if m and m[2][:3].lower() in _MONTHS:
        month = _MONTHS[m[2][:3].lower()]
        if m[3]:
            return _safe(int(m[3]) + (2000 if int(m[3]) < 100 else 0), month, int(m[1]))
        d = _safe(today.year, month, int(m[1]))
        return _safe(today.year - 1, month, int(m[1])) if d and d > today and month > today.month else d
    if re.fullmatch(r"\d{1,2}", t) and 1 <= int(t) <= 31:
        return _safe(today.year, today.month, int(t))
    return None


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _norm(text: str) -> str:
    return capping_service._norm_name(text)  # noqa: SLF001


def _read_grid(grid: list[list[str]], by_code, by_name, today: date) -> dict | None:
    """The best reading of one sheet: {"kind": "dates" | "simple", "lines": [(row number, id text, name text, {date: cap text} or (cap text, start text))]}, or None."""
    width = max((len(r) for r in grid), default=0)
    cell = lambda r, j: (grid[r][j] if j is not None and j < len(grid[r]) else "").strip()  # noqa: E731

    for r in range(min(len(grid), capping_service._HEADER_SCAN_ROWS)):  # noqa: SLF001
        heads = [cell(r, j) for j in range(width)]
        idc = next((j for j, h in enumerate(heads) if _norm(h) in capping_service._ID_SET), None)  # noqa: SLF001
        nmc = next((j for j, h in enumerate(heads) if _norm(h) in capping_service._NAME_SET), None)  # noqa: SLF001
        dates = {j: d for j, h in enumerate(heads) if j not in (idc, nmc) and (d := parse_header_date(h, today)) is not None}
        if (idc is not None or nmc is not None) and dates:
            lines = []
            for rr in range(r + 1, len(grid)):
                code, name = cell(rr, idc), cell(rr, nmc)
                if code or name:
                    lines.append((rr + 1, code, name, {d: cell(rr, j) for j, d in dates.items()}))
            return {"kind": "dates", "lines": lines, "columns": len(dates), "from": min(dates.values()), "to": max(dates.values())}

    # one capping per store: the older layout detection finds the columns, then a start-date column is looked for by its heading
    best = None
    for lay in capping_service._layouts(grid, by_code, by_name):  # noqa: SLF001
        got = capping_service._read_layout(grid, lay, by_code, by_name)  # noqa: SLF001
        if best is None or got["matched"] > best["matched"]:
            best = got
    if best is None or not best["lines"]:
        return None
    lay = best["layout"]
    start_col = None
    if lay["header_row"] is not None:
        heads = [cell(lay["header_row"], j) for j in range(width)]
        start_col = next((j for j, h in enumerate(heads) if j not in (lay["id"], lay["name"], lay["cap"]) and _norm(h) in _START_HEADERS), None)
    lines = [(row, code, name, (cap, cell(row - 1, start_col))) for row, code, name, cap in best["lines"]]
    return {"kind": "simple", "lines": lines, "matched": best["matched"], "has_start_column": start_col is not None}


def _timeline(cells: dict[date, str], today: date) -> tuple[list[tuple[date, int]], list[date], int, int]:
    """(changes, zero days, invalid cells, future cells) of one store's dated cells."""
    changes: list[tuple[date, int]] = []
    zeros: list[date] = []
    invalid = future = 0
    prev: int | None = None
    for d in sorted(cells):
        if d > today:
            future += 1
            continue
        value, bad = capping_service._cap_value(cells[d])  # noqa: SLF001
        if bad:
            invalid += 1
        elif value is None:
            continue                                   # blank: the capping simply carries on
        elif value == 0:
            zeros.append(d)
        elif value != prev:
            changes.append((d, value))
            prev = value
    return changes, zeros, invalid, future


def _plan(existing: dict[date, int], wanted: list[tuple[date, int]], replace: bool) -> dict:
    """What to do to one store's rows: add, change, remove (only with replace) and the disagreements that are left alone."""
    add, change, conflicts, unchanged = [], [], [], 0
    for d, cap in wanted:
        have = existing.get(d)
        if have is None:
            add.append((d, cap))
        elif have == cap:
            unchanged += 1
        elif replace:
            change.append((d, have, cap))
        else:
            conflicts.append((d, have, cap))
    remove = []
    if replace and wanted:
        keep = {d for d, _ in wanted}
        first = wanted[0][0]
        remove = [(d, c) for d, c in sorted(existing.items()) if d >= first and d not in keep]
    final = dict(existing)
    for d, cap in add:
        final[d] = cap
    for d, _, cap in change:
        final[d] = cap
    for d, _ in remove:
        final.pop(d, None)
    return {"add": add, "change": change, "remove": remove, "conflicts": conflicts, "unchanged": unchanged, "final": sorted(final.items())}


def import_sheet(
    db: Session, user: User, perms: set[str], grids: list[list[list[str]]], *, dry_run: bool = True, replace: bool = False, default_start: date | None = None,
) -> dict:
    hist._require_change(user, perms)  # noqa: SLF001
    today = hist.today_ist()
    default_start = default_start or date(today.year, today.month, 1)
    if default_start > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The start date cannot be in the future.")
    if default_start < hist.EARLIEST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That start date is too far back.")

    partner = capping_service._partner(db, user.organization_id)  # noqa: SLF001
    all_stores = list(db.execute(select(Store).where(Store.organization_id == user.organization_id, Store.partner_organization_id == partner.id)).scalars())
    by_code = {capping_service._norm_code(s.external_code): s for s in all_stores}  # noqa: SLF001
    by_name: dict[str, list[Store]] = {}
    for st in all_stores:
        by_name.setdefault(capping_service._norm_name(st.name), []).append(st)  # noqa: SLF001

    best = None
    for grid in grids:
        got = _read_grid(grid, by_code, by_name, today)
        if got is None:
            continue
        score = sum(1 for _, code, name, _x in got["lines"] if capping_service._resolve(code, name, by_code, by_name)[0] is not None)  # noqa: SLF001
        if best is None or score > best[0]:
            best = (score, got)
    if best is None or not best[1]["lines"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No stores with a capping were found. The sheet needs a column of store names (or Outlet IDs) and either date columns (01-Oct, 02-Oct...) "
            "with the capping in each, or one capping column (and, if you like, an Effective from column).",
        )
    sheet = best[1]

    res = {"dry_run": dry_run, "applied": False, "layout": sheet["kind"], "replace": replace, "default_start": default_start, "warnings": [],
           "rows_read": 0, "stores": 0, "unknown_stores": 0, "ambiguous": 0, "invalid": 0, "duplicates": 0, "future_ignored": 0, "not_live": 0,
           "zero_caps_skipped": 0}
    if sheet["kind"] == "dates":
        res["read_as"] = f"dates across the top ({sheet['columns']} columns, {sheet['from']:%d %b %Y} to {sheet['to']:%d %b %Y}); each store's start is its first date with a number"
    else:
        res["read_as"] = ("one capping per store; the start date comes from the sheet's " + ("effective-from column" if sheet["has_start_column"] else f"choice: {default_start:%d %b %Y} for all"))

    derived: dict[uuid.UUID, dict] = {}
    seen: set[tuple[str, str]] = set()
    unknown_first = None
    ambiguous_names: list[str] = []
    for rownum, code, name, payload in sheet["lines"]:
        key = ("id", capping_service._norm_code(code)) if code else ("name", capping_service._norm_name(name))  # noqa: SLF001
        if not key[1]:
            continue
        if key in seen:
            res["duplicates"] += 1
            continue
        seen.add(key)
        res["rows_read"] += 1
        store, ambiguous = capping_service._resolve(code, name, by_code, by_name)  # noqa: SLF001
        if ambiguous:
            res["ambiguous"] += 1
            if len(ambiguous_names) < 5:
                ambiguous_names.append(name)
            continue
        if store is None:
            res["unknown_stores"] += 1
            unknown_first = unknown_first or (code or name)
            continue
        if store.status != StoreStatus.LIVE.value:
            res["not_live"] += 1
            continue
        if sheet["kind"] == "dates":
            changes, zeros, invalid, future = _timeline(payload, today)
            res["invalid"] += invalid
            res["future_ignored"] += future
        else:
            cap_text, start_text = payload
            value, bad = capping_service._cap_value(cap_text)  # noqa: SLF001
            if bad:
                res["invalid"] += 1
                continue
            if value is None:
                continue
            if value == 0:
                res["zero_caps_skipped"] += 1
                continue
            start = default_start
            if start_text:
                start = parse_header_date(start_text, today)
                if start is None or start < hist.EARLIEST:
                    res["invalid"] += 1
                    continue
                if start > today:
                    res["future_ignored"] += 1
                    continue
            changes, zeros = [(start, value)], []
        if not changes and not zeros:
            continue
        derived[store.id] = {"store": store, "changes": changes, "zeros": zeros}
    res["stores"] = len(derived)

    ids = list(derived) or [uuid.uuid4()]
    existing: dict[uuid.UUID, dict[date, CappingHistory]] = defaultdict(dict)
    for row in db.execute(select(CappingHistory).where(CappingHistory.store_id.in_(ids))).scalars():
        existing[row.store_id][row.effective_from] = row
    zero_have: dict[uuid.UUID, set[date]] = defaultdict(set)
    for sid, day in db.execute(select(CappingZeroDay.store_id, CappingZeroDay.day).where(CappingZeroDay.store_id.in_(ids))):
        zero_have[sid].add(day)

    starts: Counter = Counter()
    totals = {"add": 0, "change": 0, "remove": 0, "conflicts": 0, "unchanged_stores": 0, "zero_days": 0}
    sample, removed_log = [], []
    plans: dict[uuid.UUID, dict] = {}
    for sid, d in derived.items():
        plan = _plan({k: r.capping for k, r in existing[sid].items()}, d["changes"], replace)
        plans[sid] = plan
        if d["changes"]:
            starts[d["changes"][0][0]] += 1
        new_zero = [z for z in d["zeros"] if z not in zero_have[sid]]
        totals["add"] += len(plan["add"])
        totals["change"] += len(plan["change"])
        totals["remove"] += len(plan["remove"])
        totals["conflicts"] += len(plan["conflicts"])
        totals["zero_days"] += len(new_zero)
        busy = plan["add"] or plan["change"] or plan["remove"] or new_zero
        totals["unchanged_stores"] += 0 if busy else 1
        d["new_zero"] = new_zero
        if len(sample) < SAMPLE and (busy or plan["conflicts"]):
            current = hist.effective_capping(plan["final"], today)
            sample.append({
                "outlet_id": d["store"].external_code, "store": d["store"].name, "start": d["changes"][0][0] if d["changes"] else None,
                "current": current, "changes": [{"date": x, "capping": c} for x, c in d["changes"]][:6],
                "status": "conflict" if plan["conflicts"] and not busy else "update" if existing[sid] else "new",
                "differs_from_crm": [{"date": x, "crm": a, "sheet": b} for x, a, b in plan["conflicts"]][:3],
            })

    first_of_period = lambda x: x.day == 1  # noqa: E731
    res.update({
        "new_rows": totals["add"], "updated_rows": totals["change"], "removed_rows": totals["remove"], "conflicts": totals["conflicts"],
        "unchanged_stores": totals["unchanged_stores"], "zero_days": totals["zero_days"],
        "day_one": sum(n for d, n in starts.items() if first_of_period(d)), "mid_month": sum(n for d, n in starts.items() if not first_of_period(d)),
        "starts": [{"date": d, "stores": n} for d, n in sorted(starts.items())][:40],
        "sample": sample,
    })
    if res["unknown_stores"]:
        res["warnings"].append(f"{res['unknown_stores']} store(s) in the sheet are not Zepto stores in the CRM and were skipped (first: {unknown_first}).")
    if res["not_live"]:
        res["warnings"].append(f"{res['not_live']} store(s) are not live and were skipped.")
    if res["ambiguous"]:
        res["warnings"].append(f"{res['ambiguous']} store name(s) match more than one store and were skipped, add an Outlet ID column to settle them: {', '.join(ambiguous_names)}.")
    if res["invalid"]:
        res["warnings"].append(f"{res['invalid']} cell(s) were not a whole number or a date and were skipped.")
    if res["future_ignored"]:
        res["warnings"].append(f"{res['future_ignored']} future-dated cell(s) were ignored.")
    if res["zero_caps_skipped"]:
        res["warnings"].append(f"{res['zero_caps_skipped']} store(s) with a capping of 0 were skipped (mark zero days on the Change capping tab).")
    if res["duplicates"]:
        res["warnings"].append(f"{res['duplicates']} repeated store line(s) were ignored (the first one counts).")
    if totals["conflicts"] and not replace:
        res["warnings"].append(f"{totals['conflicts']} date(s) already have a different capping in the CRM and were left as they are (turn on Replace to use the sheet).")

    if dry_run or not derived:
        return res

    for sid, d in derived.items():
        plan = plans[sid]
        for day, cap in plan["add"]:
            db.add(CappingHistory(store_id=sid, capping=cap, effective_from=day, created_by=user.id))
        for day, _old, cap in plan["change"]:
            existing[sid][day].capping = cap
        for day, cap in plan["remove"]:
            db.delete(existing[sid][day])
            removed_log.append(f"{d['store'].external_code} {day.isoformat()} {cap}")
        for day in d["new_zero"]:
            db.add(CappingZeroDay(store_id=sid, day=day, created_by=user.id))
        db.flush()
        hist._sync_current(db, sid, user.id, today)  # noqa: SLF001
    activity_service.record(
        db, actor=user, action="capping.sheet_imported", entity_type="store", entity_id=partner.id,
        metadata={"layout": sheet["kind"], "replace": replace, "stores": res["stores"], "new_rows": res["new_rows"], "updated_rows": res["updated_rows"],
                  "removed_rows": res["removed_rows"], "zero_days": res["zero_days"], "removed": removed_log[:500], "day_one": res["day_one"], "mid_month": res["mid_month"]},
    )
    db.commit()
    res["applied"] = True
    return res
