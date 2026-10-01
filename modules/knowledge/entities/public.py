from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, desc, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import decode_cursor, encode_cursor
from core.realtime import commit_with_replay, make_graph_change
from modules.knowledge.entities.models import (
    Entity,
    EntityAlias,
    EntityEvidenceMembership,
    EntityAliasEvidence,
    EntityFieldEvidence,
    EntityOwnerAction,
)
from modules.knowledge.entities.schemas import (
    AliasCreate,
    EntityAliasRead,
    EntityCreate,
    EntityMembershipReferenceRead,
    EntityPage,
    EntityPatch,
    EntityRead,
    EntityReferenceRead,
    canonicalize_name,
)


def _entity_read(entity: Entity, aliases: list[EntityAlias] | None = None) -> EntityRead:
    return EntityRead(
        id=entity.id,
        type=entity.type,
        name=entity.name if entity.name_origin is not None else None,
        canonical_name=entity.canonical_name if entity.name_origin is not None else None,
        description=entity.description if entity.description_origin is not None else None,
        metadata=entity.metadata_json,
        revision=entity.revision,
        name_origin=entity.name_origin,
        description_origin=entity.description_origin,
        first_seen_at=entity.first_seen_at,
        last_seen_at=entity.last_seen_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        aliases=[
            EntityAliasRead(
                id=item.id,
                entity_id=item.entity_id,
                alias=item.alias,
                source_id=item.source_id,
                confirmed=item.confirmed,
                origin=item.origin,
                confidence=item.confidence,
                created_at=item.created_at,
            )
            for item in aliases or []
        ],
    )


async def _aliases(session: AsyncSession, entity_ids: list[UUID]) -> dict[UUID, list[EntityAlias]]:
    if not entity_ids:
        return {}
    result: dict[UUID, list[EntityAlias]] = {}
    aliases = (await session.scalars(
        select(EntityAlias).where(
            EntityAlias.entity_id.in_(entity_ids),
            or_(EntityAlias.origin.is_not(None), EntityAlias.source_id.is_(None)),
        ).order_by(EntityAlias.alias)
    )).all()
    for alias in aliases:
        result.setdefault(alias.entity_id, []).append(alias)
    return result


async def record_owner_action(
    session: AsyncSession,
    *,
    actor_id: int,
    operation: str,
    reason: str,
    affected_ids: list[UUID],
    revisions: dict[str, int | None] | None = None,
) -> None:
    clean_reason = " ".join(reason.split())
    if not clean_reason or len(clean_reason) > 300:
        raise ValueError("Owner action reason must contain 1 to 300 characters")
    session.add(EntityOwnerAction(
        actor_id=actor_id,
        operation=operation,
        reason=clean_reason,
        affected_ids=[str(identifier) for identifier in affected_ids],
        revisions=revisions or {},
        created_at=datetime.now(UTC),
    ))


async def list_entities(
    session: AsyncSession, limit: int, cursor: str | None, entity_type: str | None, query: str | None
) -> EntityPage:
    statement = select(Entity)
    if entity_type:
        statement = statement.where(Entity.type == entity_type)
    if query:
        statement = statement.where(
            or_(Entity.name.ilike(f"%{query}%"), Entity.canonical_name.ilike(f"%{canonicalize_name(query)}%"))
        )
    if cursor:
        created_at, identifier = decode_cursor(cursor)
        statement = statement.where(tuple_(Entity.created_at, Entity.id) < (created_at, identifier))
    rows = list((await session.scalars(
        statement.order_by(desc(Entity.created_at), desc(Entity.id)).limit(limit + 1)
    )).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    aliases = await _aliases(session, [row.id for row in rows])
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return EntityPage(items=[_entity_read(row, aliases.get(row.id)) for row in rows], next_cursor=next_cursor)


async def get_entity(session: AsyncSession, entity_id: UUID) -> EntityRead | None:
    entity = await session.get(Entity, entity_id)
    if entity is None:
        return None
    aliases = await _aliases(session, [entity.id])
    return _entity_read(entity, aliases.get(entity.id))


async def get_entity_refs(
    session: AsyncSession, ids: list[UUID], *, for_write: bool = False
) -> list[EntityReferenceRead]:
    if len(ids) > 100 or len(set(ids)) != len(ids):
        raise ValueError("Entity reference query must contain up to 100 unique IDs")
    if not ids:
        return []
    query = select(Entity).where(Entity.id.in_(ids))
    if for_write:
        query = query.order_by(Entity.id).with_for_update()
    rows = (await session.scalars(query)).all()
    by_id = {
        row.id: EntityReferenceRead(
            requested_id=row.id, canonical_id=row.id, revision=row.revision, type=row.type,
            name=row.name if row.name_origin is not None else None,
        )
        for row in rows
    }
    if set(by_id) != set(ids):
        raise LookupError("Entity reference is missing")
    return [by_id[identifier] for identifier in ids]


async def get_membership_refs(
    session: AsyncSession, ids: list[UUID], *, for_write: bool = False
) -> list[EntityMembershipReferenceRead]:
    if len(ids) > 200 or len(set(ids)) != len(ids):
        raise ValueError("Entity membership query must contain up to 200 unique IDs")
    if not ids:
        return []
    query = select(EntityEvidenceMembership).where(EntityEvidenceMembership.id.in_(ids))
    if for_write:
        query = query.order_by(EntityEvidenceMembership.entity_id, EntityEvidenceMembership.id).with_for_update()
    rows = (await session.scalars(query)).all()
    by_id = {
        row.id: EntityMembershipReferenceRead(
            id=row.id, entity_id=row.entity_id, document_version_id=row.document_version_id,
            chunk_id=row.chunk_id, observed_at=row.observed_at, extracted_at=row.extracted_at,
            confidence=row.confidence,
        )
        for row in rows
    }
    if set(by_id) != set(ids):
        raise LookupError("Entity evidence membership is missing")
    return [by_id[identifier] for identifier in ids]


async def publish_derived_field(
    session: AsyncSession,
    *,
    entity_id: UUID,
    membership_id: UUID,
    field_name: Literal["name", "description"],
    value: str,
) -> bool:
    """Publish a derived field and bind its exact value to one valid membership.

    The caller owns the source/document locks and the outer transaction. This
    command takes entity then membership locks and never commits.
    """
    if field_name not in {"name", "description"}:
        raise ValueError("Unsupported derived entity field")
    entity = await session.scalar(
        select(Entity).where(Entity.id == entity_id).with_for_update()
    )
    if entity is None:
        raise LookupError("Entity is missing")
    membership = await session.scalar(
        select(EntityEvidenceMembership)
        .where(
            EntityEvidenceMembership.id == membership_id,
            EntityEvidenceMembership.entity_id == entity_id,
        )
        .with_for_update()
    )
    if membership is None:
        raise LookupError("Entity evidence membership is missing or belongs to another entity")
    if (field_name == "name" and entity.name_origin == "owner") or (
        field_name == "description" and entity.description_origin == "owner"
    ):
        return False
    previous_value = entity.name if field_name == "name" else entity.description
    previous_origin = entity.name_origin if field_name == "name" else entity.description_origin
    if field_name == "name":
        value = " ".join(value.split())
        if not value or len(value) > 300:
            raise ValueError("Derived entity name must contain 1 to 300 characters")
        entity.name = value
        entity.canonical_name = canonicalize_name(value)
        entity.name_origin = "derived"
    else:
        if not value or len(value) > 20_000:
            raise ValueError("Derived entity description must contain 1 to 20000 characters")
        entity.description = value
        entity.description_origin = "derived"
    value_hash = sha256(value.encode("utf-8")).hexdigest()
    await session.execute(delete(EntityFieldEvidence).where(
        EntityFieldEvidence.entity_id == entity_id,
        EntityFieldEvidence.field_name == field_name,
        EntityFieldEvidence.value_hash != value_hash,
    ))
    support_exists = await session.scalar(select(EntityFieldEvidence.id).where(
        EntityFieldEvidence.entity_id == entity_id,
        EntityFieldEvidence.field_name == field_name,
        EntityFieldEvidence.value_hash == value_hash,
        EntityFieldEvidence.membership_id == membership_id,
    ).limit(1))
    if support_exists is None:
        session.add(EntityFieldEvidence(
            entity_id=entity_id,
            field_name=field_name,
            value_hash=value_hash,
            membership_id=membership_id,
        ))
        entity.revision += 1
    elif previous_value != value or previous_origin != "derived":
        entity.revision += 1
    await session.flush()
    return True


async def create_entity(session: AsyncSession, payload: EntityCreate, *, actor_id: int) -> EntityRead:
    entity = Entity(
        type=payload.type,
        name=payload.name,
        canonical_name=canonicalize_name(payload.name),
        description=payload.description,
        name_origin="owner",
        description_origin="owner" if payload.description is not None else None,
        metadata_json=payload.metadata,
    )
    session.add(entity)
    try:
        await session.flush()
        aliases = [
            EntityAlias(
                entity_id=entity.id,
                alias=alias,
                normalized_alias=canonicalize_name(alias),
                confirmed=True,
                origin="owner",
            )
            for alias in payload.aliases
            if canonicalize_name(alias) != entity.canonical_name
        ]
        session.add_all(aliases)
        await session.flush()
        await session.refresh(entity)
        result = _entity_read(entity, aliases)
        await record_owner_action(
            session, actor_id=actor_id, operation="entity_create", reason=payload.reason,
            affected_ids=[entity.id], revisions={str(entity.id): 1},
        )
        await commit_with_replay(session, [make_graph_change(entity_id=entity.id)])
    except IntegrityError:
        await session.rollback()
        raise
    return result


async def update_entity(
    session: AsyncSession, entity_id: UUID, payload: EntityPatch, *, actor_id: int
) -> EntityRead | None:
    entity = await session.scalar(select(Entity).where(Entity.id == entity_id).with_for_update())
    if entity is None:
        return None
    previous_revision = entity.revision
    if entity.revision != payload.expected_revision:
        raise ValueError("Entity revision is stale")
    if not payload.model_fields_set - {"expected_revision", "reason"}:
        raise ValueError("At least one entity field is required")
    if "name" in payload.model_fields_set and payload.name is not None:
        entity.name = payload.name
        entity.canonical_name = canonicalize_name(payload.name)
        entity.name_origin = "owner"
        await session.execute(delete(EntityFieldEvidence).where(
            EntityFieldEvidence.entity_id == entity_id,
            EntityFieldEvidence.field_name == "name",
        ))
    if "description" in payload.model_fields_set:
        entity.description = payload.description
        entity.description_origin = "owner"
        await session.execute(delete(EntityFieldEvidence).where(
            EntityFieldEvidence.entity_id == entity_id,
            EntityFieldEvidence.field_name == "description",
        ))
    if "metadata" in payload.model_fields_set and payload.metadata is not None:
        entity.metadata_json = payload.metadata
    entity.revision += 1
    await session.flush()
    await session.refresh(entity)
    aliases = await _aliases(session, [entity.id])
    result = _entity_read(entity, aliases.get(entity.id))
    await record_owner_action(
        session, actor_id=actor_id, operation="entity_update", reason=payload.reason,
        affected_ids=[entity.id], revisions={str(entity.id): previous_revision},
    )
    await commit_with_replay(session, [make_graph_change(entity_id=entity.id)])
    return result


async def add_alias(
    session: AsyncSession, entity_id: UUID, payload: AliasCreate, *, actor_id: int
) -> EntityRead | None:
    entity = await session.scalar(select(Entity).where(Entity.id == entity_id).with_for_update())
    if entity is None:
        return None
    normalized = canonicalize_name(payload.alias)
    if normalized == entity.canonical_name:
        raise ValueError("Alias duplicates the canonical entity name")
    alias = EntityAlias(
        entity_id=entity.id,
        alias=payload.alias,
        normalized_alias=normalized,
        confirmed=payload.confirmed,
        origin="owner",
    )
    session.add(alias)
    await session.flush()
    aliases = await _aliases(session, [entity.id])
    result = _entity_read(entity, aliases.get(entity.id))
    await record_owner_action(
        session, actor_id=actor_id, operation="alias_create", reason=payload.reason,
        affected_ids=[entity.id, alias.id], revisions={str(entity.id): entity.revision},
    )
    await commit_with_replay(session, [make_graph_change(entity_id=entity.id)])
    return result


async def delete_alias(
    session: AsyncSession, entity_id: UUID, alias_id: UUID, *, actor_id: int, reason: str = "owner_alias_delete"
) -> bool:
    entity = await session.scalar(select(Entity).where(Entity.id == entity_id).with_for_update())
    if entity is None:
        return False
    alias = await session.scalar(
        select(EntityAlias).where(EntityAlias.id == alias_id, EntityAlias.entity_id == entity_id).with_for_update()
    )
    if alias is None:
        return False
    await session.delete(alias)
    await record_owner_action(
        session, actor_id=actor_id, operation="alias_delete", reason=reason,
        affected_ids=[entity.id, alias_id], revisions={str(entity.id): entity.revision},
    )
    await commit_with_replay(session, [make_graph_change(entity_id=entity.id)])
    return True


async def delete_entity(
    session: AsyncSession, entity_id: UUID, *, actor_id: int, reason: str = "owner_entity_delete"
) -> bool:
    entity = await session.scalar(select(Entity).where(Entity.id == entity_id).with_for_update())
    if entity is None:
        return False
    await session.delete(entity)
    await record_owner_action(
        session, actor_id=actor_id, operation="entity_delete", reason=reason,
        affected_ids=[entity.id], revisions={str(entity.id): entity.revision},
    )
    await commit_with_replay(session, [make_graph_change(entity_id=entity.id, deleted=True)])
    return True


async def support_cleanup_ids(
    session: AsyncSession, *, document_id: UUID | None = None, source_id: UUID | None = None
) -> tuple[list[UUID], list[UUID]]:
    if (document_id is None) == (source_id is None):
        raise ValueError("Specify one document or source")
    statement = select(EntityEvidenceMembership.id, EntityEvidenceMembership.entity_id)
    statement = statement.where(
        EntityEvidenceMembership.document_id == document_id
        if document_id is not None else EntityEvidenceMembership.source_id == source_id
    ).order_by(EntityEvidenceMembership.entity_id, EntityEvidenceMembership.id).limit(10_001)
    rows = list((await session.execute(statement)).all())
    if len(rows) > 10_000:
        raise ValueError("Entity support cleanup exceeds its atomic limit")
    entity_ids = {entity_id for _, entity_id in rows}
    if source_id is not None:
        entity_ids.update((await session.scalars(
            select(EntityAlias.entity_id).where(EntityAlias.source_id == source_id).distinct()
        )).all())
    return [membership_id for membership_id, _ in rows], sorted(entity_ids, key=str)


async def lock_entity_ids(session: AsyncSession, entity_ids: list[UUID]) -> None:
    ids = sorted(set(entity_ids), key=str)
    if len(ids) > 10_000:
        raise ValueError("Entity support cleanup exceeds its atomic limit")
    if ids:
        await session.scalars(
            select(Entity.id).where(Entity.id.in_(ids)).order_by(Entity.id).with_for_update()
        )


async def remove_document_support(session: AsyncSession, document_id: UUID) -> int:
    return await _remove_entity_support(session, document_id=document_id)


async def remove_source_support(session: AsyncSession, source_id: UUID) -> int:
    return await _remove_entity_support(session, source_id=source_id)


async def _remove_entity_support(
    session: AsyncSession, *, document_id: UUID | None = None, source_id: UUID | None = None
) -> int:
    if (document_id is None) == (source_id is None):
        raise ValueError("Specify one document or source")
    membership_query = select(EntityEvidenceMembership).where(
        EntityEvidenceMembership.document_id == document_id
        if document_id is not None else EntityEvidenceMembership.source_id == source_id
    ).order_by(EntityEvidenceMembership.entity_id, EntityEvidenceMembership.id).limit(10_001)
    memberships = list((await session.scalars(membership_query)).all())
    if len(memberships) > 10_000:
        raise ValueError("Entity support cleanup exceeds its atomic limit")
    membership_ids = [item.id for item in memberships]
    entity_ids = {item.entity_id for item in memberships}
    alias_ids: set[UUID] = set()
    if membership_ids:
        alias_supports = list((await session.execute(
            select(EntityAliasEvidence.id, EntityAliasEvidence.alias_id)
            .where(EntityAliasEvidence.membership_id.in_(membership_ids))
            .order_by(EntityAliasEvidence.id)
            .limit(10_001)
        )).all())
        if len(alias_supports) > 10_000:
            raise ValueError("Entity alias support cleanup exceeds its atomic limit")
        alias_ids.update(alias_id for _, alias_id in alias_supports)
        await session.execute(
            delete(EntityAliasEvidence).where(
                EntityAliasEvidence.id.in_([support_id for support_id, _ in alias_supports])
            )
        )
        await session.execute(
            delete(EntityEvidenceMembership).where(EntityEvidenceMembership.id.in_(membership_ids))
        )
    if source_id is not None:
        sourced = list((await session.scalars(
            select(EntityAlias).where(EntityAlias.source_id == source_id).order_by(EntityAlias.id).limit(10_001)
        )).all())
        if len(sourced) > 10_000:
            raise ValueError("Entity alias cleanup exceeds its atomic limit")
        alias_ids.update(item.id for item in sourced)
        entity_ids.update(item.entity_id for item in sourced)
    for alias_id in sorted(alias_ids, key=str):
        alias = await session.get(EntityAlias, alias_id)
        if alias is None:
            continue
        if source_id is not None and alias.source_id == source_id:
            alias.source_id = None
        remaining_confidence = await session.scalar(
            select(func.max(EntityAliasEvidence.confidence))
            .join(
                EntityEvidenceMembership,
                EntityEvidenceMembership.id == EntityAliasEvidence.membership_id,
            )
            .where(
                EntityAliasEvidence.alias_id == alias.id,
                EntityEvidenceMembership.entity_id == alias.entity_id,
            )
        )
        if alias.origin == "owner":
            continue
        if remaining_confidence is not None:
            alias.confidence = remaining_confidence
            continue
        # Origin-less legacy aliases carry no proof of owner authorship. Forget
        # them with their final exact support instead of upgrading their status.
        await session.delete(alias)
    await _clear_unsupported_derived_fields(session, entity_ids)
    return len(membership_ids)


async def _clear_unsupported_derived_fields(session: AsyncSession, entity_ids: set[UUID]) -> None:
    for entity_id in entity_ids:
        entity = await session.get(Entity, entity_id)
        if entity is not None:
            changed = False
            # Unknown legacy provenance is not proof that a non-owner value is safe to retain.
            if entity.name_origin != "owner" and entity.name is not None:
                name_hash = sha256(entity.name.encode("utf-8")).hexdigest()
                name_supported = entity.name_origin == "derived" and await session.scalar(
                    select(EntityFieldEvidence.id)
                    .join(
                        EntityEvidenceMembership,
                        EntityEvidenceMembership.id == EntityFieldEvidence.membership_id,
                    )
                    .where(
                        EntityFieldEvidence.entity_id == entity_id,
                        EntityFieldEvidence.field_name == "name",
                        EntityFieldEvidence.value_hash == name_hash,
                        EntityEvidenceMembership.entity_id == entity_id,
                    ).limit(1)
                ) is not None
                if not name_supported:
                    entity.name = None
                    entity.canonical_name = None
                    entity.name_origin = None
                    changed = True
            elif entity.name is None and entity.name_origin != "owner":
                changed = entity.canonical_name is not None or changed
                entity.canonical_name = None
                entity.name_origin = None
            if entity.description_origin != "owner" and entity.description is not None:
                description_hash = sha256(entity.description.encode("utf-8")).hexdigest()
                description_supported = entity.description_origin == "derived" and await session.scalar(
                    select(EntityFieldEvidence.id)
                    .join(
                        EntityEvidenceMembership,
                        EntityEvidenceMembership.id == EntityFieldEvidence.membership_id,
                    )
                    .where(
                        EntityFieldEvidence.entity_id == entity_id,
                        EntityFieldEvidence.field_name == "description",
                        EntityFieldEvidence.value_hash == description_hash,
                        EntityEvidenceMembership.entity_id == entity_id,
                    ).limit(1)
                ) is not None
                if not description_supported:
                    entity.description = None
                    entity.description_origin = None
                    changed = True
            elif entity.description is None and entity.description_origin != "owner":
                entity.description_origin = None
            if changed:
                entity.revision += 1
