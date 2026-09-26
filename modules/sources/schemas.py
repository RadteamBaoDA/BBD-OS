from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal[
    "rss", "web", "file", "github", "calendar", "email", "api", "mcp", "manual", "other"
]
SourceStatus = Literal["active", "paused", "archived"]


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SourceType
    name: str = Field(min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=120)


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: SourceStatus | None = None


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    name: str
    provider: str | None
    status: str
    local_only: bool
    last_sync_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_code: str | None
    collected_at: datetime | None
    indexed_at: datetime | None
    collection_error_code: str | None
    processing_error_code: str | None
    generation: int
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourceList(BaseModel):
    items: list[SourceRead]
    next_cursor: str | None


class OperationRead(BaseModel):
    operation_id: UUID
    source_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    error_code: str | None
    created_at: datetime
    updated_at: datetime
