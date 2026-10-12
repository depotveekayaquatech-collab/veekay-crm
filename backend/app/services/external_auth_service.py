"""
Sign-in for vendors and POCs (external_accounts). Mirrors auth_service + session_service for CRM users, with its own
session table and token types so the two worlds can never be mixed up. There is deliberately no change-password step:
the password the admin set stays. Wrong-password lockout and rotation / reuse detection work as they do for staff.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    burn_password_check,
    create_external_access_token,
    create_external_refresh_token,
    decode_claims,
    verify_password,
)
from app.models.external_account import ExternalAccount, ExternalSession
from app.schemas.auth import TokenPair

GENERIC_ERROR = "Incorrect email or password."
EXPIRED = "Your session has expired. Please sign in again."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expired() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, EXPIRED, headers={"WWW-Authenticate": "Bearer"})


def _issue(db: Session, account: ExternalAccount, family_id: uuid.UUID, user_agent: str | None, ip: str | None) -> TokenPair:
    now = _now()
    jti = uuid.uuid4()
    db.add(ExternalSession(
        id=jti, account_id=account.id, family_id=family_id, created_at=now, last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=(user_agent or "")[:255] or None, ip=ip,
    ))
    db.flush()
    return TokenPair(
        access_token=create_external_access_token(account.id, family_id),
        refresh_token=create_external_refresh_token(account.id, family_id, jti),
    )


def _revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(
        update(ExternalSession)
        .where(ExternalSession.family_id == family_id, ExternalSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def login(db: Session, email: str, password: str, *, user_agent: str | None = None, ip: str | None = None) -> TokenPair:
    account = db.execute(select(ExternalAccount).where(ExternalAccount.email == email.strip().lower())).scalar_one_or_none()
    if account is None:
        burn_password_check(password)  # same error and timing as a wrong password: no account enumeration
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_ERROR)

    if account.locked_until is not None and _now() < account.locked_until:
        minutes = max(1, int((account.locked_until - _now()).total_seconds() // 60) + 1)
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Too many failed attempts. Try again in about {minutes} minute{'s' if minutes > 1 else ''}.")

    if not verify_password(password, account.password_hash):
        account.failed_login_attempts += 1
        if account.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            account.locked_until = _now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            account.failed_login_attempts = 0
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_ERROR)

    if not account.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated. Contact your administrator.")

    account.failed_login_attempts = 0
    account.locked_until = None
    # Signing in again from the same device replaces that device's older session; old finished rows are tidied.
    db.execute(delete(ExternalSession).where(
        (ExternalSession.expires_at < _now() - timedelta(days=7)) | (ExternalSession.revoked_at < _now() - timedelta(days=30))
    ))
    ua = (user_agent or "")[:255] or None
    same = [
        ExternalSession.account_id == account.id, ExternalSession.revoked_at.is_(None), ExternalSession.expires_at > _now(),
        ExternalSession.user_agent.is_(None) if ua is None else ExternalSession.user_agent == ua,
        ExternalSession.ip.is_(None) if ip is None else ExternalSession.ip == ip,
    ]
    for family in set(db.execute(select(ExternalSession.family_id).where(*same)).scalars()):
        _revoke_family(db, family)
    pair = _issue(db, account, uuid.uuid4(), user_agent, ip)
    db.commit()
    return pair


def rotate(db: Session, refresh_token: str, *, user_agent: str | None = None, ip: str | None = None) -> TokenPair:
    try:
        claims = decode_claims(refresh_token, TokenType.EXT_REFRESH)
    except InvalidTokenError as exc:
        raise _expired() from exc

    row = db.get(ExternalSession, claims.jti)
    if row is None or row.account_id != claims.user_id or row.family_id != claims.family_id:
        raise _expired()
    now = _now()
    if row.expires_at <= now:
        raise _expired()
    if row.revoked_at is not None:
        # A rotated token presented again: seconds later it is two tabs racing, after that it means a copied token.
        if row.replaced_by is not None and (now - row.revoked_at).total_seconds() > settings.REFRESH_REUSE_GRACE_SECONDS:
            _revoke_family(db, row.family_id)
            db.commit()
        raise _expired()

    account = db.get(ExternalAccount, claims.user_id)
    if account is None or not account.is_active:
        _revoke_family(db, row.family_id)
        db.commit()
        raise _expired()

    pair = _issue(db, account, row.family_id, user_agent or row.user_agent, ip or row.ip)
    row.revoked_at = now
    row.replaced_by = decode_claims(pair.refresh_token, TokenType.EXT_REFRESH).jti
    row.last_used_at = now
    db.commit()
    return pair


def logout(db: Session, refresh_token: str | None) -> None:
    """Never raises: signing out always 'works'."""
    if not refresh_token:
        return
    try:
        claims = decode_claims(refresh_token, TokenType.EXT_REFRESH)
    except InvalidTokenError:
        return
    _revoke_family(db, claims.family_id)
    db.commit()


def authenticate(db: Session, token: str | None) -> ExternalAccount:
    """The account behind an access token, only while its session is alive and the account is active."""
    if token is None:
        raise _expired()
    try:
        claims = decode_claims(token, TokenType.EXT_ACCESS)
    except InvalidTokenError as exc:
        raise _expired() from exc
    account = db.get(ExternalAccount, claims.user_id)
    if account is None or not account.is_active:
        raise _expired()
    alive = db.execute(
        select(ExternalSession.id).where(
            ExternalSession.account_id == account.id, ExternalSession.family_id == claims.family_id,
            ExternalSession.revoked_at.is_(None), ExternalSession.expires_at > _now(),
        ).limit(1)
    ).first()
    if alive is None:
        raise _expired()
    return account
