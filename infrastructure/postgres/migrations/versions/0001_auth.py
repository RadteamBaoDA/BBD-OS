"""Create the single owner and persisted auth sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_auth"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_owner_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "auth_session",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_auth_session_expires_at", "auth_session", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_session_expires_at", table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_table("owner")
