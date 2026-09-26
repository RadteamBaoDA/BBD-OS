"""Add lexical and generation-isolated vector search."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_search"
down_revision: str | Sequence[str] | None = "0005_source_purge_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_index("ix_document_chunks_simple_fts", "document_chunks", [sa.text("to_tsvector('simple', content)")], postgresql_using="gin")
    op.create_table(
        "search_index_generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(200)),
        sa.Column("dimensions", sa.Integer()),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'active', 'failed', 'retired')", name="ck_search_index_generations_status"),
    )
    op.create_index("uq_search_index_generations_active", "search_index_generations", ["status"], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table(
        "search_index_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("search_index_generations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name="ck_search_index_items_status"),
        sa.UniqueConstraint("generation_id", "chunk_id", name="uq_search_index_items_generation_chunk"),
    )
    op.execute("ALTER TABLE search_index_items ADD COLUMN embedding vector")
    op.create_index("ix_search_index_items_status", "search_index_items", ["generation_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_search_index_items_status", table_name="search_index_items")
    op.drop_table("search_index_items")
    op.drop_index("uq_search_index_generations_active", table_name="search_index_generations")
    op.drop_table("search_index_generations")
    op.drop_index("ix_document_chunks_simple_fts", table_name="document_chunks")
