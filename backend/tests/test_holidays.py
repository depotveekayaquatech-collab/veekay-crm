"""Company holidays: never an absence, paid like a weekly off, not counted as leave. They have NO effect on entry counts or performance percentages."""
from datetime import date, timedelta

from app.services import leave_service, performance_service

from .conftest import API, auth, login


def _day_in_past_month():
    """A weekday (Mon-Sat) of the previous month, so no salary has been paid for it in a test database."""
    d = (date.today().replace(day=1) - timedelta(days=1)).replace(day=10)
    while d.weekday() == 6:
        d -= timedelta(days=1)
    return d


def test_only_the_right_people_set_holidays_and_it_can_be_undone(client, admin, emp):
    day = date(2031, 3, 5)
    assert client.post(f"{API}/attendance/holidays", headers=emp, json={"holiday_date": day.isoformat(), "name": "Test day"}).status_code == 403
    r = client.post(f"{API}/attendance/holidays", headers=admin, json={"holiday_date": day.isoformat(), "name": "  Holi  "})
    assert r.status_code == 200 and r.json()["name"] == "Holi", r.text
    renamed = client.post(f"{API}/attendance/holidays", headers=admin, json={"holiday_date": day.isoformat(), "name": "Holi (all offices)"})
    assert renamed.status_code == 200
    listed = client.get(f"{API}/attendance/holidays", params={"year": 2031}, headers=admin).json()
    assert [(h["date"], h["name"]) for h in listed] == [(day.isoformat(), "Holi (all offices)")]
    assert client.delete(f"{API}/attendance/holidays/{day.isoformat()}", headers=emp).status_code == 403
    assert client.delete(f"{API}/attendance/holidays/{day.isoformat()}", headers=admin).status_code == 204
    assert client.delete(f"{API}/attendance/holidays/{day.isoformat()}", headers=admin).status_code == 404
    assert client.post(f"{API}/attendance/holidays", headers=admin, json={"holiday_date": day.isoformat(), "name": "  "}).status_code == 422


def test_a_holiday_is_not_an_absence_not_a_leave_day_and_not_expected_from_anyone(client, db, admin, make_user):
    day = _day_in_past_month()
    code, pw, uid = make_user()
    month = f"{day:%Y-%m}"

    def me():
        rows = client.get(f"{API}/attendance/month", params={"month": month}, headers=admin).json()
        return next(r for r in rows["rows"] if str(r["user_id"]) == str(uid)), rows

    before, _ = me()
    assert client.post(f"{API}/attendance/holidays", headers=admin, json={"holiday_date": day.isoformat(), "name": "Founders day"}).status_code == 200
    try:
        after, data = me()
        assert data["holidays"][day.isoformat()] == "Founders day"
        assert after["absent_days"] <= before["absent_days"]                       # never one more absence (fewer, when the person had joined by then)
        # leave: a holiday uses no leave day
        assert leave_service.working_days(day, day, False, {day: "x"}) == 0
        assert leave_service.working_days(day, day + timedelta(days=1), False, {day: "x"}) == (0 if (day + timedelta(days=1)).weekday() == 6 else 1)
        # performance: NOT affected. A holiday is attendance's business: the day is still judged and an entry dated on it still counts
        first = day.replace(day=1)
        perf = client.get(f"{API}/orders/performance", params={"partner": "blinkit", "month": month}, headers=admin).json()
        assert day.isoformat() in {d["date"] for e in perf["employees"][:1] for d in e["daily"]}
        assert "holidays" not in perf
        assert performance_service.parse_month(month, date.today()) == first
        # payroll: the day counts as paid
        from app.services import payroll_service
        days = payroll_service.build_days(first, {}, first, {}, {day.isoformat(): "Founders day"})
        mine = next(x for x in days if x["date"] == day.isoformat())
        assert mine["kind"] == "OFF" and mine["counted"] == 1.0 and mine["holiday"] == "Founders day"
    finally:
        client.delete(f"{API}/attendance/holidays/{day.isoformat()}", headers=admin)
