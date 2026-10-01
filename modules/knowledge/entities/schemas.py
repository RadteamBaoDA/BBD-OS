import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

EntityType = Literal[
    "person", "organization", "company", "project", "repository", "place", "country",
    "product", "topic", "technology", "asset", "device", "website", "event_subject", "other",
]


def canonicalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_metadata(value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 65_536:
        raise ValueError("metadata exceeds 64 KiB")
    return value


class EntityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: EntityType
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(default="owner_create", min_length=1, max_length=300)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values: list[str]) -> list[str]:
        aliases = [" ".join(value.split()) for value in values]
        if any(not value or len(value) > 300 for value in aliases):
            raise ValueError("aliases must contain 1 to 300 characters")
        if len({canonicalize_name(value) for value in aliases}) != len(aliases):
            raise ValueError("aliases must be unique")
        return aliases

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_metadata(value)


class EntityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    reason: str = Field(default="owner_update", min_length=1, max_length=300)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    metadata: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = " ".join(value.split())
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_metadata(value) if value is not None else value


class AliasCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str = Field(min_length=1, max_length=300)
    confirmed: bool = True
    reason: str = Field(default="owner_alias", min_length=1, max_length=300)

    @field_validator("alias")
    @classmethod
    def trim_alias(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("alias cannot be blank")
        return value


class EntityAliasRead(BaseModel):
    id: UUID
    entity_id: UUID
    alias: str
    source_id: UUID | None
    confirmed: bool
    origin: Literal["owner", "derived"] | None
    confidence: float | None
    created_at: datetime


class EntityRead(BaseModel):
    id: UUID
    type: EntityType
    name: str | None
    canonical_name: str | None
    description: str | None
    metadata: dict[str, Any]
    revision: int
    name_origin: Literal["owner", "derived"] | None = None
    description_origin: Literal["owner", "derived"] | None = None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
    aliases: list[EntityAliasRead] = Field(default_factory=list)


class EntityPage(BaseModel):
    items: list[EntityRead]
    next_cursor: str | None


class EntityExtractionStatus(BaseModel):
    document_version_id: UUID
    status: Literal["pending", "running", "succeeded", "blocked", "failed"]
    attempt: int
    error_code: str | None
    model: str | None = None
    facts: list[dict[str, Any]] = Field(default_factory=list)
    review_candidates: list[dict[str, Any]] = Field(default_factory=list)
    completed_at: datetime | None = None


class EntityReferenceRead(BaseModel):
    requested_id: UUID
    canonical_id: UUID
    revision: int
    type: EntityType
    name: str | None


class EntityMembershipReferenceRead(BaseModel):
    id: UUID
    entity_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    observed_at: datetime
    extracted_at: datetime
    confidence: float


class EntityEvidenceRead(BaseModel):
    id: UUID
    entity_id: UUID
    document_id: UUID
    document_version_id: UUID
    version_number: int
    chunk_id: UUID
    observed_at: datetime
    extracted_at: datetime
    confidence: float


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_version_id: UUID
    chunk_id: UUID
    confidence: float = Field(ge=0, le=1)
    source_membership_id: UUID | None = None
    target_membership_id: UUID | None = None
