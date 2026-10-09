"""Data access for stores. Scoped to the owning (Veekay) organization."""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.organization import Organization
from app.models.store import Store, StoreStatus


class StoreRepository:
    def __init__(self, db: Session):
        self.db = db

    def _loaded(self, stmt):
        return stmt.options(
            joinedload(Store.region), joinedload(Store.partner_organization)
        )

    def get(self, org_id: uuid.UUID, store_id: uuid.UUID) -> Store | None:
        stmt = self._loaded(select(Store)).where(
            Store.organization_id == org_id, Store.id == store_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_code(self, partner_org_id: uuid.UUID, external_code: str) -> Store | None:
        stmt = select(Store).where(
            Store.partner_organization_id == partner_org_id,
            Store.external_code == external_code,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        org_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        region_id: uuid.UUID | None = None,
        partner_slug: str | None = None,
        state: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Store], int]:
        base = self._loaded(select(Store)).where(Store.organization_id == org_id)
        if search and search.strip():
            raw = search.strip()
            for ch in ("\\", "%", "_"):
                raw = raw.replace(ch, "\\" + ch)
            like = f"%{raw}%"
            base = base.where(
                or_(
                    Store.name.ilike(like, escape="\\"),
                    Store.external_code.ilike(like, escape="\\"),
                    Store.city.ilike(like, escape="\\"),
                    Store.state.ilike(like, escape="\\"),
                    Store.vendor_name.ilike(like, escape="\\"),
                    Store.vendor_number.ilike(like, escape="\\"),
                    Store.poc_name.ilike(like, escape="\\"),
                    Store.poc_number.ilike(like, escape="\\"),
                )
            )
        if region_id is not None:
            base = base.where(Store.region_id == region_id)
        if partner_slug:
            base = base.join(Organization, Organization.id == Store.partner_organization_id).where(
                Organization.slug == partner_slug
            )
        if state:
            base = base.where(func.lower(Store.state) == state.lower())
        if status:
            base = base.where(Store.status == status)

        total = self.db.execute(
            select(func.count()).select_from(base.with_only_columns(Store.id).order_by(None).subquery())
        ).scalar_one()
        rows = (
            self.db.execute(base.order_by(Store.name).offset(offset).limit(limit))
            .unique()
            .scalars()
            .all()
        )
        return list(rows), total

    def live_in_scope(
        self,
        org_id: uuid.UUID,
        partner_org_id: uuid.UUID,
        *,
        region_id: uuid.UUID | None = None,
        states: list[str] | None = None,
    ) -> list[Store]:
        """LIVE stores for a platform, optionally narrowed to a region and/or a
        set of states (used by the assignment resolver)."""
        stmt = self._loaded(select(Store)).where(
            Store.organization_id == org_id,
            Store.partner_organization_id == partner_org_id,
            Store.status == StoreStatus.LIVE.value,
        )
        if region_id is not None:
            stmt = stmt.where(Store.region_id == region_id)
        if states is not None:
            lowered = [s.lower() for s in states]
            stmt = stmt.where(func.lower(Store.state).in_(lowered))
        return list(self.db.execute(stmt.order_by(Store.name)).unique().scalars().all())

    def get_many(self, org_id: uuid.UUID, store_ids: list[uuid.UUID]) -> list[Store]:
        if not store_ids:
            return []
        stmt = self._loaded(select(Store)).where(
            Store.organization_id == org_id, Store.id.in_(store_ids)
        )
        return list(self.db.execute(stmt).unique().scalars().all())

    def add(self, store: Store) -> Store:
        self.db.add(store)
        self.db.flush()
        return store
