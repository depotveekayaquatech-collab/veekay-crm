"""Password policy and JWT handling — pure functions, no database needed beyond import-time settings."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_claims,
    generate_temp_password,
    hash_password,
    validate_password_strength,
    verify_password,
)


@pytest.mark.parametrize("pw,reason", [
    ("short1", "at least"),
    ("onlylettersandmore", "letter and one number"),
    ("1234567890123", "letter and one number"),
    ("Password123", "too common"),
    ("Pass@123", "at least"),
    ("aaaaaaaaaa1", "repetitive"),
])
def test_weak_passwords_are_rejected_with_a_reason(pw, reason):
    msg = validate_password_strength(pw)
    assert msg and reason in msg


def test_password_may_not_contain_the_employee_id():
    assert "Employee ID" in validate_password_strength("xx-EMP0042-yy9", employee_code="EMP0042")


def test_new_password_must_differ_from_current():
    current = hash_password("Fresh#Horse42")
    assert "different" in validate_password_strength("Fresh#Horse42", current_hash=current)


def test_a_good_password_is_accepted():
    assert validate_password_strength("Fresh#Horse42", employee_code="EMP1") is None


def test_hash_roundtrip():
    h = hash_password("Fresh#Horse42")
    assert h != "Fresh#Horse42" and verify_password("Fresh#Horse42", h) and not verify_password("nope", h)


def test_generated_temp_passwords_pass_the_policy_and_are_unique():
    pws = {generate_temp_password() for _ in range(25)}
    assert len(pws) == 25
    assert all(validate_password_strength(p) is None for p in pws)


def test_token_roundtrip_carries_user_and_session():
    uid, fam, jti = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    c = decode_claims(create_access_token(uid, fam), TokenType.ACCESS)
    assert (c.user_id, c.family_id) == (uid, fam)
    r = decode_claims(create_refresh_token(uid, fam, jti), TokenType.REFRESH)
    assert r.jti == jti


def test_a_token_of_the_wrong_type_is_rejected():
    uid, fam = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(InvalidTokenError):
        decode_claims(create_access_token(uid, fam), TokenType.REFRESH)
    with pytest.raises(InvalidTokenError):
        decode_claims(create_refresh_token(uid, fam, uuid.uuid4()), TokenType.ACCESS)


def test_tampered_expired_and_garbage_tokens_are_rejected():
    uid, fam = uuid.uuid4(), uuid.uuid4()
    good = create_access_token(uid, fam)
    with pytest.raises(InvalidTokenError):
        decode_claims(good[:-3] + "abc", TokenType.ACCESS)
    with pytest.raises(InvalidTokenError):
        decode_claims("not.a.token", TokenType.ACCESS)
    expired = jwt.encode(
        {"sub": str(uid), "type": "access", "sid": str(fam), "jti": str(uuid.uuid4()),
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_claims(expired, TokenType.ACCESS)


def test_tokens_signed_with_another_key_or_without_a_session_are_rejected():
    uid = uuid.uuid4()
    payload = {"sub": str(uid), "type": "access", "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    foreign = jwt.encode({**payload, "sid": str(uuid.uuid4())}, "some-other-secret-key-0123456789abcdef", algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_claims(foreign, TokenType.ACCESS)
    no_session = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")   # a pre-upgrade token has no `sid`
    with pytest.raises(InvalidTokenError):
        decode_claims(no_session, TokenType.ACCESS)


def test_the_none_algorithm_is_never_accepted():
    uid, fam = uuid.uuid4(), uuid.uuid4()
    forged = jwt.encode({"sub": str(uid), "type": "access", "sid": str(fam), "jti": str(uuid.uuid4()),
                         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, key=None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_claims(forged, TokenType.ACCESS)
