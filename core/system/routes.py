import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.routes import SESSION_COOKIE, _current_session, get_auth_redis
from core.database import get_session
from core.system.health import PROBE_TIMEOUT_SECONDS, system_health

router = APIRouter(prefix="/api/v1/system", tags=["system"])


async def require_owner(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await _current_session(request, session, request.cookies.get(SESSION_COOKIE))


@router.get("/health")
async def read_system_health(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _owner: Annotated[None, Depends(require_owner)],
    redis: Annotated[Any, Depends(get_auth_redis)],
) -> dict[str, Any]:
    return await system_health(session, redis, request.app.state.settings)


@router.get("/ready", include_in_schema=False)
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), PROBE_TIMEOUT_SECONDS)
    except (SQLAlchemyError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Database is not ready") from exc
    return {"status": "ready"}
