from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from modules.sources import public
from modules.sources.schemas import SourceCreate, SourceList, SourcePatch, SourceRead

router = APIRouter(
    prefix="/api/v1/sources",
    tags=["sources"],
)
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


@router.get("", response_model=SourceList)
async def list_sources(
    session: Session,
    _owner: OwnerRead,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> SourceList:
    items, next_cursor = await public.list_sources(session, limit, cursor)
    return SourceList(
        items=[SourceRead.model_validate(item, from_attributes=True) for item in items],
        next_cursor=next_cursor,
    )


@router.post("", response_model=SourceRead, status_code=201)
async def create_source(payload: SourceCreate, session: Session, _owner: OwnerWrite) -> SourceRead:
    source = await public.create_source(session, payload)
    return SourceRead.model_validate(source, from_attributes=True)


@router.get("/{source_id}", response_model=SourceRead)
async def get_source(source_id: UUID, session: Session, _owner: OwnerRead) -> SourceRead:
    source = await public.get_source(session, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceRead.model_validate(source, from_attributes=True)


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: UUID, payload: SourcePatch, session: Session, _owner: OwnerWrite
) -> SourceRead:
    source = await public.get_source(session, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not payload.model_fields_set or any(
        getattr(payload, key) is None for key in payload.model_fields_set
    ):
        raise HTTPException(status_code=422, detail="At least one non-null field is required")
    source = await public.update_source(session, source, payload)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceRead.model_validate(source, from_attributes=True)


@router.delete("/{source_id}", response_model=SourceRead)
async def delete_source(
    source_id: UUID,
    session: Session,
    _owner: OwnerWrite,
    with_data: bool = False,
) -> SourceRead:
    source = await public.archive_source(session, source_id, with_data)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceRead.model_validate(source, from_attributes=True)
