from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.ingestion.models import EventOutbox

DISPATCH_STALE_AFTER = timedelta(seconds=30)


async def dispatch_pending_work(ctx: dict[str, object]) -> int:
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    redis = cast(ArqRedis, ctx["redis"])
    now = datetime.now(UTC)
    async with factory() as session:
        events = list(
            (
                await session.scalars(
                    select(EventOutbox)
                    .where(
                        or_(
                            and_(EventOutbox.status == "pending", EventOutbox.next_attempt_at <= now),
                            and_(
                                EventOutbox.status == "queued",
                                EventOutbox.dispatched_at < now - DISPATCH_STALE_AFTER,
                            ),
                        )
                    )
                    .order_by(EventOutbox.created_at)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        enqueued = 0
        for event in events:
            await redis.enqueue_job(
                "process_ingestion_event",
                str(event.id),
                _job_id=f"ingestion:{event.id}",
                _defer_until=now,
            )
            event.status = "queued"
            event.dispatched_at = now
            enqueued += 1
        if events:
            await session.commit()
        return enqueued


async def mark_event_delivered(session: AsyncSession, event_id: UUID) -> None:
    event = await session.get(EventOutbox, event_id, with_for_update=True)
    if event is not None:
        event.status = "delivered"
        await session.commit()
