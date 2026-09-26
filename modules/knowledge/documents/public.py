import base64
import binascii
import hashlib
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, desc, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import decode_cursor, encode_cursor
from core.chunking import chunk_text
from modules.knowledge.documents.models import Document, DocumentChunk, DocumentVersion
from modules.knowledge.documents.schemas import DocumentCreate, DocumentPatch
from modules.sources import public as sources
from modules.sources.models import Source


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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
        await session.commit()
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
) -> Document:
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
    return document


async def save_extraction(
    session: AsyncSession,
    document_id: UUID,
    text: str,
    chunks: list[dict[str, object]],
    extraction_status: str,
) -> Document | None:
    document = await session.scalar(select(Document).where(Document.id == document_id).with_for_update())
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
    return document


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
    if "title" in payload.model_fields_set:
        document.title = payload.title or ""
    if "metadata" in payload.model_fields_set:
        document.metadata_json = payload.metadata or {}
    await session.commit()
    await session.refresh(document)
    return document


async def delete_document(session: AsyncSession, document_id: UUID) -> bool:
    identity = await session.execute(select(Document.source_id).where(Document.id == document_id))
    source_id = identity.scalar_one_or_none()
    if source_id is None:
        return False
    await sources.lock_source(session, source_id)
    result = await session.scalars(
        delete(Document)
        .where(Document.id == document_id, Document.source_id == source_id)
        .returning(Document.id)
    )
    await session.commit()
    return result.first() is not None


async def delete_source_documents(session: AsyncSession, source_id: UUID) -> None:
    """Delete owned data inside the caller's source-locked transaction; do not commit."""
    await session.execute(delete(Document).where(Document.source_id == source_id))


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
    await session.commit()
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
