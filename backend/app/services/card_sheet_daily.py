"""
Random Card PDF, "my own daily entries" mode: a sheet of store name, total count, and one column per day of a chosen month.
The cells are the entries; nothing is randomised. The sheet's own total is only checked against the days (the page flags a
store whose days don't add up), never used to change them. Reading is the only server-side step (it needs the CRM to match
each row to a store); the PDF is drawn by card_sheet_bulk.render_bulk, so, like the random modes, nothing is stored or logged.
"""
from __future__ import annotations

import calendar
import re
import uuid
from collections import defaultdict
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.store import Store
from app.models.user import User
from app.services.card_sheet_bulk import MAX_BULK_STORES, _suggestions
from app.services.card_sheet_service import MAX_COUNT, _ALIASES, _alnum, _content_store_col, _grids, _header_date, _norm_header

_DAY = re.compile(r"^(?:day\s*)?(\d{1,2})(?:st|nd|rd|th)?$", re.IGNORECASE)
_TOTAL_HEADS = ("totalcount", "total", "totalbottles", "grandtotal", "count", "bottles", "sum")
_TOTAL_ROWS = ("total", "grandtotal")
_HEADER_SCAN_ROWS = 25
_MIN_DAY_COLUMNS = 3


def _day_number(raw: str, month: date) -> int | None:
    """'7', 'Day 7', '7th', '7-Oct' or a real date in the chosen month -> 7. 1-31 are all accepted here: whether the month has that day is checked per cell."""
    text = str(raw or "").strip()
    bare = _DAY.match(text)
    if bare:
        n = int(bare.group(1))
        return n if 1 <= n <= 31 else None
    full = _header_date(text, date.today(), month)
    return full.day if full and (full.year, full.month) == (month.year, month.month) else None


def _find_header(grid: list[list[str]], month: date) -> tuple[int, dict[int, int]] | None:
    """(row, {column: day}) of the first row whose cells count up through the days, in column order (a data row of repeated
    numbers like 5, 5, 5 is not a header)."""
    for r, row in enumerate(grid[:_HEADER_SCAN_ROWS]):
        days = {i: n for i, c in enumerate(row) if (n := _day_number(c, month)) is not None}
        nums = list(days.values())
        if len(days) >= _MIN_DAY_COLUMNS and nums == sorted(set(nums)):
            return r, days
    return None


def _whole(raw: str) -> int | None:
    text = raw.strip().replace(",", "")
    try:
        n = float(text)
    except ValueError:
        return None
    return int(n) if n.is_integer() and 0 <= n <= MAX_COUNT else None


def _first_col(heads: list[str], aliases: tuple[str, ...], taken: set[int]) -> int | None:
    for alias in aliases:
        for i, h in enumerate(heads):
            if h == alias and i not in taken:
                return i
    return None


def _lookup(by_key: dict[str, list[Store]], name_raw: str, code_raw: str) -> list[Store]:
    """The store a row names: its name first, then its Outlet ID; an Outlet ID breaks a tie between equal names."""
    for raw in (name_raw, code_raw):
        found = by_key.get(_alnum(raw), []) if raw else []
        if found:
            if len(found) > 1 and code_raw:
                found = [s for s in found if _alnum(s.external_code) == _alnum(code_raw)] or found
            return found
    return []


def _read_row(row: list[str], days: dict[int, int], total_col: int | None, month: date) -> tuple[dict[date, int], int | None, list[str]]:
    """(entries, the sheet's own total or None, problems). A blank day is no entry; a typed 0 is one."""
    last = calendar.monthrange(month.year, month.month)[1]
    entries: dict[date, int] = {}
    issues: list[str] = []
    for col, day in days.items():
        raw = row[col].strip() if col < len(row) else ""
        if not raw:
            continue
        count = _whole(raw)
        if count is None:
            issues.append(f"Day {day}: '{raw[:20]}' is not a whole number of zero or more.")
        elif day > last:
            issues.append(f"Day {day}: {calendar.month_name[month.month]} {month.year} has no day {day}.")
        else:
            entries[date(month.year, month.month, day)] = count
    raw_total = row[total_col].strip() if total_col is not None and total_col < len(row) else ""
    sheet_total = _whole(raw_total) if raw_total else None
    if raw_total and sheet_total is None:
        issues.append(f"Total count '{raw_total[:20]}' is not a whole number of zero or more.")
    return entries, sheet_total, issues


def parse_daily(db: Session, user: User, filename: str, content: bytes, month: date) -> dict:
    """Reads the sheet for `month`. Returns what matched a store and what didn't (with suggestions), each with its daily entries,
    the total the sheet states, and any problems, so the person can fix the sheet or point a row at a store before any card is drawn."""
    stores = db.execute(
        select(Store).options(joinedload(Store.partner_organization)).where(Store.organization_id == user.organization_id)
    ).unique().scalars().all()
    by_key: dict[str, list[Store]] = defaultdict(list)
    for st in stores:
        for k in {_alnum(st.external_code), _alnum(st.name)}:
            if k:
                by_key[k].append(st)

    found = next(((g, h) for g in _grids(filename, content) if (h := _find_header(g, month))), None)
    if found is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Couldn't find the day columns. The header row needs the store name, the total count and one column for each day of the month "
            "(1, 2, 3 ... or 1-Oct, 2-Oct ...).",
        )
    grid, (header_row, days) = found
    heads = [_norm_header(c) for c in grid[header_row]]
    total_col = _first_col(heads, _TOTAL_HEADS, set(days))
    name_col = _first_col(heads, _ALIASES["name"], set(days))
    code_col = _first_col(heads, _ALIASES["code"], set(days) | {total_col})
    if name_col is None and code_col is None:
        name_col = _content_store_col(grid, header_row, set(days) | {total_col}, set(by_key))
    if name_col is None and code_col is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Couldn't find the column with the store names (a heading like Store name or Outlet ID).")

    def at(row: list[str], i: int | None) -> str:
        return row[i].strip() if i is not None and i < len(row) else ""

    matched: dict[uuid.UUID, dict] = {}
    unmatched: list[dict] = []
    repeated = 0
    empty: list[str] = []
    nameless = 0
    for n, row in enumerate(grid[header_row + 1:], start=header_row + 2):
        if not any(c.strip() for c in row):
            continue
        name_raw, code_raw = at(row, name_col), at(row, code_col)
        label = name_raw or code_raw
        if _norm_header(label) in _TOTAL_ROWS:
            continue                                              # the totals line at the bottom of a sheet
        entries, sheet_total, issues = _read_row(row, days, total_col, month)
        if not label:
            nameless += 1 if (entries or issues) else 0
            continue
        if not entries and not issues and not sheet_total:
            empty.append(label)                                   # a store with nothing to print
            continue
        stores_found = _lookup(by_key, name_raw, code_raw)
        if len(stores_found) != 1:
            unmatched.append({
                "row": n, "name": label, "total": sum(entries.values()), "sheet_total": sheet_total,
                "entries": _listed(entries), "issues": issues,
                "reason": "More than one store has this name." if stores_found else "No store with that name or Outlet ID.",
                "suggestions": [{"store_id": s.id, "name": s.name, "code": s.external_code} for s in stores_found[:4]]
                if stores_found else _suggestions(_alnum(label), by_key),
            })
            continue
        st = stores_found[0]
        if st.id in matched:
            repeated += 1
            prev = matched[st.id]
            for d, c in entries.items():
                prev["_entries"][d] = prev["_entries"].get(d, 0) + c
            prev["sheet_total"] = None if None in (prev["sheet_total"], sheet_total) else prev["sheet_total"] + sheet_total
            prev["issues"] += issues
        else:
            matched[st.id] = {
                "row": n, "sheet_name": label, "store_id": st.id, "store_name": st.name, "code": st.external_code,
                "platform": st.partner_organization.slug if st.partner_organization else None,
                "sheet_total": sheet_total, "issues": issues, "_entries": dict(entries),
            }

    if len(matched) + len(unmatched) > MAX_BULK_STORES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"That sheet has {len(matched) + len(unmatched)} stores; the limit is {MAX_BULK_STORES} per PDF. Split it.",
        )
    rows = []
    for m in sorted(matched.values(), key=lambda m: m["store_name"].lower()):
        entries = m.pop("_entries")
        rows.append({**m, "total": sum(entries.values()), "entries": _listed(entries)})

    warnings: list[str] = []
    if repeated:
        warnings.append(f"{repeated} store(s) appeared more than once in the sheet; their days and totals were added together.")
    if empty:
        warnings.append(f"{len(empty)} row(s) had no daily numbers and were left out: {', '.join(empty[:10])}{' ...' if len(empty) > 10 else ''}.")
    if nameless:
        warnings.append(f"{nameless} row(s) had numbers but no store name and were left out.")
    if total_col is None:
        warnings.append("There is no Total count column, so the daily numbers could not be checked against a total.")
    return {
        "file": filename, "month": f"{month.year}-{month.month:02d}", "rows": len(rows) + len(unmatched), "matched": rows, "unmatched": unmatched,
        "warnings": warnings, "has_entries": True,
    }


def _listed(entries: dict[date, int]) -> list[dict]:
    return [{"date": d, "count": c} for d, c in sorted(entries.items())]
