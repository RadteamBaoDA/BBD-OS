from typing import Any

from modules.connectors.public import ConnectorConfig, DEFAULT_TIMEZONE, overlap_floor
from modules.sources.models import Source

SUPPORTED_TYPES = {"rss", "web", "api"}


def configuration(source: Source) -> ConnectorConfig:
    return ConnectorConfig.model_validate(source.configuration or {})


def validate(source: Source) -> dict[str, Any]:
    if source.status != "active":
        raise ValueError("Source is not active")
    if source.type not in SUPPORTED_TYPES:
        raise ValueError("This source type has no packaged connector")
    config = configuration(source)
    required_url = config.feed_url if source.type == "rss" else config.url
    if required_url is None:
        raise ValueError("Source connector URL is not configured")
    if source.type == "api" and not config.items_path:
        raise ValueError("REST connector requires items_path")
    return {
        "source_id": str(source.id),
        "type": source.type,
        "timezone": config.timezone or DEFAULT_TIMEZONE,
        "url": str(required_url),
        "configuration": config.model_dump(mode="json", exclude_none=True),
    }


def health(source: Source) -> dict[str, str]:
    if source.status != "active":
        return {"status": source.status, "connector": source.type}
    try:
        validate(source)
    except ValueError:
        return {"status": "misconfigured", "connector": source.type}
    return {"status": "ready", "connector": source.type}


def sync(source: Source, cursor: str | None) -> dict[str, Any]:
    from modules.connectors.n8n import workflow_state

    return {**validate(source), **workflow_state(cursor)}


def normalize(record: dict[str, Any]) -> dict[str, Any]:
    from datetime import UTC, datetime

    raw_timestamp = str(record.get("observed_at") or "")
    timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")) if raw_timestamp else datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return {
        "provider_id": str(record.get("provider_id") or record.get("url") or "")[:512],
        "content": str(record.get("content") or "")[:1_000_000],
        "observed_at": timestamp.astimezone(UTC).isoformat(),
        "version": str(record["version"])[:255] if record.get("version") is not None else None,
        "metadata": dict(record.get("metadata") or {}),
    }
