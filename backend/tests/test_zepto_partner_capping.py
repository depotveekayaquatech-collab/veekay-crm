"""A Zepto partner login (the platform's own account) can see the capping and each store's history, and cannot change anything."""
from datetime import timedelta

from app.models.capping_history import CappingHistory
from app.services import capping_history_service as svc

from .conftest import API, auth, login


def test_a_zepto_partner_login_sees_the_capping_and_its_history_but_cannot_change_anything(client, admin, make_user, make_store, db):
    store = make_store(platform="zepto", region=None, state="Karnataka", city="Bengaluru")
    today = svc.today_ist()
    row = CappingHistory(store_id=store.id, capping=11, effective_from=today - timedelta(days=3))
    db.add(row)
    db.commit()
    code, pw, _ = make_user(role="partner", platform="zepto", region=None)
    who = auth(login(client, code, pw).json()["access_token"])

    listed = client.get(f"{API}/capping", headers=who)
    assert listed.status_code == 200, listed.text
    mine = next(x for x in listed.json()["rows"] if x["store_id"] == str(store.id))
    assert mine["capping"] == 11
    assert client.get(f"{API}/capping/alert", headers=who).status_code == 200                 # the alert is visible to the platform's own login
    assert client.get(f"{API}/capping/history", params={"storeId": str(store.id)}, headers=who).status_code == 200

    # view only: setting or removing a capping needs capping.change
    assert client.post(f"{API}/capping/change", headers=who, json={"storeId": str(store.id), "capping": 5}).status_code == 403
    assert client.post(f"{API}/capping/remove", headers=who, json={"storeId": str(store.id)}).status_code == 403

    # a Blinkit partner login still never sees Zepto capping
    other = make_user(role="partner", platform="blinkit", region=None)
    blink = auth(login(client, other[0], other[1]).json()["access_token"])
    assert client.get(f"{API}/capping", headers=blink).status_code == 403
    assert client.get(f"{API}/capping/history", params={"storeId": str(store.id)}, headers=blink).status_code == 403
