"""
Auth business logic: login, refresh, logout, password change, failed-login
lockout. Routes stay thin (parse request, call service, return response) —
everything that decides "is this login allowed" lives here so it's testable
without spinning up FastAPI.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    burn_password_check,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair
from app.services import activity_service, session_service

GENERIC_LOGIN_ERROR = "Incorrect email or password."
PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)

    # ---------------------------------------------------------------- login

    def _get_organization(self, slug: str) -> Organization | None:
        return self.db.execute(
            select(Organization).where(Organization.slug == slug, Organization.is_active.is_(True))
        ).scalar_one_or_none()

    def login(
        self, organization_slug: str, employee_code: str, password: str, *, user_agent: str | None = None, ip: str | None = None
    ) -> TokenPair:
        org = self._get_organization(organization_slug)
        user = self.users.get_by_org_and_code(org.id, employee_code) if org else None

        if user is None:
            # Same generic error AND same timing as a wrong password — no account/org enumeration.
            burn_password_check(password)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

        self._release_expired_lock(user)
        self._enforce_not_locked(user)

        if not verify_password(password, user.password_hash):
            self._register_failed_attempt(user)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

        if not user.is_active or user.status != UserStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account has been deactivated. Contact your administrator.",
            )

        user.failed_login_attempts = 0
        user.locked_until = None
        pair = session_service.start_session(self.db, user, user_agent=user_agent, ip=ip)
        activity_service.record(
            self.db, actor=user, action="auth.login", entity_type="user", entity_id=user.id,
            metadata={"ip": ip},
        )
        self.db.commit()
        return pair

    # -------------------------------------------------------------- refresh

    def refresh(self, refresh_token: str, *, user_agent: str | None = None, ip: str | None = None) -> TokenPair:
        return session_service.rotate(self.db, refresh_token, user_agent=user_agent, ip=ip)

    def logout(self, refresh_token: str | None) -> None:
        session_service.logout(self.db, refresh_token)

    # ------------------------------------------------------ password change

    def change_password(
        self, user: User, current_password: str, new_password: str, *, user_agent: str | None = None, ip: str | None = None
    ) -> TokenPair:
        if not verify_password(current_password, user.password_hash):
            self._register_failed_attempt(user)  # guessing the current password counts like a failed login
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is incorrect.")

        problem = validate_password_strength(new_password, employee_code=user.employee_code, current_hash=user.password_hash)
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)

        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        user.password_changed_at = datetime.now(timezone.utc)
        user.failed_login_attempts = 0
        # Every device is signed out; this one gets a fresh session straight away.
        session_service.revoke_user_sessions(self.db, user.id)
        pair = session_service.start_session(self.db, user, user_agent=user_agent, ip=ip)
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
