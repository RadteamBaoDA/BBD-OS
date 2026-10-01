from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import cast
from uuid import UUID

import httpx
from arq import Retry
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.storage import cleanup_orphaned_files, storage_path
from modules.connectors.public import ConnectorRecord
from modules.ingestion.dispatcher import mark_event_delivered
from modules.ingestion.models import (
    COLLECTION_LEASE,
    EventOutbox,
    IngestionBatch,
    IngestionRun,
    IngestionStage,
    SourceIngestionState,
    SourceObservation,
)
from modules.ingestion.parsers import parse_file_bounded
from modules.knowledge.documents import public as documents
from modules.sources import public as sources
from core.chunking import chunk_text

logger = logging.getLogger("bbd.worker")
STAGE_TIMEOUT_SECONDS = 120
MAX_STAGE_ATTEMPTS = 5


class ConnectorRetryError(OSError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, min(60.0, float(value)))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            return max(0.0, min(60.0, (target - datetime.now(UTC)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return None


async def _collect_web_job(
    ctx: dict[str, object],
    factory: async_sessionmaker[AsyncSession],
    event: EventOutbox,
    run_id: UUID,
    stage_id: UUID,
) -> None:
    settings = cast(Settings, ctx["settings"])
    config = cast(dict[str, object], event.payload["configuration"])
    token = settings.browser_shared_token.get_secret_value()
    if not token:
        raise ValueError("Browser collector is not configured")
    payload = {
        "source_id": str(event.payload["source_id"]),
        "url": config["url"],
        "mode": config["mode"],
        "max_pages": config["max_pages"],
        "max_depth": config["max_depth"],
        "timeout_seconds": config["timeout_seconds"],
    }
    try:
        async with httpx.AsyncClient(timeout=int(config["timeout_seconds"]) + 5) as client:
            response = await client.post(
                f"{str(settings.browser_service_url).rstrip('/')}/crawl",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code in {408, 425, 429} or response.status_code >= 500:
                raise ConnectorRetryError(
                    f"Browser collector returned HTTP {response.status_code}",
                    _retry_after_seconds(response),
                )
            if response.status_code >= 400:
                raise ValueError(f"Browser collector rejected the job with HTTP {response.status_code}")
    except httpx.TimeoutException as exc:
        raise TimeoutError("Browser collection timed out") from exc
    except httpx.NetworkError as exc:
        raise OSError("Browser collection transport failed") from exc
    try:
        raw_records = response.json()
        records = [ConnectorRecord.model_validate(item) for item in raw_records]
    except (TypeError, ValueError) as exc:
        raise ValueError("Browser collector returned invalid records") from exc
    if not records or len(records) > 500:
        raise ValueError("Browser job returned no pages or too many records")

    observed_at = event.occurred_at
    canonical_records = []
    for record in records:
        data = record.model_dump(mode="json")
        data["observed_at"] = observed_at.isoformat()
        canonical_records.append(data)
    payload_hash = hashlib.sha256(
        json.dumps(canonical_records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    async with factory() as session:
        source_id = UUID(str(event.payload["source_id"]))
        source = await sources.lock_source(session, source_id)
        source_view = await sources.get_connector_source(session, source_id)
        from modules.connectors import public as connectors

        event_revision = event.payload.get("connector_revision")
        fence_current = bool(
            source_view is not None
            and await connectors.require_batch_fence(
                session,
                source_view,
                int(event.payload.get("source_generation", -1)),
                event_revision if isinstance(event_revision, int) else None,
            )
        )
        run = await session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id, IngestionRun.source_id == source_id).with_for_update()
        )
        stage = await session.scalar(select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update())
        state = await session.get(SourceIngestionState, source_id, with_for_update=True)
        batch = await session.scalar(select(IngestionBatch).where(IngestionBatch.id == run.batch_id)) if run else None
        if (
            source is None or source.status != "active"
            or source.generation != int(event.payload.get("source_generation", -1))
            or not fence_current
            or run is None or stage is None or batch is None
            or state is None or state.lease_run_id != run.id
        ):
            raise ValueError("Crawl job is no longer active")

        observations = []
        for data in canonical_records:
            record_hash = hashlib.sha256(
                json.dumps(
                    {"version": data.get("version"), "content": data["content"], "metadata": data["metadata"]},
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            observations.append(
                {
                    "source_id": source_id,
                    "batch_id": batch.id,
                    "provider_id": data["provider_id"],
                    "record_hash": record_hash,
                    "payload": data,
                    "observed_at": observed_at,
                }
            )
        await session.execute(
            pg_insert(SourceObservation)
            .values(observations)
            .on_conflict_do_nothing(constraint="uq_source_observations_batch_record_observed")
        )
        batch.payload_hash = payload_hash
        cursor_after = observed_at.isoformat()
        if state.cursor:
            try:
                prior_cursor = datetime.fromisoformat(state.cursor.replace("Z", "+00:00"))
                if prior_cursor.tzinfo is not None and prior_cursor > observed_at:
                    cursor_after = state.cursor
            except ValueError:
                pass
        state.cursor = cursor_after
        await session.commit()


async def _fail_ingestion_stage(
    factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
    run_id: UUID,
    stage_id: UUID,
    error_code: str,
) -> None:
    async with factory() as session:
        run_hint = await session.get(IngestionRun, run_id)
        if run_hint is None:
            event = await session.get(EventOutbox, event_id, with_for_update=True)
            if event is not None:
                event.status = "failed"
                await session.commit()
            return
        source = await sources.lock_source(session, run_hint.source_id)
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        stage = await session.scalar(
            select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
        )
        event = await session.get(EventOutbox, event_id, with_for_update=True)
        if stage is None or run is None or event is None:
            return
        stage.status = "failed"
        stage.error_code = error_code
        stage.lease_expires_at = None
        run.status = "failed"
        run.error_code = error_code
        event.status = "failed"
        if source is not None:
            await sources.record_collection_result(
                session,
                source.id,
                int(event.payload.get("source_generation", source.generation)),
                datetime.now(UTC),
                error_code,
            )
        state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
        if state is not None and state.lease_run_id == run.id:
            state.lease_run_id = None
            state.lease_expires_at = None
        logger.warning("Ingestion stage failed run_id=%s stage_id=%s error_code=%s", run.id, stage.id, error_code)
        await session.commit()


async def process_ingestion_event(ctx: dict[str, object], event_id: str) -> None:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    identifier = UUID(event_id)
    async with factory() as session:
        event = await session.get(EventOutbox, identifier)
        if event is None or event.status == "delivered":
            return
        run_id = UUID(str(event.payload["run_id"]))
        stage_id = UUID(str(event.payload["stage_id"]))
        run_hint = await session.get(IngestionRun, run_id)
        if run_hint is None:
            event.status = "failed"
            await session.commit()
            return
        source = await sources.lock_source(session, run_hint.source_id)
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        stage = await session.scalar(
            select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
        )
        if stage is None or run is None:
            event.status = "failed"
            await session.commit()
            return
        if (
            source is None or source.status != "active"
            or source.generation != int(event.payload.get("source_generation", source.generation))
        ):
            stage.status = "failed"
            stage.error_code = "source_unavailable"
            run.status = "failed"
            run.error_code = "source_unavailable"
            event.status = "failed"
            state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
            if state is not None and state.lease_run_id == run.id:
                state.lease_run_id = None
                state.lease_expires_at = None
            logger.warning("Ingestion stage rejected run_id=%s stage_id=%s source unavailable", run.id, stage.id)
            await session.commit()
            return
        now = datetime.now(UTC)
        if stage.status == "succeeded":
            await mark_event_delivered(session, identifier)
            return
        if stage.status == "running" and stage.lease_expires_at and stage.lease_expires_at > now:
            return
        state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
        if (
            state is None
            or state.lease_run_id != run.id
            or state.lease_expires_at is None
            or state.lease_expires_at <= now
        ):
            stage.status = "failed"
            stage.error_code = "lease_expired"
            run.status = "failed"
            run.error_code = "lease_expired"
            event.status = "failed"
            if state is not None and state.lease_run_id == run.id:
                state.lease_run_id = None
                state.lease_expires_at = None
            logger.warning("Ingestion stage rejected run_id=%s stage_id=%s lease expired", run.id, stage.id)
            await session.commit()
            return
        stage.status = "running"
        stage.attempts += 1
        stage.lease_expires_at = now + timedelta(seconds=STAGE_TIMEOUT_SECONDS)
        state.lease_expires_at = now + COLLECTION_LEASE
        stage.error_code = None
        run.status = "running"
        logger.info("Ingestion stage started run_id=%s stage_id=%s attempt=%s", run.id, stage.id, stage.attempts)
        await session.commit()

    try:
        # Stage work is deliberately bounded; later ingestion tasks add extraction consumers.
        async with asyncio.timeout(STAGE_TIMEOUT_SECONDS):
            if event.type == "connector.crawl.requested":
                await _collect_web_job(ctx, factory, event, run_id, stage_id)
            async with factory() as session:
                observed = await session.scalar(
                    select(func.count()).select_from(SourceObservation).where(
                        SourceObservation.batch_id == (await session.scalar(
                            select(IngestionRun.batch_id).where(IngestionRun.id == run_id)
                        ))
                    )
                )
                if not observed:
                    raise RuntimeError("Accepted ingestion batch has no observations")
    except (TimeoutError, OSError, OperationalError) as exc:
        async with factory() as session:
            run_hint = await session.get(IngestionRun, run_id)
            if run_hint is None:
                return
            source = await sources.lock_source(session, run_hint.source_id)
            run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
            stage = await session.scalar(
                select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
            )
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            if (
                source is None or source.status != "active" or event is None
                or source.generation != int(event.payload.get("source_generation", -1))
            ):
                if stage is not None:
                    stage.status = "failed"
                    stage.error_code = "source_unavailable"
                if run is not None:
                    run.status = "failed"
                    run.error_code = "source_unavailable"
                if event is not None:
                    event.status = "failed"
                state = await session.get(SourceIngestionState, run_hint.source_id, with_for_update=True)
                if state is not None and state.lease_run_id == run_id:
                    state.lease_run_id = None
                    state.lease_expires_at = None
                await session.commit()
                return
            if stage is None or run is None or event is None:
                return
            attempt = stage.attempts
            if attempt >= MAX_STAGE_ATTEMPTS:
                await session.rollback()
                await _fail_ingestion_stage(factory, identifier, run_id, stage_id, "retry_exhausted")
                return
            delay = (
                max(0.5, exc.retry_after)
                if isinstance(exc, ConnectorRetryError) and exc.retry_after is not None
                else random.uniform(0.5, min(60.0, 2.0 ** attempt))
            )
            stage.status = "retrying"
            stage.error_code = "transient_failure"
            stage.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            stage.lease_expires_at = None
            run.status = "queued"
            event.status = "pending"
            event.next_attempt_at = stage.next_attempt_at
            state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
            if state is not None and state.lease_run_id == run.id:
                state.lease_expires_at = datetime.now(UTC) + COLLECTION_LEASE
            logger.warning(
                "Ingestion stage retry scheduled run_id=%s stage_id=%s attempt=%s",
                run.id,
                stage.id,
                attempt,
            )
            await session.commit()
        raise Retry(defer=delay) from exc
    except Exception:
        await _fail_ingestion_stage(factory, identifier, run_id, stage_id, "stage_failed")
        return

    async with factory() as session:
        run_hint = await session.get(IngestionRun, run_id)
        if run_hint is None:
            return
        source = await sources.lock_source(session, run_hint.source_id)
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        stage = await session.scalar(
            select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
        )
        if stage is None or run is None:
            return
        if source is None or source.status != "active" or source.generation != int(event.payload.get("source_generation", -1)):
            stage.status = "failed"
            stage.error_code = "source_unavailable"
            run.status = "failed"
            run.error_code = "source_unavailable"
            state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
            if state is not None and state.lease_run_id == run.id:
                state.lease_run_id = None
                state.lease_expires_at = None
            await session.commit()
            return
        stage.status = "succeeded"
        stage.error_code = None
        stage.lease_expires_at = None
        run.status = "succeeded"
        run.error_code = None
        await sources.record_collection_result(
            session,
            source.id,
            int(event.payload.get("source_generation", source.generation)),
            datetime.now(UTC),
            None,
        )
        state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
        if state is not None and state.lease_run_id == run.id:
            state.lease_run_id = None
            state.lease_expires_at = None
        logger.info("Ingestion stage completed run_id=%s stage_id=%s", run.id, stage.id)
        await session.commit()
        await mark_event_delivered(session, identifier)


async def process_uploaded_file(ctx: dict[str, object], event_id: str) -> None:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    settings = cast(Settings, ctx["settings"])
    identifier = UUID(event_id)
    async with factory() as session:
        event = await session.get(EventOutbox, identifier)
        if event is None or event.status == "delivered":
            return
        run_id = UUID(str(event.payload["run_id"]))
        stage_id = UUID(str(event.payload["stage_id"]))
        document_id = UUID(str(event.payload["document_id"]))
        run_hint = await session.get(IngestionRun, run_id)
        if run_hint is None:
            event.status = "failed"
            await session.commit()
            return
        source_id = run_hint.source_id
        # Match source archive/retry order: source, run, stage, then document.
        source = await sources.lock_source(session, source_id)
        run = await session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id, IngestionRun.source_id == source_id).with_for_update()
        )
        stage = await session.scalar(select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update())
        document_exists = await documents.lock_document_for_extraction(session, document_id, source_id)
        if (
            stage is None or run is None or not document_exists or source is None
            or source.status != "active"
            or source.generation != int(event.payload.get("source_generation", source.generation))
        ):
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
        await documents.set_extraction_status(session, document_id, source_id, "processing")
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
            source = await sources.lock_source(session, source_id)
            run = await session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id, IngestionRun.source_id == source_id).with_for_update()
            )
            stage = await session.scalar(select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update())
            if (
                source is None or source.status != "active"
                or source.generation != int(event.payload.get("source_generation", -1))
                or run is None or stage is None
            ):
                if stage is not None:
                    stage.status = "failed"
                    stage.error_code = "source_unavailable"
                if run is not None:
                    run.status = "failed"
                    run.error_code = "source_unavailable"
                event = await session.get(EventOutbox, identifier, with_for_update=True)
                if event is not None:
                    event.status = "failed"
                await session.commit()
                return
            document_id = await documents.save_extraction(
                session,
                document_id,
                source_id,
                parsed.text,
                [
                    {"content": draft.content, "token_count": draft.token_count, "metadata": draft.metadata}
                    for draft in drafts
                ],
                extraction_status,
                parsed.metadata,
                parsed.warnings,
                "p02-t2-v1",
            )
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            if document_id is None or stage is None or run is None or event is None:
                return
            stage.status = "succeeded"
            stage.result_count = len(drafts)
            stage.lease_expires_at = None
            stage.error_code = None
            run.status = extraction_status if extraction_status == "needs_ocr" else "succeeded"
            run.error_code = None
            event.status = "delivered"
            await sources.record_processing_result(session, source_id, source.generation, datetime.now(UTC), None)
            await session.commit()
    except Exception as exc:
        async with factory() as session:
            source = await sources.lock_source(session, source_id)
            run = await session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id, IngestionRun.source_id == source_id).with_for_update()
            )
            stage = await session.scalar(select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update())
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            if (
                event is None or source is None or source.status != "active"
                or source.generation != int(event.payload.get("source_generation", -1))
            ):
                if event is not None:
                    event.status = "failed"
                await session.commit()
                return
            if stage is not None:
                stage.status = "failed"
                stage.error_code = "parser_timeout" if isinstance(exc, TimeoutError) else "parse_failed"
                stage.lease_expires_at = None
            if run is not None:
                run.status = "failed"
                run.error_code = "parser_timeout" if isinstance(exc, TimeoutError) else "parse_failed"
            await documents.set_extraction_status(session, document_id, source_id, "failed")
            if source is not None:
                code = "parser_timeout" if isinstance(exc, TimeoutError) else "parse_failed"
                await sources.record_processing_result(session, source_id, source.generation, datetime.now(UTC), code)
            if event is not None:
                event.status = "failed"
            await session.commit()


async def cleanup_storage_orphans(ctx: dict[str, object]) -> int:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    settings = cast(Settings, ctx["settings"])
    async with factory() as session:
        referenced = await documents.raw_uris(session)
    return cleanup_orphaned_files(settings.data_dir, referenced, settings.storage_orphan_grace_seconds)
