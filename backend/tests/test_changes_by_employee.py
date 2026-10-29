"""Audit log: per person who entered numbers, how many of their entries were never changed, changed once, changed more than once."""
from datetime import date

from app.services.performance_service import _pct

from .conftest import API
from .test_entry_hierarchy import _mark, cast  # noqa: F401  (cast is a fixture)

TODAY = date.today()
URL = f"{API}/entries/changes-by-employee"


def _fix(client, who, store, n):
    r = client.patch(f"{API}/orders/entry", headers=who, json={"store_id": str(store.id), "order_date": TODAY.isoformat(), "bottle_count": n})
    assert r.status_code == 200, r.text


def _row(body, uid):
    return next((r for r in body["employees"] if r["employee_id"] == str(uid)), None)


def test_each_employees_entries_are_counted_as_unchanged_changed_once_or_changed_more_than_once(client, db, cast, make_store):  # noqa: F811
    s1, s2, s3, s4 = cast["s1"], cast["s2"], make_store(code="HX-3"), make_store(code="HX-4")
    a, b = cast["ids"]["A"], cast["ids"]["B"]
    for store, n in ((s1, 11), (s2, 12), (s3, 13)):
        assert _mark(client, cast["A"], store, n).status_code == 200
    assert _mark(client, cast["B"], s4, 5).status_code == 200
    _fix(client, cast["ADM"], s2, 20)                                       # s2: changed once
    _fix(client, cast["ADM"], s3, 20)
    _fix(client, cast["ADM"], s3, 21)                                       # s3: changed twice

    body = client.get(URL, headers=cast["ADM"]).json()
    mine = _row(body, a)
    assert (mine["entries"], mine["unchanged"], mine["changed_once"], mine["changed_multiple"], mine["changes"]) == (3, 1, 1, 1, 3)
    assert mine["employee_code"] == cast["codes"]["A"] and mine["changed_percent"] == 66.7
    theirs = _row(body, b)
    assert (theirs["entries"], theirs["unchanged"], theirs["changed_once"], theirs["changed_multiple"]) == (1, 1, 0, 0)
    assert body["employees"].index(mine) < body["employees"].index(theirs)  # the people with the most repeated changes come first

    several = client.get(f"{URL}/{a}", headers=cast["ADM"], params={"kind": "multiple"}).json()["items"]
    assert [(i["store_code"], i["first_count"], i["count_now"], i["changes"]) for i in several] == [("HX-3", 13, 21, 2)]
    assert several[0]["last_changed_role"] == "Administrator"
    once = client.get(f"{URL}/{a}", headers=cast["ADM"], params={"kind": "once"}).json()["items"]
    assert [(i["store_code"], i["first_count"], i["count_now"]) for i in once] == [("HX-2", 12, 20)]
    assert len(client.get(f"{URL}/{a}", headers=cast["ADM"]).json()["items"]) == 2          # "changed" = once or more than once


def test_a_team_lead_sees_only_their_teams_people_and_an_employee_is_refused(client, db, cast, make_store):  # noqa: F811
    s3 = make_store(code="HX-3")
    assert _mark(client, cast["A"], cast["s1"], 11).status_code == 200      # A reports to the Team Lead
    assert _mark(client, cast["B"], s3, 5).status_code == 200               # B does not
    seen = client.get(URL, headers=cast["L"]).json()
    assert _row(seen, cast["ids"]["A"]) is not None and _row(seen, cast["ids"]["B"]) is None
    assert client.get(f"{URL}/{cast['ids']['B']}", headers=cast["L"]).json()["items"] == []
    assert client.get(URL, headers=cast["A"]).status_code == 403
    assert client.get(f"{URL}/{cast['ids']['A']}", headers=cast["A"]).status_code == 403
    assert client.get(URL, params={"month": "2026-13"}, headers=cast["ADM"]).status_code in (422,)


def test_a_percentage_is_100_only_when_nothing_is_missing():
    assert _pct(1999, 2000) == 99.9 and _pct(2000, 2000) == 100.0 and _pct(0, 0) == 0.0 and _pct(1, 2) == 50.0
