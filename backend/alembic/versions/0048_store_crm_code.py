"""every store gets a permanent system code: BKT000123 (Blinkit), ZPT000045 (Zepto), unique across the whole system

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

# the prefix per platform; any other platform gets the first three letters of its slug
PREFIX_SQL = (
    "CASE o.slug WHEN 'blinkit' THEN 'BKT' WHEN 'zepto' THEN 'ZPT' "
    "ELSE upper(left(regexp_replace(o.slug, '[^a-z0-9]', '', 'g'), 3)) END"
)


def upgrade() -> None:
    op.add_column("stores", sa.Column("crm_code", sa.String(16), nullable=True))
    op.create_table(
        "store_code_counters",
        sa.Column("prefix", sa.String(8), primary_key=True),
        sa.Column("last_value", sa.Integer, nullable=False, server_default="0"),
    )
    bind = op.get_bind()
    # number the existing stores of each platform in the order they were created
    bind.execute(sa.text(f"""
        UPDATE stores s SET crm_code = x.code
        FROM (
            SELECT s2.id,
                   {PREFIX_SQL} || lpad((row_number() OVER (PARTITION BY s2.partner_organization_id ORDER BY s2.created_at, s2.id))::text, 6, '0') AS code
            FROM stores s2 JOIN organizations o ON o.id = s2.partner_organization_id
        ) x
        WHERE s.id = x.id
    """))
    bind.execute(sa.text(f"""
        INSERT INTO store_code_counters (prefix, last_value)
        SELECT {PREFIX_SQL}, count(*)
        FROM stores s JOIN organizations o ON o.id = s.partner_organization_id
        GROUP BY {PREFIX_SQL}
        ON CONFLICT (prefix) DO UPDATE SET last_value = EXCLUDED.last_value
    """))
    op.alter_column("stores", "crm_code", nullable=False)
    op.create_index("uq_stores_crm_code", "stores", ["crm_code"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_stores_crm_code", table_name="stores")
    op.drop_table("store_code_counters")
    op.drop_column("stores", "crm_code")
