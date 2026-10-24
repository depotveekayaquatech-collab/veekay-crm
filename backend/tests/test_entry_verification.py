"""The verification workflow: Submitted (L1) -> Verified by Team Lead (L2) -> Reviewed by Reviewer (L3), the Reviewer shortcut and requests, filters,
final-value reports, what Level 1 is told, the Level 3 / 4 tools and the rules the database itself enforces (migration 0053)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.models.order_entry import OrderEntry
from app.models.role import Role
from app.models.user import User, UserRole

from .conftest import API, auth, login

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


def _mark(client, who, store, n=10, day=None):
    r = client.post(f"{API}/orders/mark", headers=who, json={"store_id": str(store.id), "order_date": (day or TODAY).isoformat(), "bottle_count": n})
    assert r.status_code == 200, r.text
    return r


def _entry(db, store, day=None) -> OrderEntry:
    db.expire_all()
    return db.query(OrderEntry).filter_by(store_id=store.id, order_date=day or TODAY).one()


def _events(db, entry_id):
    return db.execute(text("SELECT event_type, actor_role, old_values, new_values, comment, reason FROM order_entry_events WHERE entry_id=:e ORDER BY seq"),
                      {"e": entry_id}).mappings().all()


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return {i["entry_id"] for i in resp.json()["items"]}


def _post(client, who, entry, path, body=None):
    return client.post(f"{API}/entries/{entry.id}/{path}", headers=who, json=body or {})


@pytest.fixture()
def cast(client, db, make_user, make_store):
    """Contributors A and C report to Team Lead L; B reports to nobody. R is a Reviewer, ADM an administrator. Three stores (own state, so reports are exact)."""
    people = {}
    for key in ("A", "B", "C", "L"):
        code, pw, uid = make_user(role="employee", platform="blinkit", region="NORTH")
        people[key] = (code, pw, uid)
    cr, pr, ur = make_user(role="entry_reviewer")
    _role(db, people["L"][2], "team_lead")
    for key in ("A", "C"):
        db.query(User).filter(User.id == people[key][2]).update({"reports_to_user_id": people["L"][2]})
    db.commit()
    stores = [make_store(code=f"VF-{i}", state="Testland-V") for i in (1, 2, 3)]
    out = {k: _as(client, c, p) for k, (c, p, _u) in people.items()}
    out.update({"R": _as(client, cr, pr), "ADM": _as(client, "ADMIN001"), "ids": {k: u for k, (_c, _p, u) in people.items()} | {"R": ur},
                "codes": {k: c for k, (c, _p, _u) in people.items()} | {"R": cr}, "names": {}, "stores": stores, "s1": stores[0], "s2": stores[1], "s3": stores[2]})
    return out


def _report_total(client, admin, day=TODAY):
    r = client.get(f"{API}/orders/report?start={day}&end={day}&group_by=partner&state=testland-v", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()["total_bottles"]


# =========================================================================== acceptance 1: the whole flow, and reports show the final value only
def test_submitted_then_verified_then_reviewed_and_the_report_shows_only_the_final_value(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    assert e.verification_status == "submitted"

    # L1 submitted: the Team Lead sees it as pending; it is not ready for the Reviewer yet
    assert str(e.id) in _ids(client.get(SEARCH, headers=cast["L"], params={"verification": "pending_l2"}))
    assert str(e.id) not in _ids(client.get(SEARCH, headers=cast["R"], params={"verification": "verified_l2"}))
    assert client.get(SEARCH, headers=cast["L"], params={"verification": "pending_l2"}).json()["items"][0]["actions"]["verify"] is True
    assert _report_total(client, cast["ADM"]) == 11                       # nobody has touched it: the L1 value

    # L2 corrects (and so verifies) it: 11 -> 12
    r = client.patch(f"{API}/entries/{e.id}", headers=cast["L"], json={"bottle_count": 12, "reason": "delivery note says 12", "expected_version": 1})
    assert r.status_code == 200, r.text
    assert r.json()["entry"]["verification"]["status"] == "verified_l2" and r.json()["entry"]["verification"]["verified_by"]["name"]
    assert _report_total(client, cast["ADM"]) == 12                       # the Verified value
    assert str(e.id) not in _ids(client.get(SEARCH, headers=cast["L"], params={"verification": "pending_l2"}))
    assert str(e.id) in _ids(client.get(SEARCH, headers=cast["R"], params={"verification": "verified_l2"}))      # ready for the Reviewer
    again = client.patch(f"{API}/entries/{e.id}", headers=cast["L"], json={"bottle_count": 13, "reason": "second thoughts", "expected_version": 2})
    assert again.status_code == 409                                       # the Team Lead acts only on Submitted entries

    # L3 edits using their own knowledge: 12 -> 14, final
    r = client.patch(f"{API}/entries/{e.id}", headers=cast["R"], json={"bottle_count": 14, "reason": "checked with the vendor", "expected_version": 2})
    assert r.status_code == 200, r.text
    assert r.json()["entry"]["verification"]["status"] == "reviewed_l3" and r.json()["entry"]["version"] == 3
    assert str(e.id) in _ids(client.get(SEARCH, headers=cast["R"], params={"verification": "reviewed_l3"}))
    assert _report_total(client, cast["ADM"]) == 14                       # the Reviewed value only: 11 and 12 appear in no report

    # ... while the history keeps every version, with who / role / reason
    ev = _events(db, e.id)
    assert [x["event_type"] for x in ev] == ["CREATED", "EDITED", "VERIFIED_L2", "EDITED", "REVIEWED_L3"]
    edits = [(x["old_values"]["bottle_count"], x["new_values"]["bottle_count"], x["actor_role"]) for x in ev if x["event_type"] == "EDITED"]
    assert edits == [(11, 12, "team_lead"), (12, 14, "entry_reviewer")]


def test_a_team_lead_can_verify_an_entry_as_it_is(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    r = _post(client, cast["L"], e, "verify", {"comment": "matches the delivery note"})
    assert r.status_code == 200 and r.json()["entry"]["verification"]["status"] == "verified_l2"
    after = _entry(db, cast["s1"])
    assert after.bottle_count == 11 and after.version == 1 and after.verified_by_user_id == cast["ids"]["L"] and after.verified_at is not None
    assert _events(db, e.id)[-1]["event_type"] == "VERIFIED_L2" and _events(db, e.id)[-1]["comment"] == "matches the delivery note"
    assert _post(client, cast["L"], e, "verify").status_code == 409                                    # already verified
    assert _post(client, cast["A"], e, "verify").status_code == 403                                    # Level 1 cannot
    assert _post(client, cast["R"], e, "verify").status_code == 403                                    # verification is the Team Lead's step


def test_a_team_lead_cannot_verify_outside_their_team(client, db, cast):
    _mark(client, cast["B"], cast["s2"], 5)                                                            # B reports to nobody
    e = _entry(db, cast["s2"])
    assert _post(client, cast["L"], e, "verify").status_code == 404
    assert _entry(db, cast["s2"]).verification_status == "submitted"


# =========================================================================== acceptance 2: the Reviewer shortcut
def test_a_reviewer_can_review_a_pending_entry_directly_and_the_team_lead_is_not_asked(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    got = client.get(SEARCH, headers=cast["R"], params={"entry_id": str(e.id)}).json()["items"][0]
    assert got["verification"]["status"] == "submitted" and got["actions"]["review"] and got["actions"]["request_check"]      # the two choices
    r = _post(client, cast["R"], e, "review", {"action": "reviewed", "comment": "checked on site"})
    assert r.status_code == 200 and r.json()["entry"]["verification"]["status"] == "reviewed_l3"
    after = _entry(db, cast["s1"])
    assert after.verification_status == "reviewed_l3" and after.verified_by_user_id is None and after.l3_reviewed_by_user_id == cast["ids"]["R"]
    assert after.bottle_count == 11 and after.version == 1
    assert [x["event_type"] for x in _events(db, e.id)] == ["CREATED", "REVIEWED_L3"]                   # no VERIFIED_L2 anywhere
    assert str(e.id) not in _ids(client.get(SEARCH, headers=cast["L"], params={"verification": "pending_l2"}))     # not in the Team Lead's pending list
    assert _post(client, cast["L"], e, "verify").status_code == 409                                    # and not theirs to verify afterwards
    assert client.patch(f"{API}/entries/{e.id}", headers=cast["L"], json={"bottle_count": 3, "reason": "too late", "expected_version": 1}).status_code == 409
    assert _post(client, cast["R"], e, "review", {"action": "reviewed"}).status_code == 200            # repeating is harmless
    assert [x["event_type"] for x in _events(db, e.id)] == ["CREATED", "REVIEWED_L3"]


def test_a_reviewer_edit_on_a_pending_entry_is_final_too(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    assert client.patch(f"{API}/entries/{e.id}", headers=cast["R"], json={"bottle_count": 9, "reason": "I counted 9 myself", "expected_version": 1}).status_code == 200
    after = _entry(db, cast["s1"])
    assert after.verification_status == "reviewed_l3" and after.bottle_count == 9 and after.verified_by_user_id is None
    assert _report_total(client, cast["ADM"]) == 9


# =========================================================================== acceptance 3: the Reviewer's request reaches the Team Lead
def test_a_reviewer_request_appears_in_the_team_leads_pending_list_and_notifies_them(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["C"], cast["s2"], 7)
    e = _entry(db, cast["s1"])
    r = _post(client, cast["R"], e, "request-check", {"note": "A usually delivers 20 here"})
    assert r.status_code == 200, r.text
    assert r.json()["request"]["team_lead"]["id"] == str(cast["ids"]["L"]) and r.json()["entry"]["verification"]["check_requested"]["note"] == "A usually delivers 20 here"
    requested = client.get(SEARCH, headers=cast["L"], params={"verification": "requested"}).json()
    assert [i["entry_id"] for i in requested["items"]] == [str(e.id)]                                   # only the one that was asked for
    assert requested["items"][0]["verification"]["check_requested"]["by_name"]
    assert len(client.get(SEARCH, headers=cast["L"], params={"verification": "pending_l2"}).json()["items"]) == 2
    assert [i["entry_id"] for i in client.get(SEARCH, headers=cast["R"], params={"verification": "requested"}).json()["items"]] == [str(e.id)]
    notes = client.get(f"{API}/me/notifications", headers=cast["L"]).json()
    assert any(n["kind"] == "entry_check" and n["ref_id"] == str(e.id) for n in notes["items"])
    assert [x["event_type"] for x in _events(db, e.id)] == ["CREATED", "CHECK_REQUESTED"]
    assert client.get(f"{API}/entries/summary", headers=cast["L"]).json()["requested"] == 1

    # asking again with nothing new is a no-op; the Team Lead verifying closes the request
    assert _post(client, cast["R"], e, "request-check").json()["request"]["already_open"] is True
    assert _post(client, cast["L"], e, "verify").status_code == 200
    assert client.get(SEARCH, headers=cast["L"], params={"verification": "requested"}).json()["items"] == []
    assert _entry(db, cast["s1"]).check_requested_at is None
    assert _post(client, cast["R"], e, "request-check").status_code == 409                              # nothing left to check


def test_only_a_reviewer_or_administrator_can_request_a_check(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    for who in ("A", "L", "B"):
        assert _post(client, cast[who], e, "request-check").status_code == 403, who
    assert _post(client, cast["ADM"], e, "request-check").status_code == 200
    assert _entry(db, cast["s1"]).check_requested_by_user_id is not None


def test_a_request_for_a_contributor_with_no_team_lead_is_recorded_and_says_so(client, db, cast):
    _mark(client, cast["B"], cast["s2"], 5)
    r = _post(client, cast["R"], _entry(db, cast["s2"]), "request-check")
    assert r.status_code == 200 and r.json()["request"]["team_lead"] is None


# =========================================================================== acceptance 4: Level 3 / 4 tools
def test_cash_purchase_import_and_the_random_card_pdf_are_for_level_3_and_4_only(client, db, cast):
    cash = f"{API}/developer/cash-adjustments"
    sheet = f"{API}/developer/card-sheet"
    for who in ("A", "L", "B"):                                       # Level 1 and Level 2: refused by the API, whatever the page shows
        assert client.get(f"{cash}/stores", headers=cast[who]).status_code == 403, who
        assert client.post(f"{cash}/sync/apply", headers=cast[who], json={"record_ids": []}).status_code == 403, who
        assert client.post(f"{cash}/apply", headers=cast[who], json={"store_ids": [], "purchase_date": TODAY.isoformat(), "amount": "100", "price_per_item": "30"}).status_code == 403
        assert client.post(f"{cash}/sync/upload", headers=cast[who], files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}).status_code == 403
        assert client.post(f"{sheet}/unlock", headers=cast[who], json={"code": "2580"}).status_code == 403, who
        assert client.post(f"{sheet}/random-pdf", headers=cast[who], json={"token": "x", "store_id": str(cast["s1"].id), "rows": []}).status_code == 403
        perms = client.get(f"{API}/auth/me", headers=cast[who]).json()["permissions"]
        assert "cash.adjust" not in perms and "cards.sheet" not in perms
    for who in ("R", "ADM"):                                          # Level 3 and Level 4
        assert client.get(f"{cash}/stores", headers=cast[who]).status_code == 200, who
        perms = client.get(f"{API}/auth/me", headers=cast[who]).json()["permissions"]
        assert "cash.adjust" in perms and "cards.sheet" in perms
    # the random card PDF keeps its password lock: the Reviewer still has to enter the code
    assert client.post(f"{sheet}/unlock", headers=cast["R"], json={"code": "0000"}).status_code == 403
    assert client.post(f"{sheet}/random-pdf", headers=cast["R"], json={"token": "not-a-token", "store_id": str(cast["s1"].id), "rows": []}).status_code == 403
    ok = client.post(f"{sheet}/unlock", headers=cast["R"], json={"code": "2580"})
    assert ok.status_code == 200 and ok.json()["token"]
    assert client.post(f"{sheet}/totals-preview", headers=cast["R"], data={"token": "stolen"}, files={"file": ("t.csv", b"store,total\n", "text/csv")}).status_code == 403


def test_a_reviewer_limited_to_one_platform_gets_no_company_wide_tools(client, db, cast, make_user):
    code, pw, uid = make_user(role="entry_reviewer")
    db.query(User).filter(User.id == uid).update({"platform_organization_id": cast["s1"].partner_organization_id})
    db.commit()
    limited = _as(client, code, pw)
    assert client.get(f"{API}/developer/cash-adjustments/stores", headers=limited).status_code == 403
    assert "cards.sheet" not in client.get(f"{API}/auth/me", headers=limited).json()["permissions"]


def test_the_tools_cannot_be_granted_per_person(client, db, cast, make_user, admin):
    code, _pw, uid = make_user("employee")
    r = client.put(f"{API}/employees/{uid}/permissions", headers=admin, json={"codes": ["orders.view", "cash.adjust"]})
    assert r.status_code == 422


# =========================================================================== acceptance 5: what Level 1 is told
def test_level_1_sees_who_changed_their_entry_in_the_calendar_and_my_entries(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    cal = lambda: next(d for d in client.get(f"{API}/orders/calendar", headers=cast["A"], params={"store_id": str(cast["s1"].id)}).json()["days"] if d["date"] == TODAY.isoformat())
    assert cal()["changed"] is None and cal()["verification"]["status"] == "submitted"
    assert client.patch(f"{API}/entries/{e.id}", headers=cast["L"], json={"bottle_count": 14, "reason": "delivery note shows 14", "expected_version": 1}).status_code == 200
    d = cal()
    assert d["count"] == 14 and d["mine"] is True
    ch = d["changed"]
    assert ch["by_role_label"] == "Team Lead" and ch["by_name"].startswith("Test team_lead") is False and ch["by_name"]         # the person's NAME, not a role alone
    assert ch["old_count"] == 11 and ch["new_count"] == 14 and ch["reason"] == "delivery note shows 14" and ch["at"]
    assert d["verification"]["status"] == "verified_l2" and d["verification"]["label"] == "Verified by Team Lead" and d["verification"]["by_name"] == ch["by_name"]
    mine = client.get(f"{API}/orders/my-entries", headers=cast["A"]).json()["items"]
    row = next(i for i in mine if i["store_id"] == str(cast["s1"].id))
    assert row["changed"]["by_name"] == ch["by_name"] and row["changed"]["old_count"] == 11 and row["changed"]["new_count"] == 14
    assert row["verification"]["status"] == "verified_l2"
    # then the Reviewer changes it again: the LATEST change is the one reported
    client.patch(f"{API}/entries/{e.id}", headers=cast["R"], json={"bottle_count": 15, "reason": "vendor confirmed 15", "expected_version": 2})
    ch2 = cal()["changed"]
    assert ch2["by_role_label"] == "Reviewer" and (ch2["old_count"], ch2["new_count"]) == (14, 15) and cal()["verification"]["status"] == "reviewed_l3"
    assert client.get(f"{API}/orders/my-entries", headers=cast["C"]).json()["items"] == []                                   # a colleague learns nothing about it


def test_level_1_quick_entry_list_says_who_changed_todays_number(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["A"], cast["s2"], 6)
    e = _entry(db, cast["s1"])
    assert client.patch(f"{API}/entries/{e.id}", headers=cast["R"], json={"bottle_count": 15, "reason": "checked on site", "expected_version": 1}).status_code == 200
    rows = {r["id"]: r for r in client.get(f"{API}/orders/my-stores", headers=cast["A"]).json()}
    changed = rows[str(cast["s1"].id)]
    assert changed["today_count"] == 15 and changed["today_changed"]["by_role_label"] == "Reviewer"
    assert (changed["today_changed"]["old_count"], changed["today_changed"]["new_count"]) == (11, 15) and changed["today_changed"]["by_name"]
    assert rows[str(cast["s2"].id)]["today_changed"] is None                                             # untouched entries say nothing


def test_a_developers_hidden_cash_adjustment_is_never_reported_to_level_1(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    dev_id = db.query(User).filter_by(employee_code="ADMIN001").one().id
    db.execute(text("SELECT set_config('app.actor_id', :i, false)"), {"i": str(dev_id)})
    db.execute(text("UPDATE order_entries SET bottle_count = bottle_count + 5, cash_adjustment = 5 WHERE id = :e"), {"e": e.id})
    db.commit()
    db.execute(text("SELECT set_config('app.actor_id', '', false)"))
    d = next(x for x in client.get(f"{API}/orders/calendar", headers=cast["A"], params={"store_id": str(cast["s1"].id)}).json()["days"] if x["date"] == TODAY.isoformat())
    assert d["count"] == 11 and d["changed"] is None                                                   # still their own 11; no trace of the adjustment
    assert d["verification"]["by_name"] is None                                                         # the person behind it is not named either


# =========================================================================== acceptance 6: store-wise and employee-wise filters
def test_store_and_employee_filters_work_alone_and_together_for_the_team_lead_and_the_reviewer(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["A"], cast["s2"], 12)
    _mark(client, cast["C"], cast["s1"], 13, day=TODAY - timedelta(days=1))
    _mark(client, cast["C"], cast["s2"], 14, day=TODAY - timedelta(days=1))
    _mark(client, cast["B"], cast["s3"], 15)                                                           # outside L's team
    s1, s2, s3 = (str(cast[k].id) for k in ("s1", "s2", "s3"))
    a, c, b = (str(cast["ids"][k]) for k in ("A", "C", "B"))

    def counts(who, **f):
        r = client.get(SEARCH, headers=cast[who], params={"store": "VF-", **f})
        assert r.status_code == 200, r.text
        return sorted((i["store"]["id"], i["creator"]["id"]) for i in r.json()["items"])

    for who in ("L", "R"):
        assert counts(who, store_id=s1) == sorted([(s1, a), (s1, c)]), who                             # store alone
        assert counts(who, creator_id=a) == sorted([(s1, a), (s2, a)]), who                            # employee alone
        assert counts(who, store_id=s1, creator_id=a) == [(s1, a)], who                                # together
        assert counts(who, store_id=s2, creator_id=c, verification="pending_l2") == [(s2, c)], who     # with the status filter
        assert counts(who, store_id=s1, creator_id=c, date_from=TODAY.isoformat()) == [], who          # with the date filter (C's s1 entry was yesterday)
        assert counts(who, store_id=s1, creator_id=c, date_to=(TODAY - timedelta(days=1)).isoformat()) == [(s1, c)], who
    assert counts("R", store_id=s3) == [(s3, b)] and counts("L", store_id=s3) == []                   # the Reviewer sees everything, the Team Lead only the team
    assert counts("R", creator_id=b, store_id=s3, verification="pending_l2") == [(s3, b)]
    assert counts("L", creator_id=b) == []                                                             # a filter never widens the scope

    page = client.get(SEARCH, headers=cast["R"], params={"store": "VF-", "page_size": 2, "page": 2}).json()
    assert page["total"] == 5 and len(page["items"]) == 2                                             # paginated on the server


def test_the_filter_pickers_stay_inside_the_callers_scope(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["B"], cast["s3"], 15)
    people = lambda who, **p: {x["id"] for x in client.get(f"{API}/entries/options", headers=cast[who], params={"kind": "person", **p}).json()}
    stores = lambda who, **p: {x["code"] for x in client.get(f"{API}/entries/options", headers=cast[who], params={"kind": "store", **p}).json()}
    assert people("L") == {str(cast["ids"][k]) for k in ("A", "C", "L")}                               # the team (and themselves)
    assert str(cast["ids"]["B"]) in people("R") and str(cast["ids"]["B"]) in people("ADM")
    assert people("R", q=cast["codes"]["B"]) == {str(cast["ids"]["B"])}
    assert stores("L", q="VF-") == {"VF-1"}                                                            # only stores their team entered
    assert {"VF-1", "VF-3"} <= stores("R", q="VF-")
    assert client.get(f"{API}/entries/options", headers=cast["A"], params={"kind": "store"}).status_code == 403
    assert client.get(f"{API}/entries/options", headers=cast["R"], params={"kind": "nope"}).status_code == 422


# =========================================================================== comments
def test_comments_are_part_of_the_history_and_follow_the_same_scope(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["B"], cast["s2"], 5)
    e, other = _entry(db, cast["s1"]), _entry(db, cast["s2"])
    r = _post(client, cast["L"], e, "comments", {"text": "Called the store, count is right."})
    assert r.status_code == 200
    last = r.json()["events"][-1]
    assert last["type"] == "COMMENTED" and last["comment"] == "Called the store, count is right." and last["actor"]["role"] == "team_lead" and r.json()["chain_ok"] is True
    assert _post(client, cast["R"], e, "comments", {"text": "Thanks, noted."}).status_code == 200
    assert _post(client, cast["A"], e, "comments", {"text": "can I?"}).status_code == 403              # Level 1 has no history access
    assert _post(client, cast["L"], e, "comments", {"text": "   "}).status_code == 422
    assert _post(client, cast["L"], other, "comments", {"text": "not my team"}).status_code == 404      # outside the team
    assert _entry(db, cast["s1"]).version == 1                                                         # a comment changes nothing about the entry
    assert [x["event_type"] for x in _events(db, e.id)] == ["CREATED", "COMMENTED", "COMMENTED"]


# =========================================================================== the database enforces the rules too
def _as_actor(db, user_id, sql, **params):
    db.execute(text("SELECT set_config('app.actor_id', :i, true)"), {"i": str(user_id)})
    db.execute(text(sql), params)


def test_the_database_refuses_a_state_it_should_never_reach(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    from sqlalchemy.exc import DBAPIError

    # a Team Lead cannot finalise, a contributor cannot verify, nobody can reopen
    for actor, new in ((cast["ids"]["L"], "reviewed_l3"), (cast["ids"]["A"], "verified_l2")):
        with pytest.raises(DBAPIError):
            _as_actor(db, actor, "UPDATE order_entries SET verification_status = :s WHERE id = :e", s=new, e=e.id)
        db.rollback()
    assert _entry(db, cast["s1"]).verification_status == "submitted"
    assert _post(client, cast["R"], e, "review", {"action": "reviewed"}).status_code == 200
    with pytest.raises(DBAPIError):
        _as_actor(db, cast["ids"]["R"], "UPDATE order_entries SET verification_status = 'submitted' WHERE id = :e", e=e.id)
    db.rollback()
    with pytest.raises(DBAPIError):                                                                   # a Team Lead changing a number that is already final
        _as_actor(db, cast["ids"]["L"], "UPDATE order_entries SET bottle_count = 99 WHERE id = :e", e=e.id)
    db.rollback()
    assert _entry(db, cast["s1"]).bottle_count == 11


def test_a_number_changed_by_a_contributor_after_verification_goes_back_to_submitted(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    assert _post(client, cast["L"], e, "verify").status_code == 200
    _as_actor(db, cast["ids"]["A"], "UPDATE order_entries SET bottle_count = 12 WHERE id = :e", e=e.id)
    db.commit()
    after = _entry(db, cast["s1"])
    assert after.verification_status == "submitted" and after.verified_by_user_id is None and after.bottle_count == 12
    assert _events(db, e.id)[-1]["event_type"] == "STATUS_CHANGED"


def test_entries_made_by_senior_people_start_at_their_own_level(client, db, cast):
    _mark(client, cast["L"], cast["s1"], 9)                                                           # a Team Lead's own entry
    assert _entry(db, cast["s1"]).verification_status == "verified_l2"
    r = client.patch(f"{API}/orders/entry", headers=cast["ADM"], json={"store_id": str(cast["s2"].id), "order_date": TODAY.isoformat(), "bottle_count": 4})
    assert r.status_code == 200
    e = _entry(db, cast["s2"])
    assert e.verification_status == "reviewed_l3" and e.l3_reviewed_by_user_id is not None            # an administrator's number is final


def test_administrators_can_do_everything_a_reviewer_can_and_see_everything(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    got = client.get(SEARCH, headers=cast["ADM"], params={"entry_id": str(e.id)}).json()
    assert got["level"] == "administrator" and got["items"][0]["actions"] == {"edit": True, "verify": False, "review": True, "request_check": True, "flag": True, "comment": True}
    assert _post(client, cast["ADM"], e, "request-check", {"note": "please look"}).status_code == 200
    assert client.patch(f"{API}/entries/{e.id}", headers=cast["ADM"], json={"bottle_count": 13, "reason": "admin knows better", "expected_version": 1}).status_code == 200
    assert _entry(db, cast["s1"]).verification_status == "reviewed_l3" and _entry(db, cast["s1"]).check_requested_at is None
    assert client.get(f"{API}/entries/summary", headers=cast["ADM"]).json()["reviewed_l3"] >= 1


def test_a_reviewer_flag_is_cleared_when_they_review_the_entry(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    e = _entry(db, cast["s1"])
    assert _post(client, cast["R"], e, "review", {"action": "flagged", "comment": "looks too low"}).status_code == 200
    assert _entry(db, cast["s1"]).review_status == "flagged" and _entry(db, cast["s1"]).verification_status == "submitted"
    assert _post(client, cast["R"], e, "review", {"action": "reviewed", "comment": "confirmed with the vendor"}).status_code == 200
    after = _entry(db, cast["s1"])
    assert after.review_status == "none" and after.verification_status == "reviewed_l3"


# =========================================================================== drill-down: partner -> employee -> that employee's stores -> a store's entries
def test_partner_then_employee_pickers_narrow_each_other(client, db, cast, make_user):
    zcode, zpw, zuid = make_user(role="employee", platform="zepto", region=None)
    blink = str(cast["s1"].partner_organization_id)
    plats = client.get(f"{API}/entries/options", headers=cast["R"], params={"kind": "platform"}).json()
    assert {"blinkit", "zepto"} <= {p["slug"] for p in plats}
    zepto_id = next(p["id"] for p in plats if p["slug"] == "zepto")
    people = lambda **p: {x["id"] for x in client.get(f"{API}/entries/options", headers=cast["R"], params={"kind": "person", **p}).json()}
    assert str(zuid) in people() and str(cast["ids"]["A"]) in people()
    assert str(zuid) in people(platform_id=zepto_id) and str(cast["ids"]["A"]) not in people(platform_id=zepto_id)       # only that partner's employees
    assert str(cast["ids"]["A"]) in people(platform_id=blink) and str(zuid) not in people(platform_id=blink)
    # a Team Lead has only the partners of their own team; a Reviewer limited to Blinkit has only Blinkit
    assert {p["slug"] for p in client.get(f"{API}/entries/options", headers=cast["L"], params={"kind": "platform"}).json()} == {"blinkit"}
    code, pw, uid = make_user(role="entry_reviewer")
    db.query(User).filter(User.id == uid).update({"platform_organization_id": cast["s1"].partner_organization_id})
    db.commit()
    mine = _as(client, code, pw)
    assert [p["slug"] for p in client.get(f"{API}/entries/options", headers=mine, params={"kind": "platform"}).json()] == ["blinkit"]
    assert str(zuid) not in {x["id"] for x in client.get(f"{API}/entries/options", headers=mine, params={"kind": "person", "platform_id": zepto_id}).json()}
    assert client.get(f"{API}/entries/options", headers=cast["A"], params={"kind": "platform"}).status_code == 403


def test_an_employees_stores_list_counts_entries_by_state_and_stays_in_scope(client, db, cast):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["A"], cast["s1"], 12, day=TODAY - timedelta(days=1))
    _mark(client, cast["A"], cast["s2"], 6)
    _mark(client, cast["B"], cast["s2"], 9, day=TODAY - timedelta(days=1))                       # a different employee, same store
    first = _entry(db, cast["s1"])
    assert _post(client, cast["L"], first, "verify").status_code == 200
    url = f"{API}/entries/employee-stores"
    a = str(cast["ids"]["A"])
    for who in ("R", "L", "ADM"):
        body = client.get(url, headers=cast[who], params={"creator_id": a}).json()
        by = {i["store"]["outlet_id"]: i for i in body["items"]}
        assert set(by) == {"VF-1", "VF-2"} and body["employee"]["id"] == a, who                     # only the stores THIS employee entered
        assert by["VF-1"]["entries"] == 2 and by["VF-1"]["pending_l2"] == 1 and by["VF-1"]["verified_l2"] == 1 and by["VF-1"]["bottles"] == 23, who
        assert by["VF-2"]["entries"] == 1 and by["VF-2"]["last_entry"] == TODAY.isoformat(), who    # B's entry at VF-2 is not counted
    only_pending = client.get(url, headers=cast["R"], params={"creator_id": a, "verification": "verified_l2"}).json()
    assert [i["store"]["outlet_id"] for i in only_pending["items"]] == ["VF-1"]
    ranged = client.get(url, headers=cast["R"], params={"creator_id": a, "date_from": TODAY.isoformat()}).json()
    assert {i["store"]["outlet_id"]: i["entries"] for i in ranged["items"]} == {"VF-1": 1, "VF-2": 1}
    # scope: a Team Lead cannot list a stranger's stores, Level 1 cannot use it at all
    assert client.get(url, headers=cast["L"], params={"creator_id": str(cast["ids"]["B"])}).json()["items"] == []
    assert client.get(url, headers=cast["A"], params={"creator_id": a}).status_code == 403
    assert client.get(url, headers=cast["R"], params={"creator_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404


def test_the_team_lead_dashboard_totals_the_team_and_nobody_else(client, db, cast, make_store):
    _mark(client, cast["A"], cast["s1"], 11)
    _mark(client, cast["A"], cast["s2"], 6)
    _mark(client, cast["C"], cast["s3"], 4)                                                      # a second team member
    _mark(client, cast["B"], make_store(code="VF-4", state="Testland-V"), 50)                    # not on the team: never counted
    assert _post(client, cast["L"], _entry(db, cast["s2"]), "verify").status_code == 200
    o = client.get(f"{API}/entries/team-overview", headers=cast["L"]).json()
    assert (o["members"], o["stores"], o["entries"], o["bottles"]) == (3, 3, 3, 21)             # the team lead, A and C; three distinct stores; B's 50 is not here
    assert (o["today_entries"], o["today_bottles"]) == (3, 21)
    assert (o["pending_l2"], o["verified_l2"], o["reviewed_l3"]) == (2, 1, 0)
    by = {p["code"]: p for p in o["people"]}
    assert by[cast["codes"]["A"]]["entries"] == 2 and by[cast["codes"]["A"]]["stores"] == 2 and by[cast["codes"]["A"]]["bottles"] == 17
    assert by[cast["codes"]["L"]]["entries"] == 0 and o["not_entered_today"] == 0
    for who in ("A", "R", "ADM"):
        assert client.get(f"{API}/entries/team-overview", headers=cast[who]).status_code == 403, who

