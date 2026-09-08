"""
Auth business logic: login, refresh, failed-login lockout. Routes stay
thin (parse request, call service, return response) — everything that
decides "is this login allowed" lives here so it's testable without
spinning up FastAPI.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair

GENERIC_LOGIN_ERROR = "Incorrect email or password."


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)

    def _get_organization(self, slug: str) -> Organization:
        org = self.db.execute(
            select(Organization).where(Organization.slug == slug, Organization.is_active.is_(True))
        ).scalar_one_or_none()
        if org is None:
            # Same generic error as bad credentials — don't let attackers
            # enumerate valid organization slugs.
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)
        return org

    def login(self, organization_slug: str, email: str, password: str) -> TokenPair:
        org = self._get_organization(organization_slug)
        user = self.users.get_by_org_and_email(org.id, email)

        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

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
        self.users.save(user)

        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        try:
            user_id: uuid.UUID = decode_token(refresh_token, TokenType.REFRESH)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your session has expired. Please sign in again.",
            ) from exc

        user = self.users.get_by_id(user_id)
        if user is None or not user.is_active or user.status != UserStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your session has expired. Please sign in again.",
            )

        # Rotate both tokens on refresh (refresh-token rotation) rather than
        # re-signing only the access token, so a leaked refresh token has a
        # short useful life once the legitimate client refreshes again.
        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    def _enforce_not_locked(self, user: User) -> None:
        if user.locked_until is None:
            return
        locked_until = datetime.fromisoformat(user.locked_until)
        if datetime.now(timezone.utc) < locked_until:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Too many failed attempts. Try again later.",
            )

    def _register_failed_attempt(self, user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = (
                datetime.now(timezone.utc) + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            ).isoformat()
            user.status = UserStatus.LOCKED.value
        self.users.save(user)
