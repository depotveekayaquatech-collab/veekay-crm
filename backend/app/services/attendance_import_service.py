"""Attendance sheet upload: fill a month's attendance from a sheet (one row per employee, one column per day, "P" = present).

Meant for days before people used the app's Check in (for example 1 to 16 October) so the month is complete.

* Rows are matched by Employee ID (a "Name" column is only used when there is no ID column or the ID cell is empty, and then only when exactly one
  person has that name). Admins and accounts of nobody are skipped and reported, never guessed.
* Only "P" cells write anything. A blank, "A" or other cell leaves the day exactly as it is. Other letters are counted and reported.
* A day that already has a record is OVERWRITTEN (that is what was asked for); what it held before is kept in the activity log.
* The sheet gives no clock times, so none are invented: the record is marked as coming from the sheet (`source = "sheet"`) and the screens show
  "P", not hours. These days are NOT passed to payroll (see payroll_service.build_days).
* Only days before today are written, so a sheet can never block a real Check in.
* Always run as a preview first (`apply=False`), which changes nothing.
"""
from __future__ import annotations

import calendar
import re
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord
from app.models.user import User
from app.services import activity_service, attendance_service
from app.services.order_import_service import OrderImportError, _grids

SOURCE = "sheet"
PRESENT_MARKS = {"P", "PRESENT"}
BLANK_MARKS = {"", "A", "ABSENT", "-", "--", "—", "NA", "N/A"}
ID_HEADERS = {"employee id", "emp id", "empid", "employee code", "emp code", "employee no", "id", "code", "login id", "staff id"}
NAME_HEADERS = {"employee name", "emp name", "name", "employee", "full name", "staff name"}
MAX_LISTED = 60
HEADER_SEARCH_ROWS = 200       # the table may sit below a title, notes or blank rows (a real sheet had its header on row 31)
MAX_BYTES = 10 * 1024 * 1024


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v).strip()).lower() if v is not None else ""


def _day_of(cell: Any, month: date) -> int | None:
    """The day of the month a header cell stands for: 1..31, '01', 1.0, or a real date inside the month."""
    if isinstance(cell, (datetime, date)):
        d = cell.date() if isinstance(cell, datetime) else cell
        return d.day if (d.year, d.month) == (month.year, month.month) else None
    if isinstance(cell, bool) or cell is None:
        return None
    try:
        n = int(float(str(cell).strip()))
    except ValueError:
        return None
    return n if 1 <= n <= 31 else None


def _locate(rows: list[tuple], month: date) -> tuple[int, int | None, int | None, dict[int, int]] | None:
    """(header row index, id column, name column, {column index: day}) from the first rows of a sheet."""
    for i, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        id_col = name_col = None
        for j, cell in enumerate(row):
            h = _norm(cell)
            if h in ID_HEADERS and id_col is None:
                id_col = j
            elif h in NAME_HEADERS and name_col is None:
                name_col = j
        days = {j: d for j, cell in enumerate(row) if (d := _day_of(cell, month)) is not None}
        if (id_col is not None or name_col is not None) and len(days) >= 5:
            return i, id_col, name_col, days
    return None


def _cell_mark(v: Any) -> str:
    return re.sub(r"\s+", "", str(v)).upper() if v is not None else ""


def run(db: Session, actor: User, month: date, filename: str, content: bytes, *, apply: bool) -> dict:
    """Read the sheet for `month` and report what would be written (apply=False), or write it (apply=True)."""
    try:
        sheets = _grids(filename, content)
    except OrderImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    found = None
    for name, rows in sheets:
        loc = _locate(rows, month)
        if loc:
            found = (name, rows, loc)
            break
    if found is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Couldn't find the table. The sheet needs a header row with an 'Employee ID' (and/or 'Name') column and the day numbers (1, 2, 3 ...) as columns.",
        )
    sheet_name, rows, (hdr, id_col, name_col, day_cols) = found

    org = actor.organization_id
    users = list(db.execute(select(User).where(User.organization_id == org)).scalars())
    by_code = {u.employee_code.strip().lower(): u for u in users}
    by_name: dict[str, list[User]] = {}
    for u in users:
        by_name.setdefault(_norm(u.full_name), []).append(u)
    roles = attendance_service._roles_by_user(db, org)  # noqa: SLF001

    today = attendance_service.today_local()
    last_day = calendar.monthrange(month.year, month.month)[1]
    tz = attendance_service._tz()  # noqa: SLF001
    start = attendance_service._work_start()  # noqa: SLF001

    unmatched: list[dict] = []
    skipped: list[dict] = []
    ignored: dict[str, int] = {}
    future_days = 0
    wanted: dict[tuple[uuid.UUID, date], str] = {}      # (person, day) -> the sheet row it came from
    people: dict[uuid.UUID, User] = {}

    for n, row in enumerate(rows[hdr + 1:], start=hdr + 2):
        cells = list(row) + [None] * (max(day_cols) + 1 - len(row))
        raw_id = cells[id_col] if id_col is not None and id_col < len(cells) else None
        raw_name = cells[name_col] if name_col is not None and name_col < len(cells) else None
        code = str(int(raw_id)) if isinstance(raw_id, float) and raw_id.is_integer() else (str(raw_id).strip() if raw_id is not None else "")
        label = {"row": n, "id": code or None, "name": str(raw_name).strip() if raw_name else None}
        if not code and not raw_name:
            continue                                                       # an empty line
        user = by_code.get(code.lower()) if code else None
        if user is None and not code and raw_name:
            cands = by_name.get(_norm(raw_name), [])
            if len(cands) == 1:
                user = cands[0]
            elif len(cands) > 1:
                skipped.append({**label, "reason": "More than one person has this name: put the Employee ID in the sheet."})
                continue
        if user is None:
            unmatched.append(label)
            continue
        r = set(roles.get(user.id, []))
        if "admin" in r or not (attendance_service.ATTENDING_ROLES & r):
            skipped.append({**label, "reason": "Not on the attendance list (admins and non-attending accounts are never tracked)."})
            continue
        people[user.id] = user
        for col, day in day_cols.items():
            mark = _cell_mark(cells[col])
            if mark in BLANK_MARKS:
                continue
            if mark not in PRESENT_MARKS:
                ignored[mark] = ignored.get(mark, 0) + 1
                continue
            if day > last_day:
                continue
            d = date(month.year, month.month, day)
            if d >= today:
                future_days += 1
                continue
            wanted[(user.id, d)] = f"row {n}"

    existing = {}
    if wanted:
        ids = {uid for uid, _ in wanted}
        for rec in db.execute(select(AttendanceRecord).where(
            AttendanceRecord.organization_id == org, AttendanceRecord.user_id.in_(ids),
            AttendanceRecord.work_date >= month, AttendanceRecord.work_date <= date(month.year, month.month, last_day),
        )).scalars():
            existing[(rec.user_id, rec.work_date)] = rec

    def was(rec: AttendanceRecord) -> dict:
        return {
            "source": rec.source, "check_in_at": rec.check_in_at.isoformat() if rec.check_in_at else None,
            "check_out_at": rec.check_out_at.isoformat() if rec.check_out_at else None, "late": rec.late, "half_day": rec.half_day,
            "check_in_status": rec.check_in_status, "check_in_label": rec.check_in_label,
        }

    overwriting = []
    n_create = n_over = n_same = 0
    for (uid, d), where in sorted(wanted.items(), key=lambda kv: (people[kv[0][0]].employee_code, kv[0][1])):
        rec = existing.get((uid, d))
        if rec is None:
            n_create += 1
        elif rec.source == SOURCE:
            n_same += 1                                                     # already from a sheet: writing it again changes nothing
        else:
            n_over += 1
            overwriting.append({"employee_code": people[uid].employee_code, "full_name": people[uid].full_name, "date": d.isoformat(), "was": was(rec)})

    if apply:
        for (uid, d), _where in wanted.items():
            rec = existing.get((uid, d))
            at = datetime.combine(d, start, tzinfo=tz)                     # a placeholder (NOT NULL column): never shown for a sheet day
            if rec is None:
                db.add(AttendanceRecord(organization_id=org, user_id=uid, work_date=d, check_in_at=at, check_in_status="unknown", late=False,
                                        half_day=False, source=SOURCE))
                continue
            if rec.source == SOURCE:
                continue
            rec.check_in_at, rec.check_in_status, rec.late, rec.half_day, rec.source = at, "unknown", False, False, SOURCE
            rec.check_in_lat = rec.check_in_lng = rec.check_in_accuracy_m = rec.check_in_distance_m = rec.check_in_label = None
            rec.check_out_at = rec.check_out_status = None
            rec.check_out_lat = rec.check_out_lng = rec.check_out_accuracy_m = rec.check_out_distance_m = rec.check_out_label = None
        activity_service.record(
            db, actor=actor, action="attendance.sheet_imported", entity_type="attendance", entity_id=f"{month:%Y-%m}",
            metadata={"file": filename, "month": f"{month:%Y-%m}", "people": len(people), "created": n_create, "overwritten": n_over,
                      "unchanged": n_same, "overwritten_records": overwriting[:3000]},     # what each overwritten day held before
        )
        db.commit()

    return {
        "applied": apply, "month": f"{month:%Y-%m}", "sheet": sheet_name, "people": len(people),
        "days_in_sheet": sorted(set(day_cols.values())), "present_cells": len(wanted),
        "will_create": n_create, "will_overwrite": n_over, "already_from_sheet": n_same,
        "overwriting": overwriting[:MAX_LISTED], "overwriting_total": n_over,
        "unmatched": unmatched[:MAX_LISTED], "unmatched_total": len(unmatched),
        "skipped": skipped[:MAX_LISTED], "skipped_total": len(skipped),
        "ignored_cells": ignored, "future_days_skipped": future_days,
    }
