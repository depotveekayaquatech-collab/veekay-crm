"""The sales report can be narrowed to one platform / region / state — chart series and breakdown together."""
from datetime import date, timedelta

from app.models.order_entry import EntrySource, OrderEntry

from .conftest import API


def _mark(db, store, day, n):
    from app.core.cache import read_cache

    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=day, bottle_count=n,
                      source=EntrySource.ADMIN.value))
    db.commit()
    read_cache.invalidate()   # a real write goes through the API, which does this; direct inserts must say so


def test_report_can_be_filtered_by_partner_region_and_state(client, admin, db, make_store):
    d = date.today() - timedelta(days=1)

    def report(extra=""):
        r = client.get(f"{API}/orders/report?start={d}&end={d}&group_by=partner{extra}", headers=admin)
        assert r.status_code == 200, r.text
        return r.json()

    # Demo data may already hold entries for this day, so measure what our two entries *add*.
    base_all = report()["total_bottles"]
    base_zepto = report("&partner=zepto")["total_bottles"]
    base_north_blink = report("&partner=blinkit&region=north")["total_bottles"]

    blink = make_store(code="RF-B1", platform="blinkit", region="NORTH", state="Testland-A")
    zep = make_store(code="RF-Z1", platform="zepto", region=None, state="Testland-Z")
    _mark(db, blink, d, 30)
    _mark(db, zep, d, 12)

    assert report()["total_bottles"] == base_all + 42
    assert report()["series"][0]["bottles"] == base_all + 42                     # chart == totals

    only_zepto = report("&partner=zepto")
    assert [r["label"] for r in only_zepto["rows"]] == ["Zepto"]
    assert only_zepto["total_bottles"] == base_zepto + 12
    assert only_zepto["series"][0]["bottles"] == base_zepto + 12                 # the chart narrows with the rows

    assert report("&partner=zepto&state=testland-z")["total_bottles"] == 12      # state match ignores case
    assert report("&state=testland-a")["total_bottles"] == 30
    assert report("&partner=blinkit&region=north")["total_bottles"] == base_north_blink + 30
    assert report("&partner=zepto&state=testland-a")["total_bottles"] == 0       # filters combine (AND)


# ---------------------------------------------------------------- the bulk store-visibility used by the dashboards
def test_bulk_employee_scopes_match_the_per_employee_rules(db, make_store):
    """`employee_store_scopes` must give every employee exactly the stores `visible_stores` gives them."""
    from app.models.organization import Organization
    from app.repositories.employee_repository import EmployeeRepository
    from app.services import assignment_service as svc

    make_store(code="BK-1", platform="blinkit", region="NORTH", state="Delhi")
    make_store(code="BK-2", platform="blinkit", region="WEST", state="Maharashtra")
    make_store(code="BK-3", platform="zepto", region=None, state="Karnataka")
    for slug in ("blinkit", "zepto"):
        partner = db.query(Organization).filter_by(slug=slug).one()
        employees = EmployeeRepository(db).all_for_platform(partner.organization_id if hasattr(partner, "organization_id") and False else db.query(Organization).filter_by(slug="veekay").one().id, partner.id)
        scopes, all_ids = svc.employee_store_scopes(db, partner, employees)
        assert employees, f"no {slug} employees to compare"
        for emp in employees:
            assert sorted(scopes[emp.id]) == sorted(s.id for s in svc.visible_stores(db, emp)), emp.employee_code
        assert set(all_ids) >= {sid for ids in scopes.values() for sid in ids}


# ---------------------------------------------------------------- matrix: totals now computed by the database
def test_matrix_totals_rows_and_paging(client, admin, db, make_store):
    d1, d2 = date.today() - timedelta(days=2), date.today() - timedelta(days=1)
    a = make_store(code="MX-A", platform="zepto", region=None, state="Testland-M", city="Alpha", name="Mx Alpha")
    b = make_store(code="MX-B", platform="zepto", region=None, state="Testland-M", city="Beta", name="Mx Beta")
    make_store(code="MX-C", platform="zepto", region=None, state="Testland-M", city="Gamma", name="Mx Gamma")  # no entries
    _mark(db, a, d1, 10)
    _mark(db, a, d2, 0)       # a real zero is a marked day
    _mark(db, b, d2, 7)

    base = f"{API}/orders/matrix?start={d1}&end={d2}&partner=zepto&state=testland-m"
    m = client.get(base, headers=admin).json()
    assert m["total"] == 3 and m["stores_with_entries"] == 2 and m["grand_total_bottles"] == 17
    rows = {r["external_code"]: r for r in m["rows"]}
    assert rows["MX-A"]["values"] == {d1.isoformat(): 10, d2.isoformat(): 0}
    assert rows["MX-A"]["total_bottles"] == 10 and rows["MX-A"]["days_marked"] == 2
    assert rows["MX-B"]["values"] == {d2.isoformat(): 7} and rows["MX-C"]["values"] == {}

    # Paging shows only that page's rows, but the totals still cover every matching store.
    p1 = client.get(base + "&page=1&page_size=2", headers=admin).json()
    p2 = client.get(base + "&page=2&page_size=2", headers=admin).json()
    assert [r["external_code"] for r in p1["rows"]] + [r["external_code"] for r in p2["rows"]] == ["MX-A", "MX-B", "MX-C"]
    assert p1["grand_total_bottles"] == p2["grand_total_bottles"] == 17 and p2["stores_with_entries"] == 2


def test_card_regions_follow_the_selected_platform(client, admin, make_store):
    make_store(code="CR-B", platform="blinkit", region="NORTH", state="Testland-R")
    make_store(code="CR-Z", platform="zepto", region="SOUTH", state="Testland-R")
    names = lambda r: {x["name"] for x in r.json()["regions"]}  # noqa: E731
    both = client.get(f"{API}/cards/vendors", headers=admin)
    only_b = client.get(f"{API}/cards/vendors?partner=blinkit", headers=admin)
    only_z = client.get(f"{API}/cards/vendors?partner=zepto", headers=admin)
    assert {"North", "South"} <= names(both)
    assert "North" in names(only_b)
    assert "South" in names(only_z)
    assert names(only_b) <= names(both) and names(only_z) <= names(both)


def test_report_limit_trims_rows_but_not_totals_and_cached_copies_follow_writes(client, admin, db, make_store):
    d = date.today() - timedelta(days=1)
    s1 = make_store(code="LM-1", platform="zepto", region=None, state="Testland-L", name="Lm One")
    s2 = make_store(code="LM-2", platform="zepto", region=None, state="Testland-L", name="Lm Two")
    _mark(db, s1, d, 40)
    _mark(db, s2, d, 5)
    url = f"{API}/orders/report?start={d}&end={d}&group_by=store&state=testland-l"
    full = client.get(url, headers=admin).json()
    top1 = client.get(url + "&limit=1", headers=admin).json()
    assert [r["sub"] for r in full["rows"]] == ["LM-1", "LM-2"]
    assert [r["sub"] for r in top1["rows"]] == ["LM-1"]                          # only the biggest store comes back
    assert top1["total_bottles"] == full["total_bottles"] == 45                  # ...but the totals still cover everyone
    assert top1["series"] == full["series"]
    assert top1["row_count"] == full["row_count"] == 2                            # "how many stores had orders" survives the trim

    # A new entry (a write) must show up even though the report above is now cached.
    assert client.patch(f"{API}/orders/entry", headers=admin, json={"store_id": str(s2.id), "order_date": d.isoformat(), "bottle_count": 100}).status_code == 200
    again = client.get(url, headers=admin).json()
    assert again["total_bottles"] == 140 and again["rows"][0]["sub"] == "LM-2"
