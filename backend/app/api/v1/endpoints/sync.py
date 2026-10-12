"""Sheet sync: when it last ran, when it runs next, and "Sync now".

The daily job (10:00 Asia/Kolkata by default) and "Sync now" run the very same routine (core.scheduler.execute_sync),
under the same lock, so they can never run twice at once. Everything the web app and the mobile app show is read straight
from the CRM, so a sync is the only thing that brings sheet data in.
"""
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_permissions, get_current_user, require_permission
from app.core import scheduler
from app.core.cache import read_cache
from app.core.config import settings
from app.db.session import engine, get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/sync", tags=["sync"])


class SyncStatus(BaseModel):
    schedule: str | None            # "10:00 Asia/Kolkata", or None when the daily job is off
    next_run_at: str | None
    last_run_at: str | None
    last_run_source: str | None     # scheduled | manual
    last_run_by: str | None
    last_run_warnings: int | None
    stores_sheets: int
    orders_sheets: int
    can_sync: bool


class SyncRun(BaseModel):
    stores: list[dict]
    orders: list[dict]


@router.get("/status", response_model=SyncStatus)
def sync_status(
    user: User = Depends(get_current_user), perms: set[str] = Depends(get_current_permissions), db: Session = Depends(get_db),
) -> SyncStatus:
    last = db.execute(
        select(AuditLog).where(AuditLog.organization_id == user.organization_id, AuditLog.action == "sheet_sync.run")
        .order_by(AuditLog.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    meta = (last.metadata_json or {}) if last else {}
    by = db.get(User, last.user_id).full_name if last and last.user_id and meta.get("source") == "manual" and db.get(User, last.user_id) else None
    nxt = scheduler.next_run_at()
    return SyncStatus(
        schedule=f"{settings.STORE_SYNC_HOUR:02d}:{settings.STORE_SYNC_MINUTE:02d} {settings.STORE_SYNC_TIMEZONE}" if settings.STORE_SYNC_ENABLED else None,
        next_run_at=nxt.isoformat() if nxt else None,
        last_run_at=last.created_at.isoformat() if last else None,
        last_run_source=meta.get("source"),
        last_run_by=by,
        last_run_warnings=meta.get("warnings") if last else None,
        stores_sheets=len(settings.sheet_sources()),
        orders_sheets=len(settings.order_sheet_sources()) if settings.ORDER_SYNC_ENABLED else 0,
        can_sync="sheets.sync" in perms,
    )


@router.post("/trigger")
def trigger(x_sync_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    """For an external scheduler: runs the same daily sync (stores, then orders) when the call carries the right key.
    Calling it twice close together does nothing the second time, so a retrying scheduler is safe."""
    configured = settings.SYNC_TRIGGER_KEY
    if not configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The sync trigger is not switched on (SYNC_TRIGGER_KEY is not set).")
    if not x_sync_key or not hmac.compare_digest(x_sync_key.encode(), configured.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid sync key.")
    recent = db.execute(
        select(AuditLog.id).where(AuditLog.action == "sheet_sync.run", AuditLog.created_at > datetime.now(timezone.utc) - timedelta(minutes=30)).limit(1)
    ).first()
    if recent:
        return {"ran": False, "reason": "A sync already ran in the last 30 minutes."}
    actor = scheduler._system_actor(db)
    if actor is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No admin user exists to attribute the sync to.")
    conn = engine.connect()
    try:
        if not scheduler.try_lock(conn):
            return {"ran": False, "reason": "A sync is already running."}
        try:
            result = scheduler.execute_sync(db, actor, "scheduled")
        finally:
            read_cache.invalidate()
            scheduler.unlock(conn)
    finally:
        conn.close()
    return {"ran": True, "stores": len(result["stores"]), "orders": len(result["orders"])}


@router.post("/run", response_model=SyncRun, dependencies=[Depends(require_permission("sheets.sync"))])
def run_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SyncRun:
    """Pull stores, then order counts, from the configured sheets right now (same routine as the 10:00 job)."""
    if not settings.sheet_sources() and not (settings.ORDER_SYNC_ENABLED and settings.order_sheet_sources()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No sheets are configured. Set STORE_SYNC_SHEETS / ORDER_SYNC_SHEETS on the server first.")
    conn = engine.connect()
    try:
        if not scheduler.try_lock(conn):
            raise HTTPException(status.HTTP_409_CONFLICT, "A sync is already running. Try again in a minute.")
        try:
            result = scheduler.execute_sync(db, user, "manual")
        except Exception as exc:  # noqa: BLE001 - surface the reason instead of a bare 500
            db.rollback()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The sync failed: {exc}") from exc
        finally:
            read_cache.invalidate()
            scheduler.unlock(conn)
    finally:
        conn.close()
    return SyncRun(**result)
