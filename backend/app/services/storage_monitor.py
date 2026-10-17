"""
Storage usage watch (read-only). Once a day it lists the bucket (1 Tigris "Class A" request per 1,000 objects) and writes ONE
structured log line, with a WARNING when

  * the total reaches STORAGE_WARN_PERCENT of STORAGE_QUOTA_GB (a number to warn at, not a price and not enforced), or
  * the last 7 days added far more than usual (more than 3x the weekly average of the 4 weeks before, and at least 100 MB).

It never deletes or changes anything and never logs a key list or a link. The same numbers appear in scripts/storage_audit.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core import storage
from app.core.config import settings

log = logging.getLogger("veekay.storage")

GROWTH_FACTOR = 3.0
GROWTH_MIN_BYTES = 100 * 1000 * 1000      # a quiet week of a few photos is never "unusual growth"
GROWTH_NO_HISTORY_BYTES = 500 * 1000 * 1000


def summarize(objects, *, now: datetime | None = None, quota_gb: float | None = None, warn_percent: int | None = None) -> dict:
    """objects: iterable of (key, size_bytes, last_modified). Pure function so it can be tested with made-up data."""
    now = now or datetime.now(timezone.utc)
    quota_bytes = int((quota_gb if quota_gb is not None else settings.STORAGE_QUOTA_GB) * 1000 ** 3)
    warn_percent = warn_percent if warn_percent is not None else settings.STORAGE_WARN_PERCENT
    total = count = last7 = prev28 = 0
    week_ago, five_weeks_ago = now - timedelta(days=7), now - timedelta(days=35)
    for _key, size, modified in objects:
        total += size
        count += 1
        if modified >= week_ago:
            last7 += size
        elif modified >= five_weeks_ago:
            prev28 += size
    weekly_avg = prev28 / 4
    used_percent = round(100 * total / quota_bytes, 1) if quota_bytes else 0.0
    unusual = last7 >= GROWTH_MIN_BYTES and (last7 > GROWTH_FACTOR * weekly_avg if weekly_avg > 0 else last7 >= GROWTH_NO_HISTORY_BYTES)
    return {
        "objects": count, "total_bytes": total, "quota_bytes": quota_bytes, "used_percent": used_percent,
        "last_7_days_bytes": last7, "previous_weekly_average_bytes": int(weekly_avg),
        "near_quota": used_percent >= warn_percent, "over_quota": used_percent >= 100, "unusual_growth": unusual,
    }


def check_and_log() -> dict | None:
    """The daily check. Never raises: a monitoring problem must not affect the sync it rides on."""
    try:
        s = summarize(storage.list_objects())
    except Exception as exc:  # noqa: BLE001
        log.warning("storage usage check failed", extra={"error": type(exc).__name__})
        return None
    extra = {k: s[k] for k in ("objects", "total_bytes", "used_percent", "last_7_days_bytes")}
    log.info("storage usage", extra=extra)
    if s["over_quota"]:
        log.warning("storage is over the configured quota", extra=extra)
    elif s["near_quota"]:
        log.warning("storage is close to the configured quota", extra=extra)
    if s["unusual_growth"]:
        log.warning("storage grew unusually fast this week", extra={**extra, "previous_weekly_average_bytes": s["previous_weekly_average_bytes"]})
    return s
