from typing import cast
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from modules.connectors import provisioning
from modules.connectors.credentials import N8nCredentials
from modules.connectors.models import ConnectorManagedCredential, ConnectorProvisioning
from modules.connectors.n8n import N8nApi, workflow_matches


async def _delete_credential(
    session: AsyncSession,
    client: N8nCredentials,
    source_id: UUID,
    slot: str,
    operation_id: UUID,
) -> bool:
    claimed = await provisioning.claim_credential_operation(
        session, source_id, slot, operation_id
    )
    if claimed is None:
        return False
    target = claimed.get("target_id")
    if not isinstance(target, str):
        await provisioning.fail_credential_operation(
            session, source_id, slot, operation_id, "credential_delete_target_missing", unknown=False
        )
        await session.commit()
        return False
    try:
        await client.delete(target)
    except Exception as exc:
        rejected = (
            isinstance(exc, httpx.HTTPStatusError)
            and 400 <= exc.response.status_code < 500
            and exc.response.status_code != 408
        )
        await provisioning.fail_credential_operation(
            session,
            source_id,
            slot,
            operation_id,
            "credential_delete_rejected" if rejected else "credential_delete_outcome_unknown",
            unknown=not rejected,
        )
        await session.commit()
        return False
    result = await provisioning.acknowledge_credential_delete(
        session, source_id, slot, operation_id, target
    )
    if result:
        await session.commit()
    else:
        await session.rollback()
    return result


async def _resume_activation(
    session: AsyncSession,
    source_id: UUID,
    api: N8nApi,
    credentials: N8nCredentials,
    settings: Settings,
) -> bool:
    from modules.connectors.activation import drive_activation

    return await drive_activation(
        session,
        source_id,
        api,
        credentials,
        settings.connector_credential_encryption_key.get_secret_value(),
    )

async def reconcile_connectors(ctx: dict[str, object]) -> int:
    settings = cast(Settings, ctx["settings"])
    api_key = settings.n8n_api_key.get_secret_value()
    if not api_key:
        return 0
    factory = cast(async_sessionmaker[AsyncSession], ctx["session_factory"])
    encryption_key = settings.connector_credential_encryption_key.get_secret_value()
    credentials = N8nCredentials(str(settings.n8n_service_url), api_key)
    api = N8nApi(str(settings.n8n_service_url), api_key)
    async with factory() as session:
        credential_rows = list((await session.scalars(
            select(ConnectorManagedCredential)
            .where(
                ConnectorManagedCredential.operation_envelope["state"].astext == "prepared",
                ConnectorManagedCredential.operation_envelope["kind"].astext == "delete",
                ConnectorManagedCredential.operation_id.is_not(None),
            )
            .order_by(ConnectorManagedCredential.updated_at)
            .limit(40)
        )).all())
        workflow_rows = list((await session.scalars(
            select(ConnectorProvisioning)
            .where(
                ConnectorProvisioning.workflow_operation["step"]["state"].astext == "prepared"
            )
            .order_by(ConnectorProvisioning.updated_at)
            .limit(40)
        )).all())
        unknown_create_rows = list((await session.scalars(
            select(ConnectorProvisioning)
            .where(
                ConnectorProvisioning.workflow_operation["step"]["state"].astext == "unknown",
                ConnectorProvisioning.workflow_operation["step"]["kind"].astext == "create",
            )
            .order_by(ConnectorProvisioning.updated_at)
            .limit(40)
        )).all())
        activation_rows = list((await session.scalars(
            select(ConnectorProvisioning)
            .where(
                ConnectorProvisioning.desired_enabled.is_(True),
                ConnectorProvisioning.state == "provisioning",
                ConnectorProvisioning.workflow_operation.is_(None),
                ConnectorProvisioning.activation_intent.is_not(None),
            )
            .order_by(ConnectorProvisioning.updated_at)
            .limit(40)
        )).all())
        credentials_pending = [
            (row.source_id, row.slot, row.operation_id,
             row.operation_envelope.get("kind") if isinstance(row.operation_envelope, dict) else None)
            for row in credential_rows
        ]
        workflow_pending = [
            (
                row.source_id,
                row.workflow_operation.get("id"),
                row.workflow_operation.get("step", {}).get("id"),
                row.workflow_operation.get("step", {}).get("kind"),
                row.workflow_operation.get("workflow_name"),
                row.workflow_operation.get("step", {}).get("request"),
            )
            for row in workflow_rows
        ]
        unknown_create_pending = [
            (
                row.source_id,
                row.workflow_operation.get("id"),
                row.workflow_operation.get("step", {}).get("id"),
                row.workflow_operation.get("workflow_name"),
                row.workflow_operation.get("step", {}).get("request"),
            )
            for row in unknown_create_rows
        ]
        activation_pending = [row.source_id for row in activation_rows]
        await session.rollback()

    completed = 0
    for source_id, slot, operation_id, kind in credentials_pending:
        if operation_id is None or kind != "delete":
            continue
        async with factory() as session:
            completed += await _delete_credential(
                session, credentials, source_id, slot, operation_id
            )

    for source_id, _operation_value, _step_value, _kind, _name, _body in workflow_pending:
        async with factory() as session:
            completed += await provisioning.drive_workflow_operation(session, source_id, api)

    for source_id, operation_value, step_value, name, body in unknown_create_pending:
        operation_id: UUID | None = None
        workflow_id: str | None = None
        try:
            operation_id = UUID(str(operation_value))
            matches = await api.find_workflows(str(name))
            if (
                len(matches) == 1
                and isinstance(matches[0].get("id"), str)
                and isinstance(body, dict)
            ):
                candidate_id = str(matches[0]["id"])
                actual = await api.get_workflow(candidate_id)
                if workflow_matches(body, actual):
                    workflow_id = candidate_id
        except Exception:
            pass
        if workflow_id is not None and operation_id is not None:
            async with factory() as session:
                resolved = await provisioning.resolve_unknown_workflow_create(
                    session, source_id, operation_id, str(step_value), workflow_id
                )
                if resolved:
                    await session.commit()
                    completed += 1
                    continue
                await session.rollback()
        async with factory() as session:
            deferred = await provisioning.defer_unknown_workflow_create(
                session, source_id, str(operation_value), str(step_value)
            )
            if deferred:
                await session.commit()
            else:
                await session.rollback()

    for source_id in activation_pending:
        async with factory() as session:
            completed += await _resume_activation(
                session, source_id, api, credentials, settings
            )
    return completed
