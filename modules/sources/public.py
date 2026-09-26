from uuid import UUID

from sqlalchemy import desc, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import decode_cursor, encode_cursor
from modules.knowledge.documents import public as documents
from modules.sources.models import Source
from modules.sources.schemas import SourceCreate, SourcePatch


async def create_source(session: AsyncSession, payload: SourceCreate) -> Source:
    source = Source(
        type=payload.type,
        name=payload.name,
        provider=payload.provider,
        local_only=payload.type == "manual",
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def get_source(session: AsyncSession, source_id: UUID) -> Source | None:
    return await session.get(Source, source_id)


async def lock_source(session: AsyncSession, source_id: UUID) -> Source | None:
    return await session.scalar(
        select(Source)
        .where(Source.id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def lock_source_for_document(session: AsyncSession, source_id: UUID) -> None:
    """Validate the source and hold its lock until the caller's transaction ends."""
    source = await lock_source(session, source_id)
    if source is None:
        raise LookupError("Source not found")
    if source.status == "archived":
        raise ValueError("Cannot add documents to an archived source")


async def list_sources(
    session: AsyncSession, limit: int, cursor: str | None
) -> tuple[list[Source], str | None]:
    statement = select(Source).order_by(desc(Source.created_at), desc(Source.id))
    if cursor is not None:
        timestamp, identifier = decode_cursor(cursor)
        statement = statement.where(tuple_(Source.created_at, Source.id) < (timestamp, identifier))
    rows = list((await session.scalars(statement.limit(limit + 1))).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return rows, next_cursor


async def update_source(
    session: AsyncSession, source: Source, payload: SourcePatch
) -> Source | None:
    source = await session.scalar(
        select(Source)
        .where(Source.id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source is None:
        return None
    if "name" in payload.model_fields_set:
        source.name = payload.name or ""
    if "status" in payload.model_fields_set:
        source.status = payload.status or ""
    await session.commit()
    await session.refresh(source)
    return source


async def archive_source(
    session: AsyncSession, source_id: UUID, with_data: bool
) -> Source | None:
    source = await session.scalar(select(Source).where(Source.id == source_id).with_for_update())
    if source is None:
        return None
    if with_data:
        await documents.delete_source_documents(session, source_id)
    source.status = "archived"
    await session.commit()
    await session.refresh(source)
    return source
