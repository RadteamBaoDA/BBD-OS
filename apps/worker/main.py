import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, cast
from uuid import UUID

from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.auth.models import AuthSession
from core.config import Settings
from core.system.health import ARQ_WORKER_HEALTH_KEY
from modules.ingestion.dispatcher import dispatch_pending_work, mark_event_delivered
from modules.ingestion.models import (
    COLLECTION_LEASE,
    EventOutbox,
    IngestionRun,
    IngestionStage,
    SourceIngestionState,
    SourceObservation,
)
from modules.ingestion.worker import cleanup_storage_orphans, process_uploaded_file
from modules.sources.models import Source

logger = logging.getLogger("bbd.worker")
STAGE_TIMEOUT_SECONDS = 120
MAX_STAGE_ATTEMPTS = 5


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
        await session.scalar(select(Source).where(Source.id == run_hint.source_id).with_for_update())
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
        state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
        if state is not None and state.lease_run_id == run.id:
            state.lease_run_id = None
            state.lease_expires_at = None
        logger.warning("Ingestion stage failed run_id=%s stage_id=%s error_code=%s", run.id, stage.id, error_code)
        await session.commit()


async def startup(ctx: dict[str, object]) -> None:
    settings = Settings()
    ctx["settings"] = settings
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=2)
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["db_engine"] = engine


async def shutdown(ctx: dict[str, object]) -> None:
    engine = ctx.get("db_engine")
    if engine is not None:
        await cast(AsyncEngine, engine).dispose()


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
        source = await session.scalar(select(Source).where(Source.id == run_hint.source_id).with_for_update())
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        stage = await session.scalar(
            select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
        )
        if stage is None or run is None:
            event.status = "failed"
            await session.commit()
            return
        if source is None or source.status != "active":
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
            source = await session.scalar(
                select(Source).where(Source.id == run_hint.source_id).with_for_update()
            )
            run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
            stage = await session.scalar(
                select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
            )
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            if source is None or source.status != "active":
                if stage is not None:
                    stage.status = "failed"
                    stage.error_code = "source_unavailable"
                if run is not None:
                    run.status = "failed"
                    run.error_code = "source_unavailable"
                if event is not None:
                    event.status = "failed"
                state = await session.get(SourceIngestionState, run_hint.source_id, with_for_update())
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
            delay = random.uniform(0.5, min(60.0, 2.0 ** attempt))
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
        source = await session.scalar(select(Source).where(Source.id == run_hint.source_id).with_for_update())
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        stage = await session.scalar(
            select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
        )
        if stage is None or run is None:
            return
        if source is None or source.status != "active":
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
        state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
        if state is not None and state.lease_run_id == run.id:
            state.lease_run_id = None
            state.lease_expires_at = None
        logger.info("Ingestion stage completed run_id=%s stage_id=%s", run.id, stage.id)
        await session.commit()
        await mark_event_delivered(session, identifier)


async def purge_expired_sessions(ctx: dict[str, object]) -> int:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    async with factory() as session:
        expired = (
            select(AuthSession.token_hash)
            .where(AuthSession.expires_at <= func.now())
            .order_by(AuthSession.expires_at)
            .limit(1000)
        )
        result = cast(
            CursorResult[Any],
            await session.execute(delete(AuthSession).where(AuthSession.token_hash.in_(expired))),
        )
        await session.commit()
        return result.rowcount or 0


class WorkerSettings:
    functions: ClassVar[list[object]] = [purge_expired_sessions, process_ingestion_event, process_uploaded_file]
    cron_jobs: ClassVar[list[object]] = [
        cron(purge_expired_sessions, minute=0),
        cron(cleanup_storage_orphans, minute=set(range(0, 60, 5))),
        cron(dispatch_pending_work, second=set(range(0, 60, 5)), run_at_start=True),
    ]
    redis_settings = RedisSettings.from_dsn(Settings().redis_url)
    max_jobs = 1
    max_tries = 5
    job_timeout = 120
    health_check_key = ARQ_WORKER_HEALTH_KEY
    health_check_interval = 15
    on_startup = startup
    on_shutdown = shutdown
