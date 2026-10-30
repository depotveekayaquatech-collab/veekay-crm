"""PerformanceSnapshot = what a performance report said when it was produced (migration 0062). Append-only: the database refuses UPDATE, DELETE and
TRUNCATE. A report that needs correcting is a NEW snapshot with `revision_of` and a reason, never an edit."""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    partner_slug: Mapped[str] = mapped_column(Text)
    month: Mapped[date] = mapped_column(Date)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    generated_by_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text)
    definition_version: Mapped[str] = mapped_column(Text)
    judged_days: Mapped[list] = mapped_column(JSONB)
    employees: Mapped[list] = mapped_column(JSONB)
    scopes: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[dict] = mapped_column(JSONB)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(Text)
    revision_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_snapshots.id"), nullable=True)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
