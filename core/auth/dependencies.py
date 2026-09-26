import hashlib
import hmac
import time
from datetime import UTC, datetime
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.models import AuthSession
from core.config import Settings
from core.database import get_session

SESSION_COOKIE = "bbd_session"
CSRF_COOKIE = "bbd_csrf"
CSRF_MAX_AGE_SECONDS = 600


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _origin_allowed(origin: str | None, settings: Settings) -> bool:
    return origin is not None and origin.rstrip("/") == str(settings.public_origin).rstrip("/")


def _csrf_signature(token: str, expires_at: int, settings: Settings) -> str:
    secret = settings.csrf_signing_secret.get_secret_value()
    if not secret:
        raise HTTPException(status_code=503, detail="CSRF protection is not configured")
    signed = f"{token}.{expires_at}"
    return hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()


def _valid_csrf(cookie: str | None, submitted: str | None, settings: Settings) -> bool:
    if not cookie or not submitted:
        return False
    try:
        token, expiry, signature = cookie.rsplit(".", 2)
        expires_at = int(expiry)
    except ValueError:
        return False
    now = int(time.time())
    if expires_at <= now or expires_at > now + CSRF_MAX_AGE_SECONDS:
        return False
    return compare_digest(token, submitted) and compare_digest(
        signature, _csrf_signature(token, expires_at, settings)
    )


async def _current_session(
    request: Request,
    session: AsyncSession,
    token: str | None,
) -> AuthSession:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    row = await session.get(AuthSession, _hash(token))
    if row is None or row.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.auth_session = row
    return row


async def require_owner(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthSession:
    return await _current_session(request, session, request.cookies.get(SESSION_COOKIE))


async def require_owner_write(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    origin: Annotated[str | None, Header()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthSession:
    settings: Settings = request.app.state.settings
    if not _origin_allowed(origin, settings):
        raise HTTPException(status_code=403, detail="Origin is not allowed")
    auth_session = await require_owner(request, session)
    if not _valid_csrf(request.cookies.get(CSRF_COOKIE), csrf_token, settings) or not compare_digest(
        auth_session.csrf_hash, _hash(csrf_token or "")
    ):
        raise HTTPException(
            status_code=403,
            detail="CSRF token is invalid",
            headers={"X-CSRF-Error": "invalid"},
        )
    return auth_session
