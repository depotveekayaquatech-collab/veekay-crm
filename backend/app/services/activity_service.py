"""
Activity trail. `record()` is the ONLY way the rest of the codebase writes
to audit_logs — it only ever INSERTs (the table is append-only, see
models/audit_log.py). `list_activity()` powers the Activity page.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.repositories.activity_repository import ActivityRepository
from app.schemas.activity import ActivityOut
from app.schemas.common import Page, PageParams


def record(
    db: Session,
    *,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            organization_id=actor.organization_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            metadata_json=metadata,
        )
    )
    db.flush()


def list_for_entity(
    db: Session, org_id: uuid.UUID, entity_type: str, entity_id: str
) -> list[ActivityOut]:
    rows = ActivityRepository(db).for_entity(org_id, entity_type, entity_id)
    return [
        ActivityOut(
            id=log.id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            actor_name=actor_name,
            metadata=log.metadata_json,
            created_at=log.created_at,
        )
        for log, actor_name in rows
    ]


def list_activity(
    db: Session,
    org_id: uuid.UUID,
    params: PageParams,
    *,
    entity_type: str | None = None,
) -> Page[ActivityOut]:
    rows, total = ActivityRepository(db).list(
        org_id, offset=params.offset, limit=params.limit, entity_type=entity_type
    )
    items = [
        ActivityOut(
            id=log.id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            actor_name=actor_name,
            metadata=log.metadata_json,
            created_at=log.created_at,
        )
        for log, actor_name in rows
    ]
    return Page(items=items, total=total, page=params.page, page_size=params.page_size)
