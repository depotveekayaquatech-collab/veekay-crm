"""
What vendors / POCs (external_accounts) write from their app: ticket photos, delivery confirmations, and the
notification feed + device tokens that drive push messages. Tickets and comments themselves live in the normal
ticket tables (raised with source='vendor_app'), so staff see them in the same place as every other ticket.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DeliveryOutcome:
    RECEIVED = "RECEIVED"
    SHORT = "SHORT"
    DAMAGED = "DAMAGED"


class TicketAttachment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A photo on a ticket (or on one comment of it). Append-only, like compliance files."""
    __tablename__ = "ticket_attachments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    comment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ticket_comments.id", ondelete="CASCADE"), nullable=True)
    file_key: Mapped[str] = mapped_column(String(512))
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_accounts.id", ondelete="SET NULL"), nullable=True
    )


class DeliveryConfirmation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A vendor / POC saying "this store's delivery on <date> arrived complete / short / damaged"."""
    __tablename__ = "delivery_confirmations"
    __table_args__ = (UniqueConstraint("account_id", "store_id", "delivery_date", name="uq_delivery_account_store_date"),)

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("external_accounts.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    delivery_date: Mapped[date] = mapped_column(Date, index=True)
    outcome: Mapped[str] = mapped_column(String(10))
    expected_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    received_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)


class ExternalDevice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A phone registered for push messages (an FCM token). One token belongs to one account at a time."""
    __tablename__ = "external_devices"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("external_accounts.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[str] = mapped_column(String(16))     # android | ios | web
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExternalNotification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """In-app feed entry; a push is sent for it too when Firebase is configured."""
    __tablename__ = "external_notifications"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("external_accounts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))         # ticket | bill
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(500))
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # the ticket / document id to open
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StaffNotification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """In-app feed entry for a Veekay employee or admin (leave decided, ticket assigned, new ticket from a POC ...)."""
    __tablename__ = "staff_notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))         # leave | ticket
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(500))
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StaffDevice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A phone registered for push messages by a Veekay employee (an FCM token)."""
    __tablename__ = "staff_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[str] = mapped_column(String(16))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BillReminder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A bill-due reminder already sent for a stage, so each stage is sent once per bill however often the job runs."""
    __tablename__ = "bill_reminders"
    __table_args__ = (UniqueConstraint("document_id", "stage", name="uq_bill_reminder_stage"),)

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("compliance_documents.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(16))        # soon | due | late7 | late14 | late30
