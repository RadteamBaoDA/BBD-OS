from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CatalogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    label: str
    auth_methods: tuple[str, ...]
    scope_fields: tuple[str, ...]
    configuration_fields: tuple[str, ...] = ()
    quota_limits: dict[str, int] = Field(default_factory=dict)
    history_description: str | None = None
    collection_modes: tuple[str, ...]
    supports_history: bool
    supports_edit: bool
    supports_delete: bool
    availability: Literal["available", "planned", "unavailable"]
    unavailable_reason: str | None = None
    unavailable_operations: tuple[str, ...] = ()


_ENTRIES = (
    CatalogEntry(
        provider_id="rss",
        label="RSS / Atom",
        auth_methods=("none",),
        scope_fields=("feed_url",),
        configuration_fields=("feed_url", "timezone"),
        quota_limits={"max_pages": 10, "max_feed_bytes": 26_214_400, "max_records": 500, "max_batch_bytes": 10_485_760},
        history_description="Available feed entries within the current bounded feed response.",
        collection_modes=("scheduled", "manual"),
        supports_history=True,
        supports_edit=False,
        supports_delete=False,
        availability="available",
    ),
    CatalogEntry(
        provider_id="web",
        label="Web page",
        auth_methods=("none",),
        scope_fields=("url", "max_depth", "max_pages", "timeout_seconds", "js_render"),
        configuration_fields=("url", "max_pages", "max_depth", "timeout_seconds", "js_render", "timezone"),
        quota_limits={"max_pages": 10, "max_depth": 2, "timeout_seconds": 60, "max_job_bytes": 26_214_400, "max_records": 500, "max_batch_bytes": 10_485_760},
        history_description="Pages discovered within the configured page and depth limits.",
        collection_modes=("scheduled", "manual"),
        supports_history=True,
        supports_edit=False,
        supports_delete=False,
        availability="available",
    ),
    CatalogEntry(
        provider_id="rest",
        label="REST API",
        auth_methods=("none", "http_header"),
        scope_fields=("url", "items_path", "id_field", "title_field", "content_field"),
        configuration_fields=("url", "items_path", "id_field", "title_field", "content_field", "updated_field", "timezone"),
        quota_limits={"max_pages": 10, "max_records": 500, "max_batch_bytes": 10_485_760},
        history_description="Records returned by the current API response and pagination window.",
        collection_modes=("scheduled", "manual"),
        supports_history=True,
        supports_edit=False,
        supports_delete=False,
        availability="available",
        unavailable_operations=("automatic_recovery_after_lost_n8n_credential_create_id",),
    ),
    CatalogEntry(
        provider_id="github",
        label="GitHub",
        auth_methods=("oauth2",),
        scope_fields=("repository", "resource_types"),
        collection_modes=("scheduled", "manual"),
        supports_history=True,
        supports_edit=False,
        supports_delete=False,
        availability="planned",
        unavailable_reason="GitHub authorization and collection are delivered with P09-T1.",
    ),
    *(
        CatalogEntry(
            provider_id=provider,
            label=label,
            auth_methods=("oauth2",),
            scope_fields=(),
            collection_modes=(),
            supports_history=False,
            supports_edit=False,
            supports_delete=False,
            availability="unavailable",
            unavailable_reason="No provider adapter consumes this authorization yet.",
        )
        for provider, label in (
            ("google_mail", "Gmail"),
            ("google_calendar", "Google Calendar"),
            ("google_drive", "Google Drive"),
        )
    ),
)


def list_catalog() -> tuple[CatalogEntry, ...]:
    return _ENTRIES


def get_catalog_entry(provider_id: str) -> CatalogEntry | None:
    return next((entry for entry in _ENTRIES if entry.provider_id == provider_id), None)
