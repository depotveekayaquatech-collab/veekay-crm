"""a store's name is its identity: the Outlet ID may repeat (duplicates are listed for someone to correct)

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-22
"""
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_store_partner_code", "stores", type_="unique")
    op.create_index("ix_stores_partner_code", "stores", ["partner_organization_id", "external_code"])


def downgrade() -> None:
    # fails on purpose while two stores of a platform still share an Outlet ID: fix them (Stores > Duplicates) first
    op.drop_index("ix_stores_partner_code", table_name="stores")
    op.create_unique_constraint("uq_store_partner_code", "stores", ["partner_organization_id", "external_code"])
