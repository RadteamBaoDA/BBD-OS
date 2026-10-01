from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.knowledge.entities.schemas import EvidenceRef, validate_metadata


class EntityGraphRead(BaseModel):
    id: UUID
    type: str
    name: str | None
    revision: int


class RelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_entity_id: UUID
    target_entity_id: UUID
    type: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    origin: Literal["owner", "derived"] = "owner"
    confidence: float | None = Field(default=None, ge=0, le=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    reason: str = Field(default="owner_relationship", min_length=1, max_length=300)

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_metadata(value)


class EvidenceRead(BaseModel):
    id: UUID
    relationship_id: UUID
    document_id: UUID
    document_version_id: UUID
    version_number: int
    chunk_id: UUID
    observed_at: datetime
    extracted_at: datetime
    confidence: float
    source_entity_membership_id: UUID | None
    target_entity_membership_id: UUID | None
    title: str
    canonical_url: str | None
    source_id: UUID
    excerpt: str
    metadata_is_version_snapshot: bool


class RelationshipRead(BaseModel):
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    type: str
    origin: Literal["owner", "derived"]
    confidence: float | None
    valid_from: datetime | None
    valid_to: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    evidence: list[EvidenceRead] = Field(default_factory=list)


class RelationshipPage(BaseModel):
    items: list[RelationshipRead]
    next_cursor: str | None


class EvidencePage(BaseModel):
    items: list[EvidenceRead]
    next_cursor: str | None


class NeighborRead(BaseModel):
    entity: EntityGraphRead
    relationship: RelationshipRead


class NeighborPage(BaseModel):
    items: list[NeighborRead]
    truncated: bool
    next_cursor: str | None
