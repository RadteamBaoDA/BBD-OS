"""Persist desired connector state and external reconciliation progress."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r03_connector_provisioning"
down_revision: str | Sequence[str] | None = "r02_google_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connector_provisioning",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("desired_revision", sa.Integer(), nullable=False),
        sa.Column("applied_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "desired_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("workflow_id", sa.String(length=128), nullable=True),
        sa.Column("workflow_name", sa.String(length=255), nullable=True),
        sa.Column("desired_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("workflow_operation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("activation_intent", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("state", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'provisioning', 'active', 'saved_not_active', 'reconciliation_required', 'disabled')",
            name="ck_connector_provisioning_state",
        ),
        sa.CheckConstraint(
            "desired_revision > 0 AND applied_revision >= 0",
            name="ck_connector_provisioning_revisions",
        ),
        sa.Index("ix_connector_provisioning_reconcile", "state", "updated_at"),
        sa.Index("ix_connector_provisioning_desired_enabled", "desired_enabled", "updated_at"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_table(
        "connector_managed_credentials",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot", sa.String(length=64), nullable=False),
        sa.Column("credential_id", sa.String(length=128), nullable=True),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operation_revision", sa.Integer(), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("credential_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("operation_envelope", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolved_binding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'dispatching', 'ready', 'reconciliation_required', 'delete_pending')",
            name="ck_connector_managed_credential_state",
        ),
        sa.Index("ix_connector_managed_credentials_state", "state"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id", "slot"),
    )


def downgrade() -> None:
    op.drop_table("connector_managed_credentials")
    op.drop_table("connector_provisioning")
