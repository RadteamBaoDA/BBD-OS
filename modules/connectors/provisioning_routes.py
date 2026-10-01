from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from modules.connectors import catalog, provisioning, registry
from modules.connectors.activation import drive_activation, prepare_credential_assignment
from modules.connectors.credentials import (
    CredentialEncryptionUnavailable,
    N8nCredentials,
    secret_fingerprint,
)
from modules.connectors.n8n import N8nApi
from modules.connectors import public as connector_owner
from modules.connectors.public import ConnectorConfig, validate_public_url
from modules.ingestion import public as ingestion
from modules.sources import public as sources
from modules.sources.schemas import ConnectorSource

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


class ConnectorSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    configuration: ConnectorConfig
    auth_method: Literal["none", "http_header"] = "none"
    auth_header_name: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_auth(self) -> "ConnectorSettingsRequest":
        if self.auth_method == "http_header" and not self.auth_header_name:
            raise ValueError("auth_header_name is required for header authentication")
        if self.auth_method == "none" and self.auth_header_name is not None:
            raise ValueError("auth_header_name requires header authentication")
        return self


class DraftValidationRequest(ConnectorSettingsRequest):
    expected_source_generation: int = Field(ge=1)


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    secret_action: Literal["keep", "replace"] = "keep"
    secret: SecretStr | None = None

    @model_validator(mode="after")
    def validate_secret_action(self) -> "ActivationRequest":
        if self.secret_action == "replace" and (self.secret is None or not self.secret.get_secret_value()):
            raise ValueError("A non-empty replacement secret is required")
        if self.secret_action == "keep" and self.secret is not None:
            raise ValueError("secret is only accepted for replacement")
        return self


class ActivationRead(BaseModel):
    source_id: UUID
    desired_revision: int
    applied_revision: int
    state: str
    error_code: str | None
    credential_recovery: str = "supported"


class ConnectorConfigurationRead(BaseModel):
    source_id: UUID
    source_type: str
    source_generation: int
    configuration: ConnectorConfig
    expected_revision: int
    auth_method: Literal["none", "http_header"]
    auth_header_name: str | None
    desired_enabled: bool
    activation_state: str
    activation_error_code: str | None
    provider_credential_configured: bool
    provider_credential_state: str | None


class DraftValidationRead(BaseModel):
    source_id: UUID
    source_generation: int
    expected_revision: int
    validated_at: datetime
    validation_status: Literal["valid"]
    checks: tuple[Literal["configuration", "public_url_policy"], ...]


@router.get("/{source_id}/configuration", response_model=ConnectorConfigurationRead)
async def get_configuration(
    source_id: UUID, session: Session, _owner: OwnerRead
) -> ConnectorConfigurationRead:
    snapshot = await connector_owner.get_connector_configuration(session, source_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if snapshot.source_type not in registry.SUPPORTED_TYPES:
        raise HTTPException(status_code=409, detail="This source has no managed connector configuration")
    return ConnectorConfigurationRead(
        source_id=snapshot.source_id,
        source_type=snapshot.source_type,
        source_generation=snapshot.source_generation,
        configuration=ConnectorConfig.model_validate(snapshot.configuration),
        expected_revision=snapshot.expected_revision,
        auth_method=snapshot.auth_method,
        auth_header_name=snapshot.auth_header_name,
        desired_enabled=snapshot.desired_enabled,
        activation_state=snapshot.activation_state,
        activation_error_code=snapshot.activation_error_code,
        provider_credential_configured=snapshot.provider_credential_configured,
        provider_credential_state=snapshot.provider_credential_state,
    )


@router.post("/{source_id}/validate-draft", response_model=DraftValidationRead)
async def validate_draft_configuration(
    source_id: UUID,
    payload: DraftValidationRequest,
    session: Session,
    _owner: OwnerRead,
) -> DraftValidationRead:
    source = await _source(session, source_id)
    if source.status != "active" or source.type not in registry.SUPPORTED_TYPES:
        raise HTTPException(status_code=409, detail="Active packaged connector required")
    if payload.expected_source_generation != source.generation:
        raise HTTPException(status_code=409, detail="Source generation changed; reload before validating")
    row = await provisioning.activation_status(session, source_id)
    current_revision = row.desired_revision if row is not None else 0
    if payload.expected_revision != current_revision:
        raise HTTPException(status_code=409, detail="Connector configuration revision changed; reload before validating")
    if payload.auth_method == "http_header" and source.type != "api":
        raise HTTPException(status_code=422, detail="Header authentication is supported only for REST sources")
    candidate = source.model_copy(update={
        "configuration": payload.configuration.model_dump(mode="json", exclude_none=True)
    })
    try:
        data = registry.validate(candidate)
        await validate_public_url(data["url"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Draft connector configuration is invalid") from exc
    return DraftValidationRead(
        source_id=source_id,
        source_generation=source.generation,
        expected_revision=payload.expected_revision,
        validated_at=datetime.now(UTC),
        validation_status="valid",
        checks=("configuration", "public_url_policy"),
    )


async def _source(session: AsyncSession, source_id: UUID) -> ConnectorSource:
    source = await sources.get_connector_source(session, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.get("/catalog")
async def get_catalog(_owner: OwnerRead) -> list[catalog.CatalogEntry]:
    return list(catalog.list_catalog())


@router.put("/{source_id}/configuration", response_model=ActivationRead)
async def put_configuration(
    source_id: UUID,
    payload: ConnectorSettingsRequest,
    session: Session,
    _owner: OwnerWrite,
) -> ActivationRead:
    source = await _source(session, source_id)
    if source.status != "active" or source.type not in registry.SUPPORTED_TYPES:
        raise HTTPException(status_code=409, detail="Active packaged connector required")
    pending = await provisioning.activation_status(session, source_id)
    if pending is not None and pending.state == "disabled" and pending.error_code == "deactivation_pending":
        raise HTTPException(status_code=409, detail="Wait for source deactivation to finish before saving")
    if payload.auth_method == "http_header" and source.type != "api":
        raise HTTPException(status_code=422, detail="Header authentication is supported only for REST sources")
    source_configuration = payload.configuration.model_dump(mode="json", exclude_none=True)
    desired_configuration = dict(source_configuration)
    desired_configuration["auth_method"] = payload.auth_method
    if payload.auth_header_name:
        desired_configuration["auth_header_name"] = payload.auth_header_name
    candidate = source.model_copy(update={"configuration": source_configuration})
    try:
        data = registry.validate(candidate)
        await validate_public_url(data["url"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    saved_result = await connector_owner.save_connector_configuration(
        session,
        source,
        payload.expected_revision,
        source_configuration,
        desired_configuration,
    )
    if saved_result is None:
        raise HTTPException(status_code=409, detail="Source or connector revision changed while configuration was validated")
    saved, row = saved_result
    unresolved = await provisioning.unresolved_credential_error(session, source_id)
    row.state = "reconciliation_required" if unresolved else "saved_not_active"
    row.error_code = unresolved
    await session.commit()
    return await _activation_read(session, source_id, row)


@router.post("/{source_id}/validate", response_model=ActivationRead)
async def validate_configuration(
    source_id: UUID, session: Session, _owner: OwnerRead
) -> ActivationRead:
    source = await _source(session, source_id)
    try:
        data = registry.validate(source)
        await validate_public_url(data["url"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Connector configuration is invalid") from exc
    row = await provisioning.activation_status(session, source_id)
    if row is None:
        raise HTTPException(status_code=409, detail="Save connector configuration before validation")
    return await _activation_read(session, source_id, row)


@router.get("/{source_id}/activation", response_model=ActivationRead)
async def get_activation(
    source_id: UUID, session: Session, _owner: OwnerRead
) -> ActivationRead:
    await _source(session, source_id)
    row = await provisioning.activation_status(session, source_id)
    if row is None:
        return ActivationRead(
            source_id=source_id,
            desired_revision=0,
            applied_revision=0,
            state="saved_not_active",
            error_code=None,
        )
    return await _activation_read(session, source_id, row)


@router.post("/{source_id}/activate", response_model=ActivationRead)
async def activate_source(
    source_id: UUID,
    payload: ActivationRequest,
    session: Session,
    request: Request,
    _owner: OwnerWrite,
) -> ActivationRead:
    source = await _source(session, source_id)
    row = await provisioning.activation_status(session, source_id)
    if row is None or row.desired_revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="Connector configuration revision is stale")
    if row.state == "provisioning":
        raise HTTPException(status_code=409, detail="Connector activation is already being reconciled")
    if row.state == "disabled" and row.error_code == "deactivation_pending":
        raise HTTPException(status_code=409, detail="Wait for source deactivation to finish before enabling")
    if await provisioning.unresolved_credential_error(session, source_id):
        raise HTTPException(
            status_code=409,
            detail="An n8n credential operation is pending or requires recovery",
        )
    if source.status != "active" or source.generation != row.source_generation:
        raise HTTPException(status_code=409, detail="Source changed; save its current configuration before enabling")
    settings = request.app.state.settings
    api_key = settings.n8n_api_key.get_secret_value()
    if not api_key:
        raise HTTPException(status_code=503, detail="n8n provisioning is not configured")
    webhook_token = settings.n8n_webhook_token.get_secret_value()
    if not webhook_token:
        raise HTTPException(status_code=503, detail="Manual trigger authentication is not configured")
    encryption_key = settings.connector_credential_encryption_key.get_secret_value()
    try:
        secret_fingerprint(encryption_key, "connector-key-validation")
    except CredentialEncryptionUnavailable as exc:
        raise HTTPException(status_code=503, detail="Connector credential encryption is not configured") from exc

    activation_id = uuid4()
    try:
        credential_intents: dict[str, dict[str, object]] = {}
        required_credentials: dict[str, object] = {}

        collector = await provisioning.get_managed_credential(session, source_id, "collector")
        collector_token: str | None = None
        collector_binding = collector.resolved_binding if collector is not None else None
        if not (
            collector is not None and collector.state == "ready" and collector.credential_id
            and isinstance(collector_binding, dict)
            and collector_binding.get("source_generation") == source.generation
        ):
            collector_token = await ingestion.create_collector_credential(session, source_id)
            collector_binding = {
                "source_generation": source.generation,
                "token_fingerprint": secret_fingerprint(encryption_key, collector_token),
            }
        required, intent = prepare_credential_assignment(
            source_id=source_id,
            activation_id=activation_id,
            slot="collector",
            credential_name=f"BBD-OS source collector {source_id}",
            header_name="Authorization",
            secret=f"Bearer {collector_token}" if collector_token is not None else None,
            binding=collector_binding if isinstance(collector_binding, dict) else {},
            existing=collector,
            encryption_key=encryption_key,
        )
        required_credentials["collector"] = required
        if intent is not None:
            credential_intents["collector"] = intent

        manual = await provisioning.get_managed_credential(session, source_id, "manual_trigger")
        required, intent = prepare_credential_assignment(
            source_id=source_id,
            activation_id=activation_id,
            slot="manual_trigger",
            credential_name="BBD-OS manual trigger",
            header_name="X-BBD-Webhook-Token",
            secret=webhook_token,
            binding={"binding_kind": "manual_trigger"},
            existing=manual,
            encryption_key=encryption_key,
        )
        required_credentials["manual_trigger"] = required
        if intent is not None:
            credential_intents["manual_trigger"] = intent

        if row.desired_configuration.get("auth_method") == "http_header":
            provider = await provisioning.get_managed_credential(session, source_id, "provider")
            provider_header = str(row.desired_configuration.get("auth_header_name", ""))
            if payload.secret_action == "keep":
                provider_binding = provider.resolved_binding if provider is not None else None
                if (
                    provider is None or provider.state != "ready" or not provider.credential_id
                    or not isinstance(provider_binding, dict)
                    or provider_binding.get("header_name") != provider_header
                ):
                    raise ValueError("Provide a provider credential for the current header binding")
                provider_secret = None
                binding = dict(provider_binding)
            else:
                provider_secret = payload.secret.get_secret_value() if payload.secret else None
                binding = {"binding_kind": "provider"}
            required, intent = prepare_credential_assignment(
                source_id=source_id,
                activation_id=activation_id,
                slot="provider",
                credential_name=f"BBD-OS REST source {source_id}",
                header_name=provider_header,
                secret=provider_secret,
                binding=binding,
                existing=provider,
                encryption_key=encryption_key,
            )
            required_credentials["provider"] = required
            if intent is not None:
                credential_intents["provider"] = intent
    except (CredentialEncryptionUnavailable, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not await provisioning.begin_activation_bundle(
        session,
        source_id,
        source.generation,
        payload.expected_revision,
        dict(row.desired_configuration),
        activation_id,
        required_credentials,
        credential_intents,
    ):
        await session.rollback()
        raise HTTPException(status_code=409, detail="Connector activation changed; reload and retry")
    await session.commit()

    credentials = N8nCredentials(str(settings.n8n_service_url), api_key)
    api = N8nApi(str(settings.n8n_service_url), api_key)
    await drive_activation(
        session,
        source_id,
        api,
        credentials,
        encryption_key,
    )
    latest = await provisioning.activation_status(session, source_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="Connector state disappeared during activation")
    if latest.state != "active":
        if latest.state == "saved_not_active" and latest.error_code == "n8n_credential_rejected":
            raise HTTPException(status_code=422, detail="n8n rejected a connector credential; review it and retry")
        raise HTTPException(status_code=503, detail="Connector activation is pending reconciliation")
    return await _activation_read(session, source_id, latest)


@router.post("/{source_id}/deactivate", response_model=ActivationRead)
async def deactivate_source(
    source_id: UUID,
    session: Session,
    _owner: OwnerWrite,
) -> ActivationRead:
    source = await sources.pause_source_for_connector(session, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    row = await provisioning.activation_status(session, source_id)
    if row is None:
        raise HTTPException(status_code=409, detail="No connector provisioning state exists")
    await session.commit()
    return await _activation_read(session, source_id, row)


@router.delete("/{source_id}/credentials/provider", response_model=ActivationRead)
async def remove_provider_credential(
    source_id: UUID,
    expected_revision: Annotated[int, Query(ge=1)],
    session: Session,
    _owner: OwnerWrite,
) -> ActivationRead:
    source = await sources.get_connector_source(session, source_id)
    row = await provisioning.activation_status(session, source_id)
    if source is None or row is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    if row.desired_revision != expected_revision:
        raise HTTPException(status_code=409, detail="Connector configuration revision is stale")
    if (
        source.status != "paused"
        or row.state != "disabled"
        or row.error_code == "deactivation_pending"
    ):
        raise HTTPException(status_code=409, detail="Pause the source before removing its provider credential")
    desired = dict(row.desired_configuration)
    desired["auth_method"] = "none"
    desired.pop("auth_header_name", None)
    saved = await connector_owner.save_connector_configuration(
        session,
        source,
        expected_revision,
        dict(source.configuration),
        desired,
        allow_paused=True,
    )
    if saved is None:
        raise HTTPException(status_code=409, detail="Connector configuration revision changed")
    _, updated = saved
    updated.state = "disabled"
    intent = await provisioning.create_delete_intent(
        session, source_id, "provider", updated.desired_revision
    )
    if intent is None:
        existing = await provisioning.get_managed_credential(session, source_id, "provider")
        if existing is not None and existing.credential_id is not None:
            raise HTTPException(status_code=409, detail="Provider credential operation cannot be changed until its current operation settles")
        updated.error_code = None
    else:
        updated, _, _ = intent
        updated.error_code = "credential_delete_pending"
    await session.commit()
    return await _activation_read(session, source_id, updated)


async def _activation_read(
    session: AsyncSession, source_id: UUID, row: object
) -> ActivationRead:
    state = getattr(row, "state")
    error_code = getattr(row, "error_code")
    unresolved = await provisioning.unresolved_credential_error(session, source_id)
    if unresolved:
        error_code = unresolved
        if state != "disabled":
            state = "reconciliation_required"
    return ActivationRead(
        source_id=source_id,
        desired_revision=getattr(row, "desired_revision"),
        applied_revision=getattr(row, "applied_revision"),
        state=state,
        error_code=error_code,
        credential_recovery=(
            "unsupported_operation" if unresolved else "supported"
        ),
    )
