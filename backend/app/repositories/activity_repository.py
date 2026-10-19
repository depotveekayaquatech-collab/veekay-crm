"""Read access to the append-only audit_logs table for the activity feed."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


class ActivityRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        org_id: uuid.UUID,
        *,
        offset: int,
        limit: int,
        entity_type: str | None = None,
    ) -> tuple[list[tuple[AuditLog, str | None]], int]:
        base = (
            select(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(AuditLog.organization_id == org_id)
        )
        if entity_type:
            base = base.where(AuditLog.entity_type == entity_type)

        total = self.db.execute(
            select(func.count()).select_from(
                base.with_only_columns(AuditLog.id).order_by(None).subquery()
            )
        ).scalar_one()
        rows = self.db.execute(
            base.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return [(row[0], row[1]) for row in rows], total

    def for_entity(
        self, org_id: uuid.UUID, entity_type: str, entity_id: str
    ) -> list[tuple[AuditLog, str | None]]:
        stmt = (
            select(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(
                AuditLog.organization_id == org_id,
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc())
        )
        return [(row[0], row[1]) for row in self.db.execute(stmt).all()]
