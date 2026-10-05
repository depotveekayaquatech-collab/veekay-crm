"""compliance documents: never delete files - versions, archive flag, checksums

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("compliance_documents", sa.Column("sha256", sa.String(64), nullable=True))
    op.add_column("compliance_documents", sa.Column("storage_backend", sa.String(16), nullable=False, server_default="local"))
    op.add_column("compliance_documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("compliance_documents", sa.Column(
        "deleted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_compliance_documents_deleted_at", "compliance_documents", ["deleted_at"])

    op.create_table(
        "compliance_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("compliance_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("file_key", sa.String(512), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("storage_backend", sa.String(16), nullable=False, server_default="local"),
        sa.Column("source_files", sa.Integer, nullable=False, server_default="1"),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "version", name="uq_compliance_version"),
    )
    op.create_index("ix_compliance_document_versions_document_id", "compliance_document_versions", ["document_id"])
    # every existing document becomes version 1 of itself
    op.execute("""
        INSERT INTO compliance_document_versions
            (id, document_id, version, file_key, file_name, content_type, size_bytes, storage_backend, source_files,
             uploaded_by_user_id, created_at, updated_at)
        SELECT gen_random_uuid(), id, 1, file_key, file_name, content_type, size_bytes, storage_backend, 1,
               uploaded_by_user_id, created_at, updated_at
        FROM compliance_documents
    """)


def downgrade() -> None:
    op.drop_table("compliance_document_versions")
    op.drop_index("ix_compliance_documents_deleted_at", table_name="compliance_documents")
    op.drop_column("compliance_documents", "deleted_by_user_id")
    op.drop_column("compliance_documents", "deleted_at")
    op.drop_column("compliance_documents", "storage_backend")
    op.drop_column("compliance_documents", "sha256")
