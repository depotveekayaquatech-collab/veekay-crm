"""tickets raised from outside (Google Apps Script)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("source", sa.String(16), nullable=False, server_default="app"))
    op.add_column("tickets", sa.Column("external_id", sa.String(128), nullable=True))
    op.add_column("tickets", sa.Column("reporter", sa.String(255), nullable=True))
    op.create_index(
        "uq_tickets_org_external_id", "tickets", ["organization_id", "external_id"], unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tickets_org_external_id", table_name="tickets")
    op.drop_column("tickets", "reporter")
    op.drop_column("tickets", "external_id")
    op.drop_column("tickets", "source")
