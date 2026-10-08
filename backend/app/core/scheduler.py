"""
Background scheduler. Currently runs one job: the daily sync from the partner Google Sheets —
stores first, then order counts (default 10:00 Asia/Kolkata).

Runs in-process inside the API worker. With several instances every one fires
the job, but a Postgres advisory lock makes only one of them actually run it.
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.role import Role
from app.models.user import User, UserRole

log = logging.getLogger("veekay.scheduler")

_scheduler: BackgroundScheduler | None = None
_SYNC_LOCK_KEY = 7_340_001   # arbitrary app-wide constant for pg advisory locks


def _system_actor(db) -> User | None:
    """The daily job needs a User to attribute audit-log rows to — use the
    first admin in the org."""
    return db.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == "admin")
        .order_by(User.created_at)
    ).scalars().first()


def run_daily_store_sync() -> None:
    from app.services import order_import_service, store_sync_service

    db = SessionLocal()
    # Session-level locks belong to one connection, so hold a dedicated one (the ORM session commits and
    # may hand its connection back to the pool mid-job).
    lock_conn = engine.connect()
    locked = False
    try:
        # Several API machines may all fire this job; a Postgres advisory lock lets exactly one of them run it.
        locked = bool(lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SYNC_LOCK_KEY}).scalar())
        if not locked:
            log.info("store sync skipped: another instance is already running it")
            return
        actor = _system_actor(db)
        if actor is None:
            log.warning("store sync skipped: no admin user to attribute it to")
            return
        if settings.sheet_sources():
            for r in store_sync_service.sync_all(db, actor):
                log.info(
                    "store sync [%s]: +%d new, %d updated, %d unchanged (%d rows)%s",
                    r.platform, r.created, r.updated, r.unchanged, r.rows_read,
                    f" — {len(r.warnings)} warnings" if r.warnings else "",
                )
        # Orders after stores, so a store added by the sheet above can receive its counts in the same run.
        if settings.ORDER_SYNC_ENABLED and settings.order_sheet_sources():
            for o in order_import_service.sync_all(db, actor):
                log.info(
                    "order sync [%s]: +%d new, %d updated, %d unchanged (%d rows)%s",
                    o.platform, o.created, o.updated, o.unchanged, o.rows_read,
                    f" — {len(o.warnings)} warnings" if o.warnings else "",
                )
    except Exception:  # noqa: BLE001 — a scheduled job must never crash the worker
        log.exception("daily store sync failed")
    finally:
        if locked:
            from app.core.cache import read_cache

            read_cache.invalidate()  # the sync wrote outside a web request, so tell every worker the data changed
        if locked:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SYNC_LOCK_KEY})
        lock_conn.close()
        db.close()


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    has_sheets = bool(settings.sheet_sources()) or (settings.ORDER_SYNC_ENABLED and bool(settings.order_sheet_sources()))
    if not (settings.STORE_SYNC_ENABLED and has_sheets):
        log.info("sheet sync scheduler not started (disabled or no sheets configured)")
        return

    try:
        tz = ZoneInfo(settings.STORE_SYNC_TIMEZONE)
    except Exception:  # noqa: BLE001
        log.warning("unknown timezone %r, falling back to UTC", settings.STORE_SYNC_TIMEZONE)
        tz = ZoneInfo("UTC")

    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.add_job(
        run_daily_store_sync,
        CronTrigger(hour=settings.STORE_SYNC_HOUR, minute=settings.STORE_SYNC_MINUTE, timezone=tz),
        id="daily_store_sync",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    _scheduler.start()
    log.info(
        "store sync scheduled daily at %02d:%02d %s",
        settings.STORE_SYNC_HOUR, settings.STORE_SYNC_MINUTE, settings.STORE_SYNC_TIMEZONE,
    )


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
