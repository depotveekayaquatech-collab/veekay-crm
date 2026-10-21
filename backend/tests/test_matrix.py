"""Daily delivery matrix: the Region filter (and the regions offered per channel) and totals over every matching store."""
from datetime import date, timedelta

from app.models.order_entry import OrderEntry

from .conftest import API

DAY = date.today() - timedelta(days=2)


def _entry(db, store, day, n):
    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=day, bottle_count=n))
    db.commit()


def _matrix(client, who, **extra):
    return client.get(f"{API}/orders/matrix", headers=who, params={"start": (DAY - timedelta(days=1)).isoformat(), "end": DAY.isoformat(), **extra})


def test_region_filter_regions_per_channel_and_totals_for_every_store(client, admin, db, make_store):
    north = make_store(code="MX-N", platform="blinkit", region="NORTH", vendor="MX")
    south = make_store(code="MX-S", platform="blinkit", region="SOUTH", vendor="MX")
    zep = make_store(code="MX-Z", platform="zepto", region="SOUTH", vendor="MX", state="Karnataka")
    for s, n in ((north, 5), (south, 7), (zep, 11)):
        _entry(db, s, DAY, n)

    regions = lambda **p: {r["name"] for r in client.get(f"{API}/orders/matrix/regions", headers=admin, params=p).json()}
    assert {"North", "South"} <= regions(partner="blinkit")
    assert "South" in regions(partner="zepto")

    south_id = next(r["id"] for r in client.get(f"{API}/orders/matrix/regions", headers=admin, params={"partner": "blinkit"}).json() if r["name"] == "South")
    codes = lambda m: {r["external_code"] for r in m["rows"]}
    only_south = _matrix(client, admin, partner="blinkit", region=south_id, page_size=200).json()
    assert "MX-S" in codes(only_south) and "MX-N" not in codes(only_south) and "MX-Z" not in codes(only_south)

    # the footer totals cover every matching store, not just the rows on the first page
    small_page = _matrix(client, admin, partner="blinkit", page_size=1).json()
    assert len(small_page["rows"]) == 1 and small_page["total"] > 1
    assert small_page["day_totals"][DAY.isoformat()] >= 12                      # north 5 + south 7 (+ any other blinkit stores)

    export = client.get(f"{API}/orders/matrix/export", headers=admin, params={
        "start": DAY.isoformat(), "end": DAY.isoformat(), "partner": "blinkit", "region": south_id})
    assert export.status_code == 200
