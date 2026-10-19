"""Payroll: how a month is counted, the pay window, marking days, paying, and what the employee sees."""
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.attendance import AttendanceRecord
from app.models.organization import Organization
from app.models.payroll import PayrollPeriod
from app.models.user import User
from app.services import payroll_service

from .conftest import API, auth, login


def _last_month() -> date:
    t = date.today().replace(day=1)
    return date(t.year - (t.month == 1), (t.month - 2) % 12 + 1, 1)


def _dim(m: date) -> int:
    return calendar.monthrange(m.year, m.month)[1]


# ---------------------------------------------------------------- how a month is counted (pure)

def _entry(status="CHECKED_OUT", **kw):
    t = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    return {"status": status, "check_in_at": t, "check_out_at": t + timedelta(hours=8), "minutes": 480, "late": False,
            "location": {"label": "Office", "status": "office"}, **kw}


SEPT = date(2026, 9, 1)     # 30 days, Sundays on the 6th, 13th, 20th and 27th


def _present(days):
    return {date(2026, 9, d).isoformat(): _entry() for d in days}


def test_present_days_and_sundays_off_are_paid_and_the_rest_are_not():
    working = [d for d in range(1, 31) if date(2026, 9, d).weekday() != 6][:20]
    days = payroll_service.build_days(SEPT, _present(working), date(2026, 1, 1), {})
    paid, amount = payroll_service.compute_amount(Decimal("30000"), days, 30)
    assert paid == 24 and amount == Decimal("24000.00")           # 20 worked + 4 Sundays; 6 absent days unpaid
    assert {d["kind"] for d in days} == {"PRESENT", "OFF", "ABSENT"}


def test_marks_override_what_attendance_shows():
    working = [d for d in range(1, 31) if date(2026, 9, d).weekday() != 6]
    entries = _present(working)
    marks = {date(2026, 9, 1): "HALF", date(2026, 9, 2): "ABSENT", date(2026, 9, 6): "ABSENT", date(2026, 9, 7): "FULL"}
    days = payroll_service.build_days(SEPT, entries, date(2026, 1, 1), marks)
    paid, amount = payroll_service.compute_amount(Decimal("30000"), days, 30)
    assert paid == Decimal("30") - Decimal("0.5") - 1 - 1        # half day, a day marked absent, a Sunday marked absent
    assert amount == Decimal("27500.00")
    by_date = {d["date"]: d for d in days}
    assert by_date["2026-09-01"]["counted"] == 0.5 and by_date["2026-09-02"]["counted"] == 0


def test_leave_days_before_joining_and_rounding():
    entries = {
        "2026-09-01": {"status": "ON_LEAVE", "leave_type": "PAID", "half_day": False, "minutes": 0, "late": False, "check_in_at": None, "check_out_at": None, "location": {"label": "—"}},
        "2026-09-02": {"status": "ON_LEAVE", "leave_type": "UNPAID", "half_day": False, "minutes": 0, "late": False, "check_in_at": None, "check_out_at": None, "location": {"label": "—"}},
        "2026-09-03": {"status": "ON_LEAVE", "leave_type": "SICK", "half_day": True, "minutes": 0, "late": False, "check_in_at": None, "check_out_at": None, "location": {"label": "—"}},
    }
    days = payroll_service.build_days(SEPT, entries, date(2026, 9, 10), {})
    by_date = {d["date"]: d for d in days}
    assert [by_date[f"2026-09-0{i}"]["counted"] for i in (1, 2, 3)] == [1, 0, 0.5]
    assert by_date["2026-09-04"]["kind"] == "BEFORE_JOINING" and by_date["2026-09-06"]["kind"] == "BEFORE_JOINING"   # joined on the 10th
    assert by_date["2026-09-13"]["kind"] == "OFF" and by_date["2026-09-13"]["counted"] == 1                        # Sundays after joining are paid
    paid, amount = payroll_service.compute_amount(Decimal("10000"), days, 30)
    assert amount == (Decimal("10000") * paid / 30).quantize(Decimal("0.01"))      # e.g. 10000 / 30 x 7.5 -> 2500.00
    assert payroll_service.compute_amount(None, days, 30)[1] is None


# ---------------------------------------------------------------- the whole flow

@pytest.fixture()
def staff(client, make_user, db):
    """A Zepto employee who joined long ago and worked 15 weekdays of last month."""
    code, pw, uid = make_user("employee", platform="zepto")
    db.query(User).filter(User.id == uid).update({"created_at": datetime.now(timezone.utc) - timedelta(days=400)})
    org = db.query(Organization).filter_by(slug="veekay").one()
    month = _last_month()
    db.query(PayrollPeriod).filter_by(organization_id=org.id, month=month).delete()   # payout dates persist: start each test from the defaults
    db.commit()
    worked = [date(month.year, month.month, d) for d in range(1, _dim(month) + 1) if date(month.year, month.month, d).weekday() != 6][:15]
    for d in worked:
        t = datetime(d.year, d.month, d.day, 4, 30, tzinfo=timezone.utc)      # 10:00 IST
        db.add(AttendanceRecord(organization_id=org.id, user_id=uid, work_date=d, check_in_at=t, check_out_at=t + timedelta(hours=8), check_in_status="office", check_in_label="Office"))
    db.commit()
    sundays = sum(1 for d in range(1, _dim(month) + 1) if date(month.year, month.month, d).weekday() == 6)
    yield {"code": code, "pw": pw, "uid": uid, "month": month, "worked": worked, "paid_days": len(worked) + sundays, "dim": _dim(month)}
    db.query(PayrollPeriod).filter_by(organization_id=org.id, month=month).delete()   # also removes the payslips made in the test
    db.commit()


def _expected(salary, days, dim):
    return float((Decimal(str(salary)) * Decimal(str(days)) / dim).quantize(Decimal("0.01")))


def _open_window(monkeypatch, db, month):
    """Pretend today is the release date (the 15th of the month after `month`)."""
    rel = payroll_service._next_month(month).replace(day=15)
    monkeypatch.setattr(payroll_service, "_today", lambda: rel)
    return rel


def test_set_salary_review_mark_pay_and_the_employee_is_told(client, admin, staff, db, monkeypatch):
    m, uid = f"{staff['month']:%Y-%m}", staff["uid"]
    _open_window(monkeypatch, db, staff["month"])
    assert client.put(f"{API}/payroll/salaries/{uid}", headers=admin, json={"monthly_salary": 30000}).status_code == 200

    ov = client.get(f"{API}/payroll", params={"month": m}, headers=admin).json()
    row = next(r for r in ov["rows"] if r["user_id"] == str(uid))
    assert row["status"] == "READY" and row["paid_days"] == staff["paid_days"] and row["amount"] == _expected(30000, staff["paid_days"], staff["dim"])
    assert ov["period"]["state"] == "OPEN" and ov["period"]["release_date"].endswith("-15")

    d = client.get(f"{API}/payroll/employees/{uid}", params={"month": m}, headers=admin).json()
    assert len(d["days"]) == staff["dim"]
    worked_day = staff["worked"][0].isoformat()
    day = next(x for x in d["days"] if x["date"] == worked_day)
    assert day["kind"] == "PRESENT" and day["minutes"] == 480 and day["counted"] == 1 and day["mark"] is None

    # the admin looks at the timing and calls it a half day
    r = client.put(f"{API}/payroll/employees/{uid}/marks", params={"month": m}, headers=admin, json={"marks": [{"date": worked_day, "mark": "HALF"}]})
    assert r.status_code == 200 and r.json()["paid_days"] == staff["paid_days"] - 0.5
    assert r.json()["amount"] == _expected(30000, staff["paid_days"] - 0.5, staff["dim"])

    paid = client.post(f"{API}/payroll/employees/{uid}/pay", params={"month": m}, headers=admin)
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "PAID" and body["payslip"]["paid_by"] and body["amount"] == _expected(30000, staff["paid_days"] - 0.5, staff["dim"])

    # paid is final: no second payment, no more marks, and a new salary does not change the paid slip
    assert client.post(f"{API}/payroll/employees/{uid}/pay", params={"month": m}, headers=admin).status_code == 409
    assert client.put(f"{API}/payroll/employees/{uid}/marks", params={"month": m}, headers=admin, json={"marks": [{"date": worked_day, "mark": "FULL"}]}).status_code == 409
    client.put(f"{API}/payroll/salaries/{uid}", headers=admin, json={"monthly_salary": 99999})
    again = client.get(f"{API}/payroll/employees/{uid}", params={"month": m}, headers=admin).json()
    assert again["status"] == "PAID" and again["monthly_salary"] == 30000 and again["amount"] == body["amount"]

    # the employee: a notification, a popup until seen, and their own payslip with the day-wise breakdown
    h = auth(login(client, staff["code"], staff["pw"]).json()["access_token"])
    unseen = client.get(f"{API}/payroll/me/unseen", headers=h).json()["items"]
    assert len(unseen) == 1 and unseen[0]["amount"] == body["amount"] and unseen[0]["month"] == m
    feed = client.get(f"{API}/me/notifications", headers=h).json()["items"]
    assert any(n["kind"] == "salary" for n in feed)
    mine = client.get(f"{API}/payroll/me", headers=h).json()["items"]
    assert mine[0]["amount"] == body["amount"] and len(mine[0]["days"]) == staff["dim"]
    assert client.post(f"{API}/payroll/me/{unseen[0]['id']}/seen", headers=h).status_code == 200
    assert client.get(f"{API}/payroll/me/unseen", headers=h).json()["items"] == []
    assert client.get(f"{API}/payroll/me", headers=h).json()["items"][0]["seen"] is True


def test_paying_only_inside_the_window_and_the_dates_can_be_changed_by_hand(client, admin, staff, db, monkeypatch):
    m, uid = f"{staff['month']:%Y-%m}", staff["uid"]
    rel = payroll_service._next_month(staff["month"]).replace(day=15)
    client.put(f"{API}/payroll/salaries/{uid}", headers=admin, json={"monthly_salary": 30000})
    pay = lambda: client.post(f"{API}/payroll/employees/{uid}/pay", params={"month": m}, headers=admin)  # noqa: E731

    monkeypatch.setattr(payroll_service, "_today", lambda: rel - timedelta(days=1))
    assert client.get(f"{API}/payroll", params={"month": m}, headers=admin).json()["period"]["state"] == "UPCOMING"
    r = pay()
    assert r.status_code == 409 and "can be paid from" in r.json()["detail"]
    # salary released on the 20th instead: move the date, and the window follows
    new = rel + timedelta(days=5)
    r = client.put(f"{API}/payroll/period", params={"month": m}, headers=admin, json={"release_date": new.isoformat(), "window_days": 2})
    assert r.status_code == 200 and r.json()["closes_on"] == (new + timedelta(days=1)).isoformat()
    assert pay().status_code == 409

    monkeypatch.setattr(payroll_service, "_today", lambda: new + timedelta(days=2))     # one day after the window closed
    r = pay()
    assert r.status_code == 409 and "closed" in r.json()["detail"]
    client.put(f"{API}/payroll/period", params={"month": m}, headers=admin, json={"release_date": new.isoformat(), "window_days": 5})
    assert pay().status_code == 200


def test_period_dates_are_validated(client, admin, staff):
    m = f"{staff['month']:%Y-%m}"
    end = date(staff["month"].year, staff["month"].month, staff["dim"])
    put = lambda body, month=m: client.put(f"{API}/payroll/period", params={"month": month}, headers=admin, json=body)  # noqa: E731
    assert put({"release_date": end.isoformat(), "window_days": 3}).status_code == 422                       # not before the month has ended
    assert put({"release_date": (end + timedelta(days=1)).isoformat(), "window_days": 0}).status_code == 422
    assert put({"release_date": (end + timedelta(days=400)).isoformat(), "window_days": 3}).status_code == 422
    this = date.today().strftime("%Y-%m")
    assert put({"release_date": (end + timedelta(days=5)).isoformat(), "window_days": 3}, month=this).status_code == 422   # a month still running


def test_nothing_to_pay_without_a_salary_or_paid_days(client, admin, staff, make_user, db, monkeypatch):
    m = f"{staff['month']:%Y-%m}"
    _open_window(monkeypatch, db, staff["month"])
    r = client.post(f"{API}/payroll/employees/{staff['uid']}/pay", params={"month": m}, headers=admin)
    assert r.status_code == 422 and "salary" in r.json()["detail"]
    # someone who joined after the month and never checked in has no paid days
    _, _, late_uid = make_user("employee", platform="zepto")
    client.put(f"{API}/payroll/salaries/{late_uid}", headers=admin, json={"monthly_salary": 20000})
    r = client.post(f"{API}/payroll/employees/{late_uid}/pay", params={"month": m}, headers=admin)
    assert r.status_code == 422 and "nothing to pay" in r.json()["detail"]
    # ...until the admin marks the days they did work
    first = staff["month"]
    r = client.put(f"{API}/payroll/employees/{late_uid}/marks", params={"month": m}, headers=admin,
                   json={"marks": [{"date": (first + timedelta(days=i)).isoformat(), "mark": "FULL"} for i in range(10)]})
    assert r.status_code == 200 and r.json()["paid_days"] == 10
    assert client.post(f"{API}/payroll/employees/{late_uid}/pay", params={"month": m}, headers=admin).status_code == 200


def test_marks_outside_the_month_and_unknown_values_are_refused(client, admin, staff):
    m, uid = f"{staff['month']:%Y-%m}", staff["uid"]
    outside = (staff["month"] - timedelta(days=1)).isoformat()
    assert client.put(f"{API}/payroll/employees/{uid}/marks", params={"month": m}, headers=admin, json={"marks": [{"date": outside, "mark": "FULL"}]}).status_code == 422
    assert client.put(f"{API}/payroll/employees/{uid}/marks", params={"month": m}, headers=admin, json={"marks": [{"date": staff["worked"][0].isoformat(), "mark": "MAYBE"}]}).status_code == 422
    # a mark can be taken back
    day = staff["worked"][0].isoformat()
    client.put(f"{API}/payroll/employees/{uid}/marks", params={"month": m}, headers=admin, json={"marks": [{"date": day, "mark": "ABSENT"}]})
    r = client.put(f"{API}/payroll/employees/{uid}/marks", params={"month": m}, headers=admin, json={"marks": [{"date": day, "mark": None}]})
    assert next(x for x in r.json()["days"] if x["date"] == day)["mark"] is None


# ---------------------------------------------------------------- who may do what

def test_only_payroll_managers_see_or_change_salaries(client, admin, staff, emp, zepto_emp):
    m, uid = f"{staff['month']:%Y-%m}", staff["uid"]
    mine = auth(login(client, staff["code"], staff["pw"]).json()["access_token"])
    for h in (emp, zepto_emp, mine):
        assert client.get(f"{API}/payroll", params={"month": m}, headers=h).status_code == 403
        assert client.get(f"{API}/payroll/employees/{uid}", params={"month": m}, headers=h).status_code == 403
        assert client.put(f"{API}/payroll/salaries/{uid}", headers=h, json={"monthly_salary": 1}).status_code == 403
        assert client.put(f"{API}/payroll/period", params={"month": m}, headers=h, json={"release_date": "2030-01-01", "window_days": 3}).status_code == 403
        assert client.post(f"{API}/payroll/employees/{uid}/pay", params={"month": m}, headers=h).status_code == 403
        assert client.put(f"{API}/payroll/employees/{uid}/marks", params={"month": m}, headers=h, json={"marks": []}).status_code == 403
    assert client.get(f"{API}/payroll").status_code in (401, 403)


def test_an_employee_sees_only_their_own_payslips_and_cannot_clear_anyone_elses_popup(client, admin, staff, make_user, db, monkeypatch):
    m, uid = f"{staff['month']:%Y-%m}", staff["uid"]
    _open_window(monkeypatch, db, staff["month"])
    client.put(f"{API}/payroll/salaries/{uid}", headers=admin, json={"monthly_salary": 30000})
    slip = client.post(f"{API}/payroll/employees/{uid}/pay", params={"month": m}, headers=admin).json()["payslip"]["id"]
    code, pw, _ = make_user("employee", platform="zepto")
    other = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/payroll/me", headers=other).json()["items"] == []
    assert client.get(f"{API}/payroll/me/unseen", headers=other).json()["items"] == []
    assert client.post(f"{API}/payroll/me/{slip}/seen", headers=other).status_code == 404


def test_admins_are_not_on_the_payroll_and_the_permission_is_offered(client, admin):
    from .conftest import DEMO_PASSWORD  # noqa: F401
    ov = client.get(f"{API}/payroll", headers=admin).json()           # last month by default
    assert all(r["employee_code"] != "ADMIN001" for r in ov["rows"])
    admin_id = client.get(f"{API}/auth/me", headers=admin).json()["id"]
    assert client.put(f"{API}/payroll/salaries/{admin_id}", headers=admin, json={"monthly_salary": 1}).status_code == 422
    groups = client.get(f"{API}/permissions", headers=admin).json()
    assert {p["code"]: g["label"] for g in groups for p in g["permissions"]}.get("payroll.manage") == "Payroll"


def test_salaries_never_reach_the_activity_log(client, admin, staff):
    uid = staff["uid"]
    client.put(f"{API}/payroll/salaries/{uid}", headers=admin, json={"monthly_salary": 123456})
    log = client.get(f"{API}/activity", headers=admin, params={"page_size": 50}).json()
    items = log["items"] if isinstance(log, dict) else log
    assert any("payroll.salary_set" in str(i) for i in items)
    assert "123456" not in str(items)
