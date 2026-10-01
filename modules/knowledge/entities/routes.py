from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from modules.knowledge.entities import corrections, public
from modules.knowledge.entities.corrections import CorrectionConflictError
from modules.knowledge.entities.schemas import (
    AliasCreate, EntityCorrectionPreview, EntityCorrectionResult, EntityCreate,
    EntityEvidencePage, EntityExtractionStatus, EntityMergeRequest,
    EntityPage, EntityPatch, EntityRead, EntitySplitRequest, EntitySuppressionRequest,
)
from modules.knowledge.relationships import public as relationships
from modules.knowledge.relationships.schemas import NeighborPage

router = APIRouter(tags=["knowledge"])
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


@router.get("/api/v1/entities/extractions/{document_version_id}", response_model=EntityExtractionStatus)
async def get_extraction_status(document_version_id: UUID, session: Session, _owner: OwnerRead) -> EntityExtractionStatus:
    result = await public.get_extraction_status(session, document_version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Entity extraction status not found")
    return result


@router.get("/api/v1/entities", response_model=EntityPage)
async def list_entities(
    session: Session,
    _owner: OwnerRead,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    entity_type: Annotated[str | None, Query(alias="type", max_length=32)] = None,
    q: Annotated[str | None, Query(max_length=300)] = None,
) -> EntityPage:
    return await public.list_entities(session, limit, cursor, entity_type, q)


@router.post("/api/v1/entities", response_model=EntityRead, status_code=201)
async def create_entity(payload: EntityCreate, session: Session, owner: OwnerWrite) -> EntityRead:
    try:
        return await public.create_entity(session, payload, actor_id=owner.owner_id)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Entity alias already exists") from exc


@router.get("/api/v1/entities/{entity_id}/neighbors", response_model=NeighborPage)
async def get_neighbors(
    entity_id: UUID,
    session: Session,
    _owner: OwnerRead,
    limit: Annotated[int, Query(ge=2, le=100)] = 50,
    cursor: str | None = Query(default=None, max_length=512),
) -> NeighborPage:
    try:
        result = await relationships.get_neighbors(session, entity_id, limit, cursor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


@router.post("/api/v1/entities/{entity_id}/aliases", response_model=EntityRead, status_code=201)
async def add_alias(entity_id: UUID, payload: AliasCreate, session: Session, owner: OwnerWrite) -> EntityRead:
    try:
        result = await public.add_alias(session, entity_id, payload, actor_id=owner.owner_id)
    except public.TerminalEntityConflict as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except public.RedirectedEntityConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_REDIRECTED", "message": str(exc), "details": {}}) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Alias already exists for this entity") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return result


@router.delete("/api/v1/entities/{entity_id}/aliases/{alias_id}", status_code=204)
async def delete_alias(
    entity_id: UUID, alias_id: UUID, session: Session, owner: OwnerWrite,
    reason: Annotated[str, Query(min_length=1, max_length=300)] = "owner_alias_delete",
) -> None:
    try:
        if not await public.delete_alias(session, entity_id, alias_id, actor_id=owner.owner_id, reason=reason):
            raise HTTPException(status_code=404, detail="Alias not found")
    except public.TerminalEntityConflict as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except public.RedirectedEntityConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_REDIRECTED", "message": str(exc), "details": {}}) from exc


@router.get("/api/v1/entities/{entity_id}", response_model=EntityRead)
async def get_entity(entity_id: UUID, session: Session, _owner: OwnerRead) -> EntityRead:
    entity = await public.get_entity(session, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/api/v1/entities/{entity_id}/evidence", response_model=EntityEvidencePage)
async def list_evidence(
    entity_id: UUID, session: Session, _owner: OwnerRead,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> EntityEvidencePage:
    try:
        page = await public.list_entity_evidence(session, entity_id, limit, cursor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if page is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return page


@router.post("/api/v1/entities/{entity_id}/corrections/merge-preview", response_model=EntityCorrectionPreview)
async def preview_merge(
    entity_id: UUID, payload: EntityMergeRequest, session: Session, _owner: OwnerRead,
) -> EntityCorrectionPreview:
    return await corrections.preview_merge(session, entity_id, payload)


@router.post("/api/v1/entities/{entity_id}/corrections/split-preview", response_model=EntityCorrectionPreview)
async def preview_split(
    entity_id: UUID, payload: EntitySplitRequest, session: Session, _owner: OwnerRead,
) -> EntityCorrectionPreview:
    return await corrections.preview_split(session, entity_id, payload)


@router.post("/api/v1/entities/{entity_id}/merge", response_model=EntityCorrectionResult)
async def merge_entity(
    entity_id: UUID, payload: EntityMergeRequest, session: Session, owner: OwnerWrite,
) -> EntityCorrectionResult:
    try:
        return await corrections.merge_entity(session, entity_id, payload, actor_id=owner.owner_id)
    except CorrectionConflictError as exc:
        if exc.conflict.code == "entity_missing":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail={
            "code": "ENTITY_CORRECTION_CONFLICT", "message": str(exc),
            "details": {"conflicts": [exc.conflict.model_dump(mode="json")]},
        }) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_CORRECTION_CONFLICT", "message": str(exc), "details": {}}) from exc


@router.post("/api/v1/entities/{entity_id}/split", response_model=EntityCorrectionResult)
async def split_entity(
    entity_id: UUID, payload: EntitySplitRequest, session: Session, owner: OwnerWrite,
) -> EntityCorrectionResult:
    try:
        return await corrections.split_entity(session, entity_id, payload, actor_id=owner.owner_id)
    except CorrectionConflictError as exc:
        if exc.conflict.code == "entity_missing":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail={
            "code": "ENTITY_CORRECTION_CONFLICT", "message": str(exc),
            "details": {"conflicts": [exc.conflict.model_dump(mode="json")]},
        }) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_CORRECTION_CONFLICT", "message": str(exc), "details": {}}) from exc


@router.post("/api/v1/entities/{entity_id}/suppressions", response_model=EntityCorrectionResult)
async def suppress_candidates(
    entity_id: UUID, payload: EntitySuppressionRequest, session: Session, owner: OwnerWrite,
) -> EntityCorrectionResult:
    try:
        return await corrections.suppress_candidates(session, entity_id, payload, actor_id=owner.owner_id)
    except CorrectionConflictError as exc:
        if exc.conflict.code == "entity_missing":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail={
            "code": "ENTITY_CORRECTION_CONFLICT", "message": str(exc),
            "details": {"conflicts": [exc.conflict.model_dump(mode="json")]},
        }) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_CORRECTION_CONFLICT", "message": str(exc), "details": {}}) from exc


@router.patch("/api/v1/entities/{entity_id}", response_model=EntityRead)
async def update_entity(entity_id: UUID, payload: EntityPatch, session: Session, owner: OwnerWrite) -> EntityRead:
    try:
        entity = await public.update_entity(session, entity_id, payload, actor_id=owner.owner_id)
    except public.TerminalEntityConflict as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.delete("/api/v1/entities/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: UUID, session: Session, owner: OwnerWrite,
    reason: Annotated[str, Query(min_length=1, max_length=300)] = "owner_entity_delete",
) -> None:
    try:
        if not await public.delete_entity(session, entity_id, actor_id=owner.owner_id, reason=reason):
            raise HTTPException(status_code=404, detail="Entity not found")
    except public.TerminalEntityConflict as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CorrectionConflictError as exc:
        if exc.conflict.code == "entity_missing":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail={"code": exc.conflict.code.upper(), "message": str(exc), "details": {"conflict": exc.conflict.model_dump(mode="json")}}) from exc
    except public.RedirectedEntityConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_REDIRECTED", "message": str(exc), "details": {}}) from exc
