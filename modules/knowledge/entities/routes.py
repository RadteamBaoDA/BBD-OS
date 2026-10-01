from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from modules.knowledge.entities import public
from modules.knowledge.entities.schemas import AliasCreate, EntityCreate, EntityPage, EntityPatch, EntityRead
from modules.knowledge.relationships import public as relationships
from modules.knowledge.relationships.schemas import NeighborPage

router = APIRouter(tags=["knowledge"])
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


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
    if not await public.delete_alias(session, entity_id, alias_id, actor_id=owner.owner_id, reason=reason):
        raise HTTPException(status_code=404, detail="Alias not found")


@router.get("/api/v1/entities/{entity_id}", response_model=EntityRead)
async def get_entity(entity_id: UUID, session: Session, _owner: OwnerRead) -> EntityRead:
    entity = await public.get_entity(session, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.patch("/api/v1/entities/{entity_id}", response_model=EntityRead)
async def update_entity(entity_id: UUID, payload: EntityPatch, session: Session, owner: OwnerWrite) -> EntityRead:
    try:
        entity = await public.update_entity(session, entity_id, payload, actor_id=owner.owner_id)
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
    if not await public.delete_entity(session, entity_id, actor_id=owner.owner_id, reason=reason):
        raise HTTPException(status_code=404, detail="Entity not found")
