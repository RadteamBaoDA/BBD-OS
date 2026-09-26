"""Add source retirement fences and durable purge operations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_source_purge_operations"
down_revision: str | Sequence[str] | None = "0004_document_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("generation", sa.Integer(), server_default="1", nullable=False))
    op.add_column("sources", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_error_code", sa.String(64), nullable=True))
    op.add_column("sources", sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("collection_error_code", sa.String(64), nullable=True))
    op.add_column("sources", sa.Column("processing_error_code", sa.String(64), nullable=True))
    op.add_column("ingestion_stages", sa.Column("result_count", sa.Integer(), nullable=True))
    op.create_table(
        "source_purge_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("raw_uris", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_source_purge_operations_status"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_purge_operations_status_created", "source_purge_operations", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_source_purge_operations_status_created", table_name="source_purge_operations")
    op.drop_table("source_purge_operations")
    op.drop_column("sources", "retired_at")
    op.drop_column("sources", "last_error_code")
    op.drop_column("sources", "processing_error_code")
    op.drop_column("sources", "collection_error_code")
    op.drop_column("sources", "indexed_at")
    op.drop_column("sources", "collected_at")
    op.drop_column("ingestion_stages", "result_count")
    op.drop_column("sources", "generation")
