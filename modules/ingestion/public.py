import hashlib
import json
import secrets
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import String, cast, delete, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.events import DomainEvent
from core.pagination import decode_cursor, encode_cursor
from core.realtime import commit_with_replay, make_ingestion_change, make_knowledge_change, make_source_change
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
from modules.ingestion.schemas import CrawlReceipt, EventDelivery, Receipt, ReceiveBatch, RunRead, SourceIngestionRead, StageRead
from modules.knowledge.documents import public as documents
from modules.sources import public as sources
from modules.sources.schemas import ConnectorSource

def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def create_collector_credential(session: AsyncSession, source_id: UUID) -> str:
    source = await sources.lock_source(session, source_id)
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
    await session.flush()
    return token


async def revoke_collector_credential(session: AsyncSession, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    source_id = await session.scalar(
        select(CollectorCredential.source_id).where(CollectorCredential.token_hash == token_hash)
    )
    if source_id is None or await sources.lock_source(session, source_id) is None:
        return
    row = await session.scalar(
        select(CollectorCredential)
        .where(CollectorCredential.token_hash == token_hash, CollectorCredential.source_id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is not None:
        row.revoked_at = datetime.now(UTC)


async def revoke_source_credentials(session: AsyncSession, source_id: UUID) -> None:
    if await sources.lock_source(session, source_id) is None:
        return
    await session.execute(
        update(CollectorCredential)
        .where(CollectorCredential.source_id == source_id, CollectorCredential.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def publish_event(session: AsyncSession, event: DomainEvent) -> None:
    session.add(EventOutbox(
        id=event.id,
        type=event.type,
        version=event.version,
        occurred_at=event.occurred_at,
        producer=event.producer,
        payload=event.payload,
        status="pending",
    ))


async def get_event_delivery(session: AsyncSession, event_id: UUID) -> EventDelivery | None:
    event = await session.get(EventOutbox, event_id)
    if event is None:
        return None
    return EventDelivery(id=event.id, status=event.status, payload=deepcopy(event.payload))


async def set_event_delivery(
    session: AsyncSession,
    event_id: UUID,
    status: Literal["failed", "pending", "delivered"],
    *,
    next_attempt_at: datetime | None = None,
) -> bool:
    values: dict[str, object] = {"status": status}
    if next_attempt_at is not None:
        values["next_attempt_at"] = next_attempt_at
    result = await session.execute(
        update(EventOutbox)
        .where(EventOutbox.id == event_id)
        .values(**values)
        .returning(EventOutbox.id)
    )
    return result.scalar_one_or_none() is not None


async def get_source_cursor(session: AsyncSession, source_id: UUID) -> str | None:
    state = await session.get(SourceIngestionState, source_id)
    return state.cursor if state is not None else None


async def cancel_and_purge_source_ingestion(session: AsyncSession, source_id: UUID) -> None:
    run_ids = select(cast(IngestionRun.id, String)).where(IngestionRun.source_id == source_id)
    await session.execute(
        update(EventOutbox)
        .where(EventOutbox.payload["run_id"].astext.in_(run_ids))
        .values(status="failed")
    )
    await session.execute(delete(SourceObservation).where(SourceObservation.source_id == source_id))
    await session.execute(delete(IngestionBatch).where(IngestionBatch.source_id == source_id))
    state = await session.get(SourceIngestionState, source_id, with_for_update=True)
    if state is not None:
        state.lease_run_id = None
        state.lease_expires_at = None
    await session.execute(update(CollectorCredential).where(CollectorCredential.source_id == source_id)
                          .values(revoked_at=datetime.now(UTC)))


async def collector_can_ingest(session: AsyncSession, source_id: UUID, token: str) -> bool:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    credential_valid = bool(await session.scalar(
        select(CollectorCredential.token_hash).where(
            CollectorCredential.token_hash == token_hash,
            CollectorCredential.source_id == source_id,
            CollectorCredential.scope == "ingestion:write",
            CollectorCredential.revoked_at.is_(None),
        )
    ))
    source = await sources.get_connector_source(session, source_id) if credential_valid else None
    return source is not None and source.status == "active"


async def receive_batch(
    session: AsyncSession,
    payload: ReceiveBatch,
    collector_token: str,
) -> tuple[IngestionBatch, IngestionRun]:
    source = await sources.lock_source(session, payload.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.status != "active":
        raise HTTPException(status_code=409, detail="Source is not active")
    if source.generation != payload.source_generation:
        raise HTTPException(status_code=409, detail="Source generation changed during collection")
    token_hash = hashlib.sha256(collector_token.encode()).hexdigest()
    grant_valid = bool(await session.scalar(
        select(CollectorCredential.token_hash).where(
            CollectorCredential.token_hash == token_hash,
            CollectorCredential.source_id == payload.source_id,
            CollectorCredential.scope == "ingestion:write",
            CollectorCredential.revoked_at.is_(None),
        )
    ))
    if not grant_valid:
        raise HTTPException(status_code=401, detail="Collector authentication required")
    from modules.connectors import public as connectors

    if not await connectors.require_batch_fence(
        session,
        ConnectorSource(
            id=source.id,
            type="api",
            status=source.status,
            generation=source.generation,
            configuration={},
        ),
        payload.source_generation,
        payload.connector_revision,
    ):
        raise HTTPException(status_code=409, detail="Connector collection fence is stale or required")

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
    if not await sources.record_collection_started(session, payload.source_id, source.generation, now):
        raise HTTPException(status_code=409, detail="Source is not active")
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
        payload={
            "run_id": str(run.id),
            "stage_id": str(stage.id),
            "source_generation": source.generation,
            **({"connector_revision": payload.connector_revision} if payload.connector_revision is not None else {}),
        },
    )
    await publish_event(session, event)
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
    await commit_with_replay(session, [
        make_source_change(source.id, source.generation, source.status),
        make_ingestion_change(source.id, run.id, run.status, stage.stage_key, stage.status),
    ])
    await session.refresh(batch)
    await session.refresh(run)
    return batch, run


async def receive_connector_batch(
    session: AsyncSession, payload: ReceiveBatch, collector_token: str
) -> Receipt:
    batch, run = await receive_batch(session, payload, collector_token)
    return Receipt(batch_id=batch.id, run_id=run.id, status=run.status)


async def queue_connector_crawl(
    session: AsyncSession,
    source_id: UUID,
    source_generation: int,
    connector_revision: int,
    cursor_before: str | None,
    configuration: dict[str, object],
) -> CrawlReceipt:
    source = await sources.lock_source(session, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.status != "active":
        raise HTTPException(status_code=409, detail="Source is not active")
    from modules.connectors import public as connectors
    from modules.connectors.public import CollectionFence

    if not await connectors.require_collection_fence(
        session,
        ConnectorSource(
            id=source.id,
            type="api",
            status=source.status,
            generation=source.generation,
            configuration={},
        ),
        CollectionFence(
            source_generation=source_generation,
            connector_revision=connector_revision,
        ),
        lock=True,
    ):
        raise HTTPException(status_code=409, detail="Connector collection fence is stale")
    state = await session.get(SourceIngestionState, source_id, with_for_update=True)
    if state is None:
        state = SourceIngestionState(source_id=source_id, cursor=None)
        session.add(state)
        await session.flush()
    if state.cursor != cursor_before:
        raise HTTPException(status_code=409, detail="Collection cursor is stale")

    now = datetime.now(UTC)
    if not await sources.record_collection_started(session, source_id, source.generation, now):
        raise HTTPException(status_code=409, detail="Source is not active")
    minute = now.replace(second=0, microsecond=0).isoformat()
    key = "crawl:" + _digest({"source_id": str(source_id), "cursor": cursor_before, "config": configuration, "minute": minute})
    existing = await session.scalar(
        select(IngestionBatch).where(IngestionBatch.source_id == source_id, IngestionBatch.batch_key == key)
    )
    if existing is not None:
        run = await session.scalar(select(IngestionRun).where(IngestionRun.batch_id == existing.id))
        if run is None:
            raise RuntimeError("Crawl batch has no run")
        return CrawlReceipt(run_id=run.id)
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
            "source_generation": source_generation,
            "connector_revision": connector_revision,
            "run_id": str(run.id),
            "stage_id": str(stage.id),
            "cursor_before": cursor_before,
            "configuration": configuration,
        },
    )
    await publish_event(session, event)
    state.lease_run_id = run.id
    state.lease_expires_at = now + COLLECTION_LEASE
    await commit_with_replay(session, [
        make_source_change(source.id, source.generation, source.status),
        make_ingestion_change(source.id, run.id, run.status, stage.stage_key, stage.status),
    ])
    await session.refresh(run)
    return CrawlReceipt(run_id=run.id)


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
    source = await sources.lock_source(session, source_id)
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
    if not await sources.record_collection_started(session, source_id, source.generation, now):
        raise HTTPException(status_code=409, detail="Source is not active")
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
    stored_document_id = await documents.add_uploaded_document(
        session, source_id, filename[:500] or "Uploaded file", mime_type, raw_uri, metadata, f"file:{digest}", document_id
    )
    event = DomainEvent(
        id=uuid4(),
        type="document.file.uploaded",
        version=1,
        occurred_at=now,
        producer="modules.ingestion",
        payload={"run_id": str(run.id), "stage_id": str(stage.id), "document_id": str(stored_document_id), "raw_uri": raw_uri, "mime_type": mime_type, "source_generation": source.generation},
    )
    await publish_event(session, event)
    await commit_with_replay(session, [
        make_source_change(source.id, source.generation, source.status),
        make_ingestion_change(source.id, run.id, run.status, stage.stage_key, stage.status),
        make_knowledge_change(source_id, stored_document_id, 1),
    ])
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


async def list_source_runs(
    session: AsyncSession,
    source_id: UUID,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> SourceIngestionRead | None:
    """Return detached current and bounded recent runs after source-owner existence check."""
    from modules.ingestion.schemas import SourceIngestionRead

    source = await sources.get_connector_source(session, source_id)
    if source is None:
        return None
    statement = select(IngestionRun).where(IngestionRun.source_id == source_id)
    if cursor:
        created_at, identifier = decode_cursor(cursor)
        statement = statement.where(
            tuple_(IngestionRun.created_at, IngestionRun.id) < (created_at, identifier)
        )
    rows = list((await session.scalars(
        statement.order_by(IngestionRun.created_at.desc(), IngestionRun.id.desc()).limit(limit + 1)
    )).all())
    page_rows = rows[:limit]
    next_cursor = (
        encode_cursor(page_rows[-1].created_at, page_rows[-1].id)
        if len(rows) > limit and page_rows
        else None
    )
    state = await session.get(SourceIngestionState, source_id)
    current = None
    if (
        source.status == "active"
        and state is not None
        and state.lease_run_id is not None
        and state.lease_expires_at is not None
        and state.lease_expires_at > datetime.now(UTC)
    ):
        lease_run = await session.get(IngestionRun, state.lease_run_id)
        if lease_run is not None and lease_run.source_id == source_id and lease_run.status in {"queued", "running"}:
            current = lease_run
    run_rows = list({run.id: run for run in [*page_rows, *([current] if current else [])]}.values())
    stage_rows = list((await session.scalars(
        select(IngestionStage)
        .where(IngestionStage.run_id.in_([run.id for run in run_rows]))
        .order_by(IngestionStage.stage_key)
    )).all()) if run_rows else []
    stages_by_run: dict[UUID, list[StageRead]] = {run.id: [] for run in run_rows}
    for stage in stage_rows:
        stages_by_run[stage.run_id].append(StageRead.model_validate(stage, from_attributes=True))

    def detach(run: IngestionRun) -> RunRead:
        return RunRead(
            run_id=run.id,
            source_id=run.source_id,
            status=run.status,
            stages=stages_by_run[run.id],
            error_code=run.error_code,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    return SourceIngestionRead(
        current_run=detach(current) if current is not None else None,
        items=[detach(run) for run in page_rows],
        next_cursor=next_cursor,
    )


async def retry_run(session: AsyncSession, run_id: UUID) -> IngestionRun | None:
    run_hint = await session.get(IngestionRun, run_id)
    if run_hint is None:
        return None
    # Match source archive and workers: source, run, then stage.
    source = await sources.lock_source(session, run_hint.source_id)
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
    await commit_with_replay(
        session,
        [make_ingestion_change(source.id, run.id, run.status, stage.stage_key, stage.status)],
    )
    await session.refresh(run)
    return run
