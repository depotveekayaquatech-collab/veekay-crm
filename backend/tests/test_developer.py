"""Developer role: owns the sheet sync / bulk upload tools, and nothing else. Admins can't see, grant or create it."""
import io

import pytest

from app.core.roles import RESERVED_PERMISSIONS
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository

from .conftest import API, auth, login

SHEET_CALLS = [
    ("post", f"{API}/stores/sync", {}),
    ("post", f"{API}/stores/import", {"data": {"platform": "blinkit"}, "files": {"file": ("s.csv", b"a,b\n1,2\n", "text/csv")}}),
    ("post", f"{API}/orders/sync", {}),
    ("post", f"{API}/orders/import", {"data": {"platform": "blinkit"}, "files": {"file": ("o.csv", b"a,b\n1,2\n", "text/csv")}}),
]


def test_developer_holds_every_permission(client, dev, db):
    me = client.get(f"{API}/auth/me", headers=dev).json()
    assert RESERVED_PERMISSIONS <= set(me["permissions"]) and "stores.manage" in me["permissions"] and "orders.overview" in me["permissions"]
    assert me["roles"] == ["developer"] and me["is_admin"] is False


def test_admin_does_not_get_the_sheet_permission(client, admin):
    me = client.get(f"{API}/auth/me", headers=admin).json()
    assert "sheets.sync" not in me["permissions"] and "stores.manage" in me["permissions"]


@pytest.mark.parametrize("method,url,kw", SHEET_CALLS)
def test_sheet_features_are_developer_only(client, admin, emp, dev, method, url, kw):
    for who in (admin, emp):
        assert client.request(method, url, headers=who, **kw).status_code == 403
    assert client.request(method, url, headers=dev, **kw).status_code != 403   # allowed in (any 4xx here is about the data)


def test_developer_can_reach_every_admin_area(client, dev, db):
    for url in (f"{API}/stores", f"{API}/employees", f"{API}/activity", f"{API}/cash-purchases", f"{API}/partners"):
        assert client.get(url, headers=dev).status_code == 200, url
    all_codes = {c for (c,) in db.query(Permission.code)}
    assert set(client.get(f"{API}/auth/me", headers=dev).json()["permissions"]) == all_codes


def test_admin_gets_everything_except_the_reserved_permissions(client, admin, db):
    all_codes = {c for (c,) in db.query(Permission.code)}
    assert set(client.get(f"{API}/auth/me", headers=admin).json()["permissions"]) == all_codes - RESERVED_PERMISSIONS


def test_no_one_can_grant_the_sheet_permission(client, admin, emp, make_user, db):
    code, _, uid = make_user("employee")
    me = client.get(f"{API}/employees?q={code}", headers=admin).json()["items"][0]["id"]
    r = client.put(f"{API}/employees/{me}/permissions", headers=admin, json={"codes": ["orders.view", "sheets.sync"]})
    assert r.status_code == 422
    r = client.post(f"{API}/employees", headers=admin, json={
        "employee_code": "T-DEV-X", "full_name": "X", "password": "Passw0rd!x", "permission_codes": ["sheets.sync"]})
    assert r.status_code == 422
    # even a stray database row is ignored for anyone who isn't a developer
    db.add(__import__("app.models.user_permission", fromlist=["UserPermission"]).UserPermission(
        user_id=uid, permission_id=db.query(Permission).filter_by(code="sheets.sync").one().id))
    db.commit()
    assert "sheets.sync" not in UserRepository(db).get_permission_codes(uid)


def test_the_permission_catalogue_and_team_list_hide_the_developer(client, admin, dev, db):
    dev_code = client.get(f"{API}/auth/me", headers=dev).json()["employee_code"]
    groups = client.get(f"{API}/permissions", headers=admin).json()
    assert "sheets.sync" not in {p["code"] for g in groups for p in g["permissions"]}
    team = client.get(f"{API}/employees?page_size=100", headers=admin).json()["items"]
    assert dev_code not in {e["employee_code"] for e in team}
    dev_id = db.query(User).filter_by(employee_code=dev_code).one().id
    assert client.get(f"{API}/employees/{dev_id}", headers=admin).status_code == 404
    assert client.post(f"{API}/employees/{dev_id}/deactivate", headers=admin).status_code == 404


def test_no_api_account_type_creates_a_developer(client, admin):
    r = client.post(f"{API}/employees", headers=admin, json={
        "employee_code": "T-DEV-Y", "full_name": "Y", "password": "Passw0rd!y", "account_type": "developer"})
    assert r.status_code == 422


def test_the_demo_login_is_admin_and_developer(client):
    me = client.get(f"{API}/auth/me", headers=auth(login(client, "DEV001").json()["access_token"])).json()
    assert set(me["roles"]) == {"admin", "developer"} and "sheets.sync" in me["permissions"] and "stores.manage" in me["permissions"]


def test_create_developer_script_makes_the_account(db):
    from scripts.create_developer import make_developer

    u = make_developer(db, "T-DEV-Z", "Script Dev", "Passw0rd!z")
    try:
        roles = [r for (r,) in db.query(Role.code).join(UserRole, UserRole.role_id == Role.id).filter(UserRole.user_id == u.id)]
        assert roles == ["developer"]
        assert UserRepository(db).get_permission_codes(u.id) == {c for (c,) in db.query(Permission.code)}
    finally:
        db.query(UserRole).filter_by(user_id=u.id).delete()
        db.query(User).filter_by(id=u.id).delete()
        db.commit()
