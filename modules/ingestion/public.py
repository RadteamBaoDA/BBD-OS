import hashlib
import json
import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.events import DomainEvent
from modules.ingestion.models import (
    COLLECTION_LEASE,
    CollectorCredential,
    EventOutbox,
    IngestionBatch,
    IngestionRun,
    IngestionStage,
    SourceIngestionState,
    SourceObservation,
)
from modules.ingestion.schemas import ReceiveBatch
from modules.knowledge.documents import public as documents
from modules.sources import public as sources
from modules.sources.models import Source

def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def create_collector_credential(session: AsyncSession, source_id: UUID) -> str:
    source = await session.scalar(select(Source).where(Source.id == source_id).with_for_update())
    if source is None or source.status == "archived":
        raise LookupError("Source not found")
    now = datetime.now(UTC)
    credentials = list(
        (
            await session.scalars(
                select(CollectorCredential)
                .where(CollectorCredential.source_id == source_id, CollectorCredential.revoked_at.is_(None))
                .with_for_update()
            )
        ).all()
    )
    for credential in credentials:
        credential.revoked_at = now
    token = secrets.token_urlsafe(32)
    session.add(CollectorCredential(token_hash=hashlib.sha256(token.encode()).hexdigest(), source_id=source_id))
    await session.commit()
    return token


async def revoke_collector_credential(session: AsyncSession, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = await session.get(CollectorCredential, token_hash)
    if row is not None:
        row.revoked_at = datetime.now(UTC)
        await session.commit()


async def collector_can_ingest(session: AsyncSession, source_id: UUID, token: str) -> bool:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return bool(
        await session.scalar(
            select(CollectorCredential.token_hash)
            .join(Source, Source.id == CollectorCredential.source_id)
            .where(
                CollectorCredential.token_hash == token_hash,
                CollectorCredential.source_id == source_id,
                CollectorCredential.scope == "ingestion:write",
                CollectorCredential.revoked_at.is_(None),
                Source.status == "active",
            )
        )
    )


async def receive_batch(session: AsyncSession, payload: ReceiveBatch) -> tuple[IngestionBatch, IngestionRun]:
    source = await session.scalar(
        select(Source).where(Source.id == payload.source_id).with_for_update()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.status != "active":
        raise HTTPException(status_code=409, detail="Source is not active")

    payload_hash = _digest(payload.model_dump(mode="json"))
    existing = await session.scalar(
        select(IngestionBatch).where(
            IngestionBatch.source_id == payload.source_id,
            IngestionBatch.batch_key == payload.batch_key,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(status_code=409, detail="Batch key was already used with different content")
        run = await session.scalar(select(IngestionRun).where(IngestionRun.batch_id == existing.id))
        if run is None:
            raise RuntimeError("Ingestion batch has no run")
        return existing, run

    state = await session.get(SourceIngestionState, payload.source_id, with_for_update=True)
    if state is None:
        state = SourceIngestionState(source_id=payload.source_id, cursor=None)
        session.add(state)
        await session.flush()
    now = datetime.now(UTC)
    source.last_sync_at = now
    source.collected_at = now
    if state.lease_expires_at is not None and state.lease_expires_at > now:
        raise HTTPException(status_code=409, detail="Source already has an active collection run")
    if state.cursor != payload.cursor_before:
        raise HTTPException(status_code=409, detail="Collection cursor is stale")

    batch = IngestionBatch(source_id=payload.source_id, batch_key=payload.batch_key, payload_hash=payload_hash)
    session.add(batch)
    await session.flush()
    run = IngestionRun(batch_id=batch.id, source_id=payload.source_id, status="queued")
    session.add(run)
    await session.flush()
    stage = IngestionStage(run_id=run.id, stage_key="receive", status="pending")
    session.add(stage)
    await session.flush()
    event = DomainEvent(
        id=uuid4(),
        type="ingestion.stage.requested",
        version=1,
        occurred_at=now,
        producer="modules.ingestion",
        payload={"run_id": str(run.id), "stage_id": str(stage.id), "source_generation": source.generation},
    )
    session.add(
        EventOutbox(
            id=event.id,
            type=event.type,
            version=event.version,
            occurred_at=event.occurred_at,
            producer=event.producer,
            payload=event.payload,
            status="pending",
        )
    )
    # Keep every distinct provider/content observation in the accepted batch.
    seen: set[tuple[str, str, datetime]] = set()
    for record in payload.records:
        data = record.model_dump(mode="json")
        record_hash = _digest({"version": record.version, "content": record.content, "metadata": record.metadata})
        identity = (record.provider_id, record_hash, record.observed_at)
        if identity in seen:
            continue
        seen.add(identity)
        session.add(
            SourceObservation(
                source_id=payload.source_id,
                batch_id=batch.id,
                provider_id=record.provider_id,
                record_hash=record_hash,
                payload=data,
                observed_at=record.observed_at,
            )
        )
    result = await session.execute(
        update(SourceIngestionState)
        .where(
            SourceIngestionState.source_id == payload.source_id,
            SourceIngestionState.cursor.is_not_distinct_from(payload.cursor_before),
        )
        .values(cursor=payload.cursor_after, lease_run_id=run.id, lease_expires_at=now + COLLECTION_LEASE)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="Collection cursor changed")
    await session.commit()
    await session.refresh(batch)
    await session.refresh(run)
    return batch, run


async def queue_connector_crawl(
    session: AsyncSession,
    source_id: UUID,
    cursor_before: str | None,
    configuration: dict[str, object],
) -> IngestionRun:
    source = await session.scalar(select(Source).where(Source.id == source_id).with_for_update())
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.status != "active":
        raise HTTPException(status_code=409, detail="Source is not active")
    state = await session.get(SourceIngestionState, source_id, with_for_update=True)
    if state is None:
        state = SourceIngestionState(source_id=source_id, cursor=None)
        session.add(state)
        await session.flush()
    if state.cursor != cursor_before:
        raise HTTPException(status_code=409, detail="Collection cursor is stale")

    now = datetime.now(UTC)
    source.last_sync_at = now
    source.collected_at = now
    minute = now.replace(second=0, microsecond=0).isoformat()
    key = "crawl:" + _digest({"source_id": str(source_id), "cursor": cursor_before, "config": configuration, "minute": minute})
    existing = await session.scalar(
        select(IngestionBatch).where(IngestionBatch.source_id == source_id, IngestionBatch.batch_key == key)
    )
    if existing is not None:
        run = await session.scalar(select(IngestionRun).where(IngestionRun.batch_id == existing.id))
        if run is None:
            raise RuntimeError("Crawl batch has no run")
        return run
    if state.lease_expires_at is not None and state.lease_expires_at > now:
        raise HTTPException(status_code=409, detail="Source already has an active collection run")

    batch = IngestionBatch(source_id=source_id, batch_key=key, payload_hash=_digest(configuration))
    session.add(batch)
    await session.flush()
    run = IngestionRun(batch_id=batch.id, source_id=source_id, status="queued")
    session.add(run)
    await session.flush()
    stage = IngestionStage(run_id=run.id, stage_key="collect_web", status="pending")
    session.add(stage)
    await session.flush()
    event = DomainEvent(
        id=uuid4(),
        type="connector.crawl.requested",
        version=1,
        occurred_at=now,
        producer="modules.connectors",
        payload={
            "source_id": str(source_id),
            "source_generation": source.generation,
            "run_id": str(run.id),
            "stage_id": str(stage.id),
            "cursor_before": cursor_before,
            "configuration": configuration,
        },
    )
    session.add(
        EventOutbox(
            id=event.id,
            type=event.type,
            version=event.version,
            occurred_at=event.occurred_at,
            producer=event.producer,
            payload=event.payload,
            status="pending",
        )
    )
    state.lease_run_id = run.id
    state.lease_expires_at = now + COLLECTION_LEASE
    await session.commit()
    await session.refresh(run)
    return run


async def receive_file(
    session: AsyncSession,
    source_id: UUID,
    document_id: UUID,
    filename: str,
    mime_type: str,
    raw_uri: str,
    size: int,
    digest: str,
) -> tuple[IngestionRun, bool]:
    await sources.lock_source_for_document(session, source_id)
    source = await session.get(Source, source_id)
    if source is None or source.status != "active":
        raise HTTPException(status_code=409, detail="Source is not active")
    batch_key = f"file:{digest}"
    existing = await session.scalar(
        select(IngestionBatch).where(IngestionBatch.source_id == source_id, IngestionBatch.batch_key == batch_key)
    )
    if existing is not None:
        if existing.payload_hash != digest:
            raise HTTPException(status_code=409, detail="Upload identity conflicts with stored content")
        if not await documents.has_document_identity(session, source_id, f"file:{digest}"):
            raise HTTPException(status_code=409, detail="This file was previously ingested and its document was deleted")
        run = await session.scalar(select(IngestionRun).where(IngestionRun.batch_id == existing.id))
        if run is None:
            raise RuntimeError("Ingestion batch has no run")
        await session.commit()
        return run, False

    now = datetime.now(UTC)
    source.last_sync_at = now
    source.collected_at = now
    batch = IngestionBatch(source_id=source_id, batch_key=batch_key, payload_hash=digest)
    session.add(batch)
    await session.flush()
    run = IngestionRun(batch_id=batch.id, source_id=source_id, status="queued")
    session.add(run)
    await session.flush()
    stage = IngestionStage(run_id=run.id, stage_key="parse_file", status="pending")
    session.add(stage)
    await session.flush()
    metadata = {"filename": filename, "raw_sha256": digest, "raw_size": size, "format": mime_type}
    document = await documents.add_uploaded_document(
        session, source_id, filename[:500] or "Uploaded file", mime_type, raw_uri, metadata, f"file:{digest}", document_id
    )
    event = DomainEvent(
        id=uuid4(),
        type="document.file.uploaded",
        version=1,
        occurred_at=now,
        producer="modules.ingestion",
        payload={"run_id": str(run.id), "stage_id": str(stage.id), "document_id": str(document.id), "raw_uri": raw_uri, "mime_type": mime_type, "source_generation": source.generation},
    )
    session.add(EventOutbox(
        id=event.id,
        type=event.type,
        version=event.version,
        occurred_at=event.occurred_at,
        producer=event.producer,
        payload=event.payload,
        status="pending",
    ))
    await session.commit()
    await session.refresh(run)
    return run, True


async def get_run(session: AsyncSession, run_id: UUID) -> tuple[IngestionRun, list[IngestionStage]] | None:
    run = await session.get(IngestionRun, run_id)
    if run is None:
        return None
    stages = list(
        (
            await session.scalars(
                select(IngestionStage).where(IngestionStage.run_id == run_id).order_by(IngestionStage.stage_key)
            )
        ).all()
    )
    return run, stages


async def retry_run(session: AsyncSession, run_id: UUID) -> IngestionRun | None:
    run_hint = await session.get(IngestionRun, run_id)
    if run_hint is None:
        return None
    # Match source archive and workers: source, run, then stage.
    source = await session.scalar(select(Source).where(Source.id == run_hint.source_id).with_for_update())
    if source is None or source.status != "active":
        raise HTTPException(status_code=409, detail="Source is not active")
    run = await session.scalar(
        select(IngestionRun).where(IngestionRun.id == run_id, IngestionRun.source_id == source.id).with_for_update()
    )
    if run is None:
        return None
    stage = await session.scalar(
        select(IngestionStage).where(IngestionStage.run_id == run_id).with_for_update()
    )
    if stage is None:
        raise RuntimeError("Ingestion run has no stage")
    if stage.status in {"pending", "queued", "running", "retrying"}:
        return run
    if stage.status == "succeeded":
        return run
    stage.status = "pending"
    stage.attempts = 0
    stage.error_code = None
    stage.next_attempt_at = datetime.now(UTC)
    stage.lease_expires_at = None
    run.status = "queued"
    run.error_code = None
    prior_event = await session.scalar(
        select(EventOutbox)
        .where(EventOutbox.payload["stage_id"].astext == str(stage.id))
        .order_by(EventOutbox.created_at.desc())
        .limit(1)
    )
    event = DomainEvent(
        id=uuid4(),
        type=prior_event.type if prior_event is not None else "ingestion.stage.requested",
        version=1,
        occurred_at=datetime.now(UTC),
        producer="modules.ingestion",
        payload={
            **(prior_event.payload if prior_event is not None else {"run_id": str(run.id), "stage_id": str(stage.id)}),
            "source_generation": source.generation,
        },
    )
    session.add(
        EventOutbox(
            id=event.id,
            type=event.type,
            version=1,
            occurred_at=event.occurred_at,
            producer=event.producer,
            payload=event.payload,
        )
    )
    state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
    if state is not None:
        now = datetime.now(UTC)
        if state.lease_run_id not in (None, run.id) and state.lease_expires_at and state.lease_expires_at > now:
            raise HTTPException(status_code=409, detail="Source already has an active collection run")
        state.lease_run_id = run.id
        state.lease_expires_at = now + COLLECTION_LEASE
    await session.commit()
    await session.refresh(run)
    return run
