from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.storage import cleanup_orphaned_files, storage_path
from modules.ingestion.models import EventOutbox, IngestionRun, IngestionStage
from modules.ingestion.parsers import parse_file_bounded
from modules.knowledge.documents import public as documents
from modules.knowledge.documents.models import Document
from modules.sources.models import Source
from modules.ingestion.chunking import chunk_text


async def process_uploaded_file(ctx: dict[str, object], event_id: str) -> None:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    settings = cast(Settings, ctx["settings"])
    identifier = UUID(event_id)
    async with factory() as session:
        event = await session.get(EventOutbox, identifier, with_for_update=True)
        if event is None or event.status == "delivered":
            return
        run_id = UUID(str(event.payload["run_id"]))
        stage_id = UUID(str(event.payload["stage_id"]))
        document_id = UUID(str(event.payload["document_id"]))
        stage = await session.scalar(select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update())
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        document = await session.scalar(select(Document).where(Document.id == document_id).with_for_update())
        source = await session.scalar(select(Source).where(Source.id == run.source_id).with_for_update()) if run else None
        if stage is None or run is None or document is None or source is None or source.status != "active":
            if stage is not None:
                stage.status = "failed"
                stage.error_code = "source_or_document_unavailable"
            if run is not None:
                run.status = "failed"
                run.error_code = "source_or_document_unavailable"
            event.status = "failed"
            await session.commit()
            return
        now = datetime.now(UTC)
        if stage.status == "succeeded":
            event.status = "delivered"
            await session.commit()
            return
        if stage.status == "running" and stage.lease_expires_at and stage.lease_expires_at > now:
            return
        stage.status = "running"
        stage.attempts += 1
        stage.lease_expires_at = now + timedelta(seconds=settings.parser_timeout_seconds + 30)
        stage.error_code = None
        run.status = "running"
        document.extraction_status = "processing"
        await session.commit()

    try:
        raw_path = storage_path(settings.data_dir, str(event.payload["raw_uri"]))
        parsed = await parse_file_bounded(
            raw_path,
            str(event.payload["mime_type"]),
            settings.parser_timeout_seconds,
            settings.docx_expanded_max_bytes,
            settings.pdf_page_max,
        )
        drafts = chunk_text(parsed.text)
        extraction_status = "needs_ocr" if parsed.warnings and not parsed.text else "succeeded"
        async with factory() as session:
            document = await documents.save_extraction(
                session,
                document_id,
                parsed.text,
                [
                    {"content": draft.content, "token_count": draft.token_count, "metadata": draft.metadata}
                    for draft in drafts
                ],
                extraction_status,
            )
            stage = await session.scalar(select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update())
            run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            if document is None or stage is None or run is None or event is None:
                return
            document.metadata_json = {
                **document.metadata_json,
                "extraction": parsed.metadata,
                "warnings": parsed.warnings,
                "parser": "p02-t2-v1",
            }
            stage.status = "succeeded"
            stage.lease_expires_at = None
            stage.error_code = None
            run.status = extraction_status if extraction_status == "needs_ocr" else "succeeded"
            run.error_code = None
            event.status = "delivered"
            await session.commit()
    except Exception as exc:
        async with factory() as session:
            stage = await session.scalar(select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update())
            run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            document = await session.scalar(select(Document).where(Document.id == document_id).with_for_update())
            if stage is not None:
                stage.status = "failed"
                stage.error_code = "parser_timeout" if isinstance(exc, TimeoutError) else "parse_failed"
                stage.lease_expires_at = None
            if run is not None:
                run.status = "failed"
                run.error_code = "parser_timeout" if isinstance(exc, TimeoutError) else "parse_failed"
            if document is not None:
                document.extraction_status = "failed"
            if event is not None:
                event.status = "failed"
            await session.commit()


async def cleanup_storage_orphans(ctx: dict[str, object]) -> int:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    settings = cast(Settings, ctx["settings"])
    async with factory() as session:
        referenced = set((await session.scalars(select(Document.raw_uri).where(Document.raw_uri.is_not(None)))).all())
    return cleanup_orphaned_files(settings.data_dir, cast(set[str], referenced), settings.storage_orphan_grace_seconds)
