from typing import Annotated
from pathlib import PurePosixPath, PureWindowsPath
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.database import get_session
from core.storage import save_upload, storage_path
from modules.ingestion import public
from modules.ingestion.files import validate_upload
from modules.ingestion.schemas import CollectorCredentialRead, Receipt, ReceiveBatch, RunRead, StageRead

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])
documents_router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
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


@documents_router.post("/upload", response_model=Receipt, status_code=202)
async def upload_document(
    request: Request,
    source_id: Annotated[UUID, Form()],
    upload: Annotated[UploadFile, File(alias="file")],
    session: Session,
    _owner: OwnerWrite,
) -> Receipt:
    settings = request.app.state.settings
    if upload.size is not None and upload.size > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Upload exceeds the configured size limit")
    try:
        suffix, mime_type, original_name = validate_upload(
            upload.filename, upload.content_type, upload.file
        )
        document_id = uuid4()
        raw_uri, size, digest = await save_upload(
            settings.data_dir, upload, document_id, suffix, settings.upload_max_bytes
        )
    except ValueError as exc:
        status = 413 if "size limit" in str(exc) else 415
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    filename = "".join(
        character
        for character in PurePosixPath(PureWindowsPath(original_name).name).name
        if ord(character) >= 32 and ord(character) != 127
    )[:255] or "upload"
    try:
        run, created = await public.receive_file(
            session, source_id, document_id, filename, mime_type, raw_uri, size, digest
        )
    except (HTTPException, ValueError, LookupError):
        storage_path(settings.data_dir, raw_uri).unlink(missing_ok=True)
        raise
    if not created:
        storage_path(settings.data_dir, raw_uri).unlink(missing_ok=True)
    return Receipt(batch_id=run.batch_id, run_id=run.id, status=run.status)
