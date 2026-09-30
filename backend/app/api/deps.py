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

from app.core.security import InvalidTokenError, TokenClaims, TokenType, decode_claims
from app.db.session import get_db
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository
from app.services import session_service
from app.schemas.common import PageParams

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

MAX_PAGE_SIZE = 100


def get_page_params(page: int = 1, page_size: int = 20) -> PageParams:
    """Shared list pagination. Clamps to sane bounds so a caller can't ask
    for page 0 or 10_000 rows."""
    return PageParams(
        page=max(1, page),
        page_size=min(max(1, page_size), MAX_PAGE_SIZE),
    )


def _authenticate(token: str | None, db: Session) -> tuple[User, TokenClaims]:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has expired. Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise unauthorized
    try:
        claims = decode_claims(token, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise unauthorized from exc

    user = UserRepository(db).get_by_id(claims.user_id)
    if user is None or not user.is_active or user.status != UserStatus.ACTIVE.value:
        raise unauthorized
    # The session must still be alive server-side: logout, "sign out everywhere",
    # a password change or detected token theft all end it immediately.
    if not session_service.family_active(db, user.id, claims.family_id):
        raise unauthorized
    return user, claims


def get_current_user_allow_pending(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """Authenticated user, even if they still owe a password change (used by the auth/account routes)."""
    return _authenticate(token, db)[0]


def get_current_family(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> uuid.UUID:
    return _authenticate(token, db)[1].family_id


def get_current_user(user: User = Depends(get_current_user_allow_pending)) -> User:
    """Authenticated user for everything else. A temporary / admin-set password must be replaced first."""
    if user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="PASSWORD_CHANGE_REQUIRED")
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
