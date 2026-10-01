import base64
import binascii
import hashlib
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, desc, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import decode_cursor, encode_cursor
from core.chunking import chunk_text
from core.realtime import commit_with_replay, make_knowledge_change
from modules.knowledge.documents.models import Document, DocumentChunk, DocumentVersion
from modules.knowledge.documents.schemas import DocumentCreate, DocumentPatch, EvidenceReferenceRead
from modules.sources import public as sources
from modules.sources.models import Source


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def list_evidence_ref_keys(
    session: AsyncSession, *, document_id: UUID | None = None, source_id: UUID | None = None,
    limit: int = 10_000,
) -> list[tuple[UUID, UUID]]:
    if (document_id is None) == (source_id is None) or not 1 <= limit <= 10_000:
        raise ValueError("Specify one document or source and a bounded limit")
    statement = (
        select(DocumentVersion.id, DocumentChunk.id)
        .join(DocumentChunk, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(Document, Document.id == DocumentVersion.document_id)
    )
    statement = statement.where(Document.id == document_id) if document_id else statement.where(Document.source_id == source_id)
    rows = list((await session.execute(statement.order_by(DocumentVersion.id, DocumentChunk.id).limit(limit + 1))).all())
    if len(rows) > limit:
        raise ValueError("Evidence cleanup exceeds its atomic support limit")
    return [(version_id, chunk_id) for version_id, chunk_id in rows]


async def add_content_chunks(session: AsyncSession, version: DocumentVersion) -> None:
    await session.flush()
    for index, draft in enumerate(chunk_text(version.content)):
        session.add(DocumentChunk(
            document_version_id=version.id, chunk_index=index, content=draft.content,
            content_hash=content_hash(draft.content), token_count=draft.token_count,
            metadata_json=draft.metadata,
        ))


async def backfill_current_chunks(session: AsyncSession, limit: int = 2) -> int:
    """Fill legacy manual revisions created before chunking was enabled."""
    versions = list((await session.scalars(
        select(DocumentVersion)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(Source, Source.id == Document.source_id)
        .where(
            Document.current_version == DocumentVersion.version_number,
            Document.extraction_status.in_(("ready", "succeeded")),
            Source.status == "active",
            DocumentVersion.content != "",
            ~select(DocumentChunk.id).where(DocumentChunk.document_version_id == DocumentVersion.id).exists(),
        )
        .order_by(DocumentVersion.id).limit(limit)
    )).all())
    for version in versions:
        await add_content_chunks(session, version)
    if versions:
        await session.commit()
    return len(versions)


async def raw_uris(session: AsyncSession, source_id: UUID | None = None) -> set[str]:
    statement = select(Document.raw_uri).where(Document.raw_uri.is_not(None))
    if source_id is not None:
        statement = statement.where(Document.source_id == source_id)
    return {uri for uri in (await session.scalars(statement)).all() if uri}


async def create_document(session: AsyncSession, payload: DocumentCreate) -> Document:
    await sources.lock_source_for_document(session, payload.source_id)
    digest = content_hash(payload.content)
    document = Document(
        source_id=payload.source_id,
        external_id=payload.external_id,
        title=payload.title,
        metadata_json=payload.metadata,
        current_version=1,
        content_hash=digest,
    )
    session.add(document)
    try:
        await session.flush()
        version = DocumentVersion(
                document_id=document.id,
                version_number=1,
                content=payload.content,
                content_hash=digest,
        )
        session.add(version)
        await add_content_chunks(session, version)
        await commit_with_replay(
            session,
            [make_knowledge_change(payload.source_id, document.id, 1)],
        )
    except IntegrityError:
        await session.rollback()
        raise
    await session.refresh(document)
    return document


async def get_document(session: AsyncSession, document_id: UUID) -> Document | None:
    return await session.get(Document, document_id)


async def has_document_identity(session: AsyncSession, source_id: UUID, external_id: str) -> bool:
    return bool(
        await session.scalar(
            select(Document.id).where(Document.source_id == source_id, Document.external_id == external_id)
        )
    )


async def add_uploaded_document(
    session: AsyncSession,
    source_id: UUID,
    title: str,
    mime_type: str,
    raw_uri: str,
    metadata: dict[str, object],
    external_id: str,
    document_id: UUID,
) -> UUID:
    document = Document(
        id=document_id,
        source_id=source_id,
        external_id=external_id,
        title=title,
        content_type="file",
        mime_type=mime_type,
        raw_uri=raw_uri,
        metadata_json=metadata,
        current_version=1,
        content_hash=content_hash(""),
        extraction_status="queued",
    )
    session.add(document)
    await session.flush()
    session.add(DocumentVersion(document_id=document.id, version_number=1, content="", content_hash=content_hash("")))
    await session.flush()
    return document.id


async def lock_document_for_extraction(
    session: AsyncSession, document_id: UUID, source_id: UUID
) -> bool:
    return await session.scalar(
        select(Document.id)
        .where(Document.id == document_id, Document.source_id == source_id)
        .with_for_update()
    ) is not None


async def set_extraction_status(
    session: AsyncSession, document_id: UUID, source_id: UUID, status: str
) -> bool:
    result = await session.execute(
        update(Document)
        .where(Document.id == document_id, Document.source_id == source_id)
        .values(extraction_status=status)
        .returning(Document.id)
    )
    return result.scalar_one_or_none() is not None


async def save_extraction(
    session: AsyncSession,
    document_id: UUID,
    source_id: UUID,
    text: str,
    chunks: list[dict[str, object]],
    extraction_status: str,
    extraction_metadata: dict[str, object],
    warnings: list[str],
    parser: str,
) -> UUID | None:
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.source_id == source_id).with_for_update()
    )
    if document is None:
        return None
    current = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == document.current_version,
        )
    )
    if current is None:
        raise RuntimeError("Current document version is missing")
    if current.content != text:
        digest = content_hash(text)
        current = DocumentVersion(
            document_id=document.id,
            version_number=document.current_version + 1,
            content=text,
            content_hash=digest,
        )
        session.add(current)
        document.current_version += 1
        document.content_hash = digest
        await session.flush()
    document.extraction_status = extraction_status
    document.metadata_json = {
        **document.metadata_json,
        "extraction": dict(extraction_metadata),
        "warnings": list(warnings),
        "parser": parser,
    }
    existing = await session.scalar(
        select(DocumentChunk.id).where(DocumentChunk.document_version_id == current.id).limit(1)
    )
    if existing is None:
        for index, chunk in enumerate(chunks):
            content = str(chunk["content"])
            session.add(
                DocumentChunk(
                    document_version_id=current.id,
                    chunk_index=index,
                    content=content,
                    content_hash=content_hash(content),
                    token_count=int(chunk["token_count"]),
                    metadata_json=dict(chunk.get("metadata", {})),
                )
            )
    await session.flush()
    return document.id


async def list_documents(
    session: AsyncSession, limit: int, cursor: str | None, source_id: UUID | None
) -> tuple[list[Document], str | None]:
    statement = select(Document)
    if source_id is not None:
        statement = statement.where(Document.source_id == source_id)
    statement = statement.order_by(desc(Document.created_at), desc(Document.id))
    if cursor is not None:
        timestamp, identifier = decode_cursor(cursor)
        statement = statement.where(
            tuple_(Document.created_at, Document.id) < (timestamp, identifier)
        )
    rows = list((await session.scalars(statement.limit(limit + 1))).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return rows, next_cursor


async def update_document(
    session: AsyncSession, document: Document, payload: DocumentPatch
) -> Document:
    changed = False
    if "title" in payload.model_fields_set:
        value = payload.title or ""
        changed = changed or document.title != value
        document.title = value
    if "metadata" in payload.model_fields_set:
        value = payload.metadata or {}
        changed = changed or document.metadata_json != value
        document.metadata_json = value
    drafts = [make_knowledge_change(document.source_id, document.id, document.current_version)] if changed else []
    await commit_with_replay(session, drafts)
    await session.refresh(document)
    return document


async def delete_document(session: AsyncSession, document_id: UUID) -> bool:
    identity = await session.execute(select(Document.source_id).where(Document.id == document_id))
    source_id = identity.scalar_one_or_none()
    if source_id is None:
        return False
    await sources.lock_source(session, source_id)
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.source_id == source_id).with_for_update()
    )
    if document is None:
        return False
    await _remove_graph_support(session, document_id=document_id)
    result = await session.scalars(
        delete(Document)
        .where(Document.id == document_id, Document.source_id == source_id)
        .returning(Document.id)
    )
    deleted = result.first() is not None
    drafts = [make_knowledge_change(source_id, document_id, deleted=True)] if deleted else []
    await commit_with_replay(session, drafts)
    return deleted


async def delete_source_documents(session: AsyncSession, source_id: UUID) -> None:
    """Delete owned data inside the caller's source-locked transaction; do not commit."""
    document_ids = list((await session.scalars(
        select(Document.id).where(Document.source_id == source_id).order_by(Document.id).limit(10_001).with_for_update()
    )).all())
    if len(document_ids) > 10_000:
        raise ValueError("Source graph cleanup exceeds its atomic document limit")
    await _remove_graph_support(session, source_id=source_id)
    await session.execute(delete(Document).where(Document.source_id == source_id))


async def _remove_graph_support(
    session: AsyncSession, *, document_id: UUID | None = None, source_id: UUID | None = None
) -> None:
    if (document_id is None) == (source_id is None):
        raise ValueError("Specify one document or source for graph cleanup")
    from modules.knowledge.entities import public as entities
    from modules.knowledge.relationships import public as relationships

    refs = await list_evidence_ref_keys(session, document_id=document_id, source_id=source_id)
    membership_ids, entity_ids = await entities.support_cleanup_ids(
        session, document_id=document_id, source_id=source_id
    )
    relationship_ids, relationship_entity_ids = await relationships.support_cleanup_ids(
        session, refs=refs, document_id=document_id, source_id=source_id, membership_ids=membership_ids
    )
    all_entity_ids = sorted(set(entity_ids) | set(relationship_entity_ids), key=str)
    await entities.lock_entity_ids(session, all_entity_ids)
    await relationships.lock_relationship_ids(session, relationship_ids)
    if document_id is not None:
        await relationships.remove_document_support(
            session, document_id=document_id, refs=refs, membership_ids=membership_ids
        )
        await entities.remove_document_support(session, document_id)
    else:
        await relationships.remove_source_support(
            session, source_id=source_id, refs=refs, membership_ids=membership_ids
        )
        await entities.remove_source_support(session, source_id)


async def append_content(
    session: AsyncSession, document_id: UUID, expected_version: int, content: str
) -> Document | None:
    document = await session.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )
    if document is None:
        return None
    current = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == document.current_version,
        )
    )
    if current is None:
        raise RuntimeError("Current document version is missing")
    if current.content == content:
        return document
    if document.current_version != expected_version:
        raise ValueError("Document revision is stale")
    next_version = document.current_version + 1
    digest = content_hash(content)
    version = DocumentVersion(
            document_id=document_id,
            version_number=next_version,
            content=content,
            content_hash=digest,
        )
    session.add(version)
    await add_content_chunks(session, version)
    document.current_version = next_version
    document.content_hash = digest
    await commit_with_replay(
        session,
        [make_knowledge_change(document.source_id, document.id, next_version)],
    )
    await session.refresh(document)
    return document


def encode_version_cursor(version_number: int) -> str:
    return base64.urlsafe_b64encode(str(version_number).encode()).decode().rstrip("=")


def decode_version_cursor(cursor: str) -> int:
    try:
        if "=" in cursor:
            raise ValueError("Cursor must be unpadded")
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        )
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != cursor:
            raise ValueError("Cursor is not canonical URL-safe base64")
        version_number = int(raw)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc
    if not 1 <= version_number <= 2147483647:
        raise HTTPException(status_code=422, detail="Invalid cursor")
    return version_number


async def list_versions(
    session: AsyncSession, document_id: UUID, limit: int, cursor: str | None
) -> tuple[list[DocumentVersion] | None, str | None]:
    after_version = decode_version_cursor(cursor) if cursor is not None else None
    if await session.get(Document, document_id) is None:
        return None, None
    statement = select(DocumentVersion).where(DocumentVersion.document_id == document_id)
    if after_version is not None:
        statement = statement.where(DocumentVersion.version_number > after_version)
    result = await session.scalars(
        statement.order_by(DocumentVersion.version_number).limit(limit + 1)
    )
    rows = list(result.all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_version_cursor(rows[-1].version_number) if has_more and rows else None
    return rows, next_cursor


async def get_version(
    session: AsyncSession, document_id: UUID, number: int
) -> DocumentVersion | None:
    return await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == number,
        )
    )


async def read_evidence_refs(
    session: AsyncSession, refs: list[tuple[UUID, UUID]], *, for_write: bool = False
) -> list[EvidenceReferenceRead]:
    if len(refs) > 100 or len(set(refs)) != len(refs):
        raise ValueError("Evidence references must be unique and contain at most 100 items")
    if not refs:
        return []
    result = await _read_evidence_ref_rows(session, refs)
    if for_write:
        from modules.sources import public as sources_public

        for source_id in sorted({item.source_id for item in result}, key=str):
            if await sources_public.lock_source(session, source_id) is None:
                raise ValueError("Evidence source no longer exists")
        document_ids = sorted({item.document_id for item in result}, key=str)
        await session.scalars(
            select(Document)
            .where(Document.id.in_(document_ids))
            .order_by(Document.id)
            .with_for_update()
        )
        result = await _read_evidence_ref_rows(session, refs)
    return result


async def _read_evidence_ref_rows(
    session: AsyncSession, refs: list[tuple[UUID, UUID]]
) -> list[EvidenceReferenceRead]:
    rows = (await session.execute(
        select(Document, DocumentVersion, DocumentChunk, Source.id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(DocumentChunk, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(Source, Source.id == Document.source_id)
        .where(tuple_(DocumentVersion.id, DocumentChunk.id).in_(refs))
    )).all()
    by_ref = {
        (version.id, chunk.id): EvidenceReferenceRead(
            document_id=document.id,
            document_version_id=version.id,
            version_number=version.version_number,
            chunk_id=chunk.id,
            source_id=source_id,
            title=document.title,
            canonical_url=document.canonical_url,
            metadata_is_version_snapshot=False,
            observed_at=version.observed_at,
            excerpt=chunk.content[:1000],
        )
        for document, version, chunk, source_id in rows
    }
    if set(by_ref) != set(refs):
        raise ValueError("Evidence reference is missing or does not match its document revision")
    return [by_ref[ref] for ref in refs]
