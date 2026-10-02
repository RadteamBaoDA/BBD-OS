"""Persist receipt normalization progress and immutable provider provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_receipt_normalization"
down_revision: str | Sequence[str] | None = "r06_realtime_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ingestion receipt timestamps and source generations plus normalized identity, immutable version provenance, and observation-disposition records."""
    op.add_column("ingestion_batches", sa.Column("source_generation", sa.Integer(), nullable=True))
    op.add_column("source_observations", sa.Column("received_at", sa.DateTime(timezone=True)))
    op.add_column("source_observations", sa.Column("collected_at", sa.DateTime(timezone=True)))
    op.create_table(
        "normalized_document_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_id", "external_id", name="uq_normalized_document_identities_source_external"),
    )
    op.create_table(
        "normalized_version_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.String(512), nullable=False),
        sa.Column("provider_version", sa.String(255)),
        sa.Column("accepted_record_hash", sa.String(64), nullable=False),
        sa.Column("normalization_version", sa.Integer(), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        sa.Column("selection_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("content_type", sa.String(64)),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "accepted_record_hash", "normalization_version", name="uq_normalized_version_provenance_identity"),
    )
    op.create_index("ix_normalized_version_provenance_version", "normalized_version_provenance", ["document_version_id"])
    op.create_table(
        "observation_normalizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_observations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_stages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("normalization_version", sa.Integer(), nullable=False),
        sa.Column("disposition", sa.String(16), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("disposition IN ('pending', 'normalized', 'duplicate', 'skipped', 'failed')", name="ck_observation_normalizations_disposition"),
        sa.UniqueConstraint("observation_id", "normalization_version", name="uq_observation_normalizations_identity"),
    )
    op.create_index("ix_observation_normalizations_stage", "observation_normalizations", ["stage_id", "disposition"])


def downgrade() -> None:
    """Drop normalization and provenance tables, then remove receipt timestamp and generation columns."""
    op.drop_index("ix_observation_normalizations_stage", table_name="observation_normalizations")
    op.drop_table("observation_normalizations")
    op.drop_index("ix_normalized_version_provenance_version", table_name="normalized_version_provenance")
    op.drop_table("normalized_version_provenance")
    op.drop_table("normalized_document_identities")
    op.drop_column("source_observations", "received_at")
    op.drop_column("source_observations", "collected_at")
    op.drop_column("ingestion_batches", "source_generation")
