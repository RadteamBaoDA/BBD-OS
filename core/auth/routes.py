import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.models import AuthSession, Owner
from core.auth.schemas import (
    AuthState,
    CsrfResponse,
    LoginRequest,
    SetupRequest,
    SetupResponse,
    SetupStatus,
)
from core.auth.service import hash_password, verify_password
from core.config import Settings
from core.database import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
SESSION_COOKIE = "bbd_session"
CSRF_COOKIE = "bbd_csrf"
CSRF_MAX_AGE_SECONDS = 600


def _is_owner_conflict(exc: IntegrityError) -> bool:
    original: BaseException | None = exc.orig
    while original is not None:
        if (
            getattr(original, "sqlstate", None) == "23505"
            and getattr(original, "constraint_name", None) == "owner_pkey"
        ):
            return True
        original = original.__cause__ or original.__context__
    return False


def get_auth_redis(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)


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


def _new_csrf(settings: Settings) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + CSRF_MAX_AGE_SECONDS
    return token, f"{token}.{expires_at}.{_csrf_signature(token, expires_at, settings)}"


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


def _set_csrf_cookie(request: Request, response: Response, value: str) -> None:
    settings: Settings = request.app.state.settings
    response.set_cookie(
        CSRF_COOKIE,
        value,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
        max_age=CSRF_MAX_AGE_SECONDS,
    )


async def _allow_attempt(request: Request, redis: Redis, action: str) -> None:
    minute = int(time.time() // 60)
    address = request.client.host if request.client else "unknown"
    keys = (f"auth:{action}:ip:{_hash(address)}:{minute}", f"auth:{action}:all:{minute}")
    try:
        pipeline = redis.pipeline(transaction=True)
        for key in keys:
            pipeline.incr(key)
            pipeline.expire(key, 120, nx=True)
        counts = await pipeline.execute()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Authentication is temporarily unavailable") from exc
    per_address, _, global_count, _ = counts
    if per_address > 5 or global_count > 20:
        raise HTTPException(
            status_code=429,
            detail="Too many authentication attempts",
            headers={"Retry-After": str(60 - int(time.time()) % 60)},
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


@router.get("/setup-status", response_model=SetupStatus)
async def setup_status(session: Annotated[AsyncSession, Depends(get_session)]) -> SetupStatus:
    has_owner = await session.scalar(select(Owner.id).limit(1)) is not None
    return SetupStatus(setupRequired=not has_owner)


@router.post("/setup", response_model=SetupResponse, status_code=201)
async def create_owner(
    body: SetupRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_auth_redis)],
    x_setup_token: Annotated[str | None, Header(alias="X-Setup-Token")] = None,
    origin: Annotated[str | None, Header()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> SetupResponse:
    settings: Settings = request.app.state.settings
    configured_token = settings.setup_token.get_secret_value()
    if not configured_token:
        raise HTTPException(status_code=503, detail="Owner setup is not configured")
    if not _origin_allowed(origin, settings):
        raise HTTPException(status_code=403, detail="Origin is not allowed")
    if not x_setup_token or not compare_digest(configured_token, x_setup_token):
        raise HTTPException(status_code=403, detail="Setup token is invalid")
    await _allow_attempt(request, redis, "setup")
    if not _valid_csrf(request.cookies.get(CSRF_COOKIE), csrf_token, settings):
        raise HTTPException(status_code=403, detail="CSRF token is invalid")

    owner = Owner(id=1, password_hash=hash_password(body.password))
    session.add(owner)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_owner_conflict(exc):
            raise HTTPException(status_code=409, detail="Owner is already configured") from exc
        raise
    response.delete_cookie(CSRF_COOKIE, path="/")
    return SetupResponse(created=True)


@router.get("/csrf", response_model=CsrfResponse)
async def csrf(request: Request, response: Response) -> CsrfResponse:
    token, cookie = _new_csrf(request.app.state.settings)
    _set_csrf_cookie(request, response, cookie)
    return CsrfResponse(csrfToken=token)


@router.post("/login", response_model=AuthState)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_auth_redis)],
    origin: Annotated[str | None, Header()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthState:
    settings: Settings = request.app.state.settings
    if not _origin_allowed(origin, settings):
        raise HTTPException(status_code=403, detail="Origin is not allowed")
    await _allow_attempt(request, redis, "login")
    if not _valid_csrf(request.cookies.get(CSRF_COOKIE), csrf_token, settings):
        raise HTTPException(status_code=403, detail="CSRF token is invalid")
    owner = await session.get(Owner, 1)
    if owner is None or not verify_password(owner.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")

    session_token = secrets.token_urlsafe(32)
    next_csrf, csrf_cookie = _new_csrf(settings)
    auth_session = AuthSession(
        token_hash=_hash(session_token),
        owner_id=owner.id,
        csrf_hash=_hash(next_csrf),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_lifetime_hours),
    )
    session.add(auth_session)
    await session.commit()
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
        max_age=settings.session_lifetime_hours * 3600,
    )
    _set_csrf_cookie(request, response, csrf_cookie)
    return AuthState(csrfToken=next_csrf)


@router.get("/session", response_model=AuthState)
async def auth_session(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthState:
    row = await _current_session(request, session, request.cookies.get(SESSION_COOKIE))
    settings: Settings = request.app.state.settings
    existing_cookie = request.cookies.get(CSRF_COOKIE)
    existing_token = existing_cookie.split(".", 1)[0] if existing_cookie and "." in existing_cookie else None
    if (
        existing_token
        and _valid_csrf(existing_cookie, existing_token, settings)
        and compare_digest(row.csrf_hash, _hash(existing_token))
    ):
        csrf_token = existing_token
    else:
        csrf_token, csrf_cookie = _new_csrf(settings)
        row.csrf_hash = _hash(csrf_token)
        await session.commit()
        _set_csrf_cookie(request, response, csrf_cookie)
    return AuthState(csrfToken=csrf_token)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    origin: Annotated[str | None, Header()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    settings: Settings = request.app.state.settings
    if not _origin_allowed(origin, settings):
        raise HTTPException(status_code=403, detail="Origin is not allowed")
    row = await _current_session(request, session, request.cookies.get(SESSION_COOKIE))
    if not _valid_csrf(request.cookies.get(CSRF_COOKIE), csrf_token, settings) or not compare_digest(
        row.csrf_hash, _hash(csrf_token or "")
    ):
        raise HTTPException(status_code=403, detail="CSRF token is invalid")
    await session.delete(row)
    await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
