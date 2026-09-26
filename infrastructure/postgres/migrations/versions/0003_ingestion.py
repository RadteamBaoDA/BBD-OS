"""Add durable ingestion receipts, observations and dispatch outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ingestion"
down_revision: str | Sequence[str] | None = "0002_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_key", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "batch_key", name="uq_ingestion_batches_source_key"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_ingestion_runs_status"),
        sa.ForeignKeyConstraint(["batch_id"], ["ingestion_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id"),
    )
    op.create_index("ix_ingestion_runs_source_created", "ingestion_runs", ["source_id", "created_at"])
    op.create_table(
        "ingestion_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'queued', 'running', 'retrying', 'succeeded', 'failed')", name="ck_ingestion_stages_status"),
        sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "stage_key", name="uq_ingestion_stages_run_key"),
    )
    op.create_index("ix_ingestion_stages_pending", "ingestion_stages", ["status", "next_attempt_at"])
    op.create_table(
        "source_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", sa.String(512), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["ingestion_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id", "provider_id", "record_hash", "observed_at",
            name="uq_source_observations_batch_record_observed",
        ),
    )
    op.create_index("ix_source_observations_source_observed", "source_observations", ["source_id", "observed_at"])
    op.create_table(
        "source_ingestion_state",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("lease_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["lease_run_id"], ["ingestion_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_table(
        "collector_credentials",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(64), server_default="ingestion:write", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_collector_credentials_source_id", "collector_credentials", ["source_id"])
    op.create_table(
        "event_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("producer", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'queued', 'delivered', 'failed')", name="ck_event_outbox_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_outbox_dispatch", "event_outbox", ["status", "dispatched_at"])


def downgrade() -> None:
    op.drop_index("ix_event_outbox_dispatch", table_name="event_outbox")
    op.drop_table("event_outbox")
    op.drop_index("ix_collector_credentials_source_id", table_name="collector_credentials")
    op.drop_table("collector_credentials")
    op.drop_table("source_ingestion_state")
    op.drop_index("ix_source_observations_source_observed", table_name="source_observations")
    op.drop_table("source_observations")
    op.drop_index("ix_ingestion_stages_pending", table_name="ingestion_stages")
    op.drop_table("ingestion_stages")
    op.drop_index("ix_ingestion_runs_source_created", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("ingestion_batches")
