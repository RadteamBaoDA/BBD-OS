"""Add file extraction state and deterministic document chunks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_document_processing"
down_revision: str | Sequence[str] | None = "0003_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_ingestion_runs_status", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_runs_status",
        "ingestion_runs",
        "status IN ('queued', 'running', 'succeeded', 'needs_ocr', 'failed')",
    )
    op.add_column("documents", sa.Column("extraction_status", sa.String(16), server_default="ready", nullable=False))
    op.create_check_constraint(
        "ck_documents_extraction_status",
        "documents",
        "extraction_status IN ('ready', 'queued', 'processing', 'succeeded', 'needs_ocr', 'failed')",
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_version_id", "chunk_index", name="uq_document_chunks_version_index"),
    )

def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_constraint("ck_documents_extraction_status", "documents", type_="check")
    op.drop_column("documents", "extraction_status")
    op.execute("UPDATE ingestion_runs SET status = 'failed' WHERE status = 'needs_ocr'")
    op.drop_constraint("ck_ingestion_runs_status", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_runs_status",
        "ingestion_runs",
        "status IN ('queued', 'running', 'succeeded', 'failed')",
    )
