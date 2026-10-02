"""Persist entity redirects and consumed owner correction decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p04_entity_corrections"
down_revision: str | Sequence[str] | None = "0008_entity_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add evidence match fingerprints, endpoint-specific relationship-evidence uniqueness, entity redirects, and scoped owner correction decisions."""
    op.add_column("entity_evidence_memberships", sa.Column("match_fingerprint", sa.String(64)))
    op.create_index("ix_entity_evidence_match_fingerprint", "entity_evidence_memberships", ["match_fingerprint"])
    op.drop_constraint("uq_relationship_evidence_fact_chunk", "relationship_evidence", type_="unique")
    op.create_index(
        "uq_relationship_evidence_fact_endpoint_pair", "relationship_evidence",
        ["relationship_id", "document_version_id", "chunk_id",
         sa.text("coalesce(source_membership_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
         sa.text("coalesce(target_membership_id, '00000000-0000-0000-0000-000000000000'::uuid)")],
        unique=True,
    )
    op.create_table(
        "entity_redirects",
        sa.Column("old_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("owner.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_entity_redirect_target", "entity_redirects", ["target_entity_id"])
    op.create_table(
        "entity_correction_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE")),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entity_evidence_memberships.id", ondelete="CASCADE")),
        sa.Column("match_fingerprint", sa.String(64)),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("owner.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decision IN ('assign', 'suppress')", name="ck_entity_correction_decision_kind"),
        sa.CheckConstraint("scope = 'evidence' OR (scope = 'document' AND document_id IS NOT NULL)", name="ck_entity_correction_decision_scope"),
    )
    op.create_index("ix_entity_correction_decision_match", "entity_correction_decisions", ["document_id", "match_fingerprint", "created_at"])


def downgrade() -> None:
    """Drop correction decisions and redirects, restore prior relationship-evidence uniqueness, and remove membership fingerprints."""
    op.drop_index("ix_entity_correction_decision_match", table_name="entity_correction_decisions")
    op.drop_table("entity_correction_decisions")
    op.drop_index("ix_entity_redirect_target", table_name="entity_redirects")
    op.drop_table("entity_redirects")
    op.drop_index("uq_relationship_evidence_fact_endpoint_pair", table_name="relationship_evidence")
    op.create_unique_constraint(
        "uq_relationship_evidence_fact_chunk", "relationship_evidence",
        ["relationship_id", "document_version_id", "chunk_id"],
    )
    op.drop_index("ix_entity_evidence_match_fingerprint", table_name="entity_evidence_memberships")
    op.drop_column("entity_evidence_memberships", "match_fingerprint")
