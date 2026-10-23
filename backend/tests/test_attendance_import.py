"""Attendance sheet upload: rows by Employee ID, "P" = present, existing days overwritten, nothing invented, nothing passed to payroll."""
import io
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.attendance import AttendanceRecord
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import attendance_service, payroll_service

from .conftest import API

IMPORT = f"{API}/attendance/import"
FIRST = date.today().replace(day=1)
MONTH = (FIRST - timedelta(days=1)).replace(day=1)        # last month: every day of it is in the past
M = f"{MONTH:%Y-%m}"


def _csv(rows: list[list], days: int = 16) -> bytes:
    head = ["Employee ID", "Name", *[str(d) for d in range(1, days + 1)]]
    return ("\n".join(",".join(str(c) for c in r) for r in [head, *rows]) + "\n").encode()


def _line(code, name, marks):
    """One sheet row: `marks` has one character per day, '.' meaning a blank cell."""
    cells = ["" if c == "." else c for c in marks]
    return [code, name, *cells]


def _post(client, who, content: bytes, *, apply: bool, month: str = M, name: str = "oct.csv"):
    return client.post(IMPORT, headers=who, data={"month": month, "apply": "true" if apply else "false"}, files={"file": (name, content, "text/csv")})


def _records(db, uid):
    db.expire_all()
    return {r.work_date.day: r for r in db.query(AttendanceRecord).filter_by(user_id=uid)}


@pytest.fixture()
def staff(make_user):
    a, _, ua = make_user()
    b, _, ub = make_user()
    return {"a": (a, ua), "b": (b, ub)}


def test_a_preview_changes_nothing_and_apply_writes_present_days_only(client, dev, db, staff):
    (ca, ua), (cb, ub) = staff["a"], staff["b"]
    sheet = _csv([_line(ca, "A", "PPP.PPPA.PPPPPPP"), _line(cb, "B", "pp" + "." * 14)])
    pre = _post(client, dev, sheet, apply=False).json()
    assert pre["applied"] is False and pre["people"] == 2
    assert pre["present_cells"] == 15 and pre["will_create"] == 15 and pre["will_overwrite"] == 0   # 13 for A (blank and "A" cells excluded) + 2 for B
    assert _records(db, ua) == {} and _records(db, ub) == {}                       # a preview wrote nothing

    done = _post(client, dev, sheet, apply=True).json()
    assert done["applied"] is True and done["will_create"] == pre["will_create"]
    a_days, b_days = _records(db, ua), _records(db, ub)
    assert sorted(b_days) == [1, 2]                                                 # lower-case p counts; blanks write nothing
    assert 4 not in a_days and 9 not in a_days and 1 in a_days and 16 in a_days     # blank and "A" cells are left alone
    r = a_days[1]
    assert r.source == "sheet" and r.late is False and r.half_day is False and r.check_out_at is None and r.check_in_status == "unknown"


def test_an_existing_day_is_overwritten_and_what_it_held_is_kept_in_the_log(client, dev, db, staff):
    (ca, ua) = staff["a"]
    when = datetime(MONTH.year, MONTH.month, 3, 11, 5, tzinfo=timezone.utc)
    db.add(AttendanceRecord(organization_id=db.get(User, ua).organization_id, user_id=ua, work_date=MONTH.replace(day=3), check_in_at=when,
                            check_in_status="office", check_in_label="Head Office", late=True, check_out_at=when + timedelta(hours=8),
                            check_out_status="office", source="checkin"))
    db.commit()
    pre = _post(client, dev, _csv([_line(ca, "A", "..P" + "." * 13)]), apply=False).json()
    assert pre["will_overwrite"] == 1 and pre["will_create"] == 0
    assert pre["overwriting"][0]["date"] == MONTH.replace(day=3).isoformat() and pre["overwriting"][0]["was"]["late"] is True

    assert _post(client, dev, _csv([_line(ca, "A", "..P" + "." * 13)]), apply=True).status_code == 200
    r = _records(db, ua)[3]
    assert r.source == "sheet" and r.late is False and r.check_out_at is None and r.check_in_label is None
    log = db.query(AuditLog).filter_by(action="attendance.sheet_imported").order_by(AuditLog.created_at.desc()).first()
    old = log.metadata_json["overwritten_records"][0]
    assert log.metadata_json["overwritten"] == 1 and old["employee_code"] == ca and old["was"]["late"] is True and old["was"]["check_in_label"] == "Head Office"
    assert old["was"]["check_out_at"] is not None                                    # the real check-out time survives in the log


def test_uploading_the_same_sheet_again_changes_nothing(client, dev, db, staff):
    (ca, ua) = staff["a"]
    sheet = _csv([_line(ca, "A", "PPPPP" + "." * 11)])
    _post(client, dev, sheet, apply=True)
    again = _post(client, dev, sheet, apply=True).json()
    assert again["will_create"] == 0 and again["will_overwrite"] == 0 and again["already_from_sheet"] == 5
    assert len(_records(db, ua)) == 5


def test_rows_are_matched_by_employee_id_and_the_rest_is_reported_not_guessed(client, dev, db, staff, make_user):
    (ca, ua) = staff["a"]
    other_code, _, other_id = make_user(role="accountant")
    twin1, _, _ = make_user()
    twin2, _, _ = make_user()
    for code in (twin1, twin2):
        db.query(User).filter_by(employee_code=code).update({"full_name": "Same Name"})
    db.commit()
    sheet = _csv([
        _line(ca.lower(), "whatever", "P" + "." * 15),                  # an ID in other letters still matches
        _line("NOBODY-1", "Ghost", "PPPPP" + "." * 11),                 # not in the CRM
        _line("ADMIN001", "Admin", "PPPPP" + "." * 11),                 # admins are not tracked
        _line("", "Same Name", "PPPPP" + "." * 11),                     # a name that two people share
        _line("", db.get(User, other_id).full_name, "PP" + "." * 14),   # a unique name with no ID is accepted
    ])
    out = _post(client, dev, sheet, apply=True).json()
    assert out["people"] == 2 and out["present_cells"] == 3
    assert [u["id"] for u in out["unmatched"]] == ["NOBODY-1"]
    assert len(out["skipped"]) == 2 and any("Not on the attendance list" in s["reason"] for s in out["skipped"]) and any("More than one person" in s["reason"] for s in out["skipped"])
    assert sorted(_records(db, ua)) == [1] and sorted(_records(db, other_id)) == [1, 2]


def test_unknown_letters_are_reported_and_leave_the_day_alone(client, dev, db, staff):
    (ca, ua) = staff["a"]
    out = _post(client, dev, _csv([_line(ca, "A", "PXHLP" + "." * 11)]), apply=True).json()
    assert out["ignored_cells"] == {"X": 1, "H": 1, "L": 1} and out["present_cells"] == 2
    assert sorted(_records(db, ua)) == [1, 5]


def test_only_past_days_are_written_so_a_sheet_can_never_block_todays_check_in(client, dev, db, staff):
    (ca, ua) = staff["a"]
    today = date.today()
    head = ["Employee ID", "Name", *[str(d) for d in range(1, 32)]]
    marks = ["P" if d in (1, today.day) else "" for d in range(1, 32)]
    csv = ("\n".join(",".join(r) for r in [head, [ca, "A", *marks]]) + "\n").encode()
    out = _post(client, dev, csv, apply=True, month=f"{today:%Y-%m}").json()
    if today.day == 1:
        pytest.skip("the 1st: nothing before today")
    assert out["future_days_skipped"] == 1 and out["present_cells"] == 1
    assert sorted(_records(db, ua)) == [1]


def test_the_day_and_month_views_show_present_with_no_invented_times(client, dev, db, staff):
    (ca, ua) = staff["a"]
    _post(client, dev, _csv([_line(ca, "A", "P" + "." * 15)]), apply=True)
    day = client.get(f"{API}/attendance/day", headers=dev, params={"date": MONTH.isoformat()}).json()
    row = next(r for r in day["rows"] if r["employee_code"] == ca)
    assert row["status"] == "PRESENT" and row["check_in_at"] is None and row["check_out_at"] is None and row["late"] is False and row["source"] == "sheet"
    assert day["summary"]["present"] >= 1
    month = client.get(f"{API}/attendance/month", headers=dev, params={"month": M}).json()
    mrow = next(r for r in month["rows"] if r["employee_code"] == ca)
    assert mrow["days_present"] == 1 and mrow["days"][MONTH.isoformat()]["status"] == "PRESENT" and mrow["late_days"] == 0


def test_a_sheet_day_is_not_passed_to_salary(db):
    month = MONTH
    sheet = {"status": "PRESENT", "source": "sheet", "check_in_at": None, "check_out_at": None, "minutes": 0, "late": False,
             "half_day": False, "location": {"status": "unknown", "label": "Attendance sheet"}}
    real = {"status": "CHECKED_OUT", "source": "checkin", "check_in_at": datetime(month.year, month.month, 2, 5, tzinfo=timezone.utc),
            "check_out_at": datetime(month.year, month.month, 2, 13, tzinfo=timezone.utc), "minutes": 480, "late": False, "half_day": False,
            "location": {"status": "office", "label": "Head Office"}}
    joined = month - timedelta(days=60)
    # find two weekdays that are not Sundays
    days = [d for d in range(1, 10) if date(month.year, month.month, d).weekday() != attendance_service.WEEKLY_OFF][:2]
    out = payroll_service.build_days(month, {date(month.year, month.month, days[0]).isoformat(): sheet, date(month.year, month.month, days[1]).isoformat(): real}, joined, {})
    by = {d["date"]: d for d in out}
    s_day, r_day = by[date(month.year, month.month, days[0]).isoformat()], by[date(month.year, month.month, days[1]).isoformat()]
    assert s_day["kind"] == "ABSENT" and s_day["counted"] == 0                       # only an admin's mark can pay it
    assert r_day["kind"] == "PRESENT" and r_day["counted"] == 1


def test_only_the_developer_can_upload_and_a_bad_sheet_is_refused(client, dev, admin, emp, staff):
    (ca, _) = staff["a"]
    sheet = _csv([_line(ca, "A", "P" + "." * 15)])
    assert _post(client, admin, sheet, apply=True).status_code == 403                # not even a full admin: the permission is the developer's
    assert _post(client, emp, sheet, apply=True).status_code == 403
    assert client.post(IMPORT, data={"month": M, "apply": "true"}, files={"file": ("x.csv", sheet, "text/csv")}).status_code == 401
    assert _post(client, dev, b"just,some,text\n1,2,3\n", apply=False).status_code == 422
    assert _post(client, dev, sheet, apply=False, name="x.pdf").status_code == 422
    assert _post(client, dev, sheet, apply=False, month="2026-13").status_code == 422


def test_an_excel_sheet_with_numeric_day_headers_works(client, dev, db, staff):
    import openpyxl

    (ca, ua) = staff["a"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Attendance sheet"])
    ws.append([])
    ws.append(["Employee ID", "Employee Name", *range(1, 17)])
    ws.append([ca, "A", *["P"] * 16])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post(IMPORT, headers=dev, data={"month": M, "apply": "true"},
                    files={"file": ("oct.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert len(_records(db, ua)) == 16 and r.json()["days_in_sheet"] == list(range(1, 17))
