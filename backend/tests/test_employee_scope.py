"""Several regions per employee + excluding a state or a city from what they see."""
from app.models.employee_scope import EmployeeExclusion, EmployeeRegion
from app.models.organization import Organization
from app.models.region import Region
from app.models.user import User
from app.services import assignment_service

from .conftest import API


def _ids(db, uid, stores):
    emp = db.get(User, uid)
    db.refresh(emp)
    mine = {s.id for s in assignment_service.visible_stores(db, emp)}
    return {name: s.id in mine for name, s in stores.items()}


def _bulk(db, uid, stores):
    emp = db.get(User, uid)
    blinkit = db.query(Organization).filter_by(slug="blinkit").one()
    out, _ = assignment_service.employee_store_scopes(db, blinkit, [emp])
    return {name: s.id in set(out[uid]) for name, s in stores.items()}


def _scope(client, admin, db, uid, **body):
    blinkit = db.query(Organization).filter_by(slug="blinkit").one()
    return client.put(f"{API}/assignments/scope/{uid}", headers=admin, json={"platform_id": str(blinkit.id), **body})


def test_one_employee_can_cover_several_regions_and_skip_a_state_or_city(client, admin, make_user, make_store, db):
    region = {c: str(db.query(Region).filter_by(code=c).one().id) for c in ("NORTH", "WEST", "SOUTH")}
    stores = {
        "delhi": make_store(region="NORTH", state="Delhi", city="New Delhi"),
        "gurugram": make_store(region="NORTH", state="Haryana", city="Gurugram"),
        "pune": make_store(region="WEST", state="Maharashtra", city="Pune"),
        "mumbai": make_store(region="WEST", state="Maharashtra", city="Mumbai"),
        "bengaluru": make_store(region="SOUTH", state="Karnataka", city="Bengaluru"),
    }
    _, _, uid = make_user("employee", platform="blinkit", region="NORTH")

    # before: one region, as always
    assert _ids(db, uid, stores) == {"delhi": True, "gurugram": True, "pune": False, "mumbai": False, "bengaluru": False}

    # two regions
    r = _scope(client, admin, db, uid, region_ids=[region["NORTH"], region["WEST"]])
    assert r.status_code == 200, r.text
    out = r.json()
    assert [x["name"] for x in out["regions"]] == ["North", "West"] and out["region_id"] == region["NORTH"]
    both = {"delhi": True, "gurugram": True, "pune": True, "mumbai": True, "bengaluru": False}
    assert _ids(db, uid, stores) == both == _bulk(db, uid, stores)

    # all of that, except one state and one city
    r = _scope(client, admin, db, uid, region_ids=[region["NORTH"], region["WEST"]], excluded_states=["delhi"], excluded_cities=["Pune"])
    assert r.json()["excluded_states"] == ["delhi"] and r.json()["excluded_cities"] == ["Pune"]
    expected = {"delhi": False, "gurugram": True, "pune": False, "mumbai": True, "bengaluru": False}
    assert _ids(db, uid, stores) == expected == _bulk(db, uid, stores)

    # saving the regions again without exclusions keeps them; [] clears them
    _scope(client, admin, db, uid, region_ids=[region["NORTH"], region["WEST"]])
    assert _ids(db, uid, stores) == expected
    _scope(client, admin, db, uid, region_ids=[region["NORTH"], region["WEST"]], excluded_states=[], excluded_cities=[])
    assert _ids(db, uid, stores) == both

    # back to a single region (the old way) drops the extra one
    r = _scope(client, admin, db, uid, region_id=region["WEST"])
    assert [x["name"] for x in r.json()["regions"]] == ["West"]
    assert _ids(db, uid, stores) == {"delhi": False, "gurugram": False, "pune": True, "mumbai": True, "bengaluru": False}
    assert db.query(EmployeeRegion).filter_by(user_id=uid).count() == 1


def test_region_filter_and_validation_and_locations(client, admin, emp, make_user, make_store, db):
    region = {c: str(db.query(Region).filter_by(code=c).one().id) for c in ("NORTH", "WEST")}
    make_store(region="WEST", state="Maharashtra", city="Pune")
    _, _, uid = make_user("employee", platform="blinkit", region="NORTH")
    _scope(client, admin, db, uid, region_ids=[region["NORTH"], region["WEST"]], excluded_cities=["  pune  ", "PUNE", ""])
    assert db.query(EmployeeExclusion).filter_by(user_id=uid).count() == 1            # trimmed, de-duplicated, blanks dropped
    listed = client.get(f"{API}/employees?region_id={region['WEST']}&page_size=100", headers=admin).json()["items"]
    assert str(uid) in {e["id"] for e in listed}                                     # found through their second region
    assert _scope(client, admin, db, uid, region_ids=["00000000-0000-0000-0000-000000000000"]).status_code == 422
    loc = client.get(f"{API}/assignments/locations?partner=blinkit&region_ids={region['WEST']}", headers=admin).json()
    assert "Maharashtra" in loc["states"] and {"city": "Pune", "state": "Maharashtra"} in loc["cities"]
    assert client.put(f"{API}/assignments/scope/{uid}", headers=emp, json={"region_ids": []}).status_code == 403


def test_specific_states_and_cities_can_be_added_on_top_or_on_their_own(client, admin, make_user, make_store, db):
    region = {c: str(db.query(Region).filter_by(code=c).one().id) for c in ("NORTH", "WEST")}
    stores = {
        "delhi": make_store(region="NORTH", state="Delhi", city="New Delhi"),
        "gurugram": make_store(region="NORTH", state="Haryana", city="Gurugram"),
        "pune": make_store(region="WEST", state="Maharashtra", city="Pune"),
        "mumbai": make_store(region="WEST", state="Maharashtra", city="Mumbai"),
        "nowhere": make_store(region=None, state="Goa", city="Panaji"),
    }
    _, _, uid = make_user("employee", platform="blinkit", region="NORTH")

    # North, plus one city of West
    r = _scope(client, admin, db, uid, region_ids=[region["NORTH"]], included_cities=["Pune"])
    assert r.json()["included_cities"] == ["Pune"] and r.json()["included_states"] == []
    expected = {"delhi": True, "gurugram": True, "pune": True, "mumbai": False, "nowhere": False}
    assert _ids(db, uid, stores) == expected == _bulk(db, uid, stores)

    # plus a whole state that belongs to no region at all
    _scope(client, admin, db, uid, region_ids=[region["NORTH"]], included_states=["goa"])
    assert _ids(db, uid, stores) == {**expected, "nowhere": True} == _bulk(db, uid, stores)

    # skipping wins over adding
    _scope(client, admin, db, uid, region_ids=[region["NORTH"]], excluded_cities=["pune"])
    assert _ids(db, uid, stores)["pune"] is False and _bulk(db, uid, stores)["pune"] is False

    # no region at all: only the places added by hand
    _scope(client, admin, db, uid, region_ids=[], excluded_cities=[], included_states=["Maharashtra"], included_cities=[])
    only = {"delhi": False, "gurugram": False, "pune": True, "mumbai": True, "nowhere": False}
    assert _ids(db, uid, stores) == only == _bulk(db, uid, stores)

    # clearing them takes the employee back to nothing
    out = _scope(client, admin, db, uid, region_ids=[], included_states=[]).json()
    assert out["included_states"] == [] and not any(_ids(db, uid, stores).values())
