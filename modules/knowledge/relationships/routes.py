from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from modules.knowledge.entities.public import RedirectedEntityConflict
from modules.knowledge.relationships import public
from modules.knowledge.relationships.schemas import EvidencePage, RelationshipCreate, RelationshipPage, RelationshipRead

router = APIRouter(prefix="/api/v1/relationships", tags=["knowledge"])
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


@router.get("", response_model=RelationshipPage)
async def list_relationships(
    session: Session,
    _owner: OwnerRead,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    entity_id: UUID | None = None,
) -> RelationshipPage:
    """List bounded relationships for the authenticated owner."""
    return await public.list_relationships(session, limit, cursor, entity_id)


@router.post("", response_model=RelationshipRead, status_code=201)
async def create_relationship(payload: RelationshipCreate, session: Session, owner: OwnerWrite) -> RelationshipRead:
    """Create an authorized relationship using the requested owner or derived origin.

    Public validation checks endpoint/evidence membership and derives confidence
    from evidence for derived facts; redirected/missing endpoints map to HTTP
    errors. Route authorization does not rewrite the supplied origin.
    """
    try:
        return await public.create_relationship(session, payload, actor_id=owner.owner_id)
    except RedirectedEntityConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_REDIRECTED", "message": str(exc), "details": {}}) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{relationship_id}", status_code=204)
async def delete_relationship(
    relationship_id: UUID, session: Session, owner: OwnerWrite,
    reason: Annotated[str, Query(min_length=1, max_length=300)] = "owner_relationship_delete",
) -> None:
    """Delete a relationship using the authenticated owner and bounded audit reason."""
    try:
        if not await public.remove_relationship(session, relationship_id, actor_id=owner.owner_id, reason=reason):
            raise HTTPException(status_code=404, detail="Relationship not found")
    except RedirectedEntityConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "ENTITY_REDIRECTED", "message": str(exc), "details": {}}) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{relationship_id}/evidence", response_model=EvidencePage)
async def list_evidence(
    relationship_id: UUID,
    session: Session,
    _owner: OwnerRead,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = Query(default=None, max_length=512),
) -> EvidencePage:
    """Return bounded relationship evidence or 404 when the relationship is absent."""
    rows, next_cursor = await public.list_relationship_evidence(session, relationship_id, limit, cursor)
    if rows is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return EvidencePage(items=rows, next_cursor=next_cursor)
