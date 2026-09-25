from typing import Any, ClassVar, cast

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


async def startup(ctx: dict[str, object]) -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=2)
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["db_engine"] = engine


async def shutdown(ctx: dict[str, object]) -> None:
    engine = ctx.get("db_engine")
    if engine is not None:
        await cast(AsyncEngine, engine).dispose()


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
    functions: ClassVar[list[object]] = [purge_expired_sessions]
    cron_jobs: ClassVar[list[object]] = [cron(purge_expired_sessions, minute=0)]
    redis_settings = RedisSettings.from_dsn(Settings().redis_url)
    max_jobs = 1
    health_check_key = ARQ_WORKER_HEALTH_KEY
    health_check_interval = 15
    on_startup = startup
    on_shutdown = shutdown
