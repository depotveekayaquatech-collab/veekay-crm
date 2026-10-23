"""
Auth business logic: login, refresh, logout, password change, failed-login
lockout. Routes stay thin (parse request, call service, return response) —
everything that decides "is this login allowed" lives here so it's testable
without spinning up FastAPI.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.roles import DEVELOPER
from app.core.security import (
    TokenType,
    burn_password_check,
    decode_claims,
    hash_password,
    match_password,
    seal_password,
    set_password,
    unseal_password,
    validate_password_strength,
)
from app.models.organization import Organization
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginResponse, TokenPair
from app.services import activity_service, session_service

log = logging.getLogger(__name__)

GENERIC_LOGIN_ERROR = "Incorrect email or password."
PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)

    def _is_developer(self, user: User) -> bool:
        return DEVELOPER in self.users.get_role_codes(user.id)

    # ---------------------------------------------------------------- login

    def _get_organization(self, slug: str) -> Organization | None:
        return self.db.execute(
            select(Organization).where(Organization.slug == slug, Organization.is_active.is_(True))
        ).scalar_one_or_none()

    def login(
        self, organization_slug: str, employee_code: str, password: str, *, user_agent: str | None = None, ip: str | None = None,
    ) -> LoginResponse:
        org = self._get_organization(organization_slug)
        user = self.users.get_by_org_and_code(org.id, employee_code) if org else None

        if user is None:
            # Same generic error AND same timing as a wrong password — no account/org enumeration.
            burn_password_check(password)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

        self._release_expired_lock(user)
        self._enforce_not_locked(user)

        matched = match_password(password, user.password_hash)
        if matched is None:
            log.info("login refused: wrong password for %s (typed %d characters)", user.employee_code, len(password))
            self._register_failed_attempt(user)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

        if not user.is_active or user.status != UserStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account has been deactivated. Contact your administrator.",
            )

        user.failed_login_attempts = 0
        user.locked_until = None
        # Passwords set before the developer view existed have no readable copy: the first correct sign-in is the one moment it is known.
        if matched != matched.strip():
            # Saved before stray spaces were dropped: keep it working as typed, but store what the person actually sees from now on
            # (typing it with or without the space both keep working). Not a password change, so the change date stays.
            matched = matched.strip()
            user.password_hash = hash_password(matched)
        if self._is_developer(user):
            user.password_enc = None                    # a developer's password is never kept in readable form
        elif unseal_password(user.password_enc) != matched:
            user.password_enc = seal_password(matched)
        pair = session_service.start_session(self.db, user, user_agent=user_agent, ip=ip)
        activity_service.record(
            self.db, actor=user, action="auth.login", entity_type="user", entity_id=user.id,
            metadata={"ip": ip},
        )
        self.db.commit()
        return LoginResponse(**pair.model_dump(), attendance=False)  # attendance is an explicit Check in now, not a side effect of signing in

    # -------------------------------------------------------------- refresh

    def refresh(self, refresh_token: str, *, user_agent: str | None = None, ip: str | None = None) -> TokenPair:
        return session_service.rotate(self.db, refresh_token, user_agent=user_agent, ip=ip)

    def logout(self, refresh_token: str | None) -> None:
        session_service.logout(self.db, refresh_token)

    # ------------------------------------------------------ password change

    def change_password(
        self, user: User, current_password: str, new_password: str, *, current_family: uuid.UUID | None = None,
        user_agent: str | None = None, ip: str | None = None,
    ) -> TokenPair:
        if match_password(current_password, user.password_hash) is None:
            self._register_failed_attempt(user)  # guessing the current password counts like a failed login
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is incorrect.")

        new_password = new_password.strip()  # stored exactly as validated here
        problem = validate_password_strength(new_password, employee_code=user.employee_code, current_hash=user.password_hash)
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)

        set_password(user, new_password, must_change=False)
        if self._is_developer(user):
            user.password_enc = None
        user.failed_login_attempts = 0
        # Every other device is signed out; this one gets a fresh session straight away.
        pair = session_service.start_session(self.db, user, user_agent=user_agent, ip=ip)
        new_family = decode_claims(pair.refresh_token, TokenType.REFRESH).family_id
        session_service.revoke_user_sessions(self.db, user.id, except_family=new_family)
        activity_service.record(
            self.db, actor=user, action="auth.password_changed", entity_type="user", entity_id=user.id,
        )
        self.db.commit()
        return pair

    # -------------------------------------------------------------- lockout

    def _release_expired_lock(self, user: User) -> None:
        """A lockout is temporary: once it lapses the account is usable again (it used to stay 'locked' forever)."""
        if user.status != UserStatus.LOCKED.value:
            return
        if user.locked_until is None or datetime.now(timezone.utc) >= datetime.fromisoformat(user.locked_until):
            user.status = UserStatus.ACTIVE.value
            user.failed_login_attempts = 0
            user.locked_until = None
            self.users.save(user)

    def _enforce_not_locked(self, user: User) -> None:
        if user.locked_until is None:
            return
        locked_until = datetime.fromisoformat(user.locked_until)
        if datetime.now(timezone.utc) < locked_until:
            minutes = max(1, int((locked_until - datetime.now(timezone.utc)).total_seconds() // 60) + 1)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Too many failed attempts. Try again in about {minutes} minute{'s' if minutes > 1 else ''}.",
            )

    def _register_failed_attempt(self, user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = (
                datetime.now(timezone.utc) + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            ).isoformat()
            user.status = UserStatus.LOCKED.value
            activity_service.record(
                self.db, actor=user, action="auth.locked", entity_type="user", entity_id=user.id,
                metadata={"attempts": user.failed_login_attempts},
            )
        self.users.save(user)


def parse_family(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.") from exc
