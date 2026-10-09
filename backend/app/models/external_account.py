"""
ExternalAccount = a login for a vendor or a store POC (point of contact), created ahead of the app they will use.

These are NOT CRM users: they have no role, no permissions and cannot sign in to this CRM. They live in their own
table so the Team page, attendance and assignments never see them. The future vendor / POC app signs them in from here.

Standard format (see scripts/create_external_accounts.py):
    vendor  <name>@supplier.com   password 123456
    POC     <name>@blinkit.com    password <name>@123
`must_change_password` is set on every account: the first thing the app must do is make the person choose their own.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AccountKind:
    VENDOR = "vendor"
    POC = "poc"


class ExternalAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "external_accounts"
    __table_args__ = (UniqueConstraint("email", name="uq_external_account_email"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)
    email: Mapped[str] = mapped_column(String(255))                      # the login id, always lower case
    full_name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platforms: Mapped[list] = mapped_column(JSONB, default=list)         # ["blinkit", "zepto"] the person works with
    store_count: Mapped[int] = mapped_column(Integer, default=0)
    password_hash: Mapped[str] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ExternalAccountStore(Base):
    """Which stores a vendor supplies / a POC looks after."""
    __tablename__ = "external_account_stores"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("external_accounts.id", ondelete="CASCADE"), primary_key=True)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True, index=True)
