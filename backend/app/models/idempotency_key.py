"""
IdempotencyKey = one client-chosen key for one create request, so a retry returns the ORIGINAL result instead of making
a second ticket / reply / document / purchase.

The phone generates a key per form submission and sends it as the `Idempotency-Key` header; resending the same key (a
timed-out upload, a double tap, an app restart) replays the stored response. Optional: a request without the header
behaves exactly as before. Rows are only bookkeeping and are purged after a few days (see core/idempotency.py).
"""
from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IdempotencyKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("owner", "endpoint", "key", name="uq_idempotency_owner_endpoint_key"),
        Index("ix_idempotency_keys_created_at", "created_at"),
    )

    owner: Mapped[str] = mapped_column(String(64))      # the account / user that sent it: keys never collide across people
    endpoint: Mapped[str] = mapped_column(String(64))   # e.g. "external.ticket.create"
    key: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(12), default="pending")   # pending -> done
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
