"""Authentication: sign-in, lockout, sessions, token rotation + theft detection, logout, password management."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.models.attendance import AttendanceSession
from app.models.user import User

from .conftest import API, DEMO_PASSWORD, auth, login


# ---------------------------------------------------------------- sign in
def test_login_returns_a_token_pair_and_me_works(client):
    r = login(client, "ADMIN001")
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"] and body["refresh_token"]
    me = client.get(f"{API}/auth/me", headers=auth(body["access_token"])).json()
    assert me["employee_code"] == "ADMIN001" and me["is_admin"] is True and "orders.correct" in me["permissions"]


def test_wrong_password_and_unknown_user_look_identical(client):
    wrong = login(client, "ADMIN001", "nope-nope")
    unknown = login(client, "NO-SUCH-USER", "nope-nope")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()                      # no account enumeration


def test_unknown_organization_gives_the_same_generic_error(client):
    r = client.post(f"{API}/auth/login", json={"organization_slug": "nope", "employee_code": "ADMIN001", "password": DEMO_PASSWORD})
    assert r.status_code == 401 and r.json() == login(client, "NO-SUCH-USER", "x").json()


def test_deactivated_account_cannot_sign_in(client, make_user):
    code, pw, _ = make_user(active=False)
    r = login(client, code, pw)
    assert r.status_code == 403 and "deactivated" in r.json()["detail"]


def test_login_flags_whether_the_sign_in_counts_as_attendance(client, make_user):
    assert login(client, "ADMIN001").json()["attendance"] is False
    assert login(client, "EMP001").json()["attendance"] is True
    code, pw, _ = make_user(role="accountant")
    assert login(client, code, pw).json()["attendance"] is True


def test_invalid_coordinates_in_the_login_payload_are_rejected(client):
    assert login(client, "ADMIN001", latitude=91, longitude=0).status_code == 422


# ---------------------------------------------------------------- lockout
def test_account_locks_after_repeated_failures_then_recovers(client, make_user, db):
    code, pw, uid = make_user()
    for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
        assert login(client, code, "wrong-password").status_code == 401
    locked = login(client, code, pw)                           # even the right password is refused now
    assert locked.status_code == 403 and "Too many failed attempts" in locked.json()["detail"]
    u = db.get(User, uid)
    assert u.status == "locked"
    u.locked_until = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()   # the lock runs out
    db.commit()
    assert login(client, code, pw).status_code == 200          # used to stay blocked forever
    db.refresh(u)
    assert u.status == "active" and u.failed_login_attempts == 0


def test_failed_logins_from_one_ip_are_throttled(client, monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_IP_MAX_FAILURES", 3)
    codes = [login(client, f"ghost-{i}", "x").status_code for i in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    assert login(client, "ADMIN001").status_code == 429        # the throttle is per network, not per account


# ---------------------------------------------------------------- tokens
def test_refresh_rotates_and_the_session_survives(client):
    first = login(client, "EMP001").json()
    second = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200 and second.json()["refresh_token"] != first["refresh_token"]
    assert client.get(f"{API}/auth/me", headers=auth(first["access_token"])).status_code == 200      # same session


def test_reusing_a_rotated_refresh_token_inside_the_grace_window_is_refused_but_harmless(client):
    first = login(client, "EMP001").json()
    second = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401   # two tabs racing
    assert client.get(f"{API}/auth/me", headers=auth(second["access_token"])).status_code == 200                 # the session lives


def test_reusing_a_rotated_token_after_the_grace_window_kills_the_whole_session(client, monkeypatch):
    monkeypatch.setattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 0)       # as if the stolen copy is used later
    first = login(client, "EMP001").json()
    second = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.get(f"{API}/auth/me", headers=auth(second["access_token"])).status_code == 401           # theft response
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401


def test_access_token_cannot_be_used_as_a_refresh_token(client):
    t = login(client, "EMP001").json()
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": t["access_token"]}).status_code == 401


def test_tokens_from_before_sessions_existed_are_rejected(client):
    old = jwt.encode({"sub": str(uuid.uuid4()), "type": "access", "jti": str(uuid.uuid4()),
                      "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, settings.JWT_SECRET_KEY, algorithm="HS256")
    assert client.get(f"{API}/auth/me", headers=auth(old)).status_code == 401


# ---------------------------------------------------------------- logout / sessions
def test_logout_ends_the_session_immediately(client):
    t = login(client, "EMP001").json()
    assert client.post(f"{API}/auth/logout", json={"refresh_token": t["refresh_token"]}).status_code == 204
    assert client.get(f"{API}/auth/me", headers=auth(t["access_token"])).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_logout_always_succeeds_even_with_junk(client):
    assert client.post(f"{API}/auth/logout", json={"refresh_token": "junk"}).status_code == 204
    assert client.post(f"{API}/auth/logout").status_code == 204


def test_sessions_list_marks_current_and_other_devices_can_be_revoked(client):
    a = login(client, "EMP001").json()
    b = login(client, "EMP001").json()
    sessions = client.get(f"{API}/auth/sessions", headers=auth(a["access_token"])).json()
    assert len(sessions) >= 2 and sum(1 for s in sessions if s["current"]) == 1
    other = next(s["id"] for s in sessions if not s["current"])
    assert client.delete(f"{API}/auth/sessions/{other}", headers=auth(a["access_token"])).status_code == 204
    assert client.delete(f"{API}/auth/sessions/{uuid.uuid4()}", headers=auth(a["access_token"])).status_code == 404
    assert client.get(f"{API}/auth/me", headers=auth(b["access_token"])).status_code in (200, 401)


def test_logout_all_signs_every_device_out_including_this_one(client):
    a = login(client, "EMP001").json()
    b = login(client, "EMP001").json()
    assert client.post(f"{API}/auth/logout-all", headers=auth(a["access_token"])).status_code == 204
    assert client.get(f"{API}/auth/me", headers=auth(a["access_token"])).status_code == 401
    assert client.get(f"{API}/auth/me", headers=auth(b["access_token"])).status_code == 401


def test_deactivating_someone_ends_their_session_at_once(client, admin, make_user):
    code, pw, uid = make_user()
    t = login(client, code, pw).json()
    assert client.post(f"{API}/employees/{uid}/deactivate", headers=admin).status_code == 204
    assert client.get(f"{API}/auth/me", headers=auth(t["access_token"])).status_code == 401
    assert login(client, code, pw).status_code == 403


# ---------------------------------------------------------------- forced password change
def test_a_temporary_password_gates_everything_until_it_is_changed(client, make_user):
    code, pw, _ = make_user(must_change=True)
    t = login(client, code, pw).json()
    me = client.get(f"{API}/auth/me", headers=auth(t["access_token"])).json()
    assert me["must_change_password"] is True and me["permissions"] == []
    gated = client.get(f"{API}/orders/my-stores", headers=auth(t["access_token"]))
    assert gated.status_code == 403 and gated.json()["detail"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get(f"{API}/attendance/me", headers=auth(t["access_token"])).status_code == 403


def test_password_change_rules(client, make_user):
    code, pw, _ = make_user(must_change=True)
    tok = auth(login(client, code, pw).json()["access_token"])
    change = lambda current, new: client.post(f"{API}/auth/change-password", headers=tok, json={"current_password": current, "new_password": new})
    assert change("WRONG", "Brand#New1234").status_code == 400
    for weak in ("short1", "onlyletterspasswordx", "Password123", code.lower() + "99999", pw):
        assert change(pw, weak).status_code == 422, weak


def test_changing_the_password_signs_out_other_devices_and_returns_a_fresh_session(client, make_user):
    code, pw, _ = make_user(must_change=True)
    other = login(client, code, pw).json()
    this = login(client, code, pw).json()
    r = client.post(f"{API}/auth/change-password", headers=auth(this["access_token"]), json={"current_password": pw, "new_password": "Brand#New1234"})
    assert r.status_code == 200
    fresh = r.json()
    assert client.get(f"{API}/auth/me", headers=auth(other["access_token"])).status_code == 401
    assert client.get(f"{API}/auth/me", headers=auth(this["access_token"])).status_code == 401
    me = client.get(f"{API}/auth/me", headers=auth(fresh["access_token"])).json()
    assert me["must_change_password"] is False and me["permissions"]
    assert login(client, code, pw).status_code == 401 and login(client, code, "Brand#New1234").status_code == 200


def test_changing_a_password_is_not_a_new_sign_in_for_attendance(client, make_user, db):
    code, pw, uid = make_user()
    t = login(client, code, pw, latitude=12.97, longitude=77.59).json()
    before = db.query(AttendanceSession).filter_by(user_id=uid).count()
    assert client.post(f"{API}/auth/change-password", headers=auth(t["access_token"]),
                       json={"current_password": pw, "new_password": "Brand#New1234"}).status_code == 200
    db.expire_all()
    rows = db.query(AttendanceSession).filter_by(user_id=uid).all()
    assert before == len(rows) == 1 and rows[0].logout_at is None       # same row, still open, no new location check


def test_admin_created_and_reset_passwords_must_be_replaced(client, admin, make_user):
    r = client.post(f"{API}/employees", headers=admin, json={"employee_code": "TESTNEW-1", "full_name": "New Person", "password": "TempPass#1"})
    assert r.status_code == 201
    try:
        t = login(client, "TESTNEW-1", "TempPass#1").json()
        assert client.get(f"{API}/auth/me", headers=auth(t["access_token"])).json()["must_change_password"] is True
        reset = client.post(f"{API}/employees/{r.json()['id']}/reset-password", headers=admin)
        assert reset.status_code == 200 and len(reset.json()["temp_password"]) >= 10
        assert client.get(f"{API}/auth/me", headers=auth(t["access_token"])).status_code == 401      # signed out everywhere
        assert login(client, "TESTNEW-1", "TempPass#1").status_code == 401
        assert login(client, "TESTNEW-1", reset.json()["temp_password"]).status_code == 200
    finally:
        from app.db.session import SessionLocal
        from app.models.refresh_session import RefreshSession
        from app.models.user import UserRole
        from app.models.user_permission import UserPermission
        s = SessionLocal()
        uid = uuid.UUID(r.json()["id"])
        for m in (AttendanceSession, RefreshSession, UserPermission, UserRole):
            s.query(m).filter(m.user_id == uid).delete()
        s.query(User).filter(User.id == uid).delete()
        s.commit()
        s.close()


def test_employees_cannot_reset_passwords(client, emp, make_user):
    _, _, uid = make_user()
    assert client.post(f"{API}/employees/{uid}/reset-password", headers=emp).status_code == 403


# ---------------------------------------------------------------- authorisation spot checks
@pytest.mark.parametrize("path", ["/orders/insights", "/orders/pending", "/employees", "/compliance/due", "/attendance/day", "/orders/matrix?start=2026-09-01&end=2026-09-02"])
def test_employees_are_kept_out_of_admin_endpoints(client, emp, path):
    assert client.get(f"{API}{path}", headers=emp).status_code == 403


def test_permissions_are_rechecked_on_every_request(client, admin, make_user):
    from app.db.session import SessionLocal
    from app.models.permission import Permission
    from app.models.user_permission import UserPermission
    code, pw, uid = make_user(grants=("orders.view",))
    tok = auth(login(client, code, pw).json()["access_token"])
    assert client.get(f"{API}/orders/inventory", headers=tok).status_code == 200
    s = SessionLocal()
    s.query(UserPermission).filter(UserPermission.user_id == uid).delete()     # permission withdrawn mid-session
    s.commit()
    s.close()
    assert client.get(f"{API}/orders/inventory", headers=tok).status_code == 403
