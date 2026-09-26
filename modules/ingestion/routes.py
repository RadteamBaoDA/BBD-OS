from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from modules.ingestion import public
from modules.ingestion.schemas import CollectorCredentialRead, Receipt, ReceiveBatch, RunRead, StageRead

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])
Session = Annotated[AsyncSession, Depends(get_session)]
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


@router.post("/sources/{source_id}/collector-credential", response_model=CollectorCredentialRead)
async def issue_collector_credential(
    source_id: UUID,
    session: Session,
    _owner: OwnerWrite,
) -> CollectorCredentialRead:
    try:
        token = await public.create_collector_credential(session, source_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    return CollectorCredentialRead(source_id=source_id, token=token)


@router.post("/batches", response_model=Receipt, status_code=202)
async def receive_batch(
    payload: ReceiveBatch,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> Receipt:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not await public.collector_can_ingest(
        session, payload.source_id, token
    ):
        raise HTTPException(status_code=401, detail="Collector authentication required")
    batch, run = await public.receive_batch(session, payload)
    return Receipt(batch_id=batch.id, run_id=run.id, status=run.status)


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: UUID, session: Session, _owner: OwnerRead) -> RunRead:
    result = await public.get_run(session, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    run, stages = result
    return RunRead(
        run_id=run.id,
        source_id=run.source_id,
        status=run.status,
        stages=[StageRead.model_validate(stage, from_attributes=True) for stage in stages],
        error_code=run.error_code,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.post("/runs/{run_id}/retry", response_model=Receipt, status_code=202)
async def retry_run(run_id: UUID, session: Session, _owner: OwnerWrite) -> Receipt:
    run = await public.retry_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return Receipt(batch_id=run.batch_id, run_id=run.id, status=run.status)
