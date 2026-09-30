import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import (
    CSRF_COOKIE,
    CSRF_MAX_AGE_SECONDS,
    SESSION_COOKIE,
    _csrf_signature,
    _current_session,
    _hash,
    _origin_allowed,
    _valid_csrf,
    require_owner_write,
)
from core.auth.google import GOOGLE_CALLBACK_PATH, GOOGLE_ISSUER, google_client
from core.auth.google_schemas import (
    GoogleStartRequest,
    GoogleStartResponse,
    GoogleStatus,
    ReauthenticateRequest,
)
from core.auth.models import AuthSession, GoogleIdentity, Owner
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


def _new_csrf(settings: Settings) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + CSRF_MAX_AGE_SECONDS
    return token, f"{token}.{expires_at}.{_csrf_signature(token, expires_at, settings)}"


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
    if not x_setup_token or not hmac.compare_digest(configured_token, x_setup_token):
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
        reauthenticated_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_lifetime_hours),
    )
    session.add(auth_session)
    await session.commit()
    _issue_auth_session(settings, response, request, session_token, csrf_cookie)
    return AuthState(csrfToken=next_csrf)


def _google_configured(settings: Settings) -> bool:
    return bool(settings.google_client_id and settings.google_client_secret.get_secret_value())


def _require_recent_reauthentication(auth_session: AuthSession) -> None:
    timestamp = auth_session.reauthenticated_at
    age = datetime.now(UTC) - timestamp if timestamp is not None else None
    if age is None or age < timedelta(0) or age > timedelta(minutes=5):
        raise HTTPException(status_code=403, detail="Reauthentication required")


def _google_callback_url(settings: Settings) -> str:
    return f"{str(settings.public_origin).rstrip('/')}{GOOGLE_CALLBACK_PATH}"


@router.get("/google/status", response_model=GoogleStatus)
async def google_status(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GoogleStatus:
    linked = await session.get(GoogleIdentity, 1) is not None
    return GoogleStatus(configured=_google_configured(request.app.state.settings), linked=linked)


@router.post("/reauthenticate", status_code=204)
async def reauthenticate(
    body: ReauthenticateRequest,
    auth_session: Annotated[AuthSession, Depends(require_owner_write)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    owner = await session.get(Owner, auth_session.owner_id)
    if owner is None or not verify_password(owner.password_hash, body.password):
        raise HTTPException(status_code=403, detail="Password is incorrect")
    auth_session.reauthenticated_at = datetime.now(UTC)
    await session.commit()


@router.post("/google/start", response_model=GoogleStartResponse)
async def google_start(
    body: GoogleStartRequest,
    request: Request,
    response: Response,
    redis: Annotated[Redis, Depends(get_auth_redis)],
    session: Annotated[AsyncSession, Depends(get_session)],
    origin: Annotated[str | None, Header()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> GoogleStartResponse:
    settings: Settings = request.app.state.settings
    auth_session: AuthSession | None = None
    if not _google_configured(settings):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    if body.purpose == "login":
        if not _origin_allowed(origin, settings) or not _valid_csrf(
            request.cookies.get(CSRF_COOKIE), csrf_token, settings
        ):
            raise HTTPException(status_code=403, detail="CSRF token is invalid")
        await _allow_attempt(request, redis, "google")
    else:
        auth_session = await require_owner_write(request, session, origin, csrf_token)
        if auth_session is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        _require_recent_reauthentication(auth_session)

    state = secrets.token_urlsafe(32)
    binding = secrets.token_urlsafe(32)
    transaction = {
        "purpose": body.purpose,
        "binding": _hash(binding),
        "owner_id": auth_session.owner_id if auth_session else None,
        "session_hash": auth_session.token_hash if auth_session else None,
    }
    try:
        stored = await redis.set(
            f"auth:google:state:{state}", json.dumps(transaction), ex=300, nx=True
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Authentication is temporarily unavailable") from exc
    if not stored:
        raise HTTPException(status_code=503, detail="Authentication is temporarily unavailable")

    response.set_cookie(
        "bbd_google_binding",
        binding,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=GOOGLE_CALLBACK_PATH,
        max_age=300,
    )
    oauth = google_client(settings)
    authorization = await oauth.google.authorize_redirect(
        request, _google_callback_url(settings), state=state
    )
    return GoogleStartResponse(authorization_url=authorization.headers["location"])


def _issue_auth_session(
    settings: Settings,
    response: Response,
    request: Request,
    session_token: str,
    csrf_cookie: str,
) -> None:
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


@router.get("/google/callback")
async def google_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_auth_redis)],
) -> Response:
    settings: Settings = request.app.state.settings
    state = request.query_params.get("state", "")
    try:
        raw_transaction = (
            await redis.getdel(f"auth:google:state:{state}")
            if state and len(state) <= 256
            else None
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Authentication is temporarily unavailable") from exc
    try:
        transaction = json.loads(raw_transaction) if raw_transaction else None
    except json.JSONDecodeError:
        transaction = None
    binding = request.cookies.get("bbd_google_binding", "")
    response = Response(status_code=303)
    response.headers["location"] = "/login?google=error"
    if isinstance(transaction, dict) and transaction.get("purpose") == "link":
        response.headers["location"] = "/settings/account?google=error"
    response.delete_cookie("bbd_google_binding", path=GOOGLE_CALLBACK_PATH)
    if (
        not isinstance(transaction, dict)
        or transaction.get("purpose") not in {"login", "link"}
        or not isinstance(transaction.get("binding"), str)
        or not binding
        or not hmac.compare_digest(transaction["binding"], _hash(binding))
        or not _google_configured(settings)
    ):
        return response

    try:
        token = await google_client(settings).google.authorize_access_token(request)
    except Exception:
        return response
    userinfo = token.get("userinfo")
    if (
        not userinfo
        or userinfo.get("iss") != GOOGLE_ISSUER
        or not isinstance(userinfo.get("sub"), str)
        or userinfo.get("email_verified") is not True
        or not isinstance(userinfo.get("email"), str)
    ):
        return response

    identity = await session.get(GoogleIdentity, 1)
    if transaction["purpose"] == "login":
        if identity is None or identity.issuer != GOOGLE_ISSUER or identity.subject != userinfo["sub"]:
            return response
        owner_id = identity.owner_id
        reauthenticated_at = datetime.now(UTC)
        response.headers["location"] = "/app"
    else:
        old_token = request.cookies.get(SESSION_COOKIE, "")
        auth_session = await _current_session(request, session, old_token)
        _require_recent_reauthentication(auth_session)
        if (
            auth_session.owner_id != transaction["owner_id"]
            or auth_session.token_hash != transaction["session_hash"]
        ):
            return response
        if identity and (identity.issuer != GOOGLE_ISSUER or identity.subject != userinfo["sub"]):
            return response
        if identity is None:
            identity = GoogleIdentity(
                owner_id=auth_session.owner_id,
                issuer=GOOGLE_ISSUER,
                subject=userinfo["sub"],
                email=userinfo["email"],
            )
            session.add(identity)
        else:
            identity.email = userinfo["email"]
        owner_id = auth_session.owner_id
        reauthenticated_at = auth_session.reauthenticated_at
        await session.delete(auth_session)
        response.headers["location"] = "/settings/account?google=linked"

    session_token = secrets.token_urlsafe(32)
    csrf_token, csrf_cookie = _new_csrf(settings)
    session.add(
        AuthSession(
            token_hash=_hash(session_token),
            owner_id=owner_id,
            csrf_hash=_hash(csrf_token),
            reauthenticated_at=reauthenticated_at,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.session_lifetime_hours),
        )
    )
    await session.commit()
    _issue_auth_session(settings, response, request, session_token, csrf_cookie)
    return response


@router.post("/google/unlink", status_code=204)
async def google_unlink(
    auth_session: Annotated[AuthSession, Depends(require_owner_write)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    _require_recent_reauthentication(auth_session)
    identity = await session.get(GoogleIdentity, auth_session.owner_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Google account is not linked")
    owner = await session.get(Owner, auth_session.owner_id)
    if owner is None or not owner.password_hash:
        raise HTTPException(status_code=409, detail="Cannot remove the last sign-in method")
    await session.delete(identity)
    await session.commit()


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
        and hmac.compare_digest(row.csrf_hash, _hash(existing_token))
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
    _auth_session: Annotated[AuthSession, Depends(require_owner_write)],
) -> None:
    await session.delete(_auth_session)
    await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
