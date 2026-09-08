"""
Append-only audit trail (spec section 25). No update/delete endpoint
should ever be built against this table — services only ever INSERT.
"""
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    action: Mapped[str] = mapped_column(String(64), index=True)       # "order.status_changed"
    entity_type: Mapped[str] = mapped_column(String(64))              # "order"
    entity_id: Mapped[str] = mapped_column(String(64))                # str(uuid) — entity may be non-UUID later
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
