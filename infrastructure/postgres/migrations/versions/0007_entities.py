"""Add canonical entities, aliases, relationships and provenance links."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_entities"
down_revision: str | Sequence[str] | None = "0006_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("canonical_name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "type IN ('person', 'organization', 'company', 'project', 'repository', 'place', 'country', 'product', 'topic', 'technology', 'asset', 'device', 'website', 'event_subject', 'other')",
            name="ck_entities_type",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_entities_revision"),
    )
    op.create_index("ix_entities_type_canonical_name", "entities", ["type", "canonical_name"])
    op.create_index("ix_entities_created_at_id", "entities", ["created_at", "id"])
    op.create_table(
        "entity_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(300), nullable=False),
        sa.Column("normalized_alias", sa.String(300), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column("confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("entity_id", "normalized_alias", name="uq_entity_aliases_entity_normalized"),
    )
    op.create_index("ix_entity_aliases_normalized", "entity_aliases", ["normalized_alias"])
    op.create_table(
        "relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_entity_id <> target_entity_id", name="ck_relationships_distinct_entities"),
        sa.CheckConstraint("origin IN ('owner', 'derived')", name="ck_relationships_origin"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_relationships_confidence"),
    )
    op.create_index("ix_relationships_source_type", "relationships", ["source_entity_id", "type"])
    op.create_index("ix_relationships_target_type", "relationships", ["target_entity_id", "type"])
    op.create_index("ix_relationships_created_at_id", "relationships", ["created_at", "id"])
    op.create_table(
        "relationship_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("relationship_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("relationships.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_relationship_evidence_confidence"),
        sa.UniqueConstraint("relationship_id", "document_version_id", "chunk_id", name="uq_relationship_evidence_fact_chunk"),
    )
    op.create_index("ix_relationship_evidence_version", "relationship_evidence", ["document_version_id"])
    op.create_index("ix_relationship_evidence_chunk", "relationship_evidence", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_relationship_evidence_chunk", table_name="relationship_evidence")
    op.drop_index("ix_relationship_evidence_version", table_name="relationship_evidence")
    op.drop_table("relationship_evidence")
    op.drop_index("ix_relationships_created_at_id", table_name="relationships")
    op.drop_index("ix_relationships_target_type", table_name="relationships")
    op.drop_index("ix_relationships_source_type", table_name="relationships")
    op.drop_table("relationships")
    op.drop_index("ix_entity_aliases_normalized", table_name="entity_aliases")
    op.drop_table("entity_aliases")
    op.drop_index("ix_entities_created_at_id", table_name="entities")
    op.drop_index("ix_entities_type_canonical_name", table_name="entities")
    op.drop_table("entities")
