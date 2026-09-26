from datetime import datetime
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IngestionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=1_000_000)
    observed_at: datetime
    version: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def require_aware_observation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value


class ReceiveBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    batch_key: str = Field(min_length=1, max_length=255)
    cursor_before: str | None = Field(default=None, max_length=4096)
    cursor_after: str | None = Field(default=None, max_length=4096)
    records: list[IngestionRecord] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def limit_serialized_payload(self) -> "ReceiveBatch":
        payload = json.dumps(self.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False)
        if len(payload.encode("utf-8")) > 10 * 1024 * 1024:
            raise ValueError("Batch payload exceeds 10 MiB")
        return self


class Receipt(BaseModel):
    batch_id: UUID
    run_id: UUID
    status: Literal["queued", "running", "succeeded", "needs_ocr", "failed"]


class CollectorCredentialRead(BaseModel):
    source_id: UUID
    token: str


class StageRead(BaseModel):
    stage_key: str
    status: Literal["pending", "queued", "running", "retrying", "succeeded", "failed"]
    attempts: int
    error_code: str | None
    result_count: int | None = None
    updated_at: datetime


class RunRead(BaseModel):
    run_id: UUID
    source_id: UUID
    status: Literal["queued", "running", "succeeded", "needs_ocr", "failed"]
    stages: list[StageRead]
    error_code: str | None
    created_at: datetime
    updated_at: datetime
