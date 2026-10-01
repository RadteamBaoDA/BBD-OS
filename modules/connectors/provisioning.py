import copy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.connectors.models import ConnectorManagedCredential, ConnectorProvisioning
from modules.sources import public as sources
from modules.sources.schemas import ConnectorSource, SourceFence


async def lock_connector(
    session: AsyncSession,
    source_id: UUID,
    slots: tuple[str, ...] = (),
) -> tuple[SourceFence | None, ConnectorProvisioning | None, dict[str, ConnectorManagedCredential]]:
    """Lock source, provisioning, then credential slots in the one supported order."""
    source = await sources.lock_source(session, source_id)
    if source is None:
        return None, None, {}
    row = await session.scalar(
        select(ConnectorProvisioning)
        .where(ConnectorProvisioning.source_id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    locked_slots: dict[str, ConnectorManagedCredential] = {}
    for slot in sorted(set(slots)):
        credential = await session.scalar(
            select(ConnectorManagedCredential)
            .where(
                ConnectorManagedCredential.source_id == source_id,
                ConnectorManagedCredential.slot == slot,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if credential is not None:
            locked_slots[slot] = credential
    return source, row, locked_slots


async def get_managed_credential(
    session: AsyncSession, source_id: UUID, slot: str
) -> ConnectorManagedCredential | None:
    return await session.scalar(
        select(ConnectorManagedCredential)
        .where(
            ConnectorManagedCredential.source_id == source_id,
            ConnectorManagedCredential.slot == slot,
        )
        .execution_options(populate_existing=True)
    )


async def activation_status(
    session: AsyncSession, source_id: UUID
) -> ConnectorProvisioning | None:
    return await session.scalar(
        select(ConnectorProvisioning)
        .where(ConnectorProvisioning.source_id == source_id)
        .execution_options(populate_existing=True)
    )


def _step(
    kind: str,
    target: str | None,
    request: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "kind": kind,
        "target": target,
        "request": copy.deepcopy(request or {}),
        "state": "prepared",
        "dispatch_started_at": None,
        "history": [],
    }


def new_workflow_operation(
    *,
    operation_id: UUID,
    kind: str,
    source_generation: int,
    revision: int,
    configuration: dict[str, object],
    workflow_id: str | None,
    workflow_name: str,
    body: dict[str, object] | None,
    activation_id: UUID | None = None,
) -> dict[str, object]:
    step_kind = (
        "update" if kind == "enable" and workflow_id
        else "lookup" if kind == "enable"
        else "deactivate"
    )
    return {
        "id": str(operation_id),
        "kind": kind,
        "source_generation": source_generation,
        "revision": revision,
        "configuration": copy.deepcopy(configuration),
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "activation_id": str(activation_id) if activation_id else None,
        "phase": step_kind,
        "step": _step(step_kind, workflow_id, body),
        "cleanup_required": False,
        "error": None,
    }


def _new_deactivation(row: ConnectorProvisioning, generation: int) -> dict[str, object] | None:
    if not row.workflow_id:
        return None
    operation_id = uuid4()
    return new_workflow_operation(
        operation_id=operation_id,
        kind="deactivate",
        source_generation=generation,
        revision=row.desired_revision,
        configuration={},
        workflow_id=row.workflow_id,
        workflow_name=row.workflow_name or f"BBD-OS connector {row.source_id}",
        body=None,
    )


def _required_credentials_match(
    required: dict[str, dict[str, object]],
    slots: dict[str, ConnectorManagedCredential],
) -> bool:
    for slot, value in required.items():
        if not isinstance(value, dict):
            return False
        credential = slots.get(slot)
        if (
            credential is None or credential.state != "ready" or not credential.credential_id
            or credential.resolved_binding != value.get("binding")
        ):
            return False
        expected_id = value.get("credential_id")
        if expected_id is not None and credential.credential_id != expected_id:
            return False
        expected_operation = value.get("operation_id")
        if expected_operation is not None:
            envelope = credential.operation_envelope
            if (
                not isinstance(envelope, dict)
                or envelope.get("id") != expected_operation
                or envelope.get("state") != "succeeded"
            ):
                return False
    return True


async def save_desired(
    session: AsyncSession,
    source_id: UUID,
    source_generation: int,
    expected_revision: int,
    configuration: dict[str, object],
) -> ConnectorProvisioning | None:
    _, row, slots = await lock_connector(
        session, source_id, ("collector", "manual_trigger", "provider")
    )
    if row is None:
        if expected_revision != 0:
            return None
        row = ConnectorProvisioning(
            source_id=source_id,
            source_generation=source_generation,
            desired_revision=1,
            desired_configuration=copy.deepcopy(configuration),
            state="saved_not_active",
            desired_enabled=False,
        )
        session.add(row)
        await session.flush()
        return row
    if row.desired_revision != expected_revision:
        return None

    prior_enabled = row.desired_enabled or row.state == "active"
    row.source_generation = source_generation
    row.desired_revision += 1
    row.desired_configuration = copy.deepcopy(configuration)
    row.desired_enabled = False
    row.state = "saved_not_active"
    row.error_code = None
    activation = copy.deepcopy(row.activation_intent)
    if isinstance(activation, dict):
        required = activation.get("required_credentials")
        unresolved = False
        if isinstance(required, dict):
            for slot_name in required:
                credential = slots.get(str(slot_name))
                envelope = credential.operation_envelope if credential is not None else None
                if (
                    isinstance(envelope, dict)
                    and envelope.get("activation_id") == activation.get("id")
                ):
                    if envelope.get("state") == "prepared":
                        credential.operation_id = None
                        credential.operation_envelope = None
                        credential.state = "ready" if credential.credential_id else "queued"
                    elif envelope.get("state") in {"dispatched", "unknown"}:
                        unresolved = True
        if unresolved:
            activation["state"] = "stale_unresolved"
            row.activation_intent = activation
            row.state = "reconciliation_required"
            row.error_code = "activation_outcome_pending"
        else:
            row.activation_intent = None
    if row.workflow_operation is not None:
        operation = copy.deepcopy(row.workflow_operation)
        step = operation.get("step")
        if operation.get("kind") == "deactivate" and isinstance(step, dict) and step.get("state") == "prepared":
            row.error_code = "deactivation_pending"
        elif isinstance(step, dict) and step.get("state") in {"prepared", "blocked"}:
            row.workflow_operation = None
            operation = _new_deactivation(row, source_generation) if prior_enabled else None
            if operation is not None:
                row.workflow_operation = operation
                row.error_code = "deactivation_pending"
            else:
                row.error_code = None
        else:
            operation["cleanup_required"] = True
            operation["error"] = "desired_state_changed_during_dispatch"
            row.workflow_operation = operation
            row.error_code = "workflow_operation_pending"
    elif prior_enabled:
        operation = _new_deactivation(row, source_generation)
        if operation is not None:
            row.workflow_operation = operation
            row.error_code = "deactivation_pending"
    await session.flush()
    return row


async def begin_enable(
    session: AsyncSession,
    source_id: UUID,
    source_generation: int,
    revision: int,
    configuration: dict[str, object],
    workflow_name: str,
    body: dict[str, object],
    operation_id: UUID | None = None,
    required_credentials: dict[str, dict[str, object]] | None = None,
    activation_id: UUID | None = None,
) -> UUID | None:
    source, row, slots = await lock_connector(
        session, source_id, tuple((required_credentials or {}).keys())
    )
    if (
        source is None or source.status != "active" or source.generation != source_generation
        or row is None or row.source_generation != source_generation
        or row.desired_revision != revision or row.workflow_operation is not None
        or row.activation_intent is None
        or row.activation_intent.get("id") != str(activation_id)
        or not _required_credentials_match(required_credentials or {}, slots)
    ):
        return None
    operation_id = operation_id or uuid4()
    row.desired_enabled = True
    row.state = "provisioning"
    row.error_code = None
    row.workflow_operation = new_workflow_operation(
        operation_id=operation_id,
        kind="enable",
        source_generation=source_generation,
        revision=revision,
        configuration=configuration,
        workflow_id=row.workflow_id,
        workflow_name=workflow_name,
        body=body,
        activation_id=activation_id,
    )
    row.workflow_operation["required_credentials"] = copy.deepcopy(required_credentials or {})
    await session.flush()
    return operation_id


async def begin_activation_bundle(
    session: AsyncSession,
    source_id: UUID,
    source_generation: int,
    revision: int,
    configuration: dict[str, object],
    activation_id: UUID,
    required_credentials: dict[str, dict[str, object]],
    credential_intents: dict[str, dict[str, object]],
) -> bool:
    slots_to_lock = tuple(sorted(set(required_credentials) | set(credential_intents)))
    source, row, slots = await lock_connector(session, source_id, slots_to_lock)
    if (
        source is None or source.status != "active" or source.generation != source_generation
        or row is None or row.source_generation != source_generation
        or row.desired_revision != revision or row.desired_enabled
        or row.state == "provisioning" or row.workflow_operation is not None
        or row.activation_intent is not None
    ):
        return False

    for slot, intent in credential_intents.items():
        existing = slots.get(slot)
        if existing is not None and existing.state in {
            "dispatching", "reconciliation_required", "delete_pending"
        }:
            return False
        if (existing.credential_id if existing is not None else None) != intent.get("target_id"):
            return False
        operation_id = UUID(str(intent["operation_id"]))
        envelope = {
            "id": str(operation_id),
            "activation_id": str(activation_id),
            "kind": str(intent["kind"]),
            "state": "prepared",
            "source_generation": source_generation,
            "revision": revision,
            "credential_type": str(intent["credential_type"]),
            "target_id": intent.get("target_id"),
            "binding": copy.deepcopy(intent["binding"]),
            "input_ciphertext": str(intent["input_ciphertext"]),
            "dispatch_started_at": None,
        }
        if existing is None:
            existing = ConnectorManagedCredential(
                source_id=source_id,
                slot=slot,
                credential_id=intent.get("target_id"),
                operation_id=operation_id,
                operation_revision=revision,
                source_generation=source_generation,
                credential_type=str(intent["credential_type"]),
                state="queued",
                operation_envelope=envelope,
            )
            session.add(existing)
        else:
            existing.operation_id = operation_id
            existing.operation_revision = revision
            existing.source_generation = source_generation
            existing.credential_type = str(intent["credential_type"])
            existing.state = "queued"
            existing.error_code = None
            existing.operation_envelope = envelope

    for slot, required in required_credentials.items():
        if slot in credential_intents:
            required["operation_id"] = str(credential_intents[slot]["operation_id"])
            required["credential_id"] = credential_intents[slot].get("target_id")
        else:
            existing = slots.get(slot)
            if (
                existing is None or existing.state != "ready" or not existing.credential_id
                or existing.resolved_binding != required.get("binding")
            ):
                return False
            required["credential_id"] = existing.credential_id
            required["operation_id"] = None

    row.desired_enabled = True
    row.state = "provisioning"
    row.error_code = None
    row.activation_intent = {
        "id": str(activation_id),
        "source_generation": source_generation,
        "revision": revision,
        "configuration": copy.deepcopy(configuration),
        "required_credentials": copy.deepcopy(required_credentials),
        "state": "prepared",
    }
    await session.flush()
    return True


async def reject_activation(
    session: AsyncSession, source_id: UUID, revision: int, error_code: str
) -> bool:
    _, row, _ = await lock_connector(session, source_id)
    if row is None or row.desired_revision != revision or row.workflow_operation is not None:
        return False
    row.desired_enabled = False
    row.state = "saved_not_active"
    row.error_code = error_code
    await session.flush()
    return True


async def prepare_workflow_step(
    session: AsyncSession,
    source_id: UUID,
    operation_id: UUID,
    step_id: str,
    kind: str,
    target: str | None,
    request: dict[str, object] | None = None,
) -> bool:
    _, row, _ = await lock_connector(session, source_id)
    operation = copy.deepcopy(row.workflow_operation) if row is not None else None
    step = operation.get("step") if isinstance(operation, dict) else None
    if (
        row is None or not isinstance(operation, dict) or not isinstance(step, dict)
        or operation.get("id") != str(operation_id) or step.get("id") != step_id
        or step.get("state") != "dispatched"
    ):
        return False
    operation["phase"] = kind
    operation["step"] = _step(kind, target, request)
    row.workflow_operation = operation
    await session.flush()
    return True


async def fence_source_collection(
    session: AsyncSession, source: SourceFence
) -> bool:
    _, row, slots = await lock_connector(
        session, source.id, ("collector", "manual_trigger", "provider")
    )
    if row is None:
        return False
    row.source_generation = source.generation
    row.desired_enabled = False
    row.state = "disabled"
    activation = row.activation_intent
    if isinstance(activation, dict):
        unresolved = False
        required = activation.get("required_credentials")
        if isinstance(required, dict):
            for slot_name in required:
                credential = slots.get(str(slot_name))
                envelope = credential.operation_envelope if credential is not None else None
                if (
                    isinstance(envelope, dict)
                    and envelope.get("activation_id") == activation.get("id")
                ):
                    if envelope.get("state") == "prepared":
                        credential.operation_id = None
                        credential.operation_envelope = None
                        credential.state = "ready" if credential.credential_id else "queued"
                    elif envelope.get("state") in {"dispatched", "unknown"}:
                        unresolved = True
        if unresolved:
            activation["state"] = "stale_unresolved"
            row.activation_intent = activation
            row.error_code = "activation_outcome_pending"
        else:
            row.activation_intent = None
    if row.workflow_operation is not None:
        operation = copy.deepcopy(row.workflow_operation)
        step = operation.get("step")
        if isinstance(step, dict) and step.get("state") in {"prepared", "blocked"}:
            row.workflow_operation = None
        else:
            operation["cleanup_required"] = True
            operation["error"] = "source_fenced_during_dispatch"
            row.workflow_operation = operation
            row.error_code = "workflow_operation_pending"
            await session.flush()
            return True
    operation = _new_deactivation(row, source.generation)
    if operation is not None:
        row.workflow_operation = operation
        row.error_code = "deactivation_pending"
    else:
        row.error_code = None
    await session.flush()
    return True


async def require_collection_fence(
    session: AsyncSession,
    source: ConnectorSource,
    source_generation: int,
    revision: int,
    *,
    lock: bool = False,
) -> bool:
    current_source = await sources.lock_source(session, source.id)
    if (
        current_source is None
        or current_source.status != source.status
        or current_source.generation != source.generation
    ):
        return False
    statement = select(ConnectorProvisioning).where(
        ConnectorProvisioning.source_id == source.id
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    else:
        statement = statement.execution_options(populate_existing=True)
    row = await session.scalar(statement)
    return bool(
        source.status == "active"
        and source.generation == source_generation
        and row is not None
        and row.source_generation == source_generation
        and row.desired_revision == revision
        and row.applied_revision == revision
        and row.desired_enabled
        and row.state == "active"
    )


async def require_validation_fence(
    session: AsyncSession,
    source: ConnectorSource,
    source_generation: int,
    revision: int,
) -> bool:
    current_source = await sources.lock_source(session, source.id)
    if (
        current_source is None or current_source.status != "active"
        or current_source.status != source.status
        or current_source.generation != source_generation
        or source.generation != source_generation
    ):
        return False
    row = await session.scalar(
        select(ConnectorProvisioning)
        .where(ConnectorProvisioning.source_id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return bool(
        row is not None
        and row.source_generation == source_generation
        and row.desired_revision == revision
    )


async def claim_credential_operation(
    session: AsyncSession,
    source_id: UUID,
    slot: str,
    operation_id: UUID,
) -> dict[str, object] | None:
    source, desired, slots = await lock_connector(
        session, source_id, ("collector", "manual_trigger", "provider")
    )
    row = slots.get(slot)
    if row is None or row.operation_id != operation_id:
        return None
    envelope = copy.deepcopy(row.operation_envelope)
    if not isinstance(envelope, dict):
        return None
    if envelope.get("state") != "prepared":
        return None
    valid_enable = bool(
        envelope.get("kind") in {"create", "update"}
        and source is not None and source.status == "active"
        and desired is not None and desired.desired_enabled
        and isinstance(desired.activation_intent, dict)
        and envelope.get("activation_id") == desired.activation_intent.get("id")
        and isinstance(desired.activation_intent.get("required_credentials"), dict)
        and isinstance(desired.activation_intent["required_credentials"].get(slot), dict)
        and desired.activation_intent["required_credentials"][slot].get("operation_id") == str(operation_id)
        and source.generation == envelope.get("source_generation")
        and desired.source_generation == envelope.get("source_generation")
        and desired.desired_revision == envelope.get("revision")
    )
    valid_delete = bool(
        envelope.get("kind") == "delete"
        and source is not None and source.status == "paused"
        and desired is not None and not desired.desired_enabled
        and source.generation == envelope.get("source_generation")
        and desired.desired_revision == envelope.get("revision")
    )
    if not valid_enable and not valid_delete:
        activation_id = envelope.get("activation_id")
        row.operation_envelope = None
        row.operation_id = None
        row.state = "ready" if row.credential_id else "queued"
        row.error_code = "prepared_credential_intent_stale"
        if isinstance(activation_id, str) and desired is not None and isinstance(desired.activation_intent, dict):
            if desired.activation_intent.get("id") == activation_id:
                for sibling in slots.values():
                    sibling_envelope = sibling.operation_envelope
                    if (
                        sibling is not row and isinstance(sibling_envelope, dict)
                        and sibling_envelope.get("activation_id") == activation_id
                        and sibling_envelope.get("state") == "prepared"
                    ):
                        sibling.operation_id = None
                        sibling.operation_envelope = None
                        sibling.state = "ready" if sibling.credential_id else "queued"
                desired.activation_intent = None
                desired.desired_enabled = False
                desired.state = "disabled" if source is None or source.status != "active" else "saved_not_active"
                desired.error_code = "activation_intent_stale"
        await session.commit()
        return None
    envelope["state"] = "dispatched"
    envelope["dispatch_started_at"] = datetime.now(UTC).isoformat()
    row.operation_envelope = envelope
    row.state = "dispatching"
    await session.commit()
    return envelope


async def drive_credential_operation(
    session: AsyncSession,
    source_id: UUID,
    slot: str,
    client: Any,
    encryption_key: str,
) -> bool:
    from modules.connectors.credentials import (
        CredentialOutcomeUnknown,
        CredentialRequestRejected,
        CredentialUpdateOutcomeUnknown,
        CredentialEncryptionUnavailable,
        decrypt_credential_input,
    )

    row = await get_managed_credential(session, source_id, slot)
    if row is None or row.operation_id is None:
        return False
    operation_id = row.operation_id
    prepared = row.operation_envelope
    if not isinstance(prepared, dict) or prepared.get("state") != "prepared":
        return False
    try:
        request, binding = decrypt_credential_input(
            encryption_key,
            str(prepared["input_ciphertext"]),
            source_id=source_id,
            slot=slot,
            operation_id=operation_id,
        )
    except CredentialEncryptionUnavailable:
        await session.rollback()
        return False
    envelope = await claim_credential_operation(session, source_id, slot, operation_id)
    if envelope is None:
        return False
    try:
        data = request["data"]
        if not isinstance(data, dict):
            raise CredentialEncryptionUnavailable("Stored connector credential request is invalid")
        name = str(request["name"])
        header = str(data["name"])
        secret = str(data["value"])
        target = envelope.get("target_id")
        if envelope.get("kind") == "create" and target is None:
            credential_id = await client.create_http_header(name, header, secret)
        elif envelope.get("kind") == "update" and isinstance(target, str):
            await client.rotate_http_header(target, name, header, secret)
            credential_id = target
        else:
            raise CredentialEncryptionUnavailable("Stored connector credential operation is invalid")
    except CredentialRequestRejected:
        await fail_credential_operation(
            session, source_id, slot, operation_id, "n8n_credential_rejected", unknown=False
        )
        await session.commit()
        return False
    except (CredentialOutcomeUnknown, CredentialUpdateOutcomeUnknown, CredentialEncryptionUnavailable):
        await fail_credential_operation(
            session, source_id, slot, operation_id, "credential_operation_outcome_unknown", unknown=True
        )
        await session.commit()
        return False
    if not await complete_credential_operation(
        session, source_id, slot, operation_id, credential_id=credential_id, binding=binding
    ):
        await session.rollback()
        return False
    await session.commit()
    return True


async def complete_credential_operation(
    session: AsyncSession,
    source_id: UUID,
    slot: str,
    operation_id: UUID,
    *,
    credential_id: str | None,
    binding: dict[str, object],
) -> bool:
    source, desired, slots = await lock_connector(
        session, source_id, ("collector", "manual_trigger", "provider")
    )
    row = slots.get(slot)
    envelope = copy.deepcopy(row.operation_envelope) if row is not None else None
    if (
        row is None or row.operation_id != operation_id or not isinstance(envelope, dict)
        or envelope.get("state") != "dispatched"
    ):
        return False
    if credential_id is not None:
        row.credential_id = credential_id
    row.resolved_binding = copy.deepcopy(binding)
    row.state = "ready"
    row.error_code = None
    envelope["state"] = "succeeded"
    envelope.pop("input_ciphertext", None)
    row.operation_envelope = envelope
    if (
        desired is not None and isinstance(desired.activation_intent, dict)
        and desired.activation_intent.get("id") == envelope.get("activation_id")
        and (
            source is None or source.status != "active"
            or source.generation != envelope.get("source_generation")
            or desired.source_generation != envelope.get("source_generation")
            or desired.desired_revision != envelope.get("revision")
        )
    ):
        desired.activation_intent = None
        desired.desired_enabled = False
        if source is None or source.status != "active":
            desired.state = "disabled"
        else:
            desired.state = "saved_not_active"
        desired.error_code = "activation_intent_stale"
    await session.flush()
    return True


async def fail_credential_operation(
    session: AsyncSession,
    source_id: UUID,
    slot: str,
    operation_id: UUID,
    error_code: str,
    *,
    unknown: bool,
) -> bool:
    source, desired, slots = await lock_connector(
        session, source_id, ("collector", "manual_trigger", "provider")
    )
    row = slots.get(slot)
    envelope = copy.deepcopy(row.operation_envelope) if row is not None else None
    if (
        row is None or row.operation_id != operation_id or not isinstance(envelope, dict)
        or envelope.get("state") != "dispatched"
    ):
        return False
    envelope["state"] = "unknown" if unknown else "rejected"
    if not unknown:
        envelope.pop("input_ciphertext", None)
        row.state = "ready" if row.credential_id else "queued"
        row.operation_id = None
        row.operation_envelope = None
        row.error_code = error_code
        activation_id = envelope.get("activation_id")
        if isinstance(activation_id, str):
            for sibling in slots.values():
                sibling_envelope = sibling.operation_envelope
                if (
                    sibling is not row and isinstance(sibling_envelope, dict)
                    and sibling_envelope.get("activation_id") == activation_id
                    and sibling_envelope.get("state") == "prepared"
                ):
                    sibling.operation_id = None
                    sibling.operation_envelope = None
                    sibling.state = "ready" if sibling.credential_id else "queued"
            if desired is not None and isinstance(desired.activation_intent, dict) and desired.activation_intent.get("id") == activation_id:
                desired.activation_intent = None
        if (
            desired is not None
            and desired.desired_revision == int(envelope["revision"])
            and desired.source_generation == envelope.get("source_generation")
        ):
            desired.desired_enabled = False
            desired.state = "saved_not_active"
            desired.error_code = error_code
        await session.flush()
        return True
    else:
        row.state = "reconciliation_required"
        activation_id = envelope.get("activation_id")
        if isinstance(activation_id, str):
            for sibling in slots.values():
                sibling_envelope = sibling.operation_envelope
                if (
                    sibling is not row and isinstance(sibling_envelope, dict)
                    and sibling_envelope.get("activation_id") == activation_id
                    and sibling_envelope.get("state") == "prepared"
                ):
                    sibling.operation_id = None
                    sibling.operation_envelope = None
                    sibling.state = "ready" if sibling.credential_id else "queued"
            if desired is not None and isinstance(desired.activation_intent, dict) and desired.activation_intent.get("id") == activation_id:
                desired.activation_intent["state"] = "outcome_unknown"
    row.error_code = error_code
    row.operation_envelope = envelope
    if (
        desired is not None and unknown and desired.desired_revision == int(envelope["revision"])
        and desired.source_generation == envelope.get("source_generation")
    ):
        desired.state = "reconciliation_required"
        desired.error_code = error_code
    await session.flush()
    return True


async def create_delete_intent(
    session: AsyncSession,
    source_id: UUID,
    slot: str,
    expected_revision: int,
) -> tuple[ConnectorProvisioning, ConnectorManagedCredential, UUID] | None:
    source, desired, slots = await lock_connector(session, source_id, (slot,))
    row = slots.get(slot)
    if (
        source is None or source.status != "paused" or desired is None
        or desired.desired_revision != expected_revision or desired.desired_enabled
        or desired.workflow_operation is not None
        or desired.state != "disabled" or not row or not row.credential_id
        or row.state in {"dispatching", "reconciliation_required", "delete_pending"}
    ):
        return None
    operation_id = uuid4()
    row.operation_id = operation_id
    row.operation_revision = expected_revision
    row.source_generation = source.generation
    row.state = "delete_pending"
    row.error_code = None
    row.operation_envelope = {
        "id": str(operation_id),
        "kind": "delete",
        "state": "prepared",
        "source_generation": source.generation,
        "revision": expected_revision,
        "target_id": row.credential_id,
        "credential_type": row.credential_type,
        "dispatch_started_at": None,
    }
    await session.flush()
    return desired, row, operation_id


async def acknowledge_credential_delete(
    session: AsyncSession,
    source_id: UUID,
    slot: str,
    operation_id: UUID,
    target_id: str,
) -> bool:
    _, _, slots = await lock_connector(session, source_id, (slot,))
    row = slots.get(slot)
    envelope = copy.deepcopy(row.operation_envelope) if row is not None else None
    if (
        row is None or row.operation_id != operation_id or row.credential_id != target_id
        or row.state != "dispatching" or not isinstance(envelope, dict)
        or envelope.get("id") != str(operation_id) or envelope.get("target_id") != target_id
        or envelope.get("state") != "dispatched"
    ):
        return False
    row.credential_id = None
    row.operation_id = None
    row.state = "queued"
    row.error_code = None
    row.operation_envelope = None
    row.resolved_binding = None
    await session.flush()
    return True


async def claim_workflow_step(
    session: AsyncSession, source_id: UUID
) -> dict[str, object] | None:
    existing = await activation_status(session, source_id)
    required = (
        existing.workflow_operation.get("required_credentials", {})
        if existing is not None and isinstance(existing.workflow_operation, dict)
        else {}
    )
    required_slots = tuple(required.keys()) if isinstance(required, dict) else ()
    source, row, slots = await lock_connector(session, source_id, required_slots)
    if source is None or row is None or not isinstance(row.workflow_operation, dict):
        return None
    operation = copy.deepcopy(row.workflow_operation)
    step = operation.get("step")
    if not isinstance(step, dict) or step.get("state") != "prepared":
        return None
    if operation.get("kind") == "enable" and not _required_credentials_match(
        operation.get("required_credentials", {}), slots
    ):
        operation["error"] = "required_credential_binding_unresolved"
        step["state"] = "blocked"
        operation["step"] = step
        row.workflow_operation = operation
        row.state = "reconciliation_required"
        row.error_code = "required_credential_binding_unresolved"
        await session.commit()
        return None
    if operation.get("kind") == "enable" and (
        not row.desired_enabled or source.status != "active"
        or row.source_generation != operation.get("source_generation")
        or row.desired_revision != operation.get("revision")
        or source.generation != operation.get("source_generation")
    ):
        if row.workflow_id:
            row.workflow_operation = _new_deactivation(row, source.generation)
            row.error_code = "deactivation_pending"
            row.state = "saved_not_active"
        else:
            row.workflow_operation = None
            row.state = "disabled" if source.status != "active" else "saved_not_active"
        row.desired_enabled = False
        if isinstance(row.activation_intent, dict) and row.activation_intent.get("id") == operation.get("activation_id"):
            row.activation_intent = None
        await session.flush()
        return None
    step["state"] = "dispatched"
    step["dispatch_started_at"] = datetime.now(UTC).isoformat()
    operation["step"] = step
    row.workflow_operation = operation
    await session.commit()
    return operation


async def acknowledge_workflow_step(
    session: AsyncSession,
    source_id: UUID,
    operation_id: UUID,
    step_id: str,
    *,
    workflow_id: str | None = None,
) -> bool:
    existing = await activation_status(session, source_id)
    current_operation = existing.workflow_operation if existing is not None else None
    required = (
        current_operation.get("required_credentials", {})
        if isinstance(current_operation, dict) else {}
    )
    required_slots = tuple(required.keys()) if isinstance(required, dict) else ()
    source, row, slots = await lock_connector(session, source_id, required_slots)
    operation = copy.deepcopy(row.workflow_operation) if row is not None else None
    step = operation.get("step") if isinstance(operation, dict) else None
    if (
        row is None or not isinstance(operation, dict) or not isinstance(step, dict)
        or operation.get("id") != str(operation_id) or step.get("id") != step_id
        or step.get("state") != "dispatched"
    ):
        return False
    step["state"] = "succeeded"
    history = step.get("history")
    if isinstance(history, list):
        history.append({"id": step_id, "kind": step.get("kind"), "state": "succeeded"})
    operation["step"] = step
    if workflow_id is not None:
        operation["workflow_id"] = workflow_id
        row.workflow_id = workflow_id
        row.workflow_name = str(operation.get("workflow_name") or row.workflow_name or "")
    kind = step.get("kind")
    current = bool(
        source is not None and source.status == "active" and row.desired_enabled
        and source.generation == operation.get("source_generation")
        and row.source_generation == operation.get("source_generation")
        and row.desired_revision == operation.get("revision")
        and _required_credentials_match(operation.get("required_credentials", {}), slots)
    )
    target = str(operation.get("workflow_id") or row.workflow_id or "") or None
    if kind in {"create", "update"}:
        operation["workflow_id"] = target
        if current:
            operation["phase"] = "activate"
            operation["step"] = _step("activate", target)
        else:
            operation["cleanup_required"] = True
            operation["phase"] = "deactivate"
            operation["step"] = _step("deactivate", target)
            row.state = "disabled" if source is None or source.status != "active" else "saved_not_active"
            row.error_code = "deactivation_pending"
        row.workflow_operation = operation
    elif kind == "activate" and current:
        row.state = "active"
        row.applied_revision = int(operation["revision"])
        row.error_code = None
        row.workflow_operation = None
        if (
            isinstance(row.activation_intent, dict)
            and row.activation_intent.get("id") == operation.get("activation_id")
        ):
            row.activation_intent = None
    elif kind in {"activate", "create", "update"}:
        operation["cleanup_required"] = True
        operation["phase"] = "deactivate"
        operation["step"] = _step("deactivate", target)
        row.state = "disabled" if source is None or source.status != "active" else "saved_not_active"
        row.error_code = "deactivation_pending"
        row.workflow_operation = operation
        row.desired_enabled = False
    elif kind == "deactivate":
        row.workflow_operation = None
        row.error_code = None
        row.state = "disabled" if source is None or source.status != "active" else "saved_not_active"
        if (
            operation.get("cleanup_required")
            and isinstance(row.activation_intent, dict)
            and row.activation_intent.get("id") == operation.get("activation_id")
        ):
            row.activation_intent = None
    else:
        operation["error"] = "unsupported_workflow_step"
        row.workflow_operation = operation
        row.error_code = "workflow_operation_unsupported"
        row.state = "disabled" if not row.desired_enabled else "saved_not_active"
    await session.flush()
    return True


async def resolve_unknown_workflow_create(
    session: AsyncSession,
    source_id: UUID,
    operation_id: UUID,
    step_id: str,
    workflow_id: str,
) -> bool:
    source, row, _ = await lock_connector(session, source_id)
    operation = copy.deepcopy(row.workflow_operation) if row is not None else None
    step = operation.get("step") if isinstance(operation, dict) else None
    if (
        row is None or not isinstance(operation, dict) or not isinstance(step, dict)
        or operation.get("id") != str(operation_id) or step.get("id") != step_id
        or step.get("kind") != "create" or step.get("state") != "unknown"
    ):
        return False
    row.workflow_id = workflow_id
    row.workflow_name = str(operation.get("workflow_name") or row.workflow_name or "")
    operation["workflow_id"] = workflow_id
    current = bool(
        source is not None and source.status == "active" and row.desired_enabled
        and source.generation == operation.get("source_generation")
        and row.source_generation == operation.get("source_generation")
        and row.desired_revision == operation.get("revision")
    )
    if current:
        operation["phase"] = "activate"
        operation["step"] = _step("activate", workflow_id)
        row.state = "provisioning"
        row.error_code = None
    else:
        operation["cleanup_required"] = True
        operation["phase"] = "deactivate"
        operation["step"] = _step("deactivate", workflow_id)
        row.state = "disabled" if source is None or source.status != "active" else "saved_not_active"
        row.error_code = "deactivation_pending"
    row.workflow_operation = operation
    await session.flush()
    return True


async def defer_unknown_workflow_create(
    session: AsyncSession,
    source_id: UUID,
    operation_id: UUID | str,
    step_id: str,
) -> bool:
    """Move one unchanged unknown-create barrier behind other recovery work."""
    _, row, _ = await lock_connector(session, source_id)
    operation = row.workflow_operation if row is not None else None
    step = operation.get("step") if isinstance(operation, dict) else None
    if (
        not isinstance(operation, dict) or not isinstance(step, dict)
        or operation.get("id") != str(operation_id) or step.get("id") != step_id
        or step.get("kind") != "create" or step.get("state") != "unknown"
    ):
        return False
    latest = await session.scalar(
        select(func.max(ConnectorProvisioning.updated_at)).where(
            ConnectorProvisioning.workflow_operation["step"]["state"].astext == "unknown",
            ConnectorProvisioning.workflow_operation["step"]["kind"].astext == "create",
        )
    )
    now = datetime.now(UTC)
    if latest is not None and now <= latest:
        now = latest + timedelta(microseconds=1)
    row.updated_at = now
    await session.flush()
    return True


async def fail_workflow_step(
    session: AsyncSession,
    source_id: UUID,
    operation_id: UUID,
    step_id: str,
    error_code: str,
    *,
    unknown: bool,
) -> bool:
    source, row, _ = await lock_connector(session, source_id)
    operation = copy.deepcopy(row.workflow_operation) if row is not None else None
    step = operation.get("step") if isinstance(operation, dict) else None
    if (
        row is None or not isinstance(operation, dict) or not isinstance(step, dict)
        or operation.get("id") != str(operation_id) or step.get("id") != step_id
        or step.get("state") != "dispatched"
    ):
        return False
    current = bool(
        source is not None and source.status == "active" and row.desired_enabled
        and source.generation == operation.get("source_generation")
        and row.source_generation == operation.get("source_generation")
        and row.desired_revision == operation.get("revision")
    )
    if not unknown and step.get("kind") in {"lookup", "create", "update", "activate"}:
        target = str(operation.get("workflow_id") or row.workflow_id or "") or None
        if not current and target is not None:
            operation["cleanup_required"] = True
            operation["phase"] = "deactivate"
            operation["step"] = _step("deactivate", target)
            row.workflow_operation = operation
            row.error_code = "deactivation_pending"
            row.state = "disabled" if source is None or source.status != "active" else "saved_not_active"
        else:
            row.workflow_operation = None
            if current:
                row.desired_enabled = False
                row.state = "saved_not_active"
                row.error_code = error_code
                if isinstance(row.activation_intent, dict) and row.activation_intent.get("id") == operation.get("activation_id"):
                    row.activation_intent = None
            elif not row.desired_enabled or source is None or source.status != "active":
                row.state = "disabled"
                row.error_code = "workflow_operation_rejected" if source is not None and source.generation == operation.get("source_generation") else row.error_code
            else:
                row.state = "saved_not_active"
        await session.flush()
        return True
    step["state"] = "unknown" if unknown else "rejected"
    operation["step"] = step
    operation["error"] = error_code
    if unknown and not current:
        operation["cleanup_required"] = True
    row.workflow_operation = operation
    row.error_code = error_code if current else "workflow_operation_pending"
    row.state = (
        "reconciliation_required" if current
        else "disabled" if not row.desired_enabled or source is None or source.status != "active"
        else "saved_not_active"
    )
    await session.flush()
    return True


async def drive_workflow_operation(
    session: AsyncSession, source_id: UUID, api: Any
) -> bool:
    """Run prepared public n8n steps; every mutation is claimed and acknowledged by identity."""
    for _ in range(4):
        from modules.connectors.n8n import workflow_matches

        operation = await claim_workflow_step(session, source_id)
        if operation is None:
            return False
        step = operation.get("step")
        if not isinstance(step, dict):
            return False
        operation_id = UUID(str(operation["id"]))
        step_id = str(step["id"])
        kind = str(step["kind"])
        target = step.get("target")
        body = step.get("request")
        try:
            if kind == "lookup":
                matches = await api.find_workflows(str(operation["workflow_name"]))
                if len(matches) > 1:
                    raise ValueError("n8n has multiple workflows for this connector operation")
                if matches:
                    workflow_id = matches[0].get("id")
                    if not isinstance(workflow_id, str) or not workflow_id:
                        raise ValueError("n8n workflow lookup response omitted its ID")
                    if not isinstance(body, dict):
                        raise ValueError("Prepared workflow request body is invalid")
                    candidate = await api.get_workflow(workflow_id)
                    if not workflow_matches(body, candidate):
                        raise ValueError("n8n workflow lookup returned a mismatched identity")
                    next_kind = "update"
                    next_target = workflow_id
                else:
                    next_kind = "create"
                    next_target = None
                if not await prepare_workflow_step(
                    session, source_id, operation_id, step_id, next_kind, next_target,
                    body if isinstance(body, dict) else {},
                ):
                    await session.rollback()
                    return False
                await session.commit()
                continue
            if not isinstance(body, dict) and kind in {"create", "update"}:
                raise ValueError("Prepared workflow request body is invalid")
            if kind == "create":
                workflow_id = await api.create_workflow(body)
            elif kind == "update" and isinstance(target, str):
                await api.update_workflow(target, body)
                workflow_id = target
            elif kind == "activate" and isinstance(target, str):
                await api.set_active(target, True)
                workflow_id = None
            elif kind == "deactivate" and isinstance(target, str):
                await api.set_active(target, False)
                workflow_id = None
            else:
                raise ValueError("Unsupported prepared workflow step")
        except Exception as exc:
            from httpx import HTTPStatusError

            response = exc.response if isinstance(exc, HTTPStatusError) else None
            known_rejection = (
                response is not None
                and 400 <= response.status_code < 500
                and response.status_code != 408
            )
            await fail_workflow_step(
                session, source_id, operation_id, step_id,
                "n8n_request_rejected" if known_rejection else "n8n_outcome_unknown",
                unknown=not known_rejection and kind != "lookup",
            )
            await session.commit()
            return False
        if not await acknowledge_workflow_step(
            session, source_id, operation_id, step_id, workflow_id=workflow_id
        ):
            await session.rollback()
            return False
        await session.commit()
    return False


async def mark_reconciliation(
    session: AsyncSession,
    source_id: UUID,
    desired_revision: int,
    state: str,
    *,
    error_code: str | None = None,
    workflow_id: str | None = None,
    applied_revision: int | None = None,
) -> bool:
    _, row, _ = await lock_connector(session, source_id)
    if row is None or row.desired_revision != desired_revision:
        return False
    row.state = state
    row.error_code = error_code
    if workflow_id is not None:
        row.workflow_id = workflow_id
    if applied_revision is not None:
        row.applied_revision = applied_revision
    await session.flush()
    return True


async def unresolved_credential_error(session: AsyncSession, source_id: UUID) -> str | None:
    rows = await session.scalars(
        select(ConnectorManagedCredential).where(
            ConnectorManagedCredential.source_id == source_id,
            ConnectorManagedCredential.state.in_(
                ("dispatching", "reconciliation_required", "delete_pending")
            ),
        )
    )
    return "credential_operation_pending" if rows.first() is not None else None
