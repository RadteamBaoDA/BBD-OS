import base64
import binascii
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, desc, func, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import decode_cursor, encode_cursor
from core.chunking import chunk_text
from core.realtime import commit_with_replay, make_knowledge_change
from modules.knowledge.documents.models import (
    Document, DocumentChunk, DocumentVersion, NormalizedDocumentIdentity,
    NormalizedVersionProvenance,
)
from modules.knowledge.documents.schemas import (
    DocumentCreate, DocumentPatch, EvidenceReferenceRead, NormalizedDocumentInput,
    NormalizedDocumentResult,
)
from modules.sources import public as sources
from modules.sources.models import Source

EXTRACTION_CHUNK_LIMIT = 100
EXTRACTION_INPUT_BYTES = 64_000


@dataclass(frozen=True)
class ExtractionChunk:
    id: UUID
    content: str


@dataclass(frozen=True)
class ExtractionInput:
    document_id: UUID
    document_version_id: UUID
    source_id: UUID
    source_generation: int
    local_only: bool
    observed_at: datetime
    chunks: tuple[ExtractionChunk, ...]


@dataclass(frozen=True)
class ExtractionEvidenceRef:
    document_id: UUID
    document_version_id: UUID
    source_id: UUID
    source_generation: int
    chunk_id: UUID


@dataclass(frozen=True)
class ReadyVersionRef:
    document_id: UUID
    document_version_id: UUID
    source_id: UUID
    source_generation: int
    version_number: int
    created_at: datetime
    local_only: bool


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


async def add_content_chunks(session: AsyncSession, version: DocumentVersion) -> int:
    await session.flush()
    drafts = chunk_text(version.content)
    for index, draft in enumerate(drafts):
        session.add(DocumentChunk(
            document_version_id=version.id, chunk_index=index, content=draft.content,
            content_hash=content_hash(draft.content), token_count=draft.token_count,
            metadata_json=draft.metadata,
        ))
    return len(drafts)


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
        hint = await session.get(Document, version.document_id)
        source = await sources.lock_source(session, hint.source_id) if hint else None
        document = await session.scalar(
            select(Document).where(Document.id == version.document_id).with_for_update()
        )
        if (
            source is None or source.status != "active" or document is None
            or document.current_version != version.version_number
        ):
            continue
        if await add_content_chunks(session, version):
            await _publish_document_ready(session, document, version)
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
        if await add_content_chunks(session, version):
            await _publish_document_ready(session, document, version)
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


async def upsert_normalized_document(
    session: AsyncSession, payload: NormalizedDocumentInput
) -> NormalizedDocumentResult:
    """Persist one source-owned immutable normalized revision without committing."""
    source = await sources.lock_source(session, payload.source_id)
    if source is None or source.status != "active" or source.generation != payload.expected_source_generation:
        raise ValueError("Normalized source generation is no longer active")

    identity = await session.scalar(
        select(NormalizedDocumentIdentity)
        .where(
            NormalizedDocumentIdentity.source_id == payload.source_id,
            NormalizedDocumentIdentity.external_id == payload.provider_id,
        )
        .with_for_update()
    )
    created_identity = identity is None
    if identity is None:
        identity = NormalizedDocumentIdentity(source_id=payload.source_id, external_id=payload.provider_id)
        session.add(identity)
        await session.flush()
    if identity.tombstoned_at is not None:
        return NormalizedDocumentResult(
            disposition="tombstoned", document_id=None, document_version_id=None,
            version_number=None, created_version=False, selected_current=False, chunk_count=0,
        )

    document = await session.scalar(
        select(Document)
        .where(Document.source_id == payload.source_id, Document.external_id == payload.provider_id)
        .with_for_update()
    )
    if document is not None and identity.document_id not in (None, document.id):
        raise ValueError("Normalized identity points to a different document")
    if document is not None and identity.document_id is None:
        if created_identity:
            await session.delete(identity)
            await session.flush()
        raise ValueError("Provider identity conflicts with an existing non-normalized document")
    if document is None:
        document = Document(
            source_id=payload.source_id, external_id=payload.provider_id,
            title=payload.title, content_type=payload.content_type,
            canonical_url=payload.canonical_url, published_at=payload.published_at,
            observed_at=payload.observed_at, current_version=0,
            content_hash=content_hash(payload.content), extraction_status="ready",
        )
        session.add(document)
        await session.flush()
        identity.document_id = document.id

    prior = await session.scalar(
        select(NormalizedVersionProvenance).where(
            NormalizedVersionProvenance.document_id == document.id,
            NormalizedVersionProvenance.accepted_record_hash == payload.accepted_record_hash,
            NormalizedVersionProvenance.normalization_version == payload.normalization_version,
        )
    )
    if prior is not None:
        version = await session.get(DocumentVersion, prior.document_version_id)
        if version is None:
            raise RuntimeError("Normalized provenance references a missing revision")
        count = await session.scalar(
            select(func.count()).select_from(DocumentChunk)
            .where(DocumentChunk.document_version_id == version.id)
        )
        return NormalizedDocumentResult(
            disposition="duplicate", document_id=document.id, document_version_id=version.id,
            version_number=version.version_number, created_version=False,
            selected_current=document.current_version == version.version_number,
            chunk_count=int(count or 0),
        )

    current_provenance = None
    if document.current_version:
        current_provenance = await session.scalar(
            select(NormalizedVersionProvenance)
            .join(DocumentVersion, DocumentVersion.id == NormalizedVersionProvenance.document_version_id)
            .where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_number == document.current_version,
            )
        )
        if current_provenance is None:
            raise ValueError("Provider identity conflicts with an owner-authored current revision")
    current_rank = (
        (current_provenance.selection_observed_at, current_provenance.accepted_record_hash)
        if current_provenance is not None else None
    )
    selected = current_rank is None or (payload.observed_at, payload.accepted_record_hash) > current_rank
    max_number = await session.scalar(
        select(func.coalesce(func.max(DocumentVersion.version_number), 0))
        .where(DocumentVersion.document_id == document.id)
    )
    version = DocumentVersion(
        document_id=document.id, version_number=int(max_number or 0) + 1,
        content=payload.content, content_hash=content_hash(payload.content),
        observed_at=payload.observed_at,
    )
    session.add(version)
    await session.flush()
    session.add(NormalizedVersionProvenance(
        document_id=document.id, document_version_id=version.id,
        provider_id=payload.provider_id, provider_version=payload.provider_version,
        accepted_record_hash=payload.accepted_record_hash,
        normalization_version=payload.normalization_version,
        source_generation=payload.expected_source_generation,
        observed_at=payload.observed_at, received_at=payload.received_at,
        collected_at=payload.collected_at, selection_observed_at=payload.observed_at,
        title=payload.title, canonical_url=payload.canonical_url,
        published_at=payload.published_at, content_type=payload.content_type,
        provenance_json=payload.provenance,
    ))
    chunk_count = await add_content_chunks(session, version)
    if selected:
        document.current_version = version.version_number
        document.content_hash = version.content_hash
        document.title = payload.title
        document.canonical_url = payload.canonical_url
        document.published_at = payload.published_at
        document.content_type = payload.content_type
        document.observed_at = payload.observed_at
        document.extraction_status = "ready"
    await session.flush()
    return NormalizedDocumentResult(
        disposition="normalized", document_id=document.id,
        document_version_id=version.id, version_number=version.version_number,
        created_version=True, selected_current=selected, chunk_count=chunk_count,
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
    source = await sources.lock_source(session, source_id)
    if source is None or source.status != "active":
        return None
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
        max_number = await session.scalar(
            select(func.coalesce(func.max(DocumentVersion.version_number), 0))
            .where(DocumentVersion.document_id == document.id)
        )
        current = DocumentVersion(
            document_id=document.id,
            version_number=int(max_number or 0) + 1,
            content=text,
            content_hash=digest,
        )
        session.add(current)
        document.current_version = current.version_number
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
    if extraction_status == "succeeded" and chunks:
        await _publish_document_ready(session, document, current)
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
    source = await sources.lock_source(session, source_id)
    if source is None:
        return False
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.source_id == source_id).with_for_update()
    )
    if document is None:
        return False
    if document.external_id is not None:
        identity = await session.scalar(
            select(NormalizedDocumentIdentity).where(
                NormalizedDocumentIdentity.source_id == source_id,
                NormalizedDocumentIdentity.external_id == document.external_id,
            ).with_for_update()
        )
        if identity is None:
            identity = NormalizedDocumentIdentity(
                source_id=source_id,
                external_id=document.external_id,
                document_id=document.id,
            )
        session.add(identity)
        await session.flush()
        identity.tombstoned_at = datetime.now(UTC)
        identity.document_id = None
        from modules.ingestion import public as ingestion
        await ingestion.tombstone_document_materializations(session, document.id)
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
    await session.execute(
        delete(NormalizedDocumentIdentity).where(NormalizedDocumentIdentity.source_id == source_id)
    )
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
    source_id = await session.scalar(select(Document.source_id).where(Document.id == document_id))
    if source_id is None:
        return None
    source = await sources.lock_source(session, source_id)
    if source is None or source.status != "active":
        return None
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
    max_number = await session.scalar(
        select(func.coalesce(func.max(DocumentVersion.version_number), 0))
        .where(DocumentVersion.document_id == document.id)
    )
    next_version = int(max_number or 0) + 1
    digest = content_hash(content)
    version = DocumentVersion(
            document_id=document_id,
            version_number=next_version,
            content=content,
            content_hash=digest,
        )
    session.add(version)
    if await add_content_chunks(session, version):
        await _publish_document_ready(session, document, version)
    document.current_version = next_version
    document.content_hash = digest
    await commit_with_replay(
        session,
        [make_knowledge_change(document.source_id, document.id, next_version)],
    )
    await session.refresh(document)
    return document


async def read_extraction_input(
    session: AsyncSession, version_id: UUID, allowed_chunk_ids: list[UUID] | None = None
) -> ExtractionInput | None:
    statement = (
        select(
            Document.id, Document.source_id, Source.generation, Source.local_only,
            DocumentVersion.id, DocumentVersion.observed_at,
        )
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(Source, Source.id == Document.source_id)
        .where(
            DocumentVersion.id == version_id,
            Document.current_version == DocumentVersion.version_number,
            Document.extraction_status.in_(("ready", "succeeded")),
            Source.status == "active",
        )
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    document_id, source_id, source_generation, local_only, actual_version_id, observed_at = row
    chunks_query = select(DocumentChunk.id, DocumentChunk.content).where(
        DocumentChunk.document_version_id == actual_version_id
    )
    if allowed_chunk_ids is not None:
        if not allowed_chunk_ids or len(allowed_chunk_ids) > EXTRACTION_CHUNK_LIMIT or len(set(allowed_chunk_ids)) != len(allowed_chunk_ids):
            raise ValueError("Extraction chunk IDs must be unique and bounded")
        chunks_query = chunks_query.where(DocumentChunk.id.in_(allowed_chunk_ids))
    stats = await session.execute(
        select(func.count(DocumentChunk.id), func.coalesce(func.sum(func.octet_length(DocumentChunk.content)), 0))
        .where(DocumentChunk.document_version_id == actual_version_id)
        .where(DocumentChunk.id.in_(allowed_chunk_ids) if allowed_chunk_ids is not None else True)
    )
    chunk_count, byte_count = stats.one()
    if not chunk_count or chunk_count > EXTRACTION_CHUNK_LIMIT or byte_count > EXTRACTION_INPUT_BYTES:
        raise ValueError("Extraction input exceeds its chunk or byte limit")
    chunks = list((await session.execute(chunks_query.order_by(DocumentChunk.chunk_index))).all())
    if allowed_chunk_ids is not None and {identifier for identifier, _ in chunks} != set(allowed_chunk_ids):
        return None
    return ExtractionInput(
        document_id=document_id, document_version_id=actual_version_id, source_id=source_id,
        source_generation=source_generation, local_only=local_only,
        observed_at=observed_at, chunks=tuple(ExtractionChunk(id=identifier, content=content) for identifier, content in chunks),
    )


async def read_extraction_evidence_refs(
    session: AsyncSession,
    *,
    document_id: UUID,
    document_version_id: UUID,
    source_id: UUID,
    source_generation: int,
    chunk_ids: list[UUID],
) -> list[ExtractionEvidenceRef] | None:
    """Validate a bounded set of current extraction chunks and return detached evidence refs."""
    if not chunk_ids or len(chunk_ids) > 150 or len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("Extraction membership evidence must be nonempty and bounded")
    rows = (await session.execute(
        select(Document.id, DocumentVersion.id, Document.source_id, Source.generation, DocumentChunk.id)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(DocumentChunk, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(Source, Source.id == Document.source_id)
        .where(
            Document.id == document_id,
            Document.source_id == source_id,
            DocumentVersion.id == document_version_id,
            Document.current_version == DocumentVersion.version_number,
            Document.extraction_status.in_(("ready", "succeeded")),
            Source.status == "active",
            Source.generation == source_generation,
            DocumentChunk.id.in_(chunk_ids),
        )
        .order_by(DocumentChunk.id)
    )).all()
    if len(rows) != len(chunk_ids):
        return None
    return [ExtractionEvidenceRef(
        document_id=row[0], document_version_id=row[1], source_id=row[2],
        source_generation=row[3], chunk_id=row[4],
    ) for row in rows]


async def list_ready_version_refs(
    session: AsyncSession, limit: int = 50, cursor: str | None = None
) -> tuple[list[ReadyVersionRef], str | None]:
    if not 1 <= limit <= 100:
        raise ValueError("Ready-version page size must be between 1 and 100")
    statement = (
        select(
            Document.id, Document.created_at, Source.id, Source.generation,
            DocumentVersion.id, DocumentVersion.version_number, Source.local_only,
        )
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(Source, Source.id == Document.source_id)
        .where(
            Document.current_version == DocumentVersion.version_number,
            Document.extraction_status.in_(("ready", "succeeded")),
            DocumentVersion.content != "",
            Source.status == "active",
            select(DocumentChunk.id).where(DocumentChunk.document_version_id == DocumentVersion.id).exists(),
        )
    )
    if cursor:
        created_at, identifier = decode_cursor(cursor)
        statement = statement.where(tuple_(Document.created_at, Document.id) < (created_at, identifier))
    rows = list((await session.execute(statement.order_by(desc(Document.created_at), desc(Document.id)).limit(limit + 1))).all())
    more = len(rows) > limit
    rows = rows[:limit]
    result = [ReadyVersionRef(
        document_id=document_id, document_version_id=version_id, source_id=source_id,
        source_generation=generation, version_number=version_number, created_at=created_at,
        local_only=local_only,
    ) for document_id, created_at, source_id, generation, version_id, version_number, local_only in rows]
    return result, encode_cursor(rows[-1][1], rows[-1][0]) if more and rows else None


async def get_ready_version_ref(session: AsyncSession, version_id: UUID) -> ReadyVersionRef | None:
    row = (await session.execute(
        select(
            Document.id, Document.created_at, Source.id, Source.generation,
            DocumentVersion.id, DocumentVersion.version_number, Source.local_only,
        )
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .join(Source, Source.id == Document.source_id)
        .where(
            DocumentVersion.id == version_id,
            Document.current_version == DocumentVersion.version_number,
            Document.extraction_status.in_(("ready", "succeeded")),
            DocumentVersion.content != "",
            Source.status == "active",
            select(DocumentChunk.id).where(DocumentChunk.document_version_id == DocumentVersion.id).exists(),
        )
    )).one_or_none()
    if row is None:
        return None
    document_id, created_at, source_id, generation, actual_version_id, version_number, local_only = row
    return ReadyVersionRef(
        document_id=document_id, document_version_id=actual_version_id, source_id=source_id,
        source_generation=generation, version_number=version_number,
        created_at=created_at, local_only=local_only,
    )


async def _publish_document_ready(session: AsyncSession, document: Document, version: DocumentVersion) -> None:
    from core.events import DomainEvent
    from modules.ingestion import public as ingestion

    source = await session.get(Source, document.source_id)
    if source is None:
        return
    await ingestion.publish_event(session, DomainEvent(
        id=uuid4(), type="document.version.ready", version=1,
        occurred_at=datetime.now(UTC), producer="modules.knowledge.documents",
        payload={
            "source_id": str(source.id), "document_id": str(document.id),
            "document_version_id": str(version.id), "source_generation": source.generation,
            "version_number": version.version_number,
        },
    ))


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
    provenance_rows = (await session.scalars(
        select(NormalizedVersionProvenance).where(
            NormalizedVersionProvenance.document_version_id.in_(
                {version.id for _, version, _, _ in rows}
            )
        )
    )).all() if rows else []
    provenance_by_version = {item.document_version_id: item for item in provenance_rows}
    by_ref = {
        (version.id, chunk.id): EvidenceReferenceRead(
            document_id=document.id,
            document_version_id=version.id,
            version_number=version.version_number,
            chunk_id=chunk.id,
            source_id=source_id,
            title=provenance_by_version[version.id].title if version.id in provenance_by_version else document.title,
            canonical_url=(
                provenance_by_version[version.id].canonical_url
                if version.id in provenance_by_version else document.canonical_url
            ),
            metadata_is_version_snapshot=version.id in provenance_by_version,
            observed_at=version.observed_at,
            excerpt=chunk.content[:1000],
        )
        for document, version, chunk, source_id in rows
    }
    if set(by_ref) != set(refs):
        raise ValueError("Evidence reference is missing or does not match its document revision")
    return [by_ref[ref] for ref in refs]
