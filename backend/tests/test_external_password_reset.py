"""Admin sets / resets a vendor or POC password: the old one stops working, every phone is signed out, the lock clears."""
from app.core.config import settings
from app.models.audit_log import AuditLog

from .conftest import API, auth
from .test_external_portal import PW, _login, make_account  # noqa: F401  (fixture)


def test_reset_with_a_chosen_password(client, admin, make_account):
    a = make_account()
    t = _login(client, a.email).json()
    assert client.get(f"{API}/external/me", headers=auth(t["access_token"])).status_code == 200

    r = client.post(f"{API}/external-accounts/{a.id}/reset-password", json={"password": "Aqua-2026!x"}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json() == {"email": a.email, "password": "Aqua-2026!x", "generated": False}
    assert r.headers["cache-control"] == "private, no-store"

    assert _login(client, a.email, PW).status_code == 401                      # the old password is dead
    assert _login(client, a.email, "Aqua-2026!x").status_code == 200
    assert client.get(f"{API}/external/me", headers=auth(t["access_token"])).status_code == 401   # old phone signed out
    assert client.post(f"{API}/external/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_reset_without_a_password_generates_a_random_one_and_unlocks(client, admin, make_account):
    a = make_account()
    for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
        _login(client, a.email, "wrong")
    assert _login(client, a.email, PW).status_code == 403                      # locked
    r = client.post(f"{API}/external-accounts/{a.id}/reset-password", json={}, headers=admin).json()
    assert r["generated"] is True and len(r["password"]) >= 10 and r["password"] != PW
    assert _login(client, a.email, r["password"]).status_code == 200           # unlocked and working


def test_after_a_reset_the_export_no_longer_shows_the_standard_password(client, admin, make_account):
    a = make_account(must_change=True)
    before = client.get(f"{API}/external-accounts/export", params={"q": a.email}, headers=admin).text
    assert PW in before
    client.post(f"{API}/external-accounts/{a.id}/reset-password", json={"password": "Different-77"}, headers=admin)
    after = client.get(f"{API}/external-accounts/export", params={"q": a.email}, headers=admin).text
    assert PW not in after and "Different-77" not in after                      # passwords are never exported once set


def test_who_may_reset_and_what_is_logged(client, admin, emp, make_account, db):
    a = make_account()
    url = f"{API}/external-accounts/{a.id}/reset-password"
    assert client.post(url, json={}, headers=emp).status_code == 403
    assert client.post(url, json={}).status_code == 401
    assert client.post(url, json={"password": "abc"}, headers=admin).status_code == 422          # too short
    assert client.post(f"{API}/external-accounts/00000000-0000-0000-0000-000000000000/reset-password", json={}, headers=admin).status_code == 404
    assert client.post(url, json={"password": "Chosen-pass-1"}, headers=admin).status_code == 200
    log = db.query(AuditLog).filter(AuditLog.action == "external_account.password_reset").order_by(AuditLog.created_at.desc()).first()
    assert log.metadata_json == {"login": a.email, "generated": False}
    assert "Chosen-pass-1" not in str(log.metadata_json)                         # the password is never written to the log


def test_vendor_and_poc_sign_in_get_the_strict_sign_in_rate_limit():
    from app.core.middleware import _bucket

    for path in ("/auth/login", "/external/auth/login", "/external/auth/refresh"):
        assert _bucket("POST", f"{API}{path}")[0] == "auth", path
    assert _bucket("POST", f"{API}/external/tickets")[0] == "heavy"          # uploads are throttled too
    assert _bucket("GET", f"{API}/external/orders")[0] == "default"


def test_app_crash_reports_are_accepted_without_a_login_and_logged(client, caplog):
    import logging

    body = {"app": "partner-mobile", "version": "1.0.0", "platform": "android 15", "screen": "/staff/scan", "message": "Boom\nline two", "stack": "at x", "fatal": True}
    with caplog.at_level(logging.ERROR, logger="veekay.client_errors"):
        r = client.post(f"{API}/public/client-errors", json=body)
    assert r.status_code == 204
    assert any("FATAL Boom line two" in m and "partner-mobile 1.0.0" in m for m in caplog.messages)
    assert client.post(f"{API}/public/client-errors", json={**body, "message": "x" * 501}).status_code == 422   # size is capped
    assert client.post(f"{API}/public/client-errors", json={"app": "x"}).status_code == 422
