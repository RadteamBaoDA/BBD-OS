"""Add linked Google identity and recent-authentication timestamps."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r02_google_identity"
down_revision: str | Sequence[str] | None = "0006_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_session",
        sa.Column("reauthenticated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "google_identity",
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id"),
    )
    op.create_index(
        "uq_google_identity_issuer_subject",
        "google_identity",
        ["issuer", "subject"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_google_identity_issuer_subject", table_name="google_identity")
    op.drop_table("google_identity")
    op.drop_column("auth_session", "reauthenticated_at")
