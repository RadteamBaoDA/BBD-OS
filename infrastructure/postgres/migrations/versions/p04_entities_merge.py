"""Join the preserved entity revision with the integrated replay head."""

from collections.abc import Sequence

revision: str = "p04_entities_merge"
down_revision: str | Sequence[str] | None = ("r06_realtime_replay", "0007_entities")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
