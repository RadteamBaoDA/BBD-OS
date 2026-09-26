from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[UUID] = Field(default_factory=list, max_length=100)
    date_from: datetime | None = None
    date_to: datetime | None = None
    content_types: list[str] = Field(default_factory=list, max_length=20)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    mode: Literal["lexical", "hybrid"] = "hybrid"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=256)


class Citation(BaseModel):
    sourceType: Literal["document"] = "document"
    sourceId: UUID
    documentId: UUID
    chunkId: UUID
    title: str
    url: str | None
    observedAt: datetime | None
    quote: str


class SearchSource(BaseModel):
    id: UUID
    name: str
    type: str


class SearchHit(BaseModel):
    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    title: str
    excerpt: str
    score: float
    source: SearchSource
    observed_at: datetime | None
    published_at: datetime | None
    content_type: str | None
    entity_refs: list[UUID] = Field(default_factory=list)
    citation: Citation


class SearchResponse(BaseModel):
    items: list[SearchHit]
    next_cursor: str | None
    effective_mode: Literal["lexical", "hybrid"]
    warnings: list[str]


class ReindexResponse(BaseModel):
    run_id: UUID


class SearchIndexStatus(BaseModel):
    run_id: UUID | None
    status: str
    model_id: str | None
    dimensions: int | None
    indexed_items: int
    failed_items: int
