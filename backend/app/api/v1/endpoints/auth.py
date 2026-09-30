"""Auth routes — thin wrappers over AuthService / session_service."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_family,
    get_current_permissions,
    get_current_user_allow_pending,
)
from app.core.ratelimit import client_ip, login_failures
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SessionOut,
    TokenPair,
)
from app.services import activity_service, session_service
from app.services.auth_service import AuthService, GENERIC_LOGIN_ERROR

router = APIRouter(prefix="/auth", tags=["auth"])

ADMIN_ROLE_CODE = "admin"


def _meta(request: Request) -> dict:
    return {"user_agent": request.headers.get("user-agent"), "ip": client_ip(request)}


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    meta = _meta(request)
    wait = login_failures.blocked_for(meta["ip"])
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed sign-in attempts from this network. Try again in about {max(1, wait // 60 + 1)} minute(s).",
            headers={"Retry-After": str(wait)},
        )
    try:
        return AuthService(db).login(payload.organization_slug, payload.employee_code, payload.password, **meta)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and exc.detail == GENERIC_LOGIN_ERROR:
            login_failures.record_failure(meta["ip"])
        raise


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    return AuthService(db).refresh(payload.refresh_token, **_meta(request))


@router.post("/logout", status_code=204)
def logout(payload: LogoutRequest | None = None, db: Session = Depends(get_db)) -> Response:
    """Ends this device's session (server-side). Always succeeds, even with an expired access token."""
    AuthService(db).logout(payload.refresh_token if payload else None)
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
def logout_all(user: User = Depends(get_current_user_allow_pending), db: Session = Depends(get_db)) -> Response:
    session_service.revoke_user_sessions(db, user.id)
    activity_service.record(db, actor=user, action="auth.logout_all", entity_type="user", entity_id=user.id)
    db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    user: User = Depends(get_current_user_allow_pending),
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    roles = UserRepository(db).get_role_codes(user.id)
    # While a password change is owed, expose no permissions: the UI can only show the change form.
    permissions = set() if user.must_change_password else get_current_permissions(user, db)
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
        must_change_password=user.must_change_password,
    )


@router.post("/change-password", response_model=TokenPair)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user_allow_pending),
    db: Session = Depends(get_db),
) -> TokenPair:
    """Verify the current password, apply the policy, sign every device out, return a fresh session."""
    return AuthService(db).change_password(user, payload.current_password, payload.new_password, **_meta(request))


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user_allow_pending),
    family: uuid.UUID = Depends(get_current_family),
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    return [
        SessionOut(
            id=r.family_id, current=r.family_id == family, signed_in_at=r.created_at,
            last_active_at=r.last_used_at, ip=r.ip, user_agent=r.user_agent,
        )
        for r in session_service.list_active(db, user.id)
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user_allow_pending),
    db: Session = Depends(get_db),
) -> Response:
    if not any(r.family_id == session_id for r in session_service.list_active(db, user.id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    session_service.revoke_family(db, session_id)
    db.commit()
    return Response(status_code=204)
