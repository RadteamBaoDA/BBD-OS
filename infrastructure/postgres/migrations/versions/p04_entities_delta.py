"""Add exact evidence membership and owner mutation provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p04_entities_delta"
down_revision: str | Sequence[str] | None = "p04_entities_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add entity field origins, alias confidence, owner-action audit records, exact evidence memberships, field evidence, alias evidence, and endpoint membership provenance."""
    op.alter_column("entities", "name", existing_type=sa.String(300), nullable=True)
    op.alter_column("entities", "canonical_name", existing_type=sa.String(300), nullable=True)
    op.add_column("entities", sa.Column("name_origin", sa.String(16)))
    op.add_column("entities", sa.Column("description_origin", sa.String(16)))
    op.add_column("entity_aliases", sa.Column("origin", sa.String(16)))
    op.add_column("entity_aliases", sa.Column("confidence", sa.Float()))
    op.create_table(
        "entity_owner_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("owner.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("affected_ids", postgresql.JSONB(), nullable=False),
        sa.Column("revisions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_entity_owner_actions_created", "entity_owner_actions", ["created_at", "id"])
    op.create_table(
        "entity_evidence_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_identity", sa.String(256)),
        sa.Column("candidate_key", sa.String(256)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_entity_evidence_confidence"),
        sa.UniqueConstraint("extraction_identity", "candidate_key", "chunk_id", name="uq_entity_evidence_retry"),
    )
    op.create_index("ix_entity_evidence_entity", "entity_evidence_memberships", ["entity_id", "id"])
    op.create_index("ix_entity_evidence_version", "entity_evidence_memberships", ["document_version_id"])
    op.create_index("ix_entity_evidence_chunk", "entity_evidence_memberships", ["chunk_id"])
    op.create_index("ix_entity_evidence_document", "entity_evidence_memberships", ["document_id"])
    op.create_index("ix_entity_evidence_source", "entity_evidence_memberships", ["source_id"])
    op.create_table(
        "entity_alias_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alias_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entity_aliases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entity_evidence_memberships.id", ondelete="CASCADE"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_entity_alias_evidence_confidence"),
        sa.UniqueConstraint("alias_id", "membership_id", name="uq_entity_alias_evidence"),
    )
    op.create_table(
        "entity_field_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(16), nullable=False),
        sa.Column("value_hash", sa.String(64), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entity_evidence_memberships.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("field_name IN ('name', 'description')", name="ck_entity_field_evidence_field"),
        sa.UniqueConstraint("entity_id", "field_name", "value_hash", "membership_id", name="uq_entity_field_evidence_support"),
    )
    op.create_index("ix_entity_field_evidence_current", "entity_field_evidence", ["entity_id", "field_name", "value_hash"])
    op.create_index("ix_entity_field_evidence_membership", "entity_field_evidence", ["membership_id"])
    op.add_column("relationship_evidence", sa.Column("source_membership_id", postgresql.UUID(as_uuid=True)))
    op.add_column("relationship_evidence", sa.Column("target_membership_id", postgresql.UUID(as_uuid=True)))
    op.add_column("relationship_evidence", sa.Column("document_id", postgresql.UUID(as_uuid=True)))
    op.add_column("relationship_evidence", sa.Column("source_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_relationship_evidence_document", "relationship_evidence", "documents", ["document_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_relationship_evidence_source", "relationship_evidence", "sources", ["source_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(
        "fk_relationship_evidence_source_membership", "relationship_evidence",
        "entity_evidence_memberships", ["source_membership_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_relationship_evidence_target_membership", "relationship_evidence",
        "entity_evidence_memberships", ["target_membership_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_relationship_evidence_source_membership", "relationship_evidence", ["source_membership_id"])
    op.create_index("ix_relationship_evidence_target_membership", "relationship_evidence", ["target_membership_id"])
    op.create_index("ix_relationship_evidence_document", "relationship_evidence", ["document_id"])
    op.create_index("ix_relationship_evidence_source", "relationship_evidence", ["source_id"])


def downgrade() -> None:
    """Drop the owner/evidence provenance structures and fields added by this revision, then restore required entity-name columns."""
    op.drop_index("ix_relationship_evidence_target_membership", table_name="relationship_evidence")
    op.drop_index("ix_relationship_evidence_source_membership", table_name="relationship_evidence")
    op.drop_index("ix_relationship_evidence_source", table_name="relationship_evidence")
    op.drop_index("ix_relationship_evidence_document", table_name="relationship_evidence")
    op.drop_constraint("fk_relationship_evidence_target_membership", "relationship_evidence", type_="foreignkey")
    op.drop_constraint("fk_relationship_evidence_source_membership", "relationship_evidence", type_="foreignkey")
    op.drop_constraint("fk_relationship_evidence_source", "relationship_evidence", type_="foreignkey")
    op.drop_constraint("fk_relationship_evidence_document", "relationship_evidence", type_="foreignkey")
    op.drop_column("relationship_evidence", "source_id")
    op.drop_column("relationship_evidence", "document_id")
    op.drop_column("relationship_evidence", "target_membership_id")
    op.drop_column("relationship_evidence", "source_membership_id")
    op.drop_index("ix_entity_field_evidence_membership", table_name="entity_field_evidence")
    op.drop_index("ix_entity_field_evidence_current", table_name="entity_field_evidence")
    op.drop_table("entity_field_evidence")
    op.drop_column("entity_aliases", "confidence")
    op.drop_column("entity_aliases", "origin")
    op.drop_column("entities", "description_origin")
    op.drop_column("entities", "name_origin")
    op.drop_table("entity_alias_evidence")
    op.drop_index("ix_entity_evidence_chunk", table_name="entity_evidence_memberships")
    op.drop_index("ix_entity_evidence_source", table_name="entity_evidence_memberships")
    op.drop_index("ix_entity_evidence_document", table_name="entity_evidence_memberships")
    op.drop_index("ix_entity_evidence_version", table_name="entity_evidence_memberships")
    op.drop_index("ix_entity_evidence_entity", table_name="entity_evidence_memberships")
    op.drop_table("entity_evidence_memberships")
    op.drop_index("ix_entity_owner_actions_created", table_name="entity_owner_actions")
    op.drop_table("entity_owner_actions")
    op.alter_column("entities", "canonical_name", existing_type=sa.String(300), nullable=False)
    op.alter_column("entities", "name", existing_type=sa.String(300), nullable=False)
