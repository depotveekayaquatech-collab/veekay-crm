"""Auth routes — thin wrappers over AuthService."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUserResponse, LoginRequest, RefreshRequest, TokenPair
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

ADMIN_ROLE_CODE = "admin"


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    return AuthService(db).login(payload.organization_slug, payload.employee_code, payload.password)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    return AuthService(db).refresh(payload.refresh_token)


@router.post("/logout", status_code=204)
def logout() -> None:
    return None


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    user: User = Depends(get_current_user),
    permissions: set[str] = Depends(get_current_permissions),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    roles = UserRepository(db).get_role_codes(user.id)
    return CurrentUserResponse(
        id=user.id,
        employee_code=user.employee_code,
        full_name=user.full_name,
        email=user.email,
        organization_id=user.organization_id,
        organization_slug=user.organization.slug,
        platform_slug=user.platform_organization.slug if user.platform_organization else None,
        platform_label=user.platform_organization.name if user.platform_organization else None,
        region_id=user.region_id,
        region_name=user.region.name if user.region else None,
        permissions=sorted(permissions),
        roles=roles,
        is_admin=ADMIN_ROLE_CODE in roles,
    )
