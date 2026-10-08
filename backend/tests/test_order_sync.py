"""Order counts pulled from a Google Sheet (the same public-CSV route as the store sync)."""
from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.models.order_entry import EntrySource, OrderEntry
from app.services import store_sync_service

from .conftest import API


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def sheet(monkeypatch):
    """Serve fake sheet CSVs by gid and point ORDER_SYNC_SHEETS at them."""
    pages: dict[str, str] = {}
    monkeypatch.setattr(store_sync_service, "fetch_csv_text", lambda sheet_id, gid: pages[gid])
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", ["blinkit=SHEETID:0", "blinkit=SHEETID:7"])
    monkeypatch.setattr(settings, "ORDER_SYNC_OVERWRITE", False)
    return pages


def test_sources_allow_several_tabs_per_platform(monkeypatch):
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", ["Blinkit=abc:3", "blinkit=abc", "zepto=xyz:9", "junk", "empty="])
    assert settings.order_sheet_sources() == {"blinkit": [("abc", "3"), ("abc", "0")], "zepto": [("xyz", "9")]}


def test_sync_requires_the_correct_permission(client, emp):
    assert client.post(f"{API}/orders/sync", headers=emp).status_code == 403


def test_sync_without_configuration_is_a_clear_error(client, dev, monkeypatch):
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", [])
    r = client.post(f"{API}/orders/sync", headers=dev)
    assert r.status_code == 422
    assert "ORDER_SYNC_SHEETS" in r.json()["detail"]


def test_sync_imports_every_tab_and_keeps_existing_entries(client, dev, db, make_store, sheet):
    store = make_store(code="SYNC-1")
    d1, d2, d3 = _iso(3), _iso(2), _iso(1)
    # Two tabs of the same workbook: the second one adds another date column.
    sheet["0"] = f"S.No,Outlet ID,Outlet Name,{d1},{d2}\n1,SYNC-1,Shop,12,\n2,NOPE-9,Ghost,5,5\n"
    sheet["7"] = f"Outlet ID,Outlet Name,{d3}\nSYNC-1,Shop,0\n"
    # d1 was already marked by hand with a different number — it must survive (overwrite is off).
    db.add(OrderEntry(organization_id=store.organization_id, store_id=store.id, order_date=date.fromisoformat(d1),
                      bottle_count=99, source=EntrySource.EMPLOYEE.value))
    db.commit()

    r = client.post(f"{API}/orders/sync?platform=blinkit", headers=dev)
    assert r.status_code == 200, r.text
    (res,) = r.json()
    assert res["platform"] == "blinkit"
    assert res["created"] == 1                      # only d3 (a real zero) is new; d2 is blank
    assert res["kept_existing"] == 1                # d1 kept at 99
    assert res["unknown_stores"] == 1               # NOPE-9
    assert any("NOPE-9" in w or "not found" in w for w in res["warnings"])

    db.expire_all()
    rows = {e.order_date.isoformat(): e.bottle_count for e in db.query(OrderEntry).filter(OrderEntry.store_id == store.id)}
    assert rows == {d1: 99, d3: 0}

    # Overwrite on: the sheet wins.
    r = client.post(f"{API}/orders/sync?platform=blinkit&overwrite=true", headers=dev)
    assert r.status_code == 200 and r.json()[0]["updated"] == 1
    db.expire_all()
    assert db.query(OrderEntry).filter_by(store_id=store.id, order_date=date.fromisoformat(d1)).one().bottle_count == 12


def test_sync_reports_a_private_sheet_instead_of_crashing(client, dev, monkeypatch):
    monkeypatch.setattr(settings, "ORDER_SYNC_SHEETS", ["blinkit=SHEETID:0"])

    def private(sheet_id, gid):
        raise store_sync_service.SyncError("The sheet is not publicly readable.")

    monkeypatch.setattr(store_sync_service, "fetch_csv_text", private)
    r = client.post(f"{API}/orders/sync?platform=blinkit", headers=dev)
    assert r.status_code == 422 and "publicly readable" in r.json()["detail"]

    # Without ?platform a failing sheet becomes a warning on its platform, not a 500.
    r = client.post(f"{API}/orders/sync", headers=dev)
    assert r.status_code == 200 and "publicly readable" in r.json()[0]["warnings"][0]


# ---------------------------------------------------------------- devs need nobody's sign-off

def test_admin_holds_every_permission_that_exists(client, admin, db):
    from app.models.permission import Permission

    everything = {p.code for p in db.query(Permission)}
    granted = set(client.get(f"{API}/auth/me", headers=admin).json()["permissions"])
    from app.core.roles import RESERVED_PERMISSIONS

    # every permission except the developer-only ones
    assert everything and everything - RESERVED_PERMISSIONS == granted


def test_admin_sees_every_live_store_and_can_mark_and_edit_any_of_them(client, admin, emp, make_store, db):
    blink = make_store(code="ADM-B1")
    zep = make_store(code="ADM-Z1", platform="zepto", region=None, state="Karnataka")
    codes = {s["external_code"] if "external_code" in s else s["externalCode"] for s in client.get(f"{API}/orders/my-stores", headers=admin).json()}
    assert {"ADM-B1", "ADM-Z1"} <= codes                      # both platforms, no region / state assignment needed

    d = date.today().isoformat()
    for count in (7, 11):                                      # second call edits the saved day: no "ask an admin" wall
        r = client.post(f"{API}/orders/mark", headers=admin, json={"store_id": str(zep.id), "order_date": d, "bottle_count": count})
        assert r.status_code == 200, r.text
    db.expire_all()
    e = db.query(OrderEntry).filter_by(store_id=zep.id, order_date=date.today()).one()
    assert (e.bottle_count, e.source) == (11, EntrySource.ADMIN.value)

    # An ordinary employee is still one-shot and confined to their own stores.
    r = client.post(f"{API}/orders/mark", headers=emp, json={"store_id": str(zep.id), "order_date": d, "bottle_count": 1})
    assert r.status_code == 403
