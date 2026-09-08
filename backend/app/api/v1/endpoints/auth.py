"""Auth routes — thin wrappers over AuthService. See spec section 5."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUserResponse, LoginRequest, RefreshRequest, TokenPair
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    return AuthService(db).login(payload.organization_slug, payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    return AuthService(db).refresh(payload.refresh_token)


@router.post("/logout", status_code=204)
def logout() -> None:
    # Stateless JWTs: logout is enforced client-side (discard tokens).
    # jti is already embedded in every token (see security.py) so a
    # server-side revocation list can be added later without a token
    # format change, once that's needed.
    return None


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    user: User = Depends(get_current_user),
    permissions: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        organization_id=user.organization_id,
        organization_slug=user.organization.slug,
        permissions=sorted(permissions),
        roles=UserRepository(db).get_role_codes(user.id),
    )
