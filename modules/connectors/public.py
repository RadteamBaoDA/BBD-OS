from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from socket import getaddrinfo
from urllib.parse import urlsplit
from uuid import UUID
import asyncio

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from modules.sources.schemas import ConnectorSource, SourceFence
from modules.connectors.models import ConnectorProvisioning

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_OVERLAP = timedelta(days=1)


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl | None = None
    feed_url: HttpUrl | None = None
    js_render: bool = False
    max_pages: int = Field(default=10, ge=1, le=10)
    max_depth: int = Field(default=2, ge=0, le=2)
    timeout_seconds: int = Field(default=60, ge=1, le=60)
    items_path: str | None = Field(default=None, max_length=256)
    id_field: str | None = Field(default=None, max_length=128)
    title_field: str | None = Field(default=None, max_length=128)
    content_field: str | None = Field(default=None, max_length=128)
    updated_field: str | None = Field(default=None, max_length=128)
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class ConnectorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=1_000_000)
    observed_at: datetime
    version: str | None = Field(default=None, max_length=255)
    metadata: dict[str, object] = Field(default_factory=dict)


class ConnectorReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor_before: str | None = Field(default=None, max_length=4096)
    cursor_after: str | None = Field(default=None, max_length=4096)
    source_generation: int = Field(ge=1)
    connector_revision: int = Field(ge=1)
    records: list[ConnectorRecord] = Field(min_length=1, max_length=500)


class ConnectorPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor_before: str | None = Field(default=None, max_length=4096)
    cursor_after: str | None = Field(default=None, max_length=4096)
    source_generation: int = Field(ge=1)
    connector_revision: int = Field(ge=1)
    records: list[ConnectorRecord] = Field(max_length=500)


class CollectionFence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_generation: int = Field(ge=1)
    connector_revision: int = Field(ge=1)


class ConnectorConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    configuration: ConnectorConfig


async def collection_allowed(
    session: AsyncSession,
    source_id: UUID,
    source_status: str,
    source_generation: int,
    fence: CollectionFence,
    *,
    lock: bool = False,
) -> bool:
    from modules.connectors import provisioning

    source = ConnectorSource(
        id=source_id,
        type="api",
        status=source_status,
        generation=source_generation,
        configuration={},
    )
    return await provisioning.require_collection_fence(
        session, source, fence.source_generation, fence.connector_revision, lock=lock
    )


async def require_collection_fence(
    session: AsyncSession,
    source: ConnectorSource,
    fence: CollectionFence,
    *,
    lock: bool = False,
) -> bool:
    from modules.connectors import provisioning

    return await provisioning.require_collection_fence(
        session,
        source,
        fence.source_generation,
        fence.connector_revision,
        lock=lock,
    )


async def require_batch_fence(
    session: AsyncSession,
    source: ConnectorSource,
    source_generation: int,
    connector_revision: int | None,
) -> bool:
    """Require a revision for managed connector sources while preserving native ingestion."""
    from modules.connectors import provisioning

    row = await provisioning.activation_status(session, source.id)
    if row is None:
        return connector_revision is None and source.generation == source_generation
    if connector_revision is None:
        return False
    return await provisioning.require_collection_fence(
        session, source, source_generation, connector_revision, lock=True
    )


async def fence_source_collection(session: AsyncSession, source: SourceFence) -> bool:
    """Persist connector-owned deactivation after the source owner has fenced a source."""
    from modules.connectors import provisioning

    return await provisioning.fence_source_collection(session, source)


async def save_connector_configuration(
    session: AsyncSession,
    source: ConnectorSource,
    expected_revision: int,
    source_configuration: dict[str, object],
    desired_configuration: dict[str, object],
    *,
    allow_paused: bool = False,
) -> tuple[ConnectorSource, ConnectorProvisioning] | None:
    from modules.connectors import provisioning
    from modules.sources import public as source_public

    saved = await source_public.set_connector_configuration(
        session, source.id, source.generation, source_configuration,
        allow_paused=allow_paused,
    )
    if saved is None:
        return None
    row = await provisioning.save_desired(
        session,
        source.id,
        saved.generation,
        expected_revision,
        desired_configuration,
    )
    if row is None:
        await session.rollback()
        return None
    return saved, row


async def allow_external_collector_credential_issue(
    session: AsyncSession, source_id: UUID
) -> bool:
    from modules.connectors import provisioning

    source, row, _ = await provisioning.lock_connector(session, source_id)
    return bool(
        source is not None and source.status == "active"
        and (row is None or (not row.desired_enabled and row.state != "provisioning"))
    )


class RSSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    cursor: str | None = Field(default=None, max_length=4096)


class CrawlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    source_generation: int = Field(ge=1)
    connector_revision: int = Field(ge=1)
    url: HttpUrl
    mode: str = Field(default="http", pattern="^(http|playwright)$")
    max_pages: int = Field(default=10, ge=1, le=10)
    max_depth: int = Field(default=2, ge=0, le=2)
    timeout_seconds: int = Field(default=60, ge=1, le=60)


class CrawlResult(BaseModel):
    run_id: UUID


class NoChangeRequest(CollectionFence):
    pass


async def validate_public_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only credential-free HTTP(S) URLs are allowed")
    try:
        addresses = await asyncio.to_thread(
            getaddrinfo, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), 0, 0, 0
        )
    except OSError as exc:
        raise ValueError("URL host could not be resolved") from exc
    if not addresses or any(not ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("URL resolves to a non-public address")
    return value


def overlap_floor(cursor: str | None) -> datetime | None:
    if not cursor:
        return None
    try:
        value = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        return None
    return value.astimezone(UTC) - DEFAULT_OVERLAP
