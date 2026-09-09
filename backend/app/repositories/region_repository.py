"""Data access for regions. Every query is scoped to one organization."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.region import Region
from app.models.store import Store, StoreStatus


class RegionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, org_id: uuid.UUID, region_id: uuid.UUID) -> Region | None:
        stmt = select(Region).where(Region.organization_id == org_id, Region.id == region_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, org_id: uuid.UUID, code: str) -> Region | None:
        stmt = select(Region).where(Region.organization_id == org_id, Region.code == code)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(
        self, org_id: uuid.UUID, *, offset: int, limit: int, active_only: bool = False
    ) -> tuple[list[Region], int]:
        base = select(Region).where(Region.organization_id == org_id)
        if active_only:
            base = base.where(Region.is_active.is_(True))
        total = self.db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()
        rows = (
            self.db.execute(base.order_by(Region.name).offset(offset).limit(limit))
            .scalars()
            .all()
        )
        return list(rows), total

    def store_counts(self, region_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not region_ids:
            return {}
        stmt = (
            select(Store.region_id, func.count(Store.id))
            .where(Store.region_id.in_(region_ids), Store.status == StoreStatus.LIVE.value)
            .group_by(Store.region_id)
        )
        return {rid: count for rid, count in self.db.execute(stmt).all()}

    def add(self, region: Region) -> Region:
        self.db.add(region)
        self.db.flush()
        return region
