"""Vendor / POC logins prepared for the future mobile app. Not CRM users, not part of the team."""
import csv
import io
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.external_account import AccountKind, ExternalAccount, ExternalAccountStore
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
