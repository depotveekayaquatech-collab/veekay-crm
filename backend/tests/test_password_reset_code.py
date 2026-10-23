"""Forgot password by emailed one-time code, and the nightly audit-log purge."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core import mailer
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import password_reset_service
from app.services.audit_retention import purge_old_audit

from .conftest import API, login

FORGOT = f"{API}/auth/forgot-password"
RESET = f"{API}/auth/reset-with-code"
GENERIC = "If this Employee ID has an email address on file"


@pytest.fixture()
def outbox(monkeypatch):
    """Mail switched on, nothing really sent: every message lands in this list."""
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_USER", "u@test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "x")
    monkeypatch.setattr(mailer, "send_mail", lambda to, subject, body: sent.append((to, subject, body)) or True)
    return sent


def _code(outbox) -> str:
    return outbox[-1][2].split("code is ")[1][:6]


def _person(make_user, db, email="worker@example.com", **kw):
    code, pw, uid = make_user(**kw)
    u = db.get(User, uid)
    u.email = email
    db.commit()
    return code, pw, uid


def test_switched_off_without_smtp(client, make_user, db):
    code, _, _ = _person(make_user, db)
    r = client.post(FORGOT, json={"employee_code": code})
    assert r.status_code == 200 and r.json()["available"] is False


def test_a_code_resets_the_password_and_signs_everything_out(client, make_user, db, outbox):
    code, pw, uid = _person(make_user, db, password="Before-Pw-2026")
    first = login(client, code, pw).json()
    r = client.post(FORGOT, json={"employee_code": code})
    assert r.status_code == 200 and r.json()["message"].startswith(GENERIC) and r.json()["available"] is True
    assert outbox[-1][0] == "worker@example.com" and "Before-Pw-2026" not in outbox[-1][2]
    otp = _code(outbox)
    assert db.get(User, uid).reset_code_hash and otp not in db.get(User, uid).reset_code_hash   # only a keyed hash is stored

    done = client.post(RESET, json={"employee_code": code, "code": otp, "new_password": "  Brand-New-Pw-77  "})
    assert done.status_code == 204, done.text
    assert login(client, code, "Brand-New-Pw-77").status_code == 200
    assert login(client, code, "Before-Pw-2026").status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401   # old devices signed out
    db.expire_all()
    u = db.get(User, uid)
    assert u.reset_code_hash is None and u.must_change_password is False
    assert client.post(RESET, json={"employee_code": code, "code": otp, "new_password": "Another-Pw-2026x"}).status_code == 400   # one use only


def test_the_answer_is_the_same_for_unknown_ids_and_people_without_email(client, make_user, db, outbox):
    no_email, _, _ = make_user()
    known = client.post(FORGOT, json={"employee_code": no_email})
    unknown = client.post(FORGOT, json={"employee_code": "NO-SUCH-ID"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
    assert outbox == []


def test_admins_and_developers_cannot_use_it(client, outbox, dev):
    for code in ("ADMIN001",):
        assert client.post(FORGOT, json={"employee_code": code}).status_code == 200
    assert outbox == []


def test_wrong_codes_burn_the_code_after_the_limit(client, make_user, db, outbox):
    code, pw, _ = _person(make_user, db)
    client.post(FORGOT, json={"employee_code": code})
    otp = _code(outbox)
    wrong = "000000" if otp != "000000" else "111111"
    for _ in range(settings.RESET_CODE_MAX_ATTEMPTS):
        assert client.post(RESET, json={"employee_code": code, "code": wrong, "new_password": "Whatever-Pw-2026"}).status_code == 400
    assert client.post(RESET, json={"employee_code": code, "code": otp, "new_password": "Whatever-Pw-2026"}).status_code == 400   # even the right one is dead now
    assert login(client, code, pw).status_code == 200                                                                            # old password untouched


def test_an_expired_code_is_refused(client, make_user, db, outbox):
    code, _, uid = _person(make_user, db)
    client.post(FORGOT, json={"employee_code": code})
    u = db.get(User, uid)
    u.reset_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.post(RESET, json={"employee_code": code, "code": _code(outbox), "new_password": "Whatever-Pw-2026"}).status_code == 400


def test_a_weak_password_keeps_the_code_alive(client, make_user, db, outbox):
    code, _, _ = _person(make_user, db)
    client.post(FORGOT, json={"employee_code": code})
    otp = _code(outbox)
    assert client.post(RESET, json={"employee_code": code, "code": otp, "new_password": "short1"}).status_code == 422
    assert client.post(RESET, json={"employee_code": code, "code": otp, "new_password": "Strong-Enough-Pw-9"}).status_code == 204


def test_only_a_few_codes_per_hour_per_account(client, make_user, db, outbox):
    code, _, _ = _person(make_user, db)
    for _ in range(settings.RESET_CODE_MAX_PER_HOUR + 3):
        assert client.post(FORGOT, json={"employee_code": code}).status_code == 200
    assert len(outbox) == settings.RESET_CODE_MAX_PER_HOUR


def test_a_locked_account_is_unlocked_by_a_reset(client, make_user, db, outbox):
    code, _, uid = _person(make_user, db)
    for _ in range(settings.MAX_FAILED_LOGIN_ATTEMPTS):
        login(client, code, "wrong-password")
    assert db.get(User, uid).status == "locked"
    client.post(FORGOT, json={"employee_code": code})
    assert client.post(RESET, json={"employee_code": code, "code": _code(outbox), "new_password": "Unlocked-Pw-2026"}).status_code == 204
    assert login(client, code, "Unlocked-Pw-2026").status_code == 200


# ------------------------------------------------------------------ audit retention
def _log(db, action, days_old):
    row = AuditLog(action=action, entity_type="t", entity_id="x", metadata_json={"t": "purge-test"})
    db.add(row)
    db.flush()
    row.created_at = datetime.now(timezone.utc) - timedelta(days=days_old)
    db.commit()
    return row.id


def test_old_audit_rows_are_removed_for_good_but_recent_and_needed_ones_stay(db):
    from sqlalchemy import text

    old = _log(db, "test.old", 400)
    recent = _log(db, "test.recent", 5)
    keep = _log(db, "order.imported", 400)
    removed = purge_old_audit(db, keep_days=60)
    assert removed >= 1
    db.expire_all()
    assert db.get(AuditLog, old) is None and db.get(AuditLog, recent) is not None and db.get(AuditLog, keep) is not None
    # the delete trigger's safety copy is cleaned too, otherwise the purge would only move the data
    assert db.execute(text("SELECT count(*) FROM deleted_rows WHERE table_name='audit_logs' AND row_id=:i"), {"i": str(old)}).scalar() == 0
    db.query(AuditLog).filter(AuditLog.id.in_([recent, keep])).delete(synchronize_session=False)
    db.commit()
    assert purge_old_audit(db, keep_days=0) == 0                      # 0 = keep everything
