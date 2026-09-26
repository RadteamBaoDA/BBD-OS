import asyncio
import random
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, cast
from uuid import UUID

from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
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
    EventOutbox,
    IngestionRun,
    IngestionStage,
    SourceIngestionState,
    SourceObservation,
)
from modules.sources.models import Source


async def startup(ctx: dict[str, object]) -> None:
    settings = Settings()
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
        stage = await session.scalar(
            select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
        )
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        if stage is None or run is None:
            event.status = "failed"
            await session.commit()
            return
        source = await session.scalar(select(Source).where(Source.id == run.source_id).with_for_update())
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
            await session.commit()
            return
        now = datetime.now(UTC)
        if stage.status == "succeeded":
            await mark_event_delivered(session, identifier)
            return
        if stage.status == "running" and stage.lease_expires_at and stage.lease_expires_at > now:
            return
        stage.status = "running"
        stage.attempts += 1
        stage.lease_expires_at = now + timedelta(seconds=120)
        stage.error_code = None
        run.status = "running"
        await session.commit()

    try:
        # Stage work is deliberately bounded; later ingestion tasks add extraction consumers.
        async with asyncio.timeout(120):
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
    except (TimeoutError, OSError, RuntimeError) as exc:
        async with factory() as session:
            stage = await session.scalar(
                select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
            )
            run = await session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            event = await session.get(EventOutbox, identifier, with_for_update=True)
            if stage is None or run is None or event is None:
                return
            attempt = stage.attempts
            if attempt >= 5:
                stage.status = "failed"
                stage.error_code = "stage_failed"
                run.status = "failed"
                run.error_code = "stage_failed"
                event.status = "failed"
                state = await session.get(SourceIngestionState, run.source_id, with_for_update=True)
                if state is not None and state.lease_run_id == run.id:
                    state.lease_run_id = None
                    state.lease_expires_at = None
                await session.commit()
                return
            delay = random.uniform(0.5, min(60.0, 2.0 ** attempt))
            stage.status = "retrying"
            stage.error_code = "transient_failure"
            stage.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            stage.lease_expires_at = None
            run.status = "queued"
            event.status = "pending"
            event.next_attempt_at = stage.next_attempt_at
            await session.commit()
        raise Retry(defer=delay) from exc

    async with factory() as session:
        stage = await session.scalar(
            select(IngestionStage).where(IngestionStage.id == stage_id).with_for_update()
        )
        run = await session.scalar(select(IngestionRun).where(IngestionRun.id == run_id).with_for_update())
        if stage is None or run is None:
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
    functions: ClassVar[list[object]] = [purge_expired_sessions, process_ingestion_event]
    cron_jobs: ClassVar[list[object]] = [
        cron(purge_expired_sessions, minute=0),
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
