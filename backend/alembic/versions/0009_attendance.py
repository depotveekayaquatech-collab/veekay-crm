"""phase 7: attendance sessions + offices

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offices",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_m", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_offices_organization_id", "offices", ["organization_id"])

    op.create_table(
        "attendance_sessions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("family_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("login_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_by", sa.String(10), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("location_status", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("office_id", pg.UUID(as_uuid=True), sa.ForeignKey("offices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("location_label", sa.String(128), nullable=True),
    )
    for col in ("organization_id", "user_id", "work_date", "family_id"):
        op.create_index(f"ix_attendance_sessions_{col}", "attendance_sessions", [col])
    op.create_index("ix_attendance_user_date", "attendance_sessions", ["user_id", "work_date"])


def downgrade() -> None:
    op.drop_table("attendance_sessions")
    op.drop_table("offices")
