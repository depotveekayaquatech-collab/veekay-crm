"""
Storage usage watch (read-only, and it makes NO request to the file store).

Once a day it adds up the sizes the database recorded for every stored file (versions, ticket photos, cash proofs, test
reports) and writes ONE structured log line, with a WARNING when

  * the total reaches STORAGE_WARN_PERCENT of STORAGE_QUOTA_GB (a level to warn at, not a price and not enforced), or
  * the last 7 days added far more than usual (more than 3x the weekly average of the 4 weeks before, and at least 100 MB).

Using the database instead of listing the bucket matters: a LIST is a billed Class A request per 1,000 objects, and a daily
listing would grow with every file. The recorded numbers are what the application believes it stores; scripts/storage_audit.py
compares them with the bucket on demand and also finds files the database does not know about.
It never deletes or changes anything and never logs a key list or a link.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings

log = logging.getLogger("veekay.storage")

GROWTH_FACTOR = 3.0
GROWTH_MIN_BYTES = 100 * 1000 * 1000      # a quiet week of a few photos is never "unusual growth"
GROWTH_NO_HISTORY_BYTES = 500 * 1000 * 1000


def assess(
    *, total: int, count: int, last7: int, prev28: int, quota_gb: float | None = None, warn_percent: int | None = None,
) -> dict:
    """Turn the raw numbers into the verdict. Pure, so it can be tested with made-up data."""
    quota_bytes = int((quota_gb if quota_gb is not None else settings.STORAGE_QUOTA_GB) * 1000 ** 3)
    warn_percent = warn_percent if warn_percent is not None else settings.STORAGE_WARN_PERCENT
    weekly_avg = prev28 / 4
    used_percent = round(100 * total / quota_bytes, 1) if quota_bytes else 0.0
    unusual = last7 >= GROWTH_MIN_BYTES and (last7 > GROWTH_FACTOR * weekly_avg if weekly_avg > 0 else last7 >= GROWTH_NO_HISTORY_BYTES)
    return {
        "objects": count, "total_bytes": total, "quota_bytes": quota_bytes, "used_percent": used_percent,
        "last_7_days_bytes": last7, "previous_weekly_average_bytes": int(weekly_avg),
        "near_quota": used_percent >= warn_percent, "over_quota": used_percent >= 100, "unusual_growth": unusual,
    }


def summarize(objects, *, now: datetime | None = None, quota_gb: float | None = None, warn_percent: int | None = None) -> dict:
    """From an inventory of (key, size_bytes, last_modified), e.g. the bucket listing the audit script reads."""
    now = now or datetime.now(timezone.utc)
    total = count = last7 = prev28 = 0
    week_ago, five_weeks_ago = now - timedelta(days=7), now - timedelta(days=35)
    for _key, size, modified in objects:
        total += size
        count += 1
        if modified >= week_ago:
            last7 += size
        elif modified >= five_weeks_ago:
            prev28 += size
    return assess(total=total, count=count, last7=last7, prev28=prev28, quota_gb=quota_gb, warn_percent=warn_percent)


def _recorded_files():
    """One (size_bytes, created_at) row per stored file the database knows about. Zero storage requests."""
    from app.models.cash_purchase import CashPurchase
    from app.models.compliance_document import ComplianceDocument, ComplianceDocumentVersion
    from app.models.external_activity import TicketAttachment
    from app.models.test_report import TestReport

    has_versions = select(ComplianceDocumentVersion.id).where(ComplianceDocumentVersion.document_id == ComplianceDocument.id).exists()
    return [
        select(ComplianceDocumentVersion.size_bytes.label("size"), ComplianceDocumentVersion.created_at.label("at")),
        select(ComplianceDocument.size_bytes.label("size"), ComplianceDocument.created_at.label("at")).where(~has_versions),
        select(TicketAttachment.size_bytes.label("size"), TicketAttachment.created_at.label("at")),
        select(CashPurchase.proof_size_bytes.label("size"), CashPurchase.created_at.label("at")).where(CashPurchase.proof_key.is_not(None)),
        select(TestReport.size_bytes.label("size"), TestReport.created_at.label("at")),
    ]


def usage_from_database(db: Session, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    parts = _recorded_files()
    union = parts[0].union_all(*parts[1:]).subquery()
    week_ago, five_weeks_ago = now - timedelta(days=7), now - timedelta(days=35)
    total, count, last7, prev28 = db.execute(
        select(
            func.coalesce(func.sum(union.c.size), 0),
            func.count(),
            func.coalesce(func.sum(union.c.size).filter(union.c.at >= week_ago), 0),
            func.coalesce(func.sum(union.c.size).filter(union.c.at < week_ago, union.c.at >= five_weeks_ago), 0),
        )
    ).one()
    return assess(total=int(total), count=int(count), last7=int(last7), prev28=int(prev28))


def check_and_log() -> dict | None:
    """The daily check. Never raises: a monitoring problem must not affect the sync it rides on."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        s = usage_from_database(db)
    except Exception as exc:  # noqa: BLE001
        log.warning("storage usage check failed", extra={"error": type(exc).__name__})
        return None
    finally:
        db.close()
    extra = {k: s[k] for k in ("objects", "total_bytes", "used_percent", "last_7_days_bytes")}
    log.info("storage usage", extra=extra)
    if s["over_quota"]:
        log.warning("storage is over the configured quota", extra=extra)
    elif s["near_quota"]:
        log.warning("storage is close to the configured quota", extra=extra)
    if s["unusual_growth"]:
        log.warning("storage grew unusually fast this week", extra={**extra, "previous_weekly_average_bytes": s["previous_weekly_average_bytes"]})
    return s
