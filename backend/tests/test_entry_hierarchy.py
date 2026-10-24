"""The four-level hierarchy: ownership, scope, the append-only audit trail, Store Audit search, idempotent marking and role management.

Entry Contributor (employee) / Team Lead / Entry Reviewer / Administrator. The rules live in core.entry_access; the history is written by database
triggers (migration 0052), so these tests also go to the database directly to prove it cannot be rewritten.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models.audit_log import AuditLog  # noqa: F401  (keeps the metadata complete)
from app.models.order_entry import OrderEntry
from app.models.role import Role
from app.models.user import User, UserRole

from .conftest import API, auth, login, plant_entry

TODAY = date.today()
SEARCH = f"{API}/entries/search"


# --------------------------------------------------------------------------- helpers
def _as(client, code, pw="Pass@123"):
    r = login(client, code, pw)
    assert r.status_code == 200, r.text
    return auth(r.json()["access_token"])


def _role(db, uid, code):
    db.add(UserRole(user_id=uid, role_id=db.query(Role).filter_by(code=code).one().id))
    db.commit()


def _staff(make_user, db, role="employee", **kw):
    """A field employee on Blinkit / North (sees the North test stores)."""
    code, pw, uid = make_user(role=role, platform="blinkit", region="NORTH", **kw)
    return code, pw, uid


def _mark(client, who, store, n=10, day=None, **headers):
    return client.post(f"{API}/orders/mark", headers={**who, **headers},
                       json={"store_id": str(store.id), "order_date": (day or TODAY).isoformat(), "bottle_count": n})


def _entry(db, store, day=None) -> OrderEntry:
    db.expire_all()
    return db.query(OrderEntry).filter_by(store_id=store.id, order_date=day or TODAY).one()


def _events(db, entry_id):
    return db.execute(text("SELECT event_type, actor_user_id, actor_role, actor_name, old_values, new_values, reason, comment, entry_version "
                           "FROM order_entry_events WHERE entry_id = :e ORDER BY seq"), {"e": entry_id}).mappings().all()


@pytest.fixture()
def cast(client, db, make_user, make_store):
    """Two contributors (A reports to the Team Lead, B does not), a Team Lead, a reviewer and an admin, plus two stores."""
    ca, pa, ua = _staff(make_user, db)
    cb, pb, ub = _staff(make_user, db)
    cl, pl, ul = _staff(make_user, db)
    cr, pr, ur = make_user(role="entry_reviewer")
    _role(db, ul, "team_lead")
    db.query(User).filter(User.id == ua).update({"reports_to_user_id": ul})
    db.commit()
    s1, s2 = make_store(code="HX-1"), make_store(code="HX-2")
    return {
        "A": _as(client, ca, pa), "B": _as(client, cb, pb), "L": _as(client, cl, pl), "R": _as(client, cr, pr), "ADM": _as(client, "ADMIN001"),
        "ids": {"A": ua, "B": ub, "L": ul, "R": ur}, "codes": {"A": ca, "B": cb, "L": cl, "R": cr}, "s1": s1, "s2": s2,
    }


# =========================================================================== A. role permissions
def test_an_entry_is_stamped_with_the_authenticated_creator_and_the_servers_clock(client, db, cast):
    r = _mark(client, cast["A"], cast["s1"], 12, **{"X-Client-Time": "2001-01-01T00:00:00+00:00"})
    assert r.status_code == 200, r.text
    e = _entry(db, cast["s1"])
    assert e.created_by_user_id == cast["ids"]["A"] and e.creator_verified is True and e.created_by_role == "entry_contributor"
    assert e.created_by_code == cast["codes"]["A"] and e.version == 1 and e.created_via in ("android_app", "web_crm", "unknown")
    assert abs((datetime.now(timezone.utc) - e.created_at).total_seconds()) < 60                  # the server's clock...
    assert e.client_submitted_at.year == 2001                                                      # ...and the phone's, kept apart for diagnosis only


def test_a_creator_sent_by_the_client_is_ignored(client, db, cast):
    r = client.post(f"{API}/orders/mark", headers=cast["A"], json={
        "store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 5,
        "created_by_user_id": str(cast["ids"]["B"]), "creator_id": str(cast["ids"]["B"]), "employee_id": str(cast["ids"]["B"]), "role": "administrator"})
    assert r.status_code == 200
    assert _entry(db, cast["s1"]).created_by_user_id == cast["ids"]["A"]


def test_a_contributor_sees_only_their_own_entries(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["B"], cast["s2"], 22)
    mine = client.get(f"{API}/orders/my-entries", headers=cast["A"]).json()["items"]
    assert {i["store_code"]: i["bottles"] for i in mine} == {"HX-1": 11}
    assert all(i["saved_on_server"] and i["entry_id"] and i["version"] == 1 for i in mine)

    cal_b = client.get(f"{API}/orders/calendar", headers=cast["B"], params={"store_id": str(cast["s1"].id)}).json()["days"]
    day = next(d for d in cal_b if d["date"] == TODAY.isoformat())
    assert day["marked"] is True and day["masked"] is True and day["mine"] is False
    assert day["count"] is None and day["entered_by"] is None and day["entered_at"] is None and day["entry_id"] is None

    stores = {s["external_code"]: s for s in client.get(f"{API}/orders/my-stores", headers=cast["B"]).json()}
    assert stores["HX-1"]["today_marked"] is True and stores["HX-1"]["today_count"] is None and stores["HX-1"]["month_bottles"] == 0
    assert stores["HX-2"]["today_count"] == 22 and stores["HX-2"]["month_bottles"] == 22
    # and the day cannot be marked a second time by someone else (no information beyond "already marked")
    again = _mark(client, cast["B"], cast["s1"], 99)
    assert again.status_code == 409 and "11" not in again.text


def test_the_calendar_follows_the_same_scope_as_the_audit_pages(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)                                       # A reports to the Team Lead; B does not
    def day(who):
        days = client.get(f"{API}/orders/calendar", headers=who, params={"store_id": str(cast["s1"].id)}).json()["days"]
        return next(d for d in days if d["date"] == TODAY.isoformat())
    assert day(cast["A"])["count"] == 11 and day(cast["A"])["mine"] is True
    assert day(cast["L"])["count"] == 11 and day(cast["L"])["masked"] is False         # the Team Lead sees their team's number
    b = day(cast["B"])
    assert b["marked"] is True and b["masked"] is True and b["count"] is None           # a colleague outside the team sees only "marked"


def _day(client, who, store, day=None):
    days = client.get(f"{API}/orders/calendar", headers=who, params={"store_id": str(store.id)}).json()["days"]
    return next(d for d in days if d["date"] == (day or TODAY).isoformat())


def test_a_contributor_sees_what_someone_more_senior_entered_but_cannot_touch_it(client, db, cast, dev):
    # the administrator and the developer each enter a number; the Team Lead marks too
    assert client.patch(f"{API}/orders/entry", headers=cast["ADM"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 15}).status_code == 200
    csv = "\n".join([f"Outlet ID,Outlet Name,{TODAY}", f"HX-2,{cast['s2'].name},33", ""]).encode()
    assert client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")}).status_code == 200

    for who in ("A", "B"):                                                          # any contributor, on either store
        adm_day, dev_day = _day(client, cast[who], cast["s1"]), _day(client, cast[who], cast["s2"])
        assert adm_day["count"] == 15 and adm_day["by_higher"] is True and adm_day["masked"] is False and adm_day["mine"] is False
        assert dev_day["count"] == 33 and dev_day["by_higher"] is True and dev_day["masked"] is False
        assert adm_day["entry_id"] is None and adm_day["version"] is None            # the audit details stay with the supervising levels
        stores = {s["external_code"]: s for s in client.get(f"{API}/orders/my-stores", headers=cast[who]).json()}
        assert stores["HX-1"]["today_count"] == 15 and stores["HX-2"]["today_count"] == 33
        assert stores["HX-1"]["month_bottles"] == 15 and stores["HX-2"]["month_bottles"] == 33
        inv = {i["external_code"]: i for i in client.get(f"{API}/orders/inventory", headers=cast[who]).json()["items"]}
        assert inv["HX-1"]["month_bottles"] == 15 and inv["HX-2"]["month_bottles"] == 33
        # ...but they are read-only
        assert _mark(client, cast[who], cast["s1"], 99).status_code == 409
        assert client.patch(f"{API}/orders/my-entry", headers=cast[who], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 1}).status_code == 403
        assert client.patch(f"{API}/orders/entry", headers=cast[who], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 1}).status_code == 403
        assert client.patch(f"{API}/entries/{adm_day.get('entry_id') or _entry(db, cast['s1']).id}", headers=cast[who], json={"bottle_count": 1, "reason": "no right", "expected_version": 2}).status_code == 403
    assert _entry(db, cast["s1"]).bottle_count == 15 and _entry(db, cast["s2"]).bottle_count == 33
    assert not client.get(f"{API}/orders/my-entries", headers=cast["A"]).json()["items"]      # "My entries" stays the things YOU entered


def test_a_peer_stays_hidden_but_a_team_leads_number_is_visible_to_contributors(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)                      # a contributor
    _mark(client, cast["L"], cast["s2"], 30)                      # the Team Lead
    b_sees_a, b_sees_lead = _day(client, cast["B"], cast["s1"]), _day(client, cast["B"], cast["s2"])
    assert b_sees_a["masked"] is True and b_sees_a["count"] is None and b_sees_a["by_higher"] is False        # same level: hidden
    assert b_sees_lead["count"] == 30 and b_sees_lead["by_higher"] is True and b_sees_lead["masked"] is False  # more senior: visible
    assert _day(client, cast["A"], cast["s2"])["count"] == 30
    # a Team Lead does not see a more senior person's number hidden from them either
    assert client.patch(f"{API}/orders/entry", headers=cast["ADM"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 12}).status_code == 200
    assert _day(client, cast["L"], cast["s1"])["count"] == 12
    # once a more senior person corrects a number, it is theirs to the others: B can now see the corrected 12
    assert _day(client, cast["B"], cast["s1"])["count"] == 12 and _day(client, cast["B"], cast["s1"])["by_higher"] is True


def test_a_days_cash_adjustment_stays_hidden_from_everyone_below_the_developer(client, db, cast, dev):
    plant_entry(db, cast["s1"], TODAY, 8, creator=cast["ids"]["A"], cash_adjustment=5)         # A's 8, with a developer's 5 on top
    plant_entry(db, cast["s2"], TODAY, 0, creator=None, source="admin", cash_adjustment=7)      # a day holding only an adjustment
    b1, b2 = _day(client, cast["B"], cast["s1"]), _day(client, cast["B"], cast["s2"])
    assert b1["marked"] and b1["masked"] and b1["count"] is None                               # A's number is still A's
    assert b2["marked"] and b2["masked"] and b2["count"] is None                               # never shows the adjustment


def test_old_entries_last_set_by_an_administrator_are_visible_old_employee_ones_are_not(client, db, cast):
    from datetime import timedelta
    yesterday = TODAY - timedelta(days=1)
    if yesterday.month != TODAY.month:
        pytest.skip("needs two days in the month")
    plant_entry(db, cast["s1"], TODAY, 40, creator=None, source="admin", marked_by=cast["ids"]["L"])        # legacy: an admin's number
    plant_entry(db, cast["s1"], yesterday, 41, creator=None, source="employee", marked_by=cast["ids"]["A"])  # legacy: an employee's number
    assert _day(client, cast["B"], cast["s1"])["count"] == 40 and _day(client, cast["B"], cast["s1"])["by_higher"] is True
    old = _day(client, cast["B"], cast["s1"], yesterday)
    assert old["masked"] is True and old["count"] is None


def test_the_vendors_page_never_totals_a_colleagues_numbers_for_an_employee(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    inv_b = {i["external_code"]: i for i in client.get(f"{API}/orders/inventory", headers=cast["B"]).json()["items"]}
    assert inv_b["HX-1"]["month_bottles"] == 0 and inv_b["HX-1"]["marked_today"] is True          # B sees that it is done, not A's number
    inv_a = {i["external_code"]: i for i in client.get(f"{API}/orders/inventory", headers=cast["A"]).json()["items"]}
    assert inv_a["HX-1"]["month_bottles"] == 11
    inv_adm = {i["external_code"]: i for i in client.get(f"{API}/orders/inventory", headers=cast["ADM"]).json()["items"]}
    assert inv_adm["HX-1"]["month_bottles"] == 11


def test_a_contributor_cannot_edit_delete_or_read_history(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    fix = client.patch(f"{API}/orders/my-entry", headers=cast["A"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 3})
    clear = client.patch(f"{API}/orders/my-entry", headers=cast["A"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat()})
    assert fix.status_code == clear.status_code == 403
    assert client.get(f"{API}/orders/entry", headers=cast["A"]).status_code in (404, 405)
    assert client.patch(f"{API}/orders/entry", headers=cast["A"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 1}).status_code == 403
    for call in (lambda: client.get(f"{API}/entries/{e.id}", headers=cast["A"]),
                 lambda: client.patch(f"{API}/entries/{e.id}", headers=cast["A"], json={"bottle_count": 1, "reason": "no reason", "expected_version": 1}),
                 lambda: client.post(f"{API}/entries/{e.id}/review", headers=cast["A"], json={"action": "reviewed"}),
                 lambda: client.get(SEARCH, headers=cast["A"]), lambda: client.get(f"{API}/entries/attempts", headers=cast["A"])):
        assert call().status_code == 403
    assert _entry(db, cast["s1"]).bottle_count == 11 and _entry(db, cast["s1"]).version == 1


def test_unauthenticated_requests_are_rejected(client, cast):
    for url in (SEARCH, f"{API}/entries/attempts", f"{API}/entries/security-events", f"{API}/orders/my-entries"):
        assert client.get(url).status_code == 401


def test_a_team_lead_sees_and_corrects_their_team_only(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)                      # A reports to the lead
    _mark(client, cast["B"], cast["s2"], 22)                      # B does not
    seen = client.get(SEARCH, headers=cast["L"]).json()
    assert seen["level"] == "team_lead" and [i["store"]["outlet_id"] for i in seen["items"]] == ["HX-1"]
    a_entry, b_entry = _entry(db, cast["s1"]), _entry(db, cast["s2"])

    ok = client.patch(f"{API}/entries/{a_entry.id}", headers=cast["L"], json={"bottle_count": 14, "reason": "Typed 11, delivery note says 14", "expected_version": 1})
    assert ok.status_code == 200, ok.text
    e = _entry(db, cast["s1"])
    assert e.bottle_count == 14 and e.version == 2 and e.created_by_user_id == cast["ids"]["A"]            # the creator never changes
    assert e.last_modified_by_user_id == cast["ids"]["L"] and e.last_modified_by_role == "team_lead" and e.last_modified_at is not None
    created, edited, verified = _events(db, a_entry.id)
    assert verified["event_type"] == "VERIFIED_L2" and verified["actor_user_id"] == cast["ids"]["L"]          # a Team Lead's correction counts as their verification
    assert created["event_type"] == "CREATED" and created["actor_user_id"] == cast["ids"]["A"] and created["new_values"]["bottle_count"] == 11
    assert edited["event_type"] == "EDITED" and edited["actor_user_id"] == cast["ids"]["L"] and edited["actor_role"] == "team_lead"
    assert edited["old_values"] == {"bottle_count": 11, "source": "employee"} and edited["new_values"] == {"bottle_count": 14, "source": "admin"}
    assert edited["reason"].startswith("Typed 11")                                                           # what changed, what it was, and why

    out = client.patch(f"{API}/entries/{b_entry.id}", headers=cast["L"], json={"bottle_count": 1, "reason": "trying someone else's", "expected_version": 1})
    assert out.status_code == 404 and _entry(db, cast["s2"]).bottle_count == 22                              # outside the team: looks like it does not exist
    assert client.get(f"{API}/entries/{b_entry.id}", headers=cast["L"]).status_code == 404
    assert db.execute(text("SELECT count(*) FROM security_events WHERE event_type='entry_access_denied' AND actor_user_id=:u"),
                      {"u": cast["ids"]["L"]}).scalar() >= 2                                              # and the attempts are on record


def test_a_correction_needs_a_reason_and_the_current_version(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    url = f"{API}/entries/{e.id}"
    assert client.patch(url, headers=cast["L"], json={"bottle_count": 12, "reason": "", "expected_version": 1}).status_code == 422
    assert client.patch(url, headers=cast["L"], json={"bottle_count": 12, "reason": "abc", "expected_version": 1}).status_code == 422
    assert client.patch(url, headers=cast["L"], json={"bottle_count": 11, "reason": "same number", "expected_version": 1}).status_code == 422
    assert client.patch(url, headers=cast["L"], json={"bottle_count": 12, "reason": "valid reason", "expected_version": 1, "created_by_user_id": str(cast["ids"]["L"])}).status_code == 422
    assert client.patch(url, headers=cast["L"], json={"bottle_count": 12, "reason": "first correction", "expected_version": 1}).status_code == 200
    again = client.patch(url, headers=cast["L"], json={"bottle_count": 13, "reason": "a second edit", "expected_version": 2})
    assert again.status_code == 409 and "already verified" in again.json()["detail"]                          # a Team Lead acts only on Submitted entries
    stale = client.patch(url, headers=cast["ADM"], json={"bottle_count": 13, "reason": "a stale second edit", "expected_version": 1})
    assert stale.status_code == 409 and stale.json()["detail"]["current_version"] == 2
    assert _entry(db, cast["s1"]).bottle_count == 12 and len(_events(db, e.id)) == 3                           # nothing partial, nothing extra (created, edited, verified)


def test_a_team_lead_entry_belongs_to_the_team_lead(client, db, cast):
    _mark(client, cast["L"], cast["s2"], 30)
    e = _entry(db, cast["s2"])
    assert e.created_by_user_id == cast["ids"]["L"] and e.created_by_role == "team_lead"
    first = _events(db, e.id)[0]
    assert first["actor_user_id"] == cast["ids"]["L"] and first["actor_role"] == "team_lead"
    assert not any(i["creator"]["id"] == cast["ids"]["A"] for i in client.get(SEARCH, headers=cast["ADM"], params={"entry_id": str(e.id)}).json()["items"])
    assert [i["creator"]["role"] for i in client.get(SEARCH, headers=cast["L"]).json()["items"]] == ["team_lead"]       # and it is in their own scope


def test_a_reviewer_audits_everything_and_a_review_mark_changes_nothing(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["B"], cast["s2"], 22)
    e = _entry(db, cast["s1"])
    got = client.get(SEARCH, headers=cast["R"]).json()
    assert got["level"] == "entry_reviewer" and {i["store"]["outlet_id"] for i in got["items"]} >= {"HX-1", "HX-2"}
    assert client.patch(f"{API}/orders/entry", headers=cast["R"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 1}).status_code == 403
    assert client.post(f"{API}/entries/{e.id}/review", headers=cast["R"], json={"action": "flagged"}).status_code == 422            # a flag needs the reason
    flagged = client.post(f"{API}/entries/{e.id}/review", headers=cast["R"], json={"action": "flagged", "comment": "A usually delivers 20 here"})
    assert flagged.status_code == 200 and flagged.json()["entry"]["review"]["status"] == "flagged"
    after = _entry(db, cast["s1"])
    assert after.bottle_count == 11 and after.version == 1 and after.created_by_user_id == cast["ids"]["A"]      # a review never touches value, creator or version
    last = _events(db, e.id)[-1]
    assert last["event_type"] == "FLAGGED" and last["actor_role"] == "entry_reviewer" and last["comment"] == "A usually delivers 20 here"
    only_flagged = client.get(SEARCH, headers=cast["R"], params={"flagged": "true"}).json()["items"]
    assert [i["entry_id"] for i in only_flagged] == [str(e.id)]
    assert client.get(f"{API}/entries/security-events", headers=cast["R"]).status_code == 200


def test_the_administrator_sees_everything_and_corrections_keep_the_creator(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    r = client.patch(f"{API}/orders/entry", headers=cast["ADM"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat(), "bottle_count": 15})
    assert r.status_code == 200
    after = _entry(db, cast["s1"])
    assert after.created_by_user_id == cast["ids"]["A"] and after.bottle_count == 15 and after.version == 2 and after.last_modified_by_role == "administrator"
    t = client.get(f"{API}/entries/{e.id}", headers=cast["ADM"]).json()
    assert t["chain_ok"] is True and [x["type"] for x in t["events"]] == ["CREATED", "EDITED", "REVIEWED_L3"]
    assert t["entry"]["creator"]["name"] and t["entry"]["last_modified"]["role"] == "administrator"
    cal = client.get(f"{API}/orders/calendar", headers=cast["ADM"], params={"store_id": str(cast["s1"].id)}).json()["days"]
    d = next(x for x in cal if x["date"] == TODAY.isoformat())
    assert d["entry_id"] == str(e.id) and d["version"] == 2 and d["creator_verified"] is True


# =========================================================================== role management
def test_role_changes_apply_on_the_very_next_request_and_are_recorded(client, db, cast):
    _mark(client, cast["B"], cast["s2"], 5)
    assert client.get(SEARCH, headers=cast["B"]).status_code == 403
    r = client.put(f"{API}/employees/{cast['ids']['B']}/entry-role", headers=cast["ADM"], json={"level": "team_lead"})
    assert r.status_code == 200 and r.json()["level"] == "team_lead"
    assert client.get(SEARCH, headers=cast["B"]).status_code == 200                                      # same token, no re-login
    # make A report to B, and the lead sees A's entries
    _mark(client, cast["A"], cast["s1"], 7)
    assert client.put(f"{API}/employees/{cast['ids']['A']}/entry-role", headers=cast["ADM"], json={"reports_to_id": str(cast["ids"]["B"])}).status_code == 200
    assert {i["store"]["outlet_id"] for i in client.get(SEARCH, headers=cast["B"]).json()["items"]} == {"HX-1", "HX-2"}
    back = client.put(f"{API}/employees/{cast['ids']['B']}/entry-role", headers=cast["ADM"], json={"level": "entry_contributor"})
    assert back.status_code == 200 and client.get(SEARCH, headers=cast["B"]).status_code == 403
    db.expire_all()
    assert db.get(User, cast["ids"]["A"]).reports_to_user_id is None                                      # a former lead leads nobody
    assert db.execute(text("SELECT count(*) FROM security_events WHERE event_type='role_change' AND actor_user_id IS NOT NULL")).scalar() >= 3


def test_nobody_can_promote_themselves_or_be_promoted_by_a_non_admin(client, db, cast):
    me = cast["ids"]["B"]
    assert client.put(f"{API}/employees/{me}/entry-role", headers=cast["B"], json={"level": "entry_reviewer"}).status_code == 403
    assert client.put(f"{API}/employees/{me}/entry-role", headers=cast["L"], json={"level": "entry_reviewer"}).status_code == 403
    assert client.put(f"{API}/employees/{cast['ids']['L']}/entry-role", headers=cast["ADM"], json={"level": "entry_reviewer"}).status_code == 200
    adm_id = db.query(User).filter_by(employee_code="ADMIN001").one().id
    assert client.put(f"{API}/employees/{adm_id}/entry-role", headers=cast["ADM"], json={"level": "team_lead"}).status_code in (403, 404, 422)
    assert client.put(f"{API}/employees/{me}/entry-role", headers=cast["ADM"], json={"level": "super_boss"}).status_code == 422
    assert client.put(f"{API}/employees/{me}/entry-role", headers=cast["ADM"], json={"reports_to_id": str(cast["ids"]["A"])}).status_code == 422   # A is not a Team Lead


def test_new_accounts_start_with_the_least_privilege(client, db, make_user):
    code, pw, uid = make_user(role="employee", platform="blinkit", region="NORTH")
    roles = {r for (r,) in db.execute(text("SELECT r.code FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE ur.user_id = :u"), {"u": uid})}
    assert roles == {"employee"} and db.get(User, uid).reports_to_user_id is None
    assert client.get(SEARCH, headers=_as(client, code, pw)).status_code == 403


# =========================================================================== B. audit trail
def test_the_history_cannot_be_changed_or_deleted_by_anyone(db, client, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    for sql in ("UPDATE order_entry_events SET reason = 'rewritten' WHERE entry_id = :e", "DELETE FROM order_entry_events WHERE entry_id = :e",
                "TRUNCATE order_entry_events", "UPDATE security_events SET event_type = 'x'", "DELETE FROM security_events"):
        with pytest.raises(Exception, match="append-only"):
            db.execute(text(sql), {"e": e.id})
        db.rollback()
    with pytest.raises(Exception, match="can never be changed"):                                          # nor the creator or the creation time of the entry
        db.execute(text("UPDATE order_entries SET created_by_user_id = :u WHERE id = :e"), {"u": cast["ids"]["B"], "e": e.id})
    db.rollback()
    with pytest.raises(Exception, match="can never be changed"):
        db.execute(text("UPDATE order_entries SET created_at = now() - interval '5 days' WHERE id = :e"), {"e": e.id})
    db.rollback()
    assert _entry(db, cast["s1"]).created_by_user_id == cast["ids"]["A"]


def test_a_tampered_history_is_detected(db, client, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    assert db.execute(text("SELECT entry_verify_chain(:e)"), {"e": e.id}).scalar() is True
    # even a superuser-style rewrite (triggers disabled) leaves a broken chain
    db.execute(text("ALTER TABLE order_entry_events DISABLE TRIGGER trg_append_only"))
    db.execute(text("UPDATE order_entry_events SET new_values = jsonb_set(new_values, '{bottle_count}', '99') WHERE entry_id = :e"), {"e": e.id})
    try:
        assert db.execute(text("SELECT entry_verify_chain(:e)"), {"e": e.id}).scalar() is False
    finally:
        db.rollback()                                                                                       # DDL + the rewrite are undone with the transaction
    assert db.execute(text("SELECT entry_verify_chain(:e)"), {"e": e.id}).scalar() is True


def test_every_change_writes_its_own_event_and_the_original_survives(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    created_at = e.created_at
    for n, count in enumerate((12, 13, 14), start=1):
        r = client.patch(f"{API}/entries/{e.id}", headers=cast["ADM"], json={"bottle_count": count, "reason": f"correction number {n}", "expected_version": n})
        assert r.status_code == 200, r.text
    ev = _events(db, e.id)
    # the first change also finalised the entry (an administrator's number is the Reviewed one), so it carries one extra REVIEWED_L3 event
    assert [x["event_type"] for x in ev] == ["CREATED", "EDITED", "REVIEWED_L3", "EDITED", "EDITED"]
    ev = [x for x in ev if x["event_type"] in ("CREATED", "EDITED")]
    assert [x["entry_version"] for x in ev] == [1, 2, 3, 4]
    assert [x["new_values"]["bottle_count"] for x in ev] == [11, 12, 13, 14] and ev[0]["new_values"]["bottle_count"] == 11
    assert [x["reason"] for x in ev[1:]] == ["correction number 1", "correction number 2", "correction number 3"]
    now = _entry(db, cast["s1"])
    assert now.created_at == created_at and now.created_by_user_id == cast["ids"]["A"]                     # the original creation never moves
    assert now.last_modified_at > created_at


def test_a_cleared_entry_is_found_through_its_history(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    assert client.patch(f"{API}/orders/entry", headers=cast["ADM"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat()}).status_code == 200
    gone = client.get(SEARCH, headers=cast["ADM"], params={"deleted": "true", "store_id": str(cast["s1"].id)}).json()["items"]
    assert [g["entry_id"] for g in gone] == [str(e.id)] and gone[0]["employee_count"] == 11 and gone[0]["removed_by"]["code"] == "ADMIN001"
    t = client.get(f"{API}/entries/{e.id}", headers=cast["ADM"]).json()
    assert t["removed"] is True and [x["type"] for x in t["events"]] == ["CREATED", "CLEARED"]
    assert client.get(f"{API}/entries/{e.id}", headers=cast["L"]).status_code == 200                       # A is on L's team: removals of their entries stay visible
    assert client.get(f"{API}/entries/{e.id}", headers=cast["B"]).status_code == 403


def test_a_restored_entry_keeps_its_original_creator(client, db, cast, dev):
    _mark(client, cast["A"], cast["s1"], 11)
    old_id = _entry(db, cast["s1"]).id
    client.patch(f"{API}/orders/entry", headers=cast["ADM"], json={"store_id": str(cast["s1"].id), "order_date": TODAY.isoformat()})
    assert db.query(OrderEntry).filter_by(store_id=cast["s1"].id).count() == 0
    r = client.post(f"{API}/developer/order-audit/deleted/restore", headers=dev, json={"start": TODAY.isoformat(), "end": TODAY.isoformat(), "dry_run": False})
    assert r.status_code == 200 and r.json()["restored"] >= 1, r.text
    back = _entry(db, cast["s1"])
    assert back.created_by_user_id == cast["ids"]["A"] and back.creator_verified is True and back.created_by_code == cast["codes"]["A"]
    types = [e["event_type"] for e in _events(db, back.id)]
    assert types[-1] == "RESTORED" and back.id != old_id                       # a new row, with a RESTORED event naming who put it back


# =========================================================================== legacy records
def test_legacy_entries_are_unverified_and_never_given_to_whoever_opens_the_store(client, db, cast):
    legacy = plant_entry(db, cast["s1"], TODAY, 40, creator=None, marked_by=cast["ids"]["A"])             # written with no known actor
    assert legacy.creator_verified is False and legacy.created_by_user_id is None and legacy.created_via == "no_actor"
    assert not client.get(f"{API}/orders/my-entries", headers=cast["A"]).json()["items"]                   # not "theirs", even though the old marker says A
    day = next(d for d in client.get(f"{API}/orders/calendar", headers=cast["A"], params={"store_id": str(cast["s1"].id)}).json()["days"] if d["date"] == TODAY.isoformat())
    assert day["marked"] and day["masked"] and day["count"] is None
    found = client.get(SEARCH, headers=cast["ADM"], params={"unverified": "true", "store_id": str(cast["s1"].id)}).json()["items"]
    assert len(found) == 1 and found[0]["creator"]["verified"] is False and found[0]["creator"]["last_recorded_marker"]
    assert "unverified_creator" in found[0]["flags"]
    assert client.get(SEARCH, headers=cast["L"], params={"unverified": "true"}).json()["items"] == []        # a Team Lead cannot claim it either
    assert client.patch(f"{API}/entries/{legacy.id}", headers=cast["L"], json={"bottle_count": 1, "reason": "legacy fix", "expected_version": 1}).status_code == 404
    ok = client.patch(f"{API}/entries/{legacy.id}", headers=cast["ADM"], json={"bottle_count": 41, "reason": "verified against the delivery note", "expected_version": 1})
    assert ok.status_code == 200
    assert _entry(db, cast["s1"]).creator_verified is False and _entry(db, cast["s1"]).created_by_user_id is None   # editing never invents a creator


# =========================================================================== C. synchronisation
def test_a_retry_after_a_lost_response_creates_nothing_twice(client, db, cast):
    key = {"Idempotency-Key": "retry-test-0001-abcdef"}
    first = _mark(client, cast["A"], cast["s1"], 11, **key)
    retry = _mark(client, cast["A"], cast["s1"], 11, **key)                                                # the phone never got the first answer
    assert first.status_code == retry.status_code == 200
    assert db.query(OrderEntry).filter_by(store_id=cast["s1"].id).count() == 1 and len(_events(db, _entry(db, cast["s1"]).id)) == 1
    again_no_key = _mark(client, cast["A"], cast["s1"], 11)                                                # an old app without keys: same number from same person
    assert again_no_key.status_code == 200
    different = _mark(client, cast["A"], cast["s1"], 12)
    assert different.status_code == 409 and _entry(db, cast["s1"]).bottle_count == 11
    assert _mark(client, cast["B"], cast["s1"], 11).status_code == 409                                      # another person with the same number is NOT a retry
    rows = db.execute(text("SELECT outcome FROM order_mark_journal WHERE store_id = :s ORDER BY created_at"), {"s": cast["s1"].id}).scalars().all()
    assert rows == ["saved", "duplicate", "duplicate", "rejected", "rejected"]


def test_mark_many_confirms_every_saved_day_from_the_server(client, db, cast):
    yesterday = TODAY - timedelta(days=1)
    if yesterday.month != TODAY.month:
        pytest.skip("needs two days in the month")
    body = {"store_id": str(cast["s1"].id), "entries": [{"order_date": TODAY.isoformat(), "bottle_count": 5}, {"order_date": yesterday.isoformat(), "bottle_count": 6}]}
    key = {"Idempotency-Key": "batch-key-0001-abcdef"}
    r = client.post(f"{API}/orders/mark-many", headers={**cast["A"], **key}, json=body).json()
    assert r["saved"] == 2 and all(x["status"] == "saved" and x["entry_id"] and x["version"] == 1 and x["saved_at"] for x in r["results"])
    retry = client.post(f"{API}/orders/mark-many", headers={**cast["A"], **key}, json=body).json()
    assert retry["saved"] == 2 and all(x["status"] == "already_saved" for x in retry["results"])
    assert db.query(OrderEntry).filter_by(store_id=cast["s1"].id).count() == 2
    other = client.post(f"{API}/orders/mark-many", headers=cast["B"], json=body).json()
    assert other["saved"] == 0 and other["failed"] == 2 and all(x["status"] is None and x["entry_id"] is None for x in other["results"])


def test_refused_attempts_are_on_record_for_the_auditors(client, db, cast, make_store):
    elsewhere = make_store(code="HX-WEST", region="WEST")                      # a store that is not in A's region
    r = client.post(f"{API}/orders/mark", headers=cast["A"], json={"store_id": str(elsewhere.id), "order_date": TODAY.isoformat(), "bottle_count": 3})
    assert r.status_code == 403 and db.query(OrderEntry).filter_by(store_id=elsewhere.id).count() == 0
    attempts = client.get(f"{API}/entries/attempts", headers=cast["R"], params={"outcome": "rejected", "store_id": str(elsewhere.id)}).json()
    assert attempts["total"] == 1
    item = attempts["items"][0]
    assert item["user_code"] == cast["codes"]["A"] and "not assigned" in item["reason"] and item["bottle_count"] == 3 and item["store_name"]


def test_two_people_on_one_store_never_mix_their_entries(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 10)
    _mark(client, cast["B"], cast["s2"], 20)
    assert _entry(db, cast["s1"]).created_by_user_id == cast["ids"]["A"] and _entry(db, cast["s2"]).created_by_user_id == cast["ids"]["B"]
    a_items = {i["store_code"] for i in client.get(f"{API}/orders/my-entries", headers=cast["A"]).json()["items"]}
    b_items = {i["store_code"] for i in client.get(f"{API}/orders/my-entries", headers=cast["B"]).json()["items"]}
    assert a_items == {"HX-1"} and b_items == {"HX-2"}


def test_entries_written_by_a_sheet_import_name_the_person_who_ran_it(client, db, cast, dev):
    csv = (f"Outlet ID,Outlet Name,{TODAY}" + "\n" + f"HX-2,{cast['s2'].name},33" + "\n").encode()
    r = client.post(f"{API}/orders/import", headers=dev, data={"platform": "blinkit"}, files={"file": ("o.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    e = _entry(db, cast["s2"])
    assert e.created_via.startswith("order_sheet_import") and e.creator_verified is True and e.created_by_role == "developer" and e.bottle_count == 33


# =========================================================================== D. search
def test_store_audit_filters_combine_and_paginate_without_gaps(client, db, cast, make_store):
    stores = [make_store(code=f"SA-{i}") for i in range(7)]
    for i, s in enumerate(stores):
        _mark(client, cast["A"] if i % 2 == 0 else cast["B"], s, i + 1)
    ids = []
    for page in (1, 2, 3):
        got = client.get(SEARCH, headers=cast["R"], params={"store": "SA-", "page": page, "page_size": 3}).json()
        assert got["total"] == 7
        ids += [i["entry_id"] for i in got["items"]]
    assert len(ids) == 7 == len(set(ids))                                                                   # no duplicates, no gaps
    by_a = client.get(SEARCH, headers=cast["R"], params={"store": "sa-", "creator": cast["codes"]["A"].lower()}).json()
    assert by_a["total"] == 4 and all(i["creator"]["code"] == cast["codes"]["A"] for i in by_a["items"])
    one = client.get(SEARCH, headers=cast["R"], params={"outlet_id": "sa-3"}).json()
    assert [i["store"]["outlet_id"] for i in one["items"]] == ["SA-3"]
    by_id = client.get(SEARCH, headers=cast["R"], params={"entry_id": one["items"][0]["entry_id"]}).json()
    assert by_id["total"] == 1
    by_store_id = client.get(SEARCH, headers=cast["R"], params={"store_id": str(stores[4].id)}).json()
    assert by_store_id["total"] == 1
    combined = client.get(SEARCH, headers=cast["R"], params={"store": "SA-", "creator": cast["codes"]["B"], "edited": "false", "date_from": TODAY.isoformat(), "date_to": TODAY.isoformat()}).json()
    assert combined["total"] == 3
    assert client.get(SEARCH, headers=cast["R"], params={"store": "SA-", "edited": "true"}).json()["total"] == 0
    r = client.get(SEARCH, headers=cast["R"], params={"store": "100%_"}).json()                              # wildcard characters are literal
    assert r["total"] == 0


def test_searching_by_team_lead_and_modifier_and_time_window(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["B"], cast["s2"], 22)
    e = _entry(db, cast["s1"])
    client.patch(f"{API}/entries/{e.id}", headers=cast["L"], json={"bottle_count": 13, "reason": "lead correction", "expected_version": 1})
    by_lead = client.get(SEARCH, headers=cast["R"], params={"team_lead": cast["codes"]["L"]}).json()["items"]
    assert {i["store"]["outlet_id"] for i in by_lead} == {"HX-1"}                                           # A's entry (on L's team) edited by L; B is not
    by_mod = client.get(SEARCH, headers=cast["R"], params={"modifier": cast["codes"]["L"]}).json()["items"]
    assert [i["store"]["outlet_id"] for i in by_mod] == ["HX-1"] and by_mod[0]["last_modified"]["role"] == "team_lead"
    # Indian-time windows: today's entries are inside "today 00:00 IST .. tomorrow 00:00 IST", never inside last week
    now_ist = datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    inside = client.get(SEARCH, headers=cast["R"], params={"store": "HX-", "created_from": (now_ist - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S"),
                                                           "created_to": (now_ist + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")}).json()
    assert inside["total"] == 2
    week_ago = (now_ist - timedelta(days=8)).strftime("%Y-%m-%d")
    assert client.get(SEARCH, headers=cast["R"], params={"store": "HX-", "created_to": week_ago}).json()["total"] == 0
    assert client.get(SEARCH, headers=cast["R"], params={"created_from": "not-a-date"}).status_code == 422


def test_a_filter_can_never_widen_a_users_scope(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["B"], cast["s2"], 22)
    lead = client.get(SEARCH, headers=cast["L"], params={"creator": cast["codes"]["B"], "store_id": str(cast["s2"].id)}).json()
    assert lead["total"] == 0
    lead2 = client.get(SEARCH, headers=cast["L"], params={"team_lead": "ADMIN001"}).json()                  # asking about someone else's team returns nothing extra
    assert lead2["items"] == []
    own = client.get(SEARCH, headers=cast["L"]).json()["items"]
    assert {i["creator"]["id"] for i in own} == {str(cast["ids"]["A"])}
    assert client.get(f"{API}/entries/attempts", headers=cast["L"]).status_code == 403                       # the cross-team diagnostics are not a Team Lead's
    assert client.get(f"{API}/entries/security-events", headers=cast["L"]).status_code == 403


def test_a_platform_scoped_reviewer_sees_only_their_platform(client, db, cast, make_store, make_user):
    zs = make_store(code="ZP-1", platform="zepto", region=None, state="Karnataka")
    code, pw, uid = make_user(role="entry_reviewer")
    db.query(User).filter(User.id == uid).update({"platform_organization_id": cast["s1"].partner_organization_id})
    db.commit()
    zepto = _as(client, "EMP002")
    assert _mark(client, zepto, zs, 9).status_code == 200
    _mark(client, cast["A"], cast["s1"], 11)
    codes = {i["store"]["outlet_id"] for i in client.get(SEARCH, headers=_as(client, code, pw)).json()["items"]}
    assert "HX-1" in codes and "ZP-1" not in codes                                                         # Blinkit reviewer: no Zepto entries
    assert [i["store"]["outlet_id"] for i in client.get(SEARCH, headers=_as(client, code, pw), params={"store": "ZP-1"}).json()["items"]] == []
    assert [i["store"]["outlet_id"] for i in client.get(SEARCH, headers=cast["ADM"], params={"store": "ZP-1"}).json()["items"]] == ["ZP-1"]   # the administrator sees both
