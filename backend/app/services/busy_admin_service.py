"""Admin side of vendor payments: the vendor list, unmatched codes, sync history and the API-key help. Every function here is behind vendorpay.manage."""
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.busy_ledger import (
    BILL, PAYMENT, UNMATCHED_OPEN, UNMATCHED_RESOLVED, BusySyncLog, BusyUnmatchedEntry as U, BusyVendor, BusyVendorAlias,
)
from app.models.user import User
from app.schemas.busy_ledger import (
    AdminVendorOut, CodeCheck, GeneratedKey, KeyInfo, SyncLogOut, UnmatchedCreateVendor, UnmatchedGroup, UnmatchedMap, UnmatchedSelector,
    ResolveResult, VendorCreate, VendorUpdate,
)
from app.schemas.common import Page, PageParams
from app.services import activity_service
from app.services.busy_codes import is_valid_code, normalize_code, split_account_name
from app.services.busy_sync_service import ValidRow, upsert_ledger

SYNC_PATH = "/api/v1/busy-sync"
SYNC_HEADER = "x-api-key"


# ---- vendors ------------------------------------------------------------------------

def list_vendors(db: Session, params: PageParams, q: str = "", active: bool | None = None) -> Page[AdminVendorOut]:
    stmt = select(BusyVendor)
    if q.strip():
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(BusyVendor.name.ilike(like, escape="\\"), BusyVendor.city.ilike(like, escape="\\"), BusyVendor.vendor_code.ilike(like, escape="\\")))
    if active is not None:
        stmt = stmt.where(BusyVendor.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(func.lower(BusyVendor.name), BusyVendor.vendor_code).limit(params.limit).offset(params.offset)).all()
    return Page(items=[AdminVendorOut.model_validate(v) for v in rows], total=total, page=params.page, page_size=params.page_size)


def get_vendor(db: Session, code: str) -> BusyVendor:
    vendor = db.scalar(select(BusyVendor).where(BusyVendor.vendor_code == normalize_code(code)))
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No vendor has that code.")
    return vendor


def check_code(db: Session, raw: str) -> CodeCheck:
    code = normalize_code(raw)
    if not is_valid_code(code):
        return CodeCheck(vendor_code=code, valid=False, exists=False, alias_of=None, message="Use 1 to 32 letters, digits, '-' or '_'.")
    if db.scalar(select(BusyVendor.id).where(BusyVendor.vendor_code == code)) is not None:
        return CodeCheck(vendor_code=code, valid=True, exists=True, alias_of=None, message="A vendor already has this code.")
    alias = db.scalar(select(BusyVendorAlias.vendor_code).where(BusyVendorAlias.alias_code == code))
    if alias:
        return CodeCheck(vendor_code=code, valid=True, exists=True, alias_of=alias, message=f"This code is already an alias of {alias}.")
    return CodeCheck(vendor_code=code, valid=True, exists=False, alias_of=None, message=None)


def create_vendor(db: Session, actor: User, data: VendorCreate) -> BusyVendor:
    check = check_code(db, data.vendor_code)
    if check.exists:
        raise HTTPException(status.HTTP_409_CONFLICT, check.message)
    vendor = BusyVendor(vendor_code=data.vendor_code, name=data.name, city=data.city, opening_balance=data.opening_balance,
                        opening_date=data.opening_date, is_active=True)
    db.add(vendor)
    try:
        db.flush()
    except IntegrityError as exc:           # two admins creating the same code at once
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A vendor already has this code.") from exc
    activity_service.record(db, actor=actor, action="busy.vendor_created", entity_type="busy_vendor", entity_id=vendor.id,
                            metadata={"vendor_code": vendor.vendor_code, "name": vendor.name})
    return vendor


def update_vendor(db: Session, actor: User, code: str, data: VendorUpdate) -> BusyVendor:
    vendor = get_vendor(db, code)
    changes = data.model_dump(exclude_unset=True)
    for required in ("name", "opening_balance", "is_active"):
        if changes.get(required) is None:
            changes.pop(required, None)           # these cannot be blank; city and opening_date can be cleared
    for field, value in changes.items():
        setattr(vendor, field, value)
    vendor.updated_at = datetime.now(timezone.utc)
    activity_service.record(db, actor=actor, action="busy.vendor_updated", entity_type="busy_vendor", entity_id=vendor.id,
                            metadata={"vendor_code": vendor.vendor_code, "changed": sorted(changes)})
    return vendor


# ---- sync history ----------------------------------------------------------------------

def list_sync_logs(db: Session, params: PageParams) -> Page[SyncLogOut]:
    total = db.scalar(select(func.count()).select_from(BusySyncLog)) or 0
    rows = db.scalars(select(BusySyncLog).order_by(BusySyncLog.started_at.desc()).limit(params.limit).offset(params.offset)).all()
    return Page(items=[SyncLogOut.model_validate(r) for r in rows], total=total, page=params.page, page_size=params.page_size)


# ---- unmatched rows ----------------------------------------------------------------------

def unmatched_groups(db: Session) -> list[UnmatchedGroup]:
    """Open unmatched rows: one group per code, and (where Busy sent no code at all) one group per account name."""
    by_account_when_no_code = case((U.vendor_code.is_(None), U.account_name), else_="")
    rows = db.execute(
        select(
            U.vendor_code, func.coalesce(func.min(func.nullif(U.account_name, "")), "").label("account_name"), func.count().label("rows"),
            func.coalesce(func.sum(U.amount).filter(U.entry_type == BILL), 0).label("bills"),
            func.coalesce(func.sum(U.amount).filter(U.entry_type == PAYMENT), 0).label("payments"),
            func.min(U.entry_date).label("first_date"), func.max(U.entry_date).label("last_date"),
        ).where(U.status == UNMATCHED_OPEN).group_by(U.vendor_code, by_account_when_no_code).order_by(func.max(U.entry_date).desc())
    ).all()
    return [
        UnmatchedGroup(vendor_code=r.vendor_code, account_name=r.account_name, rows=r.rows, bills=r.bills, payments=r.payments,
                       first_date=r.first_date, last_date=r.last_date, suggested_name=split_account_name(r.account_name)[0])
        for r in rows
    ]


def _open_rows(db: Session, sel: UnmatchedSelector) -> list[U]:
    stmt = select(U).where(U.status == UNMATCHED_OPEN)
    if sel.vendor_code:
        stmt = stmt.where(U.vendor_code == sel.vendor_code)
    elif sel.account_name is not None:
        stmt = stmt.where(U.vendor_code.is_(None), U.account_name == sel.account_name)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Say which unmatched rows: a vendor_code or an account_name.")
    rows = list(db.scalars(stmt))
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There are no open unmatched rows for that selection.")
    return rows


def _move_to_ledger(db: Session, rows: list[U], vendor_code: str) -> tuple[int, int]:
    """Put the parked rows into the ledger under `vendor_code` and mark them resolved. A later copy of the same voucher wins."""
    now = datetime.now(timezone.utc)
    latest: dict[tuple[str, str], U] = {}
    for row in sorted(rows, key=lambda r: r.updated_at):
        latest[(row.voucher_no, row.entry_type)] = row
    inserted = updated = 0
    for source in {r.source for r in latest.values()}:
        batch = [ValidRow(0, vendor_code, r.account_name, r.entry_date, r.entry_type, r.amount, r.voucher_no, r.narration, r.raw)
                 for r in latest.values() if r.source == source]
        i, u = upsert_ledger(db, batch, source, now)
        inserted, updated = inserted + i, updated + u
    for row in rows:
        row.status, row.resolved_at, row.resolved_vendor_code = UNMATCHED_RESOLVED, now, vendor_code
    return inserted, updated


def resolve_by_creating_vendor(db: Session, actor: User, body: UnmatchedCreateVendor) -> ResolveResult:
    rows = _open_rows(db, body)
    if body.vendor_code and body.vendor_code != body.new_vendor.vendor_code:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The new vendor must use the code Busy sent. To use another code, map the rows to an existing vendor instead.")
    vendor = create_vendor(db, actor, body.new_vendor)
    inserted, updated = _move_to_ledger(db, rows, vendor.vendor_code)
    activity_service.record(db, actor=actor, action="busy.unmatched_resolved", entity_type="busy_vendor", entity_id=vendor.id,
                            metadata={"vendor_code": vendor.vendor_code, "rows": len(rows), "how": "created"})
    return ResolveResult(vendor_code=vendor.vendor_code, moved=len(rows), inserted=inserted, updated=updated)


def resolve_by_mapping(db: Session, actor: User, body: UnmatchedMap) -> ResolveResult:
    rows = _open_rows(db, body)
    target = get_vendor(db, body.map_to_vendor_code)
    code = body.vendor_code
    if code and code != target.vendor_code:
        if db.scalar(select(BusyVendor.id).where(BusyVendor.vendor_code == code)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "That code is already a vendor of its own.")
        existing = db.scalar(select(BusyVendorAlias).where(BusyVendorAlias.alias_code == code))
        if existing is not None and existing.vendor_code != target.vendor_code:
            raise HTTPException(status.HTTP_409_CONFLICT, f"That code is already an alias of {existing.vendor_code}.")
        if existing is None:
            db.add(BusyVendorAlias(alias_code=code, vendor_code=target.vendor_code))
            db.flush()
    inserted, updated = _move_to_ledger(db, rows, target.vendor_code)
    activity_service.record(db, actor=actor, action="busy.unmatched_resolved", entity_type="busy_vendor", entity_id=target.id,
                            metadata={"vendor_code": target.vendor_code, "alias": code, "rows": len(rows), "how": "mapped"})
    return ResolveResult(vendor_code=target.vendor_code, moved=len(rows), inserted=inserted, updated=updated)


# ---- API key help ---------------------------------------------------------------------------

def key_info() -> KeyInfo:
    return KeyInfo(
        configured=bool(settings.BUSY_SYNC_API_KEY), endpoint_path=SYNC_PATH, header=SYNC_HEADER, env_variable="BUSY_SYNC_API_KEY",
        stale_hours=settings.BUSY_STALE_HOURS, vendor_code_regex=settings.BUSY_VENDOR_CODE_REGEX,
        instructions=("The key is a server setting, not stored in the database. To set or rotate it: generate a new key below, run "
                      "`fly secrets set BUSY_SYNC_API_KEY=<key>` in the backend folder (the API restarts by itself), then put the same key in the script on the Busy PC. "
                      "The old key stops working the moment the API restarts."),
    )


def generate_key() -> GeneratedKey:
    return GeneratedKey(key=secrets.token_urlsafe(32), note="Shown once and not saved anywhere. Set it as BUSY_SYNC_API_KEY, then give the same value to the Busy-side script.")

