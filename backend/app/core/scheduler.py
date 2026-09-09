"""
Background scheduler. Currently runs one job: the daily store sync from the
partner Google Sheets (default 10:00 Asia/Kolkata).

Runs in-process inside the API worker. That is fine for a single-instance
deploy; if the API is ever scaled to multiple instances this should move to
a dedicated worker / external cron to avoid duplicate runs.
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User, UserRole

log = logging.getLogger("veekay.scheduler")

_scheduler: BackgroundScheduler | None = None


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
    from app.services import store_sync_service

    db = SessionLocal()
    try:
        actor = _system_actor(db)
        if actor is None:
            log.warning("store sync skipped: no admin user to attribute it to")
            return
        results = store_sync_service.sync_all(db, actor)
        for r in results:
            log.info(
                "store sync [%s]: +%d new, %d updated, %d unchanged (%d rows)%s",
                r.platform, r.created, r.updated, r.unchanged, r.rows_read,
                f" — {len(r.warnings)} warnings" if r.warnings else "",
            )
    except Exception:  # noqa: BLE001 — a scheduled job must never crash the worker
        log.exception("daily store sync failed")
    finally:
        db.close()


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    if not (settings.STORE_SYNC_ENABLED and settings.sheet_sources()):
        log.info("store sync scheduler not started (disabled or no sheets configured)")
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
