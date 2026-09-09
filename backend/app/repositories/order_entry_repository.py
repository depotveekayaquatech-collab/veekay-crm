"""Data access for daily bottle-count entries."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.order_entry import OrderEntry
from app.models.store import Store
from app.models.user import User


class OrderEntryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, store_id: uuid.UUID, order_date: date) -> OrderEntry | None:
        stmt = select(OrderEntry).where(
            OrderEntry.store_id == store_id, OrderEntry.order_date == order_date
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def month_map(self, store_id: uuid.UUID, year: int, month: int) -> dict[int, OrderEntry]:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        stmt = select(OrderEntry).where(
            OrderEntry.store_id == store_id,
            OrderEntry.order_date >= start,
            OrderEntry.order_date < end,
        )
        return {e.order_date.day: e for e in self.db.execute(stmt).scalars()}

    def rollup_for_date(
        self, store_ids: list[uuid.UUID], target: date
    ) -> tuple[int, int]:
        """(entries_count, bottles_total) across store_ids on `target`."""
        if not store_ids:
            return (0, 0)
        row = self.db.execute(
            select(func.count(OrderEntry.id), func.coalesce(func.sum(OrderEntry.bottle_count), 0)).where(
                OrderEntry.store_id.in_(store_ids), OrderEntry.order_date == target
            )
        ).one()
        return (int(row[0]), int(row[1]))

    def daily_totals_between(
        self, org_id: uuid.UUID, start: date, end: date
    ) -> dict[date, tuple[int, int]]:
        """{order_date: (entries_count, bottles_total)} for start..end inclusive."""
        stmt = (
            select(
                OrderEntry.order_date,
                func.count(OrderEntry.id),
                func.coalesce(func.sum(OrderEntry.bottle_count), 0),
            )
            .where(
                OrderEntry.organization_id == org_id,
                OrderEntry.order_date >= start,
                OrderEntry.order_date <= end,
            )
            .group_by(OrderEntry.order_date)
        )
        return {r[0]: (int(r[1]), int(r[2])) for r in self.db.execute(stmt).all()}

    def recent_for_partner(
        self, org_id: uuid.UUID, partner_id: uuid.UUID, limit: int
    ) -> list[tuple[OrderEntry, str | None, str, str]]:
        stmt = (
            select(OrderEntry, User.full_name, Store.name, Store.external_code)
            .join(Store, Store.id == OrderEntry.store_id)
            .outerjoin(User, User.id == OrderEntry.marked_by_user_id)
            .where(OrderEntry.organization_id == org_id, Store.partner_organization_id == partner_id)
            .order_by(OrderEntry.updated_at.desc())
            .limit(limit)
        )
        return [(r[0], r[1], r[2], r[3]) for r in self.db.execute(stmt).all()]

    def add(self, entry: OrderEntry) -> OrderEntry:
        self.db.add(entry)
        self.db.flush()
        return entry

    def store_with_meta(self, org_id: uuid.UUID, store_id: uuid.UUID) -> Store | None:
        stmt = (
            select(Store)
            .where(Store.organization_id == org_id, Store.id == store_id)
            .options(joinedload(Store.region), joinedload(Store.partner_organization))
        )
        return self.db.execute(stmt).scalar_one_or_none()
