"""
Server-side refresh-token sessions (see models/refresh_session.py).

All session state changes go through here: start, rotate (with reuse
detection), revoke one / all, list, and "is this access token's session
still alive". Callers commit.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_claims,
)
from app.models.refresh_session import RefreshSession
from app.models.user import User, UserStatus
from app.services import attendance_service
from app.schemas.auth import TokenPair

EXPIRED = "Your session has expired. Please sign in again."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unauthorized(detail: str = EXPIRED) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


def _issue(db: Session, user: User, family_id: uuid.UUID, user_agent: str | None, ip: str | None) -> TokenPair:
    now = _now()
    jti = uuid.uuid4()
    db.add(RefreshSession(
        id=jti, user_id=user.id, family_id=family_id, created_at=now, last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=(user_agent or "")[:255] or None, ip=ip,
    ))
    db.flush()
    return TokenPair(
        access_token=create_access_token(user.id, family_id),
        refresh_token=create_refresh_token(user.id, family_id, jti),
    )


def start_session(db: Session, user: User, *, user_agent: str | None, ip: str | None) -> TokenPair:
    """New sign-in = new family. Also tidies old rows so the table stays small."""
    cutoff = _now() - timedelta(days=30)
    db.execute(delete(RefreshSession).where(
        (RefreshSession.expires_at < _now() - timedelta(days=7)) | (RefreshSession.revoked_at < cutoff)
    ))
    return _issue(db, user, uuid.uuid4(), user_agent, ip)


def revoke_family(db: Session, family_id: uuid.UUID, ended_by: str = "revoked") -> None:
    attendance_service.close_family(db, family_id, ended_by)
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.family_id == family_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


def revoke_user_sessions(db: Session, user_id: uuid.UUID, *, except_family: uuid.UUID | None = None) -> None:
    attendance_service.close_user(db, user_id, "revoked", except_family=except_family)
    stmt = update(RefreshSession).where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
    if except_family is not None:
        stmt = stmt.where(RefreshSession.family_id != except_family)
    db.execute(stmt.values(revoked_at=_now()))


def family_active(db: Session, user_id: uuid.UUID, family_id: uuid.UUID) -> bool:
    return db.execute(
        select(RefreshSession.id).where(
            RefreshSession.user_id == user_id,
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > _now(),
        ).limit(1)
    ).first() is not None


def rotate(db: Session, refresh_token: str, *, user_agent: str | None, ip: str | None) -> TokenPair:
    try:
        claims = decode_claims(refresh_token, TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise _unauthorized() from exc

    row = db.get(RefreshSession, claims.jti)
    if row is None or row.user_id != claims.user_id or row.family_id != claims.family_id:
        raise _unauthorized()
    now = _now()
    if row.expires_at <= now:
        raise _unauthorized()

    if row.revoked_at is not None:
        if row.replaced_by is not None:
            # An already-rotated token was presented again. Within a few seconds that's
            # just two tabs racing; later it means the token was copied — kill the family.
            if (now - row.revoked_at).total_seconds() > settings.REFRESH_REUSE_GRACE_SECONDS:
                revoke_family(db, row.family_id)
                db.commit()
        raise _unauthorized()

    user = db.get(User, claims.user_id)
    if user is None or not user.is_active or user.status != UserStatus.ACTIVE.value:
        revoke_family(db, row.family_id)
        db.commit()
        raise _unauthorized()

    pair = _issue(db, user, row.family_id, user_agent or row.user_agent, ip or row.ip)
    attendance_service.touch(db, row.family_id)
    new_claims = decode_claims(pair.refresh_token, TokenType.REFRESH)
    row.revoked_at = now
    row.replaced_by = new_claims.jti
    row.last_used_at = now
    db.commit()
    return pair


def logout(db: Session, refresh_token: str | None) -> None:
    """Revoke the family of this refresh token. Never raises — logging out must always 'work'."""
    if not refresh_token:
        return
    try:
        claims = decode_claims(refresh_token, TokenType.REFRESH)
    except InvalidTokenError:
        return
    revoke_family(db, claims.family_id, ended_by="logout")  # an explicit sign-out: this is the attendance logout time
    db.commit()


def list_active(db: Session, user_id: uuid.UUID) -> list[RefreshSession]:
    return list(db.execute(
        select(RefreshSession)
        .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None), RefreshSession.expires_at > _now())
        .order_by(RefreshSession.last_used_at.desc())
    ).scalars())
