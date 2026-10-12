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


def execute_sync(db, actor: User, source: str) -> dict:
    """One full sync: stores first, then order counts (so a store added by the sheet can get its counts in the same run).
    Used by the daily 10:00 job (source="scheduled") and by "Sync now" (source="manual"). Records when it ran."""
    from app.services import activity_service, order_import_service, store_sync_service

    out: dict = {"stores": [], "orders": []}
    if settings.sheet_sources():
        out["stores"] = [r.as_dict() for r in store_sync_service.sync_all(db, actor)]
    if settings.ORDER_SYNC_ENABLED and settings.order_sheet_sources():
        out["orders"] = [o.as_dict() for o in order_import_service.sync_all(db, actor)]
    warnings = sum(len(x.get("warnings", [])) for x in out["stores"] + out["orders"])
    # Bill-due reminders to vendors and POCs ride on the same daily run. A failure here never undoes the sync.
    reminders = 0
    try:
        from app.services import reminder_service

        reminders = reminder_service.send_bill_reminders(db)["reminders"]
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("bill reminders failed")
    activity_service.record(
        db, actor=actor, action="sheet_sync.run", entity_type="sync", entity_id="sheets",
        metadata={"source": source, "stores": len(out["stores"]), "orders": len(out["orders"]), "warnings": warnings, "reminders": reminders},
    )
    db.commit()
    return out


def try_lock(conn) -> bool:
    return bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SYNC_LOCK_KEY}).scalar())


def unlock(conn) -> None:
    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SYNC_LOCK_KEY})


def next_run_at():
    """The next scheduled daily run, as a timezone-aware datetime (None when the job is switched off)."""
    from datetime import datetime, timedelta

    if not settings.STORE_SYNC_ENABLED:
        return None
    try:
        tz = ZoneInfo(settings.STORE_SYNC_TIMEZONE)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    run = now.replace(hour=settings.STORE_SYNC_HOUR, minute=settings.STORE_SYNC_MINUTE, second=0, microsecond=0)
    return run if run > now else run + timedelta(days=1)


def run_daily_store_sync() -> None:
    from app.services import order_import_service, store_sync_service  # noqa: F401

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
        result = execute_sync(db, actor, "scheduled")
        for kind in ("stores", "orders"):
            for x in result[kind]:
                log.info(
                    "%s sync [%s]: +%d new, %d updated, %d unchanged (%d rows)%s",
                    kind[:-1], x.get("platform"), x.get("created", 0), x.get("updated", 0), x.get("unchanged", 0), x.get("rows_read", 0),
                    f" — {len(x['warnings'])} warnings" if x.get("warnings") else "",
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
    if not settings.STORE_SYNC_ENABLED:
        log.info("daily sync scheduler not started (disabled)")
        return
    # Started even with no sheets configured: the daily run also sends the bill-due reminders.

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
