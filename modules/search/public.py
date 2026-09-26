import base64
import binascii
import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.model_gateway.client import ModelGatewayError
from modules.knowledge.documents.models import Document, DocumentChunk, DocumentVersion
from modules.search.indexing import configured_embedding, embedding_values, gateway
from modules.search.models import IndexGeneration, SearchIndexItem
from modules.search.schemas import Citation, SearchHit, SearchIndexStatus, SearchRequest, SearchResponse, SearchSource
from modules.sources.models import Source

MAX_CANDIDATES = 500
MAX_RANKED_CANDIDATES = MAX_CANDIDATES * 2
FALLBACK_WARNING = "Semantic search unavailable"


def _cursor_scope(request: SearchRequest) -> str:
    content = request.model_dump(exclude={"cursor", "limit"}, mode="json")
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]


def _offset(request: SearchRequest) -> int:
    if request.cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(request.cursor + "=" * (-len(request.cursor) % 4)).decode()
        scope, position = raw.split(":", 1)
        offset = int(position)
        if scope != _cursor_scope(request) or offset < 0 or offset > MAX_RANKED_CANDIDATES or _encode_cursor(request, offset) != request.cursor:
            raise ValueError
        return offset
    except (ValueError, UnicodeDecodeError, IndexError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Invalid search cursor") from exc


def _encode_cursor(request: SearchRequest, offset: int) -> str:
    return base64.urlsafe_b64encode(f"{_cursor_scope(request)}:{offset}".encode()).decode().rstrip("=")


def _filters(statement, request: SearchRequest):
    filters = request.filters
    if filters.source_ids:
        statement = statement.where(Document.source_id.in_(filters.source_ids))
    if filters.content_types:
        statement = statement.where(Document.content_type.in_(filters.content_types))
    if filters.date_from is not None:
        statement = statement.where(func.coalesce(Document.published_at, Document.observed_at, DocumentVersion.observed_at) >= filters.date_from)
    if filters.date_to is not None:
        statement = statement.where(func.coalesce(Document.published_at, Document.observed_at, DocumentVersion.observed_at) <= filters.date_to)
    return statement


def _visible_rows(*columns):
    return (
        select(*columns)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(Source, Source.id == Document.source_id)
        .where(
            Document.current_version == DocumentVersion.version_number,
            Document.extraction_status.in_(("ready", "succeeded")),
            Source.status == "active",
        )
    )


async def _lexical_ids(session: AsyncSession, request: SearchRequest) -> list[UUID]:
    vector = func.to_tsvector(text("'simple'"), DocumentChunk.content)
    query = func.websearch_to_tsquery(text("'simple'"), request.query)
    statement = _filters(_visible_rows(DocumentChunk.id), request).where(vector.op("@@")(query)).order_by(
        func.ts_rank_cd(vector, query).desc(), DocumentChunk.id,
    ).limit(MAX_CANDIDATES)
    return list((await session.scalars(statement)).all())


async def _vector_ids(session: AsyncSession, request: SearchRequest, generation: IndexGeneration, values: list[float]) -> list[UUID]:
    dimensions = generation.dimensions
    if dimensions is None:
        return []
    clauses = [
        "i.generation_id = :generation_id", "i.status = 'succeeded'", "i.embedding IS NOT NULL",
        "v.version_number = d.current_version", "d.extraction_status IN ('ready', 'succeeded')",
        "s.status = 'active'", "s.local_only = false",
    ]
    params: dict[str, object] = {"generation_id": generation.id, "embedding": json.dumps(values), "limit": MAX_CANDIDATES}
    if request.filters.source_ids:
        clauses.append("d.source_id = ANY(CAST(:source_ids AS uuid[]))")
        params["source_ids"] = request.filters.source_ids
    if request.filters.content_types:
        clauses.append("d.content_type = ANY(CAST(:content_types AS text[]))")
        params["content_types"] = request.filters.content_types
    if request.filters.date_from is not None:
        clauses.append("coalesce(d.published_at, d.observed_at, v.observed_at) >= :date_from")
        params["date_from"] = request.filters.date_from
    if request.filters.date_to is not None:
        clauses.append("coalesce(d.published_at, d.observed_at, v.observed_at) <= :date_to")
        params["date_to"] = request.filters.date_to
    statement = text(
        "SELECT i.chunk_id FROM search_index_items i "
        "JOIN document_chunks c ON c.id = i.chunk_id "
        "JOIN document_versions v ON v.id = c.document_version_id "
        "JOIN documents d ON d.id = v.document_id "
        "JOIN sources s ON s.id = d.source_id "
        f"WHERE {' AND '.join(clauses)} "
        f"ORDER BY i.embedding::vector({dimensions}) <=> CAST(:embedding AS vector({dimensions})), i.chunk_id "
        "LIMIT :limit"
    )
    return list((await session.scalars(statement, params)).all())


async def search(session: AsyncSession, redis: Redis, settings: Settings, request: SearchRequest) -> SearchResponse:
    offset = _offset(request)
    lexical = await _lexical_ids(session, request)
    vector: list[UUID] = []
    effective_mode = "lexical"
    warnings: list[str] = []
    if request.mode == "hybrid":
        generation = await session.scalar(select(IndexGeneration).where(IndexGeneration.status == "active"))
        try:
            mapping, policy = await configured_embedding(redis, settings)
            if (
                generation is None or generation.dimensions is None or mapping is None
                or mapping.model != generation.model_id or mapping.version != generation.model_version
                or not policy.embeddings_allowed
            ):
                raise ValueError("No permitted active embedding generation")
            response = await gateway(settings, redis).embed("embedding", mapping, policy, [request.query])
            values, returned_model = embedding_values(response, generation.dimensions)
            if returned_model != generation.response_model_id:
                raise ValueError("Embedding response identity changed")
            vector = await _vector_ids(session, request, generation, values)
            effective_mode = "hybrid"
        except (ModelGatewayError, RedisError, ValueError, OSError):
            warnings.append(FALLBACK_WARNING)
        except DBAPIError:
            await session.rollback()
            warnings.append(FALLBACK_WARNING)
    ranked: dict[UUID, float] = {}
    for candidates in (lexical, vector) if effective_mode == "hybrid" else (lexical,):
        for rank, chunk_id in enumerate(candidates, 1):
            ranked[chunk_id] = ranked.get(chunk_id, 0.0) + 1 / (60 + rank)
    ordered = sorted(ranked, key=lambda chunk_id: (-ranked[chunk_id], str(chunk_id)))
    selected = ordered[offset:offset + request.limit + 1]
    # Recheck all source, revision and deletion fences after the provider call.
    rows = (await session.execute(_filters(
        _visible_rows(DocumentChunk, DocumentVersion.id, DocumentVersion.version_number, DocumentVersion.observed_at, Document, Source), request,
    ).where(DocumentChunk.id.in_(selected)))).all() if selected else []
    visible = {chunk.id: (chunk, version_id, version_number, version_observed, document, source)
               for chunk, version_id, version_number, version_observed, document, source in rows}
    items = []
    for chunk_id in selected[:request.limit]:
        if chunk_id not in visible:
            continue
        chunk, version_id, version_number, version_observed, document, source = visible[chunk_id]
        excerpt = chunk.content[:500]
        items.append(SearchHit(
            document_id=document.id, document_version_id=version_id, version_number=version_number, chunk_id=chunk.id,
            title=document.title, excerpt=excerpt, score=ranked[chunk_id],
            source=SearchSource(id=source.id, name=source.name, type=source.type),
            observed_at=document.observed_at or version_observed,
            published_at=document.published_at, content_type=document.content_type,
            citation=Citation(sourceId=source.id, documentId=document.id, chunkId=chunk.id,
                              title=document.title, url=document.canonical_url,
                              observedAt=document.observed_at or version_observed, quote=excerpt),
        ))
    next_cursor = _encode_cursor(request, offset + request.limit) if len(selected) > request.limit else None
    return SearchResponse(items=items, next_cursor=next_cursor, effective_mode=effective_mode, warnings=warnings)


async def index_status(session: AsyncSession) -> SearchIndexStatus:
    generation = await session.scalar(select(IndexGeneration).order_by(IndexGeneration.created_at.desc()).limit(1))
    if generation is None:
        return SearchIndexStatus(run_id=None, status="unavailable", model_id=None, dimensions=None, indexed_items=0, failed_items=0)
    counts = dict((await session.execute(
        select(SearchIndexItem.status, func.count()).where(SearchIndexItem.generation_id == generation.id).group_by(SearchIndexItem.status)
    )).all())
    return SearchIndexStatus(run_id=generation.id, status=generation.status, model_id=generation.model_id,
                             dimensions=generation.dimensions, indexed_items=counts.get("succeeded", 0),
                             failed_items=counts.get("failed", 0))
