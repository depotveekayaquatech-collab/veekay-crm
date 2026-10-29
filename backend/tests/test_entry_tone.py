"""The colour of a calendar day: green for a Data Entry person's first entry, yellow after one change, red after two or more, blue for a Team Lead's,
and a separate colour for a Reviewer's / administrator's / developer's."""
from datetime import date

from app.core.config import settings

from .conftest import API
from .test_entry_hierarchy import _entry, _mark, cast  # noqa: F401  (cast is a fixture)

TODAY = date.today()


def _tone(client, who, store):
    cal = client.get(f"{API}/orders/calendar", headers=who, params={"store_id": str(store.id), "year": TODAY.year, "month": TODAY.month}).json()
    return next(d for d in cal["days"] if d["date"] == TODAY.isoformat())["tone"]


def test_an_entry_is_green_then_yellow_then_red_as_the_data_entry_person_changes_it(client, db, cast, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "EMPLOYEE_CAN_CORRECT_OWN", True)
    s1 = cast["s1"]
    assert _tone(client, cast["A"], s1) is None                                      # an empty day has no colour
    assert _mark(client, cast["A"], s1, 11).status_code == 200
    assert _tone(client, cast["A"], s1) == "l1_first"
    body = {"store_id": str(s1.id), "order_date": TODAY.isoformat()}
    assert client.patch(f"{API}/orders/my-entry", headers=cast["A"], json={**body, "bottle_count": 12}).status_code == 200
    assert _tone(client, cast["A"], s1) == "l1_second"                                # changed once
    assert client.patch(f"{API}/orders/my-entry", headers=cast["A"], json={**body, "bottle_count": 13}).status_code == 200
    assert _tone(client, cast["A"], s1) == "l1_third"                                 # changed a second time
    assert client.patch(f"{API}/orders/my-entry", headers=cast["A"], json={**body, "bottle_count": 14}).status_code == 200
    assert _tone(client, cast["A"], s1) == "l1_third"                                 # and it stays red


def test_a_team_leads_number_is_blue_and_an_administrators_has_its_own_colour(client, db, cast):  # noqa: F811
    s1, s2 = cast["s1"], cast["s2"]
    assert _mark(client, cast["A"], s1, 11).status_code == 200                        # A reports to the Team Lead
    assert _mark(client, cast["B"], s2, 22).status_code == 200
    entry = _entry(db, s1)
    fixed = client.patch(f"{API}/entries/{entry.id}", headers=cast["L"], json={"bottle_count": 14, "reason": "Delivery note says 14", "expected_version": 1})
    assert fixed.status_code == 200, fixed.text
    assert _tone(client, cast["A"], s1) == "l2"                                       # the colleague's view of a Team Lead's correction
    assert _tone(client, cast["ADM"], s1) == "l2"

    assert client.patch(f"{API}/orders/entry", headers=cast["ADM"], json={"store_id": str(s2.id), "order_date": TODAY.isoformat(), "bottle_count": 30}).status_code == 200
    assert _tone(client, cast["ADM"], s2) == "admin"
    assert _tone(client, cast["B"], s2) == "admin"                                    # B sees it, read-only, in the administrator's colour
