import json
import math
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.model_gateway.client import ModelGateway, ModelGatewayError
from core.model_gateway.schemas import ModelMapping, RequestPolicy
from modules.knowledge.documents.models import Document, DocumentChunk, DocumentVersion
from modules.knowledge.documents.public import backfill_current_chunks
from modules.search.models import IndexGeneration, SearchIndexItem
from modules.settings import models as settings_models
from modules.sources.models import Source

MAX_VECTOR_DIMENSIONS = 2000  # pgvector HNSW vector index limit.


def embedding_values(response: object, expected_dimensions: int | None = None) -> tuple[list[float], str | None]:
    if not isinstance(response, dict) or not isinstance(response.get("data"), list) or len(response["data"]) != 1:
        raise ValueError("Invalid embedding response")
    returned_model = response.get("model")
    if returned_model is not None and (not isinstance(returned_model, str) or not returned_model.strip()):
        raise ValueError("Embedding response model identity is invalid")
    row = response["data"][0]
    if not isinstance(row, dict) or not isinstance(row.get("embedding"), list):
        raise ValueError("Invalid embedding response")
    values = row["embedding"]
    if not 1 <= len(values) <= MAX_VECTOR_DIMENSIONS or expected_dimensions not in (None, len(values)):
        raise ValueError("Embedding dimensions do not match the index generation")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise ValueError("Embedding contains invalid values")
    if not any(value != 0 for value in values):
        raise ValueError("Embedding cannot be a zero vector")
    return [float(value) for value in values], returned_model


def gateway(settings: Settings, redis: Redis) -> ModelGateway:
    return ModelGateway(
        redis, str(settings.omniroute_base_url) if settings.omniroute_base_url else None,
        settings.omniroute_api_key.get_secret_value(), "omniroute",
    )


async def configured_embedding(redis: Redis, settings: Settings) -> tuple[ModelMapping | None, RequestPolicy]:
    mappings = await settings_models.get_mappings(redis, settings)
    privacy = await settings_models.get_privacy(redis)
    return mappings.get("embedding"), RequestPolicy(
        embeddings_allowed=privacy.allow_remote_embeddings,
        permitted_destinations=frozenset({"omniroute"}),
    )


def eligible_chunks():
    return (
        select(DocumentChunk, Source)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(Source, Source.id == Document.source_id)
        .where(
            Document.current_version == DocumentVersion.version_number,
            Document.extraction_status.in_(("ready", "succeeded")),
            Source.status == "active", Source.local_only.is_(False),
        )
    )


async def create_generation(session: AsyncSession, mapping: ModelMapping) -> IndexGeneration:
    await session.execute(text("SELECT pg_advisory_xact_lock(4603201)"))
    existing = await session.scalar(select(IndexGeneration).where(
        IndexGeneration.status.in_(("queued", "running")),
    ).order_by(IndexGeneration.created_at).limit(1))
    if existing is not None:
        await session.commit()
        return existing
    generation = IndexGeneration(model_id=mapping.model, model_version=mapping.version)
    session.add(generation)
    await session.commit()
    await session.refresh(generation)
    return generation


async def index_pending_chunks(ctx: dict[str, object]) -> int:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    redis = cast(Redis, ctx["redis"])
    settings = cast(Settings, ctx["settings"])
    async with factory() as session:
        await backfill_current_chunks(session)
    async with factory() as session:
        generation = await session.scalar(
            select(IndexGeneration)
            .where(IndexGeneration.status.in_(("queued", "running")))
            .order_by(IndexGeneration.created_at, IndexGeneration.id)
            .limit(1)
        )
        if generation is None:
            generation = await session.scalar(select(IndexGeneration).where(IndexGeneration.status == "active"))
        if generation is None:
            return 0
        generation_id = generation.id

    try:
        mapping, policy = await configured_embedding(redis, settings)
        if not policy.embeddings_allowed:
            return 0
        if mapping is None or mapping.model != generation.model_id or mapping.version != generation.model_version:
            raise ValueError("Embedding model mapping changed")
        client = gateway(settings, redis)
    except Exception:
        async with factory() as session:
            generation = await session.get(IndexGeneration, generation_id, with_for_update=True)
            if generation is not None and generation.status != "active":
                generation.status = "failed"
                generation.error_code = "model_unavailable"
                await session.commit()
        return 0

    completed = 0
    for _ in range(2):
        async with factory() as session:
            generation = await session.get(IndexGeneration, generation_id, with_for_update=True)
            if generation is None or generation.status not in {"queued", "running", "active"}:
                break
            if generation.status == "queued":
                generation.status = "running"
            row = (await session.execute(
                eligible_chunks().outerjoin(
                    SearchIndexItem,
                    (SearchIndexItem.chunk_id == DocumentChunk.id) & (SearchIndexItem.generation_id == generation_id),
                ).where((SearchIndexItem.id.is_(None)) | (SearchIndexItem.status == "pending")).order_by(DocumentChunk.id).limit(1)
            )).first()
            if row is None:
                if generation.status == "running":
                    await session.execute(text(
                        "DELETE FROM search_index_items i WHERE i.generation_id = :generation_id "
                        "AND i.status IN ('pending', 'failed') AND NOT EXISTS ("
                        "SELECT 1 FROM document_chunks c "
                        "JOIN document_versions v ON v.id = c.document_version_id "
                        "JOIN documents d ON d.id = v.document_id "
                        "JOIN sources s ON s.id = d.source_id "
                        "WHERE c.id = i.chunk_id AND v.version_number = d.current_version "
                        "AND d.extraction_status IN ('ready', 'succeeded') "
                        "AND s.status = 'active' AND s.local_only = false)"
                    ), {"generation_id": generation_id})
                    failed = await session.scalar(select(func.count()).select_from(SearchIndexItem).where(
                        SearchIndexItem.generation_id == generation_id, SearchIndexItem.status != "succeeded",
                    ))
                    if failed:
                        generation.status = "failed"
                        generation.error_code = "item_failed"
                    elif generation.dimensions is None:
                        generation.status = "failed"
                        generation.error_code = "no_indexable_chunks"
                    else:
                        await activate_generation(session, generation)
                await session.commit()
                break
            chunk, source = row
            item = await session.scalar(select(SearchIndexItem).where(
                SearchIndexItem.generation_id == generation_id, SearchIndexItem.chunk_id == chunk.id,
            ))
            if item is None:
                item = SearchIndexItem(generation_id=generation_id, chunk_id=chunk.id)
                session.add(item)
                await session.flush()
            item_id, chunk_id, source_id, content = item.id, chunk.id, source.id, chunk.content
            dimensions = generation.dimensions
            await session.commit()
        try:
            async with factory() as session:
                # Hold the source lock across transport so archive/purge cannot race a send.
                source = await session.get(Source, source_id, with_for_update=True)
                current = await session.scalar(
                    select(DocumentChunk.id)
                    .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
                    .join(Document, Document.id == DocumentVersion.document_id)
                    .where(DocumentChunk.id == chunk_id,
                           Document.current_version == DocumentVersion.version_number,
                           Document.extraction_status.in_(("ready", "succeeded")))
                )
                if source is None or source.status != "active" or source.local_only or current is None:
                    item = await session.get(SearchIndexItem, item_id, with_for_update=True)
                    if item is not None:
                        await session.delete(item)
                        await session.commit()
                    continue
                mapping, policy = await configured_embedding(redis, settings)
                if not policy.embeddings_allowed:
                    break
                if (
                    mapping is None or mapping.model != generation.model_id
                    or mapping.version != generation.model_version
                ):
                    raise ValueError("Embedding model mapping changed")
                response = await client.embed("embedding", mapping, policy, [content])
                values, returned_model = embedding_values(response, dimensions)
                generation = await session.get(IndexGeneration, generation_id, with_for_update=True)
                item = await session.get(SearchIndexItem, item_id, with_for_update=True)
                if generation is None or item is None or generation.status not in {"running", "active"}:
                    if item is not None:
                        await session.delete(item)
                        await session.commit()
                    continue
                if generation.dimensions is None:
                    generation.response_model_id = returned_model
                    generation.dimensions = len(values)
                elif returned_model != generation.response_model_id:
                    generation.status = "failed"
                    generation.error_code = "model_identity_changed"
                    item.status = "failed"
                    item.error_code = "model_identity_changed"
                    await session.commit()
                    break
                elif generation.dimensions != len(values):
                    raise ValueError("Embedding dimensions changed during indexing")
                await session.execute(text("UPDATE search_index_items SET embedding = CAST(:embedding AS vector) WHERE id = :item_id"),
                                      {"embedding": json.dumps(values), "item_id": item_id})
                item.status = "succeeded"
                item.error_code = None
                await session.commit()
                completed += 1
        except (ModelGatewayError, RedisError, ValueError):
            async with factory() as session:
                item = await session.get(SearchIndexItem, item_id, with_for_update=True)
                if item is not None:
                    item.status = "failed"
                    item.error_code = "embedding_failed"
                    await session.commit()
    return completed


async def activate_generation(session: AsyncSession, generation: IndexGeneration) -> None:
    if generation.dimensions is None or not 1 <= generation.dimensions <= MAX_VECTOR_DIMENSIONS:
        raise ValueError("Invalid generation dimensions")
    # Identifier and dimensions originate from a UUID and a bounded integer, never request text.
    index_name = f"ix_search_vector_{generation.id.hex}"
    await session.execute(text(
        f"CREATE INDEX IF NOT EXISTS {index_name} ON search_index_items "
        f"USING hnsw ((embedding::vector({generation.dimensions})) vector_cosine_ops) "
        f"WHERE generation_id = '{generation.id}' AND status = 'succeeded'"
    ))
    prior = await session.scalar(select(IndexGeneration).where(IndexGeneration.status == "active").with_for_update())
    if prior is not None:
        prior.status = "retired"
        await session.flush()
    generation.status = "active"
    generation.error_code = None
