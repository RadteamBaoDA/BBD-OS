"""Persist bounded entity extraction work and results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_entity_extraction"
down_revision: str | Sequence[str] | None = "p04_entities_delta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_extraction_work",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("extractor_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("dependency_fingerprint", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_version_id", "extractor_version", "prompt_version", name="uq_entity_extraction_work_identity"),
        sa.CheckConstraint("status IN ('pending', 'running', 'succeeded', 'blocked', 'failed')", name="ck_entity_extraction_work_status"),
        sa.CheckConstraint("attempt >= 0", name="ck_entity_extraction_work_attempt"),
        sa.CheckConstraint("source_generation >= 1", name="ck_entity_extraction_work_generation"),
    )
    op.create_index("ix_entity_extraction_work_recovery", "entity_extraction_work", ["status", "next_attempt_at", "lease_expires_at"])
    op.create_table(
        "entity_extraction_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entity_extraction_work.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(200)),
        sa.Column("usage_json", postgresql.JSONB()),
        sa.Column("facts_json", postgresql.JSONB(), nullable=False),
        sa.Column("review_json", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("work_id", name="uq_entity_extraction_results_work"),
    )


def downgrade() -> None:
    op.drop_table("entity_extraction_results")
    op.drop_index("ix_entity_extraction_work_recovery", table_name="entity_extraction_work")
    op.drop_table("entity_extraction_work")
