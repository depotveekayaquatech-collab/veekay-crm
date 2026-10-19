"""Vendor / POC logins prepared for the future mobile app. Not CRM users, not part of the team."""
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.security import generate_temp_password, hash_password
from app.services import activity_service, external_account_service
from app.db.session import get_db
from app.models.external_account import AccountKind, ExternalAccount, ExternalAccountStore, ExternalSession
from app.models.organization import Organization
from app.models.store import Store
from app.models.user import User
from app.schemas.external_account import ExternalAccountDetail, ExternalAccountList, ExternalAccountOut, StoreRef
from app.services.external_account_service import VENDOR_PASSWORD

router = APIRouter(prefix="/external-accounts", tags=["external-accounts"])

_ORDER = (ExternalAccount.kind, ExternalAccount.full_name, ExternalAccount.email)


def _out(a: ExternalAccount) -> ExternalAccountOut:
    return ExternalAccountOut(
        id=a.id, kind=a.kind, email=a.email, full_name=a.full_name, phone=a.phone, platforms=list(a.platforms or []),
        store_count=a.store_count, must_change_password=a.must_change_password, is_active=a.is_active, created_at=a.created_at,
    )


def _initial_password(a: ExternalAccount) -> str:
    """The standard password the account was created with. Blank once the person has chosen their own."""
    if not a.must_change_password:
        return ""
    return VENDOR_PASSWORD if a.kind == AccountKind.VENDOR else f"{a.email.split('@')[0]}@123"


def _filters(user: User, kind: str | None, platform: str | None, q: str | None) -> list:
    conds = [ExternalAccount.organization_id == user.organization_id]
    if kind:
        conds.append(ExternalAccount.kind == kind)
    if platform:
        conds.append(ExternalAccount.platforms.contains([platform]))
    if q and q.strip():
        like = f"%{q.strip()}%"
        conds.append(or_(ExternalAccount.email.ilike(like), ExternalAccount.full_name.ilike(like), ExternalAccount.phone.ilike(like)))
    return conds


class GenerateIn(BaseModel):
    platform: Literal["blinkit", "zepto", "all"] = "blinkit"
    dry_run: bool = True


def _plan_out(plan) -> dict:
    return {
        "accounts": len(plan.people), "skipped": len(plan.skipped), "shared_names": len(plan.split_names),
        "examples": [{"email": p.email, "name": p.name, "stores": len(p.store_ids)} for p in plan.people[:5]],
    }


@router.post("/generate", dependencies=[Depends(require_permission("sheets.sync"))])
def generate(body: GenerateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Developer: build the vendor and POC logins from the stores' vendor / POC columns (the same step as scripts/create_external_accounts.py).
    dry_run (the default) only reports what would be created. Existing accounts keep their password; each account's store list is refreshed."""
    vendors, pocs = external_account_service.build_plan(db, None if body.platform == "all" else {body.platform})
    try:
        external_account_service.check_unique([vendors, pocs])
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    out = {"platform": body.platform, "dry_run": body.dry_run, "vendors": _plan_out(vendors), "pocs": _plan_out(pocs), "applied": None}
    if body.dry_run:
        return out
    out["applied"] = external_account_service.apply(db, user.organization_id, [vendors, pocs])
    activity_service.record(
        db, actor=user, action="external_accounts.generated", entity_type="external_account", entity_id=user.organization_id,
        metadata={"platform": body.platform, **out["applied"]},
    )
    db.commit()
    return out


@router.get("", response_model=ExternalAccountList)
def list_accounts(
    kind: Literal["vendor", "poc"] | None = None, platform: str | None = Query(None, max_length=32), q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("logins.view")), db: Session = Depends(get_db),
) -> ExternalAccountList:
    conds = _filters(user, kind, platform, q)
    total = db.execute(select(func.count()).select_from(ExternalAccount).where(*conds)).scalar_one()
    rows = db.execute(select(ExternalAccount).where(*conds).order_by(*_ORDER).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    counts = dict(db.execute(
        select(ExternalAccount.kind, func.count()).where(ExternalAccount.organization_id == user.organization_id).group_by(ExternalAccount.kind)
    ).all())
    return ExternalAccountList(
        items=[_out(a) for a in rows], total=total, page=page, page_size=page_size,
        vendors=counts.get(AccountKind.VENDOR, 0), pocs=counts.get(AccountKind.POC, 0),
    )


@router.get("/export")
def export(
    kind: Literal["vendor", "poc"] | None = None, platform: str | None = Query(None, max_length=32), q: str | None = Query(None, max_length=100),
    user: User = Depends(require_permission("logins.view")), db: Session = Depends(get_db),
) -> Response:
    """CSV of the logins (with the initial password of accounts that haven't changed it yet)."""
    rows = db.execute(select(ExternalAccount).where(*_filters(user, kind, platform, q)).order_by(*_ORDER)).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["type", "login (email)", "initial password", "name", "phone", "platforms", "stores"])
    for a in rows:
        w.writerow(["Vendor" if a.kind == AccountKind.VENDOR else "POC", a.email, _initial_password(a), a.full_name, a.phone or "", ", ".join(a.platforms or []), a.store_count])
    return Response(
        buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vendor-poc-logins.csv"', "Cache-Control": "private, no-store"},
    )


@router.get("/{account_id}", response_model=ExternalAccountDetail)
def detail(account_id: uuid.UUID, user: User = Depends(require_permission("logins.view")), db: Session = Depends(get_db)) -> ExternalAccountDetail:
    a = db.get(ExternalAccount, account_id)
    if a is None or a.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
    stores = db.execute(
        select(Store, Organization.slug).join(ExternalAccountStore, ExternalAccountStore.store_id == Store.id)
        .join(Organization, Organization.id == Store.partner_organization_id)
        .where(ExternalAccountStore.account_id == a.id).order_by(Store.name)
    ).all()
    return ExternalAccountDetail(
        account=_out(a),
        stores=[StoreRef(id=s.id, name=s.name, code=s.external_code, platform=slug, city=s.city, state=s.state) for s, slug in stores],
    )


class PasswordReset(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=64, description="Leave out to generate a random one.")


class PasswordResetResult(BaseModel):
    email: str
    password: str
    generated: bool


@router.post("/{account_id}/reset-password", response_model=PasswordResetResult)
def reset_password(
    account_id: uuid.UUID, body: PasswordReset, response: Response,
    user: User = Depends(require_permission("logins.manage")), db: Session = Depends(get_db),
) -> PasswordResetResult:
    """Sets the password you choose (or a random one), unlocks the account and signs it out of every phone.
    The password is shown once, here: it is stored only as a hash."""
    a = db.get(ExternalAccount, account_id)
    if a is None or a.organization_id != user.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found.")
    chosen = (body.password or "").strip()
    pw = chosen or generate_temp_password()
    a.password_hash = hash_password(pw)
    a.must_change_password = False          # the standard starting password is gone
    a.failed_login_attempts = 0
    a.locked_until = None
    db.execute(update(ExternalSession).where(ExternalSession.account_id == a.id, ExternalSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    activity_service.record(
        db, actor=user, action="external_account.password_reset", entity_type="external_account", entity_id=a.id,
        metadata={"login": a.email, "generated": not chosen},
    )
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return PasswordResetResult(email=a.email, password=pw, generated=not chosen)
