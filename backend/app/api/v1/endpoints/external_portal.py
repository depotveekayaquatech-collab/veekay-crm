"""Vendor / POC app: sign-in (/external/auth/*) and the account's own data (/external/*).

Everything under /external/* except the auth routes depends on get_current_external_account and filters by that
account's own store links, so a vendor or POC can only ever read their own stores.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_external_account
from app.core.config import settings
from app.core.ratelimit import client_ip, login_failures
from app.db.session import get_db
from app.models.external_account import ExternalAccount, ExternalAccountStore
from app.models.organization import Organization
from app.models.store import Store
from app.schemas.auth import LogoutRequest, RefreshRequest, TokenPair
from app.schemas.external_account import ExternalLoginRequest, ExternalMe, StoreRef
from app.services import external_auth_service as svc

router = APIRouter(prefix="/external", tags=["external-portal"])

COOKIE_NAME = "vk_ext_refresh"
COOKIE_PATH = f"{settings.API_V1_PREFIX}/external/auth"


def _secure() -> bool:
    if settings.REFRESH_COOKIE_SECURE is not None:
        return settings.REFRESH_COOKIE_SECURE
    return settings.ENVIRONMENT.strip().lower() == "production"


def _deliver(request: Request, response: Response, pair: TokenPair) -> TokenPair:
    """Browser/PWA (X-Auth-Mode: cookie): the refresh token goes into an HttpOnly cookie, out of the JSON body."""
    if request.headers.get("x-auth-mode", "").lower() == "cookie" and pair.refresh_token:
        response.set_cookie(
            COOKIE_NAME, pair.refresh_token, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, httponly=True,
            secure=_secure(), samesite=settings.REFRESH_COOKIE_SAMESITE, path=COOKIE_PATH,
        )
        return pair.model_copy(update={"refresh_token": None})
    return pair


def _meta(request: Request) -> dict:
    return {"user_agent": request.headers.get("user-agent"), "ip": client_ip(request)}


@router.post("/auth/login", response_model=TokenPair)
def login(payload: ExternalLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenPair:
    meta = _meta(request)
    wait = login_failures.blocked_for(meta["ip"])
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed sign-in attempts from this network. Try again in about {max(1, wait // 60 + 1)} minute(s).",
            headers={"Retry-After": str(wait)},
        )
    try:
        return _deliver(request, response, svc.login(db, payload.email, payload.password, **meta))
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login_failures.record_failure(meta["ip"])
        raise


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(request: Request, response: Response, payload: RefreshRequest | None = None, db: Session = Depends(get_db)) -> TokenPair:
    token = (payload.refresh_token if payload else None) or request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    return _deliver(request, response, svc.rotate(db, token, **_meta(request)))


@router.post("/auth/logout", status_code=204)
def logout(request: Request, payload: LogoutRequest | None = None, db: Session = Depends(get_db)) -> Response:
    svc.logout(db, (payload.refresh_token if payload else None) or request.cookies.get(COOKIE_NAME))
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, httponly=True, secure=_secure(), samesite=settings.REFRESH_COOKIE_SAMESITE)
    return resp


@router.get("/me", response_model=ExternalMe)
def me(account: ExternalAccount = Depends(get_current_external_account)) -> ExternalMe:
    return ExternalMe(
        id=account.id, kind=account.kind, email=account.email, full_name=account.full_name, phone=account.phone,
        platforms=list(account.platforms or []), store_count=account.store_count,
    )


@router.get("/stores", response_model=list[StoreRef])
def my_stores(account: ExternalAccount = Depends(get_current_external_account), db: Session = Depends(get_db)) -> list[StoreRef]:
    """Only the stores linked to this login."""
    rows = db.execute(
        select(Store, Organization.slug)
        .join(ExternalAccountStore, ExternalAccountStore.store_id == Store.id)
        .join(Organization, Organization.id == Store.partner_organization_id)
        .where(ExternalAccountStore.account_id == account.id).order_by(Store.name)
    ).all()
    return [StoreRef(id=s.id, name=s.name, code=s.external_code, platform=slug, city=s.city, state=s.state) for s, slug in rows]
