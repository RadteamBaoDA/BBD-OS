"""Persist the single owner's display and locale preferences."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r09_owner_preferences"
down_revision: str | Sequence[str] | None = "r05_ai_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_preferences",
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("theme", sa.String(length=8), server_default="system", nullable=False),
        sa.Column("locale", sa.String(length=8), server_default="en-us", nullable=False),
        sa.Column("timezone", sa.String(length=100), server_default="Asia/Ho_Chi_Minh", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("owner_id = 1", name="ck_owner_preferences_single_owner"),
        sa.CheckConstraint("configuration_revision > 0", name="ck_owner_preferences_revision_positive"),
        sa.CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_owner_preferences_theme"),
        sa.CheckConstraint("locale IN ('en-us', 'vi-vi')", name="ck_owner_preferences_locale"),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id"),
    )


def downgrade() -> None:
    op.drop_table("owner_preferences")
