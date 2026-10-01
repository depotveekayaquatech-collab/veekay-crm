"""
Password hashing, password policy + JWT issuing/verification.

This is the ONLY place password hashes and tokens are created or
checked. Nothing outside this module should touch bcrypt or jose
directly, so the algorithm can change in one place later.

Tokens:
  access  — short-lived, carries the session family id (`sid`); accepted only
            while that family is still active server-side.
  refresh — long-lived, its `jti` is a row in refresh_sessions so it can be
            rotated, detected if reused, and revoked.
"""
import re
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS)

# Used to keep login timing identical whether or not the account exists.
_DUMMY_HASH = pwd_context.hash("not-a-real-password")


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def burn_password_check(plain_password: str) -> None:
    """Spend the same time a real password check would (user-enumeration defence)."""
    pwd_context.verify(plain_password, _DUMMY_HASH)


# --------------------------------------------------------------------------
# password policy
# --------------------------------------------------------------------------

_COMMON = {
    "password", "password1", "password12", "password123", "pass@123", "pass@1234", "admin@123",
    "admin123", "welcome1", "welcome123", "qwerty123", "qwertyuiop", "letmein123", "iloveyou1",
    "changeme123", "veekay123", "veekay@123", "12345678", "123456789", "1234567890", "abc12345",
}
_TEMP_ALPHABET = string.ascii_letters.replace("l", "").replace("I", "").replace("O", "") + "23456789"


def validate_password_strength(
    password: str, *, employee_code: str = "", current_hash: str | None = None
) -> str | None:
    """None if acceptable, else a human-readable reason."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return f"Use at least {settings.PASSWORD_MIN_LENGTH} characters."
    if len(password) > 128:
        return "Use at most 128 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Include at least one letter and one number."
    low = password.lower()
    if low in _COMMON or low.strip("!@#$%^&*") in _COMMON:
        return "That password is too common. Choose something less guessable."
    if len(set(low)) < 4:
        return "That password is too repetitive."
    code = employee_code.strip().lower()
    if len(code) >= 3 and code in low:
        return "Your password shouldn't contain your Employee ID."
    if current_hash and verify_password(password, current_hash):
        return "Your new password must be different from the current one."
    return None


def generate_temp_password() -> str:
    """10 unambiguous characters with at least one letter and one digit."""
    while True:
        pw = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(max(10, settings.PASSWORD_MIN_LENGTH)))
        if re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw):
            return pw


# --------------------------------------------------------------------------
# tokens
# --------------------------------------------------------------------------

def _create_token(subject: uuid.UUID, token_type: TokenType, expires_delta: timedelta, *, family: uuid.UUID, jti: uuid.UUID | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type.value,
        "sid": str(family),
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(jti or uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, family_id: uuid.UUID) -> str:
    return _create_token(
        user_id, TokenType.ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), family=family_id
    )


def create_refresh_token(user_id: uuid.UUID, family_id: uuid.UUID, jti: uuid.UUID) -> str:
    return _create_token(
        user_id, TokenType.REFRESH, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), family=family_id, jti=jti
    )


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    family_id: uuid.UUID
    jti: uuid.UUID


def decode_claims(token: str, expected_type: TokenType) -> TokenClaims:
    """Decode + validate a JWT. Raises InvalidTokenError on any failure — expired,
    malformed, wrong type, or missing the session family. Callers never see jose's
    exceptions directly."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], options={"require": ["exp", "sub"]}
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Token is invalid or expired") from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Expected a {expected_type.value} token")
    try:
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            family_id=uuid.UUID(payload["sid"]),  # tokens from before sessions existed have no sid -> invalid
            jti=uuid.UUID(payload["jti"]),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Token is malformed") from exc
