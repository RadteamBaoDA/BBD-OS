import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, desc, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from core.pagination import decode_cursor, encode_cursor
from core.realtime import commit_with_replay, make_graph_change
from modules.knowledge.documents import public as documents
from modules.knowledge.entities import public as entities
from modules.knowledge.relationships.models import Relationship, RelationshipEvidence
from modules.knowledge.relationships.schemas import (
    EvidenceRead,
    EntityGraphRead,
    NeighborPage,
    NeighborRead,
    RelationshipCreate,
    RelationshipPage,
    RelationshipRead,
)

MAX_CLEANUP_SUPPORTS = 10_000


def _relationship_read(
    relationship: Relationship, evidence: list[EvidenceRead] | None = None
) -> RelationshipRead:
    return RelationshipRead(
        id=relationship.id,
        source_entity_id=relationship.source_entity_id,
        target_entity_id=relationship.target_entity_id,
        type=relationship.type,
        origin=relationship.origin,
        confidence=relationship.confidence,
        valid_from=relationship.valid_from,
        valid_to=relationship.valid_to,
        metadata=relationship.metadata_json,
        created_at=relationship.created_at,
        evidence=evidence or [],
    )


async def publish_extracted_relationship(
    session: AsyncSession,
    *,
    source_entity_id: UUID,
    target_entity_id: UUID,
    relationship_type: str,
    document_version_id: UUID,
    chunk_id: UUID,
    source_membership_id: UUID,
    target_membership_id: UUID,
    confidence: float,
) -> UUID | None:
    """Publish evidence-backed extraction inside the caller's source transaction."""
    if source_entity_id == target_entity_id:
        return None
    refs = await documents.read_evidence_refs(session, [(document_version_id, chunk_id)])
    memberships = await entities.get_membership_refs(
        session, [source_membership_id, target_membership_id], for_write=True
    )
    by_id = {item.id: item for item in memberships}
    source_membership, target_membership = by_id[source_membership_id], by_id[target_membership_id]
    for item, entity_id in ((source_membership, source_entity_id), (target_membership, target_entity_id)):
        if item.entity_id != entity_id or item.document_version_id != document_version_id or item.chunk_id != chunk_id:
            raise ValueError("Relationship evidence memberships do not match the cited chunk")
    ref = refs[0]
    relationship = await session.scalar(select(Relationship).where(
        Relationship.source_entity_id == source_entity_id,
        Relationship.target_entity_id == target_entity_id,
        Relationship.type == relationship_type,
        Relationship.origin == "derived",
        Relationship.valid_from.is_(None),
        Relationship.valid_to.is_(None),
    ).with_for_update())
    if relationship is None:
        relationship = Relationship(
            source_entity_id=source_entity_id, target_entity_id=target_entity_id,
            type=relationship_type, origin="derived", confidence=confidence,
        )
        session.add(relationship)
        await session.flush()
    evidence = await session.scalar(select(RelationshipEvidence).where(
        RelationshipEvidence.relationship_id == relationship.id,
        RelationshipEvidence.document_version_id == document_version_id,
        RelationshipEvidence.chunk_id == chunk_id,
    ).with_for_update())
    if evidence is None:
        session.add(RelationshipEvidence(
            relationship_id=relationship.id, document_version_id=document_version_id,
            chunk_id=chunk_id, document_id=ref.document_id, source_id=ref.source_id,
            observed_at=ref.observed_at, confidence=confidence,
            source_membership_id=source_membership_id, target_membership_id=target_membership_id,
        ))
    else:
        evidence.confidence = max(evidence.confidence, confidence)
    await session.flush()
    supported_confidence = await session.scalar(select(func.max(RelationshipEvidence.confidence)).where(
        RelationshipEvidence.relationship_id == relationship.id,
    ))
    if supported_confidence is not None:
        relationship.confidence = supported_confidence
    return relationship.id


async def _evidence_read(session: AsyncSession, rows: list[RelationshipEvidence]) -> list[EvidenceRead]:
    if not rows:
        return []
    pairs = [(row.document_version_id, row.chunk_id) for row in rows]
    refs = await documents.read_evidence_refs(session, pairs)
    by_pair = {(ref.document_version_id, ref.chunk_id): ref for ref in refs}
    return [
        EvidenceRead(
            id=row.id,
            relationship_id=row.relationship_id,
            document_id=ref.document_id,
            document_version_id=ref.document_version_id,
            version_number=ref.version_number,
            chunk_id=ref.chunk_id,
            observed_at=ref.observed_at,
            extracted_at=row.extracted_at,
            confidence=row.confidence,
            source_entity_membership_id=row.source_membership_id,
            target_entity_membership_id=row.target_membership_id,
            title=ref.title,
            canonical_url=ref.canonical_url,
            source_id=ref.source_id,
            excerpt=ref.excerpt,
            metadata_is_version_snapshot=ref.metadata_is_version_snapshot,
        )
        for row in rows
        if (ref := by_pair.get((row.document_version_id, row.chunk_id))) is not None
    ]


async def list_relationships(
    session: AsyncSession, limit: int, cursor: str | None, entity_id: UUID | None = None
) -> RelationshipPage:
    statement = select(Relationship)
    if entity_id is not None:
        statement = statement.where(
            or_(Relationship.source_entity_id == entity_id, Relationship.target_entity_id == entity_id)
        )
    if cursor:
        created_at, identifier = decode_cursor(cursor)
        statement = statement.where(tuple_(Relationship.created_at, Relationship.id) < (created_at, identifier))
    rows = list((await session.scalars(
        statement.order_by(desc(Relationship.created_at), desc(Relationship.id)).limit(limit + 1)
    )).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return RelationshipPage(items=[_relationship_read(row) for row in rows], next_cursor=next_cursor)


async def list_relationship_evidence(
    session: AsyncSession, relationship_id: UUID, limit: int, cursor: str | None
) -> tuple[list[EvidenceRead] | None, str | None]:
    if await session.get(Relationship, relationship_id) is None:
        return None, None
    statement = select(RelationshipEvidence).where(RelationshipEvidence.relationship_id == relationship_id)
    if cursor:
        extracted_at, identifier = decode_cursor(cursor)
        statement = statement.where(tuple_(RelationshipEvidence.extracted_at, RelationshipEvidence.id) > (extracted_at, identifier))
    rows = list((await session.scalars(
        statement.order_by(RelationshipEvidence.extracted_at, RelationshipEvidence.id).limit(limit + 1)
    )).all())
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].extracted_at, rows[-1].id) if more and rows else None
    return await _evidence_read(session, rows), next_cursor


def _encode_neighbor_cursor(focus_id: UUID, created_at: datetime, relationship_id: UUID) -> str:
    raw = json.dumps([str(focus_id), encode_cursor(created_at, relationship_id)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_neighbor_cursor(cursor: str, focus_id: UUID) -> tuple[object, UUID]:
    if len(cursor) > 512 or "=" in cursor:
        raise ValueError("Invalid neighbor cursor")
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != cursor:
            raise ValueError("Invalid neighbor cursor")
        focus, cursor_value = json.loads(raw)
        if focus != str(focus_id):
            raise ValueError("Neighbor cursor belongs to another entity")
        return decode_cursor(cursor_value)
    except (ValueError, TypeError, KeyError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError("Invalid neighbor cursor") from exc


async def get_neighbors(
    session: AsyncSession, entity_id: UUID, limit: int = 50, cursor: str | None = None
) -> NeighborPage | None:
    if not 2 <= limit <= 100:
        raise ValueError("Neighbor page limit must be between 2 and 100 total nodes")
    try:
        await entities.get_entity_refs(session, [entity_id])
    except LookupError:
        return None
    statement = select(Relationship).where(
        or_(Relationship.source_entity_id == entity_id, Relationship.target_entity_id == entity_id)
    )
    if cursor:
        created_at, relationship_id = _decode_neighbor_cursor(cursor, entity_id)
        statement = statement.where(tuple_(Relationship.created_at, Relationship.id) < (created_at, relationship_id))
    rows = list((await session.scalars(
        statement.order_by(desc(Relationship.created_at), desc(Relationship.id)).limit(limit + 1)
    )).all())
    truncated = len(rows) > limit - 1
    rows = rows[: limit - 1]
    neighbor_ids = list(dict.fromkeys(
        row.target_entity_id if row.source_entity_id == entity_id else row.source_entity_id for row in rows
    ))
    refs = await entities.get_entity_refs(session, neighbor_ids) if neighbor_ids else []
    by_id = {ref.requested_id: ref for ref in refs}
    items = [
        NeighborRead(
            entity=EntityGraphRead(
                id=by_id[neighbor_id].canonical_id, type=by_id[neighbor_id].type,
                name=by_id[neighbor_id].name, revision=by_id[neighbor_id].revision,
            ),
            relationship=_relationship_read(row),
        )
        for row in rows
        if (neighbor_id := (row.target_entity_id if row.source_entity_id == entity_id else row.source_entity_id)) in by_id
    ]
    next_cursor = _encode_neighbor_cursor(entity_id, rows[-1].created_at, rows[-1].id) if truncated and rows else None
    return NeighborPage(items=items, truncated=truncated, next_cursor=next_cursor)


async def create_relationship(
    session: AsyncSession, payload: RelationshipCreate, *, actor_id: int
) -> RelationshipRead:
    if payload.source_entity_id == payload.target_entity_id:
        raise ValueError("Relationship endpoints must be different")
    if payload.origin == "derived" and not payload.evidence:
        raise ValueError("Derived relationships require at least one evidence reference")
    pairs = [(item.document_version_id, item.chunk_id) for item in payload.evidence]
    if len(set(pairs)) != len(pairs):
        raise ValueError("Evidence references must be unique")
    evidence_refs = await documents.read_evidence_refs(session, pairs, for_write=bool(pairs))
    by_pair = {(ref.document_version_id, ref.chunk_id): ref for ref in evidence_refs}
    endpoints = [payload.source_entity_id, payload.target_entity_id]
    try:
        await entities.get_entity_refs(session, endpoints, for_write=True)
    except LookupError as exc:
        raise LookupError("Relationship entity not found") from exc
    membership_ids = [
        identifier
        for item in payload.evidence
        for identifier in (item.source_membership_id, item.target_membership_id)
        if identifier is not None
    ]
    try:
        memberships = await entities.get_membership_refs(session, membership_ids, for_write=True)
    except LookupError as exc:
        raise ValueError("Relationship endpoint evidence membership is missing") from exc
    memberships_by_id = {item.id: item for item in memberships}
    evidence_rows: list[RelationshipEvidence] = []
    for item in payload.evidence:
        pair = (item.document_version_id, item.chunk_id)
        ref = by_pair.get(pair)
        if ref is None:
            raise ValueError("Relationship evidence does not exist")
        for membership_id, expected_entity_id in (
            (item.source_membership_id, payload.source_entity_id),
            (item.target_membership_id, payload.target_entity_id),
        ):
            membership = memberships_by_id.get(membership_id) if membership_id else None
            if payload.origin == "derived" and membership is None:
                raise ValueError("Derived evidence must identify both endpoint memberships")
            if membership is not None and (
                membership.entity_id != expected_entity_id
                or (membership.document_version_id, membership.chunk_id) != pair
            ):
                raise ValueError("Evidence membership does not match the relationship endpoint and evidence")
        evidence_rows.append(RelationshipEvidence(
            document_version_id=item.document_version_id,
            chunk_id=item.chunk_id,
            document_id=ref.document_id,
            source_id=ref.source_id,
            observed_at=ref.observed_at,
            confidence=item.confidence,
            source_membership_id=item.source_membership_id,
            target_membership_id=item.target_membership_id,
        ))
    relationship = Relationship(
        source_entity_id=payload.source_entity_id,
        target_entity_id=payload.target_entity_id,
        type=payload.type,
        origin=payload.origin,
        confidence=(max((item.confidence for item in payload.evidence), default=None)
                    if payload.origin == "derived" else payload.confidence),
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        metadata_json=payload.metadata,
    )
    session.add(relationship)
    await session.flush()
    for evidence in evidence_rows:
        evidence.relationship_id = relationship.id
    session.add_all(evidence_rows)
    await session.flush()
    evidence_read = await _evidence_read(session, evidence_rows)
    result = _relationship_read(relationship, evidence_read)
    await entities.record_owner_action(
        session, actor_id=actor_id, operation="relationship_create", reason=payload.reason,
        affected_ids=[relationship.id, *endpoints],
    )
    await commit_with_replay(session, [make_graph_change(relationship_id=relationship.id)])
    return result


async def remove_relationship(
    session: AsyncSession, relationship_id: UUID, *, actor_id: int, reason: str = "owner_relationship_delete"
) -> bool:
    hint = await session.get(Relationship, relationship_id)
    if hint is None:
        return False
    endpoints = [hint.source_entity_id, hint.target_entity_id]
    await entities.get_entity_refs(session, endpoints, for_write=True)
    relationship = await session.scalar(
        select(Relationship).where(Relationship.id == relationship_id).with_for_update()
    )
    if relationship is None:
        return False
    await session.delete(relationship)
    await entities.record_owner_action(
        session, actor_id=actor_id, operation="relationship_delete", reason=reason,
        affected_ids=[relationship_id, *endpoints],
    )
    await commit_with_replay(session, [make_graph_change(relationship_id=relationship_id, deleted=True)])
    return True


async def support_cleanup_ids(
    session: AsyncSession, *, refs: list[tuple[UUID, UUID]], document_id: UUID | None = None,
    source_id: UUID | None = None, membership_ids: list[UUID] | None = None,
) -> tuple[list[UUID], list[UUID]]:
    if (document_id is None) == (source_id is None):
        raise ValueError("Specify one document or source")
    statement = select(RelationshipEvidence.relationship_id).where(
        or_(
            RelationshipEvidence.document_id == document_id if document_id else RelationshipEvidence.source_id == source_id,
            tuple_(RelationshipEvidence.document_version_id, RelationshipEvidence.chunk_id).in_(refs) if refs else False,
            RelationshipEvidence.source_membership_id.in_(membership_ids) if membership_ids else False,
            RelationshipEvidence.target_membership_id.in_(membership_ids) if membership_ids else False,
        )
    )
    relation_ids = sorted(set((await session.scalars(statement.limit(MAX_CLEANUP_SUPPORTS + 1))).all()), key=str)
    if len(relation_ids) > MAX_CLEANUP_SUPPORTS:
        raise ValueError("Relationship support cleanup exceeds its atomic limit")
    if not relation_ids:
        return [], []
    rows = (await session.execute(
        select(Relationship.source_entity_id, Relationship.target_entity_id)
        .where(Relationship.id.in_(relation_ids))
    )).all()
    entity_ids = sorted({identifier for row in rows for identifier in row}, key=str)
    return relation_ids, entity_ids


async def lock_relationship_ids(session: AsyncSession, relationship_ids: list[UUID]) -> None:
    ids = sorted(set(relationship_ids), key=str)
    if len(ids) > MAX_CLEANUP_SUPPORTS:
        raise ValueError("Relationship support cleanup exceeds its atomic limit")
    if ids:
        await session.scalars(
            select(Relationship.id).where(Relationship.id.in_(ids)).order_by(Relationship.id).with_for_update()
        )


async def remove_document_support(
    session: AsyncSession, *, document_id: UUID, refs: list[tuple[UUID, UUID]], membership_ids: list[UUID]
) -> int:
    return await _remove_support(session, document_id=document_id, refs=refs, membership_ids=membership_ids)


async def remove_source_support(
    session: AsyncSession, *, source_id: UUID, refs: list[tuple[UUID, UUID]], membership_ids: list[UUID]
) -> int:
    return await _remove_support(session, source_id=source_id, refs=refs, membership_ids=membership_ids)


async def _remove_support(
    session: AsyncSession, *, refs: list[tuple[UUID, UUID]], membership_ids: list[UUID],
    document_id: UUID | None = None, source_id: UUID | None = None,
) -> int:
    statement = select(RelationshipEvidence).where(or_(
        RelationshipEvidence.document_id == document_id if document_id else RelationshipEvidence.source_id == source_id,
        tuple_(RelationshipEvidence.document_version_id, RelationshipEvidence.chunk_id).in_(refs) if refs else False,
        RelationshipEvidence.source_membership_id.in_(membership_ids) if membership_ids else False,
        RelationshipEvidence.target_membership_id.in_(membership_ids) if membership_ids else False,
    )).limit(MAX_CLEANUP_SUPPORTS + 1)
    rows = list((await session.scalars(statement)).all())
    if len(rows) > MAX_CLEANUP_SUPPORTS:
        raise ValueError("Relationship support cleanup exceeds its atomic limit")
    affected = sorted({row.relationship_id for row in rows}, key=str)
    await session.execute(delete(RelationshipEvidence).where(RelationshipEvidence.id.in_([row.id for row in rows])))
    for relationship_id in affected:
        relationship = await session.get(Relationship, relationship_id)
        if relationship is None or relationship.origin != "derived":
            continue
        remaining = list((await session.scalars(
            select(RelationshipEvidence).where(RelationshipEvidence.relationship_id == relationship_id)
        )).all())
        if not remaining:
            await session.delete(relationship)
        else:
            relationship.confidence = max(row.confidence for row in remaining)
    return len(rows)
