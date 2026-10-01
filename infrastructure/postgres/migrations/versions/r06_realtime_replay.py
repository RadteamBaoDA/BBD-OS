"""Add the core-owned durable browser replay log and singleton head."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r06_realtime_replay"
down_revision: str | Sequence[str] | None = "r09_owner_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "realtime_replay_head",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("epoch", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("floor_sequence", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_realtime_replay_head_singleton"),
        sa.CheckConstraint("sequence >= 0", name="ck_realtime_replay_head_sequence_nonnegative"),
        sa.CheckConstraint("floor_sequence >= 1", name="ck_realtime_replay_head_floor_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "realtime_replay_events",
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("epoch", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_realtime_replay_sequence_positive"),
        sa.CheckConstraint("event_type IN ('source.changed', 'ingestion.changed', 'knowledge.changed')", name="ck_realtime_replay_event_type"),
        sa.PrimaryKeyConstraint("sequence"),
    )
    op.create_index(
        "ix_realtime_replay_events_epoch_sequence",
        "realtime_replay_events",
        ["epoch", "sequence"],
    )
    op.create_index(
        "ix_realtime_replay_events_created_at",
        "realtime_replay_events",
        ["created_at"],
    )
    head = sa.table(
        "realtime_replay_head",
        sa.column("id", sa.SmallInteger()),
        sa.column("epoch", postgresql.UUID(as_uuid=True)),
        sa.column("sequence", sa.BigInteger()),
        sa.column("floor_sequence", sa.BigInteger()),
    )
    op.bulk_insert(head, [{"id": 1, "epoch": uuid4(), "sequence": 0, "floor_sequence": 1}])


def downgrade() -> None:
    op.drop_index("ix_realtime_replay_events_created_at", table_name="realtime_replay_events")
    op.drop_index("ix_realtime_replay_events_epoch_sequence", table_name="realtime_replay_events")
    op.drop_table("realtime_replay_events")
    op.drop_table("realtime_replay_head")
