"""
The home page of a partner account (a Blinkit / Zepto login): how its own platform is doing today — stores,
entries, bottles, regions, and its tickets. Everything is scoped to the caller's platform; nothing else is reachable.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.order_entry import OrderEntry
from app.models.organization import Organization
from app.models.store import Store, StoreStatus
from app.models.ticket import ACTIVE_STATUSES, Ticket
from app.models.user import User
from app.services import assignment_service, matrix_service, order_service

TREND_DAYS = 14


def _pct(done: int, total: int) -> int:
    return round(done / total * 100) if total else 0


def overview(db: Session, user: User, perms: set[str]) -> dict:
    if not assignment_service.is_partner_account(db, user) or user.platform_organization_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This page is for partner accounts.")
    org_id, platform_id = user.organization_id, user.platform_organization_id
    platform = db.get(Organization, platform_id)
    today = order_service._today()
    yesterday = today - timedelta(days=1)
    out: dict = {
        "platform": {"slug": platform.slug if platform else None, "name": platform.name if platform else "Your platform"},
        "today": today,
        "contact": user.full_name,
        "sections": {"entries": "orders.view" in perms, "tickets": "tickets.view" in perms},
    }

    if "orders.view" in perms:
        stores = db.execute(
            select(Store).where(Store.organization_id == org_id, Store.partner_organization_id == platform_id)
            .options(joinedload(Store.region))
        ).unique().scalars().all()
        live = [s for s in stores if s.status == StoreStatus.LIVE.value]
        live_ids = {s.id for s in live}
        by_status = defaultdict(int)
        for s in stores:
            by_status[s.status] += 1

        month_start = today.replace(day=1)
        trend_start = today - timedelta(days=TREND_DAYS - 1)
        since = min(month_start, trend_start)
        rows = db.execute(
            select(OrderEntry.store_id, OrderEntry.order_date, OrderEntry.bottle_count)
            .join(Store, Store.id == OrderEntry.store_id)
            .where(Store.organization_id == org_id, Store.partner_organization_id == platform_id, OrderEntry.order_date >= since)
        ).all()

        per_day: dict[date, list[int]] = defaultdict(lambda: [0, 0])  # date -> [entries, bottles]
        marked_today: dict = {}
        month_entries = month_bottles = 0
        for store_id, d, bottles in rows:
            per_day[d][0] += 1
            per_day[d][1] += int(bottles)
            if d == today:
                marked_today[store_id] = int(bottles)
            if d >= month_start:
                month_entries += 1
                month_bottles += int(bottles)

        done_today = sum(1 for sid in marked_today if sid in live_ids)
        yesterday_entries, yesterday_bottles = per_day[yesterday]
        regions: dict[str, dict] = {}
        for s in live:
            key = s.region.name if s.region else "No region"
            r = regions.setdefault(key, {"region": key, "stores": 0, "marked": 0, "bottles": 0})
            r["stores"] += 1
            if s.id in marked_today:
                r["marked"] += 1
                r["bottles"] += marked_today[s.id]
        region_rows = sorted(
            ({**r, "percent": _pct(r["marked"], r["stores"])} for r in regions.values()),
            key=lambda r: (r["percent"], r["region"]),
        )
        awaiting = sorted((s for s in live if s.id not in marked_today), key=lambda s: (s.state or "", s.name))[:8]

        out["entries"] = {
            "stores": {"live": len(live), "pending": by_status.get("PENDING", 0), "closed": by_status.get("CLOSE", 0), "total": len(stores)},
            "today": {
                "marked": done_today, "of": len(live), "percent": _pct(done_today, len(live)),
                "bottles": sum(b for sid, b in marked_today.items() if sid in live_ids),
                "yesterday_entries": yesterday_entries, "yesterday_bottles": yesterday_bottles,
            },
            "month": {"entries": month_entries, "bottles": month_bottles, "label": f"{month_start:%B %Y}"},
            "trend": [
                {
                    "label": f"{(trend_start + timedelta(days=i)).strftime('%a')} {(trend_start + timedelta(days=i)).day}",
                    "entries": per_day[trend_start + timedelta(days=i)][0],
                    "bottles": per_day[trend_start + timedelta(days=i)][1],
                }
                for i in range(TREND_DAYS)
            ],
            "regions": region_rows,
            "awaiting": [
                {"id": s.id, "name": s.name, "code": s.external_code, "city": s.city, "state": s.state,
                 "region": s.region.name if s.region else None}
                for s in awaiting
            ],
            "awaiting_total": len(live) - done_today,
        }

    if "tickets" in out["sections"] and out["sections"]["tickets"]:
        now = datetime.now(timezone.utc)
        base = Ticket.organization_id == org_id, Ticket.partner_organization_id == platform_id
        active = db.execute(select(Ticket).where(*base, Ticket.status.in_(ACTIVE_STATUSES))).scalars().all()
        resolved_30 = db.execute(
            select(func.count()).select_from(Ticket).where(
                *base, Ticket.resolved_at.is_not(None), Ticket.resolved_at >= now - timedelta(days=30)
            )
        ).scalar_one()
        recent = db.execute(
            select(Ticket).where(*base).options(joinedload(Ticket.store)).order_by(Ticket.created_at.desc()).limit(6)
        ).unique().scalars().all()
        out["tickets"] = {
            "open": sum(1 for t in active if t.status == "OPEN"),
            "in_progress": sum(1 for t in active if t.status == "IN_PROGRESS"),
            "overdue": sum(1 for t in active if t.due_at is not None and t.due_at < now),
            "resolved_30d": int(resolved_30),
            "recent": [
                {
                    "id": t.id, "number": t.number, "title": t.title, "status": t.status, "priority": t.priority,
                    "category": t.category, "store": t.store.name, "created_at": t.created_at,
                    "is_overdue": t.status in ACTIVE_STATUSES and t.due_at is not None and t.due_at < now,
                }
                for t in recent
            ],
        }
    return out


def delivery_report_xlsx(db: Session, user: User, start: date, end: date) -> tuple[bytes, str]:
    """The daily distribution sheet for the partner's own platform — never another platform, and without totals."""
    if not assignment_service.is_partner_account(db, user) or user.platform_organization_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This report is for partner accounts.")
    platform = db.get(Organization, user.platform_organization_id)
    slug = platform.slug if platform else None
    if not slug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Your platform couldn't be found.")
    data = matrix_service.matrix_xlsx(db, user, start, end, partner=slug, state=None, city=None, totals=False)
    return data, f"{slug}-delivery-report-{start}_{end}.xlsx"
