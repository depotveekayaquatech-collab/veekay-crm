"""
DeletedRow = a copy of a row at the moment it was deleted (kept by a database trigger, see migration 0043), and OrderEntryChange = the
old and new number every time an order entry was changed. Nothing in the app writes or removes these: the database does, so no code
path, app build or hand-typed SQL can lose an order entry without leaving it here.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeletedRow(Base):
    __tablename__ = "deleted_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name: Mapped[str] = mapped_column(Text)
    row_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderEntryChange(Base):
    __tablename__ = "order_entry_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    order_date: Mapped[date] = mapped_column(Date)
    old_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_cash_adjustment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_cash_adjustment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_source: Mapped[str | None] = mapped_column(String, nullable=True)
    new_source: Mapped[str | None] = mapped_column(String, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
