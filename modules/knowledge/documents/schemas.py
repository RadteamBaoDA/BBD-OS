import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_CONTENT_BYTES = 1_048_576
MAX_METADATA_BYTES = 65_536


def validate_content(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise ValueError("content exceeds 1 MiB")
    return value


def validate_metadata(value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError("metadata exceeds 64 KiB")
    return value


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    title: str = Field(min_length=1, max_length=500)
    content: str
    external_id: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def bounded_content(cls, value: str) -> str:
        return validate_content(value)

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_metadata(value)


class DocumentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    metadata: dict[str, Any] | None = None

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_metadata(value) if value is not None else value


class ContentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    content: str

    @field_validator("content")
    @classmethod
    def bounded_content(cls, value: str) -> str:
        return validate_content(value)


class DocumentRead(BaseModel):
    id: UUID
    source_id: UUID
    external_id: str | None
    title: str
    content_type: str | None
    mime_type: str | None
    raw_uri: str | None
    canonical_url: str | None
    author: str | None
    metadata: dict[str, Any]
    current_version: int
    content_hash: str
    extraction_status: str
    published_at: datetime | None
    observed_at: datetime | None
    language: str | None
    created_at: datetime
    updated_at: datetime


class VersionRead(BaseModel):
    id: UUID
    document_id: UUID
    version_number: int
    content: str
    content_hash: str
    observed_at: datetime
    created_at: datetime


class VersionList(BaseModel):
    items: list[VersionRead]
    next_cursor: str | None


class DocumentList(BaseModel):
    items: list[DocumentRead]
    next_cursor: str | None
