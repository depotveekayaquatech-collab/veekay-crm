"""Performance and attendance are scoped by level: an employee sees only themselves, a Team Lead only their team, an administrator everyone.
A day's chip can be opened to list the stores still pending on that day (what holds the percentage down), for anyone in the caller's view."""
from datetime import date, timedelta

from app.models.user import User

from .conftest import API, auth, login, plant_entry
from .test_entry_hierarchy import _role

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
GRANTS = ("orders.view", "orders.mark")


def _as(client, code, pw="Pass@123"):
    return auth(login(client, code, pw).json()["access_token"])


def _cast(client, db, make_user, extra=()):
    """A (reports to the Team Lead), B (does not), L (Team Lead) - all Blinkit / North field employees."""
    ca, pa, ua = make_user(platform="blinkit", region="NORTH", grants=GRANTS + extra)
    cb, pb, ub = make_user(platform="blinkit", region="NORTH", grants=GRANTS + extra)
    cl, pl, ul = make_user(platform="blinkit", region="NORTH", grants=GRANTS + extra)
    _role(db, ul, "team_lead")
    db.query(User).filter(User.id == ua).update({"reports_to_user_id": ul})
    db.commit()
    return {"A": _as(client, ca, pa), "B": _as(client, cb, pb), "L": _as(client, cl, pl), "ids": {"A": ua, "B": ub, "L": ul}}


def _listed(client, who, **params):
    r = client.get(f"{API}/orders/performance", params={"partner": "blinkit", **params}, headers=who)
    assert r.status_code == 200, r.text
    return r.json()


def test_an_employee_sees_only_themselves_a_team_lead_their_team_and_an_admin_everyone(client, db, admin, make_user, make_store):
    make_store(region="NORTH")
    c = _cast(client, db, make_user)
    ids = {k: str(v) for k, v in c["ids"].items()}

    mine = _listed(client, c["B"])
    assert mine["view"] == "self" and [e["employee_id"] for e in mine["employees"]] == [ids["B"]]
    team = _listed(client, c["L"])
    assert team["view"] == "team" and {e["employee_id"] for e in team["employees"]} == {ids["L"], ids["A"]}
    assert team["summary"]["stores"] >= 1
    everyone = _listed(client, admin)
    assert everyone["view"] == "all" and {ids["A"], ids["B"], ids["L"]} <= {e["employee_id"] for e in everyone["employees"]}


def test_a_team_lead_with_the_daily_overview_still_sees_only_their_team(client, db, make_user, make_store):
    make_store(region="NORTH")
    c = _cast(client, db, make_user, extra=("orders.overview",))
    got = {e["employee_id"] for e in _listed(client, c["L"])["employees"]}
    assert got == {str(c["ids"]["L"]), str(c["ids"]["A"])}


def test_the_pending_stores_of_a_day_are_the_stores_without_an_entry_and_only_for_people_in_view(client, db, admin, make_user, make_store):
    done, left = make_store(region="NORTH"), make_store(region="NORTH")
    c = _cast(client, db, make_user)
    plant_entry(db, done, YESTERDAY, 9, creator=c["ids"]["B"])          # a colleague's entry covers the store for A too
    params = {"partner": "blinkit", "date": YESTERDAY.isoformat()}

    r = client.get(f"{API}/orders/performance/pending", params=params, headers=c["A"])                 # default: the caller
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {s["store_id"]: s for s in body["stores"]}
    assert str(left.id) in by_id and YESTERDAY.isoformat() not in by_id.get(str(done.id), {}).get("missing_dates", [])      # marked that day: not missing on it
    assert by_id[str(left.id)]["can_open"] is True and body["month_open"] is True and body["employee_id"] == str(c["ids"]["A"])
    # every missing store-day from the 1st up to that day is listed: exactly what keeps the percentage below 100 as of that day
    daily = _listed(client, c["A"], month=YESTERDAY.strftime("%Y-%m"))["employees"][0]["daily"]
    assert body["missing_total"] == sum(d["expected"] - d["done"] for d in daily if d["date"] <= YESTERDAY.isoformat())
    assert body["missing_total"] == sum(s["missing_days"] for s in body["stores"]) and YESTERDAY.isoformat() in by_id[str(left.id)]["missing_dates"]

    ask = lambda who, emp: client.get(f"{API}/orders/performance/pending", params={**params, "employee_id": str(c["ids"][emp])}, headers=who).status_code
    assert ask(c["A"], "B") == 403 and ask(c["B"], "A") == 403               # an employee only asks about themselves
    assert ask(c["L"], "A") == 200 and ask(c["L"], "B") == 403               # a Team Lead about their team
    assert ask(admin, "B") == 200
    as_admin = client.get(f"{API}/orders/performance/pending", params={**params, "employee_id": str(c["ids"]["B"])}, headers=admin).json()
    assert all(s["can_open"] for s in as_admin["stores"])
    for bad in (TODAY, TODAY + timedelta(days=1)):                            # a day counts once it is over
        assert client.get(f"{API}/orders/performance/pending", params={**params, "date": bad.isoformat()}, headers=c["A"]).status_code == 422


def test_a_day_in_a_closed_month_lists_its_pending_stores_but_says_the_month_is_closed_for_an_employee(client, db, admin, make_user, make_store):
    make_store(region="NORTH")
    c = _cast(client, db, make_user)
    old = TODAY.replace(day=1) - timedelta(days=45)
    params = {"partner": "blinkit", "date": old.isoformat()}
    assert client.get(f"{API}/orders/performance/pending", params=params, headers=c["A"]).json()["month_open"] is False
    assert client.get(f"{API}/orders/performance/pending", params={**params, "employee_id": str(c["ids"]["A"])}, headers=admin).json()["month_open"] is True


def test_a_team_lead_sees_only_their_teams_attendance_and_leave(client, db, admin, make_user, make_store):
    c = _cast(client, db, make_user, extra=("attendance.view", "leave.review"))
    ids = {str(v) for v in c["ids"].values()}
    month = TODAY.strftime("%Y-%m")

    seen = {r["user_id"] for r in client.get(f"{API}/attendance/month", params={"month": month}, headers=c["L"]).json()["rows"]}
    assert seen == {str(c["ids"]["L"]), str(c["ids"]["A"])}
    brief = {r["user_id"] for r in client.get(f"{API}/attendance/month-brief", params={"month": month}, headers=c["L"]).json()["rows"]}
    assert brief == seen
    today = {r["user_id"] for r in client.get(f"{API}/attendance/day", headers=c["L"]).json()["rows"]}
    assert today == seen
    assert ids <= {r["user_id"] for r in client.get(f"{API}/attendance/month", params={"month": month}, headers=admin).json()["rows"]}

    from app.services.attendance_service import WEEKLY_OFF

    leave_day = next(d for d in (TODAY + timedelta(days=i) for i in range(3, 12)) if d.weekday() != WEEKLY_OFF).isoformat()
    ask = {}
    for who in ("A", "B"):
        r = client.post(f"{API}/attendance/leaves", headers=c[who], json={"leave_type": "CASUAL", "start_date": leave_day, "end_date": leave_day, "reason": "test"})
        assert r.status_code == 201, r.text
        ask[who] = r.json()["id"]
    listed = {i["id"] for i in client.get(f"{API}/attendance/leaves", headers=c["L"]).json()["items"]}
    assert ask["A"] in listed and ask["B"] not in listed
    assert client.post(f"{API}/attendance/leaves/{ask['B']}/review", headers=c["L"], json={"approve": True}).status_code == 404
    assert client.post(f"{API}/attendance/leaves/{ask['A']}/review", headers=c["L"], json={"approve": True}).status_code == 200
