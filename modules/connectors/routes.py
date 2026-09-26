from typing import Annotated, Any
from uuid import UUID
import hashlib

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from modules.connectors.public import (
    ConnectorConfig,
    ConnectorPreview,
    ConnectorRecord,
    ConnectorReceipt,
    CrawlRequest,
    CrawlResult,
    RSSRequest,
    validate_public_url,
)
from modules.connectors import registry
from modules.ingestion import public as ingestion
from modules.ingestion.models import SourceIngestionState
from modules.ingestion.schemas import Receipt, ReceiveBatch
from modules.sources.models import Source

router = APIRouter(prefix="/api/v1/connectors/sources", tags=["connectors"])
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


class ConnectorState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    type: str
    timezone: str
    url: str
    configuration: dict[str, Any]
    cursor_before: str | None
    catch_up_since: str | None


async def _source(session: AsyncSession, source_id: UUID) -> Source:
    source = await session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


async def _collector(
    session: AsyncSession, source_id: UUID, authorization: str | None
) -> None:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not await ingestion.collector_can_ingest(
        session, source_id, token
    ):
        raise HTTPException(status_code=401, detail="Source collector authentication required")


@router.put("/{source_id}/configuration", response_model=ConnectorState)
async def configure_source(
    source_id: UUID, payload: ConnectorConfig, session: Session, _owner: OwnerWrite
) -> ConnectorState:
    source = await _source(session, source_id)
    if source.type not in registry.SUPPORTED_TYPES:
        raise HTTPException(status_code=422, detail="This source type has no packaged connector")
    source.configuration = payload.model_dump(mode="json", exclude_none=True)
    try:
        data = registry.validate(source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        await validate_public_url(data["url"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(source)
    return ConnectorState(**registry.sync(source, None))


@router.post("/{source_id}/validate", response_model=ConnectorState)
async def validate_source(
    source_id: UUID,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> ConnectorState:
    await _collector(session, source_id, authorization)
    source = await _source(session, source_id)
    try:
        data = registry.validate(source)
        await validate_public_url(data["url"])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    state = await session.get(SourceIngestionState, source_id)
    cursor = state.cursor if state else None
    return ConnectorState(**registry.sync(source, cursor))


@router.get("/{source_id}/rss", response_model=ConnectorPreview)
async def preview_rss(
    source_id: UUID,
    session: Session,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ConnectorPreview:
    await _collector(session, source_id, authorization)
    source = await _source(session, source_id)
    try:
        data = registry.validate(source)
        if source.type != "rss":
            raise ValueError("RSS/Atom source required")
        await validate_public_url(data["url"])
        state = await session.get(SourceIngestionState, source_id)
        cursor = state.cursor if state else None
        settings = request.app.state.settings
        token = settings.browser_shared_token.get_secret_value()
        if not token:
            raise HTTPException(status_code=503, detail="Browser collector is not configured")
        async with httpx.AsyncClient(timeout=65) as client:
            response = await client.post(
                f"{str(settings.browser_service_url).rstrip('/')}/rss",
                json=RSSRequest(url=data["url"], cursor=cursor).model_dump(mode="json"),
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
        result = response.json()
        return ConnectorPreview.model_validate(result)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=422, detail="RSS source could not be collected") from exc


@router.post("/{source_id}/sync", response_model=Receipt, status_code=202)
async def receive_connector_batch(
    source_id: UUID,
    payload: ConnectorReceipt,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> Receipt:
    await _collector(session, source_id, authorization)
    source = await _source(session, source_id)
    try:
        registry.validate(source)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    batch = ReceiveBatch(
        source_id=source_id,
        batch_key="connector:" + hashlib.sha256(
            payload.model_dump_json().encode()
        ).hexdigest(),
        cursor_before=payload.cursor_before,
        cursor_after=payload.cursor_after,
        records=[record.model_dump() for record in payload.records],
    )
    stored_batch, run = await ingestion.receive_batch(session, batch)
    return Receipt(batch_id=stored_batch.id, run_id=run.id, status=run.status)


@router.post("/{source_id}/crawl", response_model=CrawlResult, status_code=202)
async def submit_crawl(
    source_id: UUID,
    payload: CrawlRequest,
    session: Session,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> CrawlResult:
    await _collector(session, source_id, authorization)
    settings = request.app.state.settings
    source = await _source(session, source_id)
    if source.type != "web" or source.status != "active":
        raise HTTPException(status_code=409, detail="Active web source required")
    try:
        config = registry.configuration(source)
        if config.url is None:
            raise ValueError("Web connector URL is required")
        url = await validate_public_url(str(config.url))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid or unsafe source URL") from exc
    if payload.source_id != source_id or str(payload.url) != url:
        raise HTTPException(status_code=422, detail="Crawl target must match the configured source URL")
    if payload.mode != ("playwright" if config.js_render else "http"):
        raise HTTPException(status_code=422, detail="Crawl mode must match the configured source")
    if (
        payload.max_pages > config.max_pages
        or payload.max_depth > config.max_depth
        or payload.timeout_seconds > config.timeout_seconds
    ):
        raise HTTPException(status_code=422, detail="Crawl request exceeds the configured source budget")
    if not settings.browser_shared_token.get_secret_value():
        raise HTTPException(status_code=503, detail="Browser collector is not configured")
    try:
        async with httpx.AsyncClient(timeout=payload.timeout_seconds + 5) as client:
            response = await client.post(
                f"{str(settings.browser_service_url).rstrip('/')}/crawl",
                json=payload.model_dump(mode="json"),
                headers={"Authorization": f"Bearer {settings.browser_shared_token.get_secret_value()}"},
            )
            response.raise_for_status()
            records = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Browser collection failed") from exc
    state = await session.get(SourceIngestionState, source_id)
    cursor = state.cursor if state else None
    try:
        normalized = [ConnectorRecord.model_validate(record) for record in records]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Browser collector returned invalid records") from exc
    if not normalized:
        raise HTTPException(status_code=422, detail="Browser job returned no pages")
    cursor_after = max(
        (record.observed_at.isoformat() for record in normalized), default=cursor or ""
    )
    payload_json = "|".join(
        f"{record.provider_id}:{record.observed_at.isoformat()}:{record.content}" for record in normalized
    )
    receipt = ReceiveBatch(
        source_id=source_id,
        batch_key="crawl:" + hashlib.sha256(payload_json.encode()).hexdigest(),
        cursor_before=cursor,
        cursor_after=cursor_after or None,
        records=[record.model_dump() for record in normalized],
    )
    _, run = await ingestion.receive_batch(session, receipt)
    return CrawlResult(run_id=run.id)
