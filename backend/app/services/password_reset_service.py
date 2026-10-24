"""Forgot password: an emailed 6-digit one-time code.

* Only accounts that have an email address, are active, and are NOT an admin / custom admin / developer can use it (those are reset by
  a developer; an email takeover must never reach the keys of the system).
* The reply to "send me a code" is always the same, whether or not the ID exists or has an email, and the email goes out after the reply.
* The code is stored only as an HMAC, expires in RESET_CODE_MINUTES, dies after RESET_CODE_MAX_ATTEMPTS wrong guesses, and at most
  RESET_CODE_MAX_PER_HOUR codes can be requested per account per hour.
* A successful reset signs every device out, clears any lockout and leaves a normal (not temporary) password."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import mailer
from app.core.config import settings
from app.core.roles import ADMIN, DEVELOPER, MANAGER
from app.core.security import burn_password_check, set_password, validate_password_strength
from app.models.organization import Organization
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.services import activity_service, session_service

log = logging.getLogger("veekay.reset")

BAD_CODE = "That code is incorrect or has expired. Ask for a new one."
_BLOCKED_ROLES = {ADMIN, MANAGER, DEVELOPER}


def _digest(user_id, code: str) -> str:
    return hmac.new(settings.JWT_SECRET_KEY.encode(), f"pwreset|{user_id}|{code}".encode(), hashlib.sha256).hexdigest()


def _find(db: Session, slug: str, employee_code: str) -> User | None:
    org = db.execute(select(Organization).where(Organization.slug == slug, Organization.is_active.is_(True))).scalar_one_or_none()
    return UserRepository(db).get_by_org_and_code(org.id, employee_code) if org else None


def _eligible(db: Session, user: User) -> bool:
    if not (user.is_active and user.status in (UserStatus.ACTIVE.value, UserStatus.LOCKED.value) and user.email):
        return False
    return not (set(UserRepository(db).get_role_codes(user.id)) & _BLOCKED_ROLES)


def issue_code(db: Session, slug: str, employee_code: str) -> tuple[str, str] | None:
    """Create + store a code for an eligible account and return (email, code) for the caller to send; None when nothing is to be sent.
    The caller must reply identically either way."""
    user = _find(db, slug, employee_code)
    if user is None or not _eligible(db, user):
        return None
    now = datetime.now(timezone.utc)
    if user.reset_window_start is None or now - user.reset_window_start > timedelta(hours=1):
        user.reset_window_start, user.reset_window_count = now, 0
    if user.reset_window_count >= settings.RESET_CODE_MAX_PER_HOUR:
        db.commit()
        return None
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.reset_window_count += 1
    user.reset_code_hash = _digest(user.id, code)
    user.reset_code_expires_at = now + timedelta(minutes=settings.RESET_CODE_MINUTES)
    user.reset_code_attempts = 0
    db.commit()
    return user.email, code


def send_code_email(email: str, code: str) -> None:
    mailer.send_mail(
        email, "Veekay password reset code",
        f"Your Veekay password reset code is {code}.\n\nEnter it in the app (or on the website) with your new password. It works for "
        f"{settings.RESET_CODE_MINUTES} minutes and only once. Do not share it with anyone.\n\n"
        "If you did not ask to reset your password, ignore this email. Nothing has changed.\n\nVeekay Aquatech",
    )


def reset_with_code(db: Session, slug: str, employee_code: str, code: str, new_password: str, *, ip: str | None = None) -> None:
    user = _find(db, slug, employee_code)
    now = datetime.now(timezone.utc)
    if user is None or not _eligible(db, user) or not user.reset_code_hash or not user.reset_code_expires_at:
        burn_password_check(code)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_CODE)
    if now > user.reset_code_expires_at or user.reset_code_attempts >= settings.RESET_CODE_MAX_ATTEMPTS:
        user.reset_code_hash = user.reset_code_expires_at = None
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_CODE)
    if not hmac.compare_digest(user.reset_code_hash, _digest(user.id, code.strip())):
        user.reset_code_attempts += 1
        if user.reset_code_attempts >= settings.RESET_CODE_MAX_ATTEMPTS:
            user.reset_code_hash = user.reset_code_expires_at = None
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_CODE)

    new_password = new_password.strip()
    problem = validate_password_strength(new_password, employee_code=user.employee_code, current_hash=user.password_hash)
    if problem:                                   # the code stays valid so they can try another password
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)

    set_password(user, new_password, must_change=False)
    user.reset_code_hash = user.reset_code_expires_at = None
    user.reset_code_attempts = 0
    user.failed_login_attempts = 0
    user.locked_until = None
    if user.status == UserStatus.LOCKED.value:
        user.status = UserStatus.ACTIVE.value
    session_service.revoke_user_sessions(db, user.id)
    activity_service.record(db, actor=user, action="auth.password_reset_by_code", entity_type="user", entity_id=user.id, metadata={"ip": ip})
    db.commit()
