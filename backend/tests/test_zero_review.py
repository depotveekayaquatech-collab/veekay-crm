"""Zero Review: the streak report, the weekly review, the monthly verification, who may do what, and the append-only log."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.services import zero_review_service as svc

from .conftest import API, auth, login
from .test_entry_verification import cast  # noqa: F401  (fixture: people and stores)

Z = f"{API}/zero-review"


def _put(db, store, day, count):
    org = db.query(Organization).filter_by(slug="veekay").one()
    db.add(OrderEntry(organization_id=org.id, store_id=store.id, order_date=day, bottle_count=count, source="employee"))
    db.commit()


def _row(resp, store):
    assert resp.status_code == 200, resp.text
    return next((r for r in resp.json()["items"] if r["store"]["id"] == str(store.id)), None)


def _range(days_back=6):
    t = svc.today()
    return t - timedelta(days=days_back), t - timedelta(days=1)


def _q(**extra):
    a, b = _range()
    return {"date_from": a.isoformat(), "date_to": b.isoformat(), **extra}


@pytest.fixture()
def seeded(cast, db):
    """s1: four zero days ending yesterday; s2: zeros broken by a 5; s3: nothing entered at all."""
    t = svc.today()
    for i in (1, 2, 3, 4):
        _put(db, cast["s1"], t - timedelta(days=i), 0)
    for i, n in ((1, 0), (2, 0), (3, 5), (4, 0), (5, 0), (6, 0)):
        _put(db, cast["s2"], t - timedelta(days=i), n)
    return cast


# ---------------------------------------------------------------------------- the report
def test_the_streak_report_finds_runs_unmarked_days_and_who_marked_them(client, seeded):
    r = client.get(f"{Z}/streaks", params=_q(), headers=seeded["ADM"])
    s1, s2, s3 = (_row(r, seeded[k]) for k in ("s1", "s2", "s3"))
    assert s1["longest"]["length"] == 4 and s1["longest"]["ongoing"] is True and s1["total_zero"] == 4 and s1["severity"] == "medium"
    assert s1["unmarked"] == 2                                          # the two earliest days of the six-day range
    assert s2["longest"]["length"] == 3 and s2["longest"]["ongoing"] is False and s2["last_nonzero"] == (svc.today() - timedelta(days=3)).isoformat()
    assert s3["longest"] is None and s3["unmarked"] == 6               # nothing entered is "unmarked", never a zero
    assert s1["status"] == "pending" and s1["marked_by"]["at"]

    only = client.get(f"{Z}/streaks", params=_q(n=4), headers=seeded["ADM"])
    assert _row(only, seeded["s1"]) and not _row(only, seeded["s2"])                       # N = 4 keeps the run of four only
    gaps = client.get(f"{Z}/streaks", params=_q(unmarked_ge=6), headers=seeded["ADM"])
    assert _row(gaps, seeded["s3"]) and not _row(gaps, seeded["s1"])                       # stores nobody reported on


def test_unmarked_days_can_break_be_ignored_or_count_as_zero(client, db, seeded):
    t = svc.today()
    store = seeded["s3"]
    for i, n in ((1, 0), (2, 0), (4, 0), (5, 0)):                      # days 3 and 6 are unmarked (6 is the first day of the range)
        _put(db, store, t - timedelta(days=i), n)
    length = lambda mode: _row(client.get(f"{Z}/streaks", params=_q(unmarked=mode), headers=seeded["ADM"]), store)["longest"]["length"]  # noqa: E731
    assert (length("break"), length("ignore"), length("count")) == (2, 4, 6)


def test_the_report_validates_its_inputs(client, seeded):
    for bad in ({"unmarked": "sometimes"}, {"n": -1}, {"review_status": "done"}, {"sort": "nope"}):
        assert client.get(f"{Z}/streaks", params=_q(**bad), headers=seeded["ADM"]).status_code == 422, bad
    assert client.get(f"{Z}/streaks", params={"date_from": "2026-02-10", "date_to": "2026-02-01"}, headers=seeded["ADM"]).status_code == 422
    assert client.get(f"{Z}/streaks", params={"date_from": "2026-01-01", "date_to": "2026-09-01"}, headers=seeded["ADM"]).status_code == 422     # over 93 days
    assert client.get(f"{Z}/streaks", params=_q(employee="not-a-uuid"), headers=seeded["ADM"]).status_code == 422
    assert client.get(f"{Z}/streaks", params=_q()).status_code == 401


def test_the_day_by_day_drawer_marks_zero_nonzero_unmarked_and_streak_days(client, seeded):
    r = client.get(f"{Z}/stores/{seeded['s2'].id}/days", params=_q(n=2), headers=seeded["ADM"])
    assert r.status_code == 200, r.text
    days = {d["date"]: d for d in r.json()["days"]}
    t = svc.today()
    assert days[(t - timedelta(days=3)).isoformat()]["kind"] == "nonzero" and days[(t - timedelta(days=3)).isoformat()]["count"] == 5
    assert days[(t - timedelta(days=1)).isoformat()]["kind"] == "zero" and days[(t - timedelta(days=1)).isoformat()]["in_streak"] is True
    assert client.get(f"{Z}/stores/{seeded['s3'].id}/days", params=_q(), headers=seeded["ADM"]).json()["unmarked"] == 6
    assert client.get(f"{Z}/stores/{uuid_zero()}/days", params=_q(), headers=seeded["ADM"]).status_code == 404


def uuid_zero():
    import uuid
    return uuid.UUID(int=0)


# ---------------------------------------------------------------------------- who sees what
def test_everyone_sees_only_their_scope_and_only_reviewers_can_review(client, seeded):
    a = client.get(f"{Z}/streaks", params=_q(), headers=seeded["A"])
    assert a.status_code == 200 and a.json()["can_review"] is False
    a_stores = {r["store"]["id"] for r in a.json()["items"]}
    assert str(seeded["s1"].id) in a_stores                              # an employee's own stores
    refused = client.post(f"{Z}/weekly/review", headers=seeded["A"], json={
        "week_start": svc.default_week().isoformat(), "store_ids": [str(seeded["s1"].id)], "reason": "other", "remark": "looked at it"})
    assert refused.status_code == 403
    assert client.get(f"{Z}/options", headers=seeded["L"]).json()["can_review"] is True
    assert client.get(f"{Z}/options", headers=seeded["ADM"]).json()["can_reopen"] is True
    assert client.get(f"{Z}/options", headers=seeded["R"]).json()["can_reopen"] is False


def test_a_partner_login_cannot_open_zero_review(client, make_user):
    code, pw, _ = make_user(role="partner", platform="blinkit")
    h = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{Z}/streaks", headers=h).status_code == 403


def test_a_team_lead_does_not_see_a_store_outside_their_scope(client, seeded, make_store):
    other = make_store(platform="zepto", region=None, state="Elsewhere")
    ids = {r["store"]["id"] for r in client.get(f"{Z}/streaks", params=_q(), headers=seeded["L"]).json()["items"]}
    assert str(other.id) not in ids
    assert client.get(f"{Z}/stores/{other.id}/days", params=_q(), headers=seeded["L"]).status_code == 404
    assert client.post(f"{Z}/weekly/review", headers=seeded["L"], json={
        "week_start": svc.default_week().isoformat(), "store_ids": [str(other.id)], "reason": "other", "remark": "not mine"}).status_code == 404


# ---------------------------------------------------------------------------- weekly review
def _week_with_zeros(db, store):
    start = svc.default_week()
    for i in range(4):
        _put(db, store, start + timedelta(days=i), 0)
    return start


def test_the_weekly_review_flags_reviews_and_logs_every_decision(client, db, cast):
    week = _week_with_zeros(db, cast["s1"])
    w = client.get(f"{Z}/weekly", params={"week_start": week.isoformat(), "threshold": 3}, headers=cast["L"])
    assert w.status_code == 200, w.text
    assert w.json()["week_end"] == (week + timedelta(days=5)).isoformat() and w.json()["is_current_default"] is True
    row = _row(w, cast["s1"])
    assert row["flagged"] and row["status"] == "pending" and w.json()["summary"]["complete"] is False
    before = w.json()["summary"]["pending"]

    body = {"week_start": week.isoformat(), "store_ids": [str(cast["s1"].id)], "threshold": 3, "reason": "store_closed", "remark": "Shop shut for repairs", "follow_up_date": (svc.today() + timedelta(days=3)).isoformat()}
    assert client.post(f"{Z}/weekly/review", headers=cast["L"], json={**body, "remark": "  "}).status_code == 422
    assert client.post(f"{Z}/weekly/review", headers=cast["L"], json={**body, "reason": "because"}).status_code == 422
    assert client.post(f"{Z}/weekly/review", headers=cast["L"], json={**body, "week_start": (week + timedelta(days=1)).isoformat()}).status_code == 422     # not a Monday
    assert client.post(f"{Z}/weekly/review", headers=cast["L"], json={**body, "follow_up_date": (svc.today() - timedelta(days=1)).isoformat()}).status_code == 422
    ok = client.post(f"{Z}/weekly/review", headers=cast["L"], json=body)
    assert ok.status_code == 200 and ok.json()["reviewed"] == 1

    again = client.get(f"{Z}/weekly", params={"week_start": week.isoformat(), "threshold": 3}, headers=cast["L"])
    done = _row(again, cast["s1"])
    assert done["status"] == "reviewed" and done["review"]["remark"] == "Shop shut for repairs" and done["review"]["by"]
    assert again.json()["summary"]["pending"] == before - 1

    # reviewing again keeps both decisions in the log; the current row holds the latest
    client.post(f"{Z}/weekly/review", headers=cast["R"], json={**body, "reason": "other", "remark": "Checked with the vendor"})
    h = client.get(f"{Z}/history", params={"status": "reviewed"}, headers=cast["ADM"]).json()
    mine = [i for i in h["items"] if i["store"] and i["store"]["id"] == str(cast["s1"].id)]
    assert [m["remark"] for m in mine][:2] == ["Checked with the vendor", "Shop shut for repairs"]
    assert mine[0]["longest_streak"] == 4 and mine[0]["threshold"] == 3 and mine[0]["by"]
    assert all(i["store"] for i in client.get(f"{Z}/history", headers=cast["A"]).json()["items"])       # an employee never sees month-level events


def test_a_bulk_review_marks_many_stores_with_one_remark(client, db, cast):
    week = _week_with_zeros(db, cast["s1"])
    for i in range(4):
        _put(db, cast["s2"], week + timedelta(days=i), 0)
    r = client.post(f"{Z}/weekly/review", headers=cast["ADM"], json={
        "week_start": week.isoformat(), "store_ids": [str(cast["s1"].id), str(cast["s2"].id)], "reason": "data_entry_missed", "remark": "Entered late by the team"})
    assert r.json()["reviewed"] == 2
    w = client.get(f"{Z}/weekly", params={"week_start": week.isoformat(), "threshold": 3, "review_status": "reviewed"}, headers=cast["ADM"])
    assert {cast["s1"].id.hex, cast["s2"].id.hex} <= {x["store"]["id"].replace("-", "") for x in w.json()["items"]}


def test_the_log_cannot_be_changed_or_deleted(client, db, cast):
    week = _week_with_zeros(db, cast["s1"])
    client.post(f"{Z}/weekly/review", headers=cast["ADM"], json={"week_start": week.isoformat(), "store_ids": [str(cast["s1"].id)], "reason": "other", "remark": "first look"})
    for sql in ("UPDATE zero_review_log SET remark = 'edited'", "DELETE FROM zero_review_log"):
        with pytest.raises(Exception, match="append-only"):
            db.execute(text(sql))
        db.rollback()


# ---------------------------------------------------------------------------- monthly verification
def test_the_month_window_and_grace_days():
    first = date(2026, 9, 1)
    assert svc.month_bounds(first) == (date(2026, 9, 1), date(2026, 9, 30))
    assert svc.month_bounds(date(2028, 2, 1))[1] == date(2028, 2, 29)                        # a leap February
    assert svc.previous_month(date(2026, 1, 3)) == date(2025, 12, 1)
    assert svc.default_week(date(2026, 10, 24)) == date(2026, 10, 19)                       # a Saturday: that same week
    assert svc.default_week(date(2026, 10, 26)) == date(2026, 10, 19)                       # Monday: the week that just closed
    assert svc.default_week(date(2026, 10, 25)) == date(2026, 10, 19)                       # Sunday


def test_a_closed_month_needs_an_administrator_to_reopen_it(client, db, cast):
    t = svc.today()
    first = svc.previous_month(t)
    closed = t > svc.month_bounds(first)[1] + timedelta(days=svc.GRACE_DAYS)
    _put(db, cast["s1"], first + timedelta(days=2), 0)
    m = client.get(f"{Z}/monthly", params={"month": f"{first:%Y-%m}"}, headers=cast["L"])
    assert m.status_code == 200 and m.json()["period"]["open"] is (not closed)
    body = {"month": f"{first:%Y-%m}", "store_ids": [str(cast["s1"].id)], "status": "verified", "remark": "All numbers match"}
    if closed:
        assert client.post(f"{Z}/monthly/verify", headers=cast["L"], json=body).status_code == 409
        assert client.post(f"{Z}/monthly/reopen", headers=cast["R"], json={"month": body["month"], "reason": "Late sheet"}).status_code == 403
        assert client.post(f"{Z}/monthly/reopen", headers=cast["ADM"], json={"month": body["month"], "reason": "Late sheet arrived"}).status_code == 200
        assert client.get(f"{Z}/monthly", params={"month": body["month"]}, headers=cast["L"]).json()["period"]["open"] is True
    ok = client.post(f"{Z}/monthly/verify", headers=cast["L"], json=body)
    assert ok.status_code == 200 and ok.json()["updated"] == 1, ok.text
    after = client.get(f"{Z}/monthly", params={"month": body["month"]}, headers=cast["L"]).json()
    mine = next(i for i in after["items"] if i["store"]["id"] == str(cast["s1"].id))
    assert mine["status"] == "verified"
    assert after["progress"]["overall"]["verified"] >= 1 and after["progress"]["by_region"]
    assert client.post(f"{Z}/monthly/verify", headers=cast["L"], json={**body, "remark": ""}).status_code == 422
    assert client.post(f"{Z}/monthly/verify", headers=cast["L"], json={**body, "status": "done"}).status_code == 422
    assert client.post(f"{Z}/monthly/verify", headers=cast["A"], json=body).status_code == 403
    flagged = client.post(f"{Z}/monthly/verify", headers=cast["R"], json={**body, "status": "flagged", "remark": "Orders look low"})
    assert flagged.status_code == 200
    assert next(i for i in client.get(f"{Z}/monthly", params={"month": body["month"]}, headers=cast["L"]).json()["items"] if i["store"]["id"] == str(cast["s1"].id))["status"] == "flagged"


def test_a_future_month_is_refused(client, cast):
    nxt = (svc.today().replace(day=1) + timedelta(days=40)).replace(day=1)
    assert client.get(f"{Z}/monthly", params={"month": f"{nxt:%Y-%m}"}, headers=cast["ADM"]).status_code == 422


# ---------------------------------------------------------------------------- badge and export
def test_the_badge_counts_what_is_waiting_and_is_zero_for_employees(client, db, cast):
    week = _week_with_zeros(db, cast["s1"])
    lead = client.get(f"{Z}/badge", headers=cast["L"]).json()
    assert lead["weekly"] >= 1 and lead["pending"] >= lead["weekly"]
    assert client.get(f"{Z}/badge", headers=cast["A"]).json()["pending"] == 0
    client.post(f"{Z}/weekly/review", headers=cast["L"], json={"week_start": week.isoformat(), "store_ids": [str(cast["s1"].id)], "reason": "other", "remark": "seen"})
    assert client.get(f"{Z}/badge", headers=cast["L"]).json()["weekly"] == lead["weekly"] - 1


def test_the_export_is_a_csv_of_the_filtered_rows(client, seeded):
    r = client.get(f"{Z}/export", params=_q(n=4), headers=seeded["ADM"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.lstrip("﻿").splitlines()
    assert lines[0].startswith("Store,Outlet ID") and "Unmarked days" in lines[0] and "Zeros marked by" in lines[0] and "Review status" in lines[0]
    assert any(seeded["s1"].name in l for l in lines[1:]) and not any(seeded["s2"].name in l for l in lines[1:])


def test_the_existing_pages_still_answer(client, admin):
    for path in ("/orders/pending", "/entries/summary", "/attendance/month"):
        assert client.get(f"{API}{path}", headers=admin).status_code == 200, path


def test_the_history_can_be_filtered_by_reviewer_name_and_period(client, db, cast):
    week = _week_with_zeros(db, cast["s1"])
    client.post(f"{Z}/weekly/review", headers=cast["L"], json={"week_start": week.isoformat(), "store_ids": [str(cast["s1"].id)], "reason": "other", "remark": "by the lead"})
    everyone = client.get(f"{Z}/history", headers=cast["ADM"]).json()["total"]
    assert everyone >= 1
    lead_name = client.get(f"{Z}/history", headers=cast["ADM"]).json()["items"][0]["by"]
    assert client.get(f"{Z}/history", params={"reviewer": lead_name}, headers=cast["ADM"]).json()["total"] >= 1
    assert client.get(f"{Z}/history", params={"reviewer": "nobody-by-this-name"}, headers=cast["ADM"]).json()["total"] == 0
    assert client.get(f"{Z}/history", params={"period_from": (week + timedelta(days=30)).isoformat()}, headers=cast["ADM"]).json()["total"] == 0
