from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.storage import storage_path
from modules.ingestion.models import (
    CollectorCredential, EventOutbox, IngestionBatch, IngestionRun, SourceIngestionState, SourceObservation,
)
from modules.knowledge.documents.models import Document
from modules.sources.models import Source, SourcePurgeOperation


async def process_source_purge(ctx: dict[str, object], event_id: str) -> None:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    settings = cast(Settings, ctx["settings"])
    identifier = UUID(event_id)
    async with factory() as session:
        event = await session.get(EventOutbox, identifier)
        if event is None or event.status == "delivered":
            return
        operation_id = UUID(str(event.payload["operation_id"]))
        hint = await session.get(SourcePurgeOperation, operation_id)
        if hint is None:
            event.status = "failed"
            await session.commit()
            return
        source = await session.scalar(select(Source).where(Source.id == hint.source_id).with_for_update())
        operation = await session.scalar(
            select(SourcePurgeOperation).where(SourcePurgeOperation.id == operation_id).with_for_update()
        )
        if operation is None or source is None or source.generation != operation.generation:
            event.status = "failed"
            if operation is not None:
                operation.status = "failed"
                operation.error_code = "source_generation_changed"
            await session.commit()
            return
        if operation.status == "succeeded":
            event.status = "delivered"
            await session.commit()
            return
        operation.status = "running"
        operation.error_code = None
        raw_uris = list(operation.raw_uris)
        run_ids = select(IngestionRun.id).where(IngestionRun.source_id == source.id)
        await session.execute(
            update(EventOutbox)
            .where(EventOutbox.payload["run_id"].astext.in_(run_ids))
            .values(status="failed")
        )
        await session.execute(delete(Document).where(Document.source_id == source.id))
        await session.execute(delete(SourceObservation).where(SourceObservation.source_id == source.id))
        await session.execute(delete(IngestionBatch).where(IngestionBatch.source_id == source.id))
        state = await session.get(SourceIngestionState, source.id, with_for_update=True)
        if state is not None:
            state.lease_run_id = None
            state.lease_expires_at = None
        await session.execute(
            update(CollectorCredential).where(CollectorCredential.source_id == source.id)
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()

    try:
        for raw_uri in raw_uris:
            storage_path(settings.data_dir, raw_uri).unlink(missing_ok=True)
    except (OSError, ValueError):
        async with factory() as session:
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            operation = await session.get(SourcePurgeOperation, operation_id, with_for_update=True)
            if operation is not None:
                operation.status = "failed"
                operation.error_code = "file_cleanup_failed"
            if event is not None:
                event.status = "pending"
                event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
            await session.commit()
        raise

    async with factory() as session:
        operation = await session.get(SourcePurgeOperation, operation_id, with_for_update=True)
        event = await session.get(EventOutbox, identifier, with_for_update=True)
        if operation is not None:
            operation.status = "succeeded"
            operation.error_code = None
        if event is not None:
            event.status = "delivered"
        await session.commit()
