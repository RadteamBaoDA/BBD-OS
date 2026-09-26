from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.config import Settings
from core.database import get_session
from modules.search import indexing, public
from modules.search.schemas import ReindexResponse, SearchIndexStatus, SearchRequest, SearchResponse

router = APIRouter(prefix="/api/v1/search", tags=["search"])
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


@router.post("", response_model=SearchResponse)
async def search(payload: SearchRequest, request: Request, session: Session, _owner: OwnerRead) -> SearchResponse:
    return await public.search(session, request.app.state.redis, request.app.state.settings, payload)


@router.get("/index", response_model=SearchIndexStatus)
async def index_status(session: Session, _owner: OwnerRead) -> SearchIndexStatus:
    return await public.index_status(session)


@router.post("/reindex", response_model=ReindexResponse, status_code=202)
async def reindex(request: Request, session: Session, _owner: OwnerWrite) -> ReindexResponse:
    redis: Redis = request.app.state.redis
    settings: Settings = request.app.state.settings
    mapping, policy = await indexing.configured_embedding(redis, settings)
    if mapping is None or not mapping.model.strip() or mapping.destination != "remote" or not policy.embeddings_allowed:
        raise HTTPException(status_code=409, detail="Configure and permit a remote embedding model first")
    generation = await indexing.create_generation(session, mapping)
    return ReindexResponse(run_id=generation.id)
