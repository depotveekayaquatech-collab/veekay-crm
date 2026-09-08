"""
Shared FastAPI dependencies: DB session, current user, and permission
checks. This is the ONLY place "am I allowed to do this" is decided.
Route handlers must never re-implement authorization inline — they
declare the permission(s) they need via Depends(require_permission(...)).
"""
import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.db.session import get_db
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has expired. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise unauthorized

    try:
        user_id: uuid.UUID = decode_token(token, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise unauthorized from exc

    user = UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active or user.status != UserStatus.ACTIVE.value:
        raise unauthorized
    return user


def get_current_permissions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> set[str]:
    """Flattened set of permission codes across all of the user's roles.
    Computed per-request (not cached on the token) so a permission or
    role change takes effect on the user's very next call, not after
    their token expires."""
    return UserRepository(db).get_permission_codes(user.id)


def require_permission(*required: str) -> Callable[..., User]:
    """Depends(require_permission("orders.assign")) — 403s if the current
    user lacks ANY of the required permission codes. Never trust a
    permission list sent by the frontend; this always re-derives from
    the DB via get_current_permissions above."""

    def checker(
        user: User = Depends(get_current_user),
        permissions: set[str] = Depends(get_current_permissions),
    ) -> User:
        if not set(required).issubset(permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this.",
            )
        return user

    return checker


def require_same_organization(target_organization_id: uuid.UUID, user: User) -> None:
    """Explicit organization-isolation guard for endpoints that take an
    organization_id or resolve one from a related entity (store, order,
    ticket). Call this from the service layer, never trust the ID
    the frontend attached to the request body — always compare against
    user.organization_id from the authenticated session."""
    if user.organization_id != target_organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this.",
        )
