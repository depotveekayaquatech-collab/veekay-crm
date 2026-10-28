"""A Zepto partner login (the platform's own account) can see everything about Zepto capping, and can change nothing."""
from datetime import timedelta

from app.models.capping_history import CappingHistory
from app.services import capping_history_service as svc

from .conftest import API, auth, login


def test_a_zepto_partner_login_sees_all_of_the_capping_pages_but_cannot_change_anything(client, admin, make_user, make_store, db):
    store = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    today = svc.today_ist()
    db.add(CappingHistory(store_id=store.id, capping=11, effective_from=today - timedelta(days=3)))
    db.commit()
    code, pw, _ = make_user(role="partner", platform="zepto", region=None)
    who = auth(login(client, code, pw).json()["access_token"])

    for url in ("/capping", "/capping/alerts", "/capping/summary", "/capping/sheet", f"/capping/history?storeId={store.id}",
                "/capping/sheet/download?format=csv", "/capping/sheet/download?format=xlsx", "/capping/print"):
        r = client.get(f"{API}{url}", headers=who)
        assert r.status_code == 200, (url, r.status_code, r.text[:200])
    row = next(x for x in client.get(f"{API}/capping/summary", headers=who).json()["rows"] if x["store_id"] == str(store.id))
    assert row["current_capping"] == 11

    # the capping.change tools (a new capping with a date, the default, the sheet with dates) stay with administrators and managers.
    # (The older "Edit cap" button on the Usage tab, PUT /capping/stores/{id}, has always been open to every eligible login; that is unchanged.)
    assert client.post(f"{API}/capping/change", headers=who, json={"storeId": str(store.id), "capping": 5, "effectiveFrom": today.isoformat()}).status_code == 403
    assert client.post(f"{API}/capping/defaults", headers=who, json={"dry_run": False}).status_code == 403
    assert client.post(f"{API}/capping/import-dated", headers=who, files={"file": ("c.csv", b"Store,1\nx,1\n", "text/csv")}).status_code == 403

    # a Blinkit partner login still never sees Zepto capping
    other = make_user(role="partner", platform="blinkit", region=None)
    blink = auth(login(client, other[0], other[1]).json()["access_token"])
    assert client.get(f"{API}/capping/summary", headers=blink).status_code == 403
