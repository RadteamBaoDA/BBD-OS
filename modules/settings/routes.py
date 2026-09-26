from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis

from core.auth.dependencies import require_owner, require_owner_write
from core.auth.models import AuthSession
from core.config import Settings
from core.model_gateway.schemas import ModelMapping, ModelSettingsRead, PrivacySettings
from modules.settings import models

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
OwnerRead = Annotated[AuthSession, Depends(require_owner)]
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


def _redis(request: Request) -> Redis:
    return request.app.state.redis


@router.get("/models", response_model=ModelSettingsRead)
async def read_models(request: Request, _owner: OwnerRead) -> ModelSettingsRead:
    settings: Settings = request.app.state.settings
    redis = _redis(request)
    mappings = await models.get_mappings(redis, settings)
    return ModelSettingsRead(
        aliases=mappings,
        capabilities=await models.list_capabilities(redis, mappings),
        credential_configured=bool(settings.omniroute_api_key.get_secret_value()),
    )


@router.patch("/models", response_model=ModelSettingsRead)
async def patch_models(values: dict[str, ModelMapping], request: Request, _owner: OwnerWrite) -> ModelSettingsRead:
    if not values or any(alias not in models.ALIASES for alias in values):
        raise HTTPException(status_code=422, detail="Unknown or empty model alias mapping")
    settings: Settings = request.app.state.settings
    redis = _redis(request)
    mappings = await models.update_mappings(redis, settings, values)
    return ModelSettingsRead(
        aliases=mappings,
        capabilities=await models.list_capabilities(redis, mappings),
        credential_configured=bool(settings.omniroute_api_key.get_secret_value()),
    )


@router.get("/privacy", response_model=PrivacySettings)
async def read_privacy(request: Request, _owner: OwnerRead) -> PrivacySettings:
    return await models.get_privacy(_redis(request))


@router.patch("/privacy", response_model=PrivacySettings)
async def patch_privacy(value: PrivacySettings, request: Request, _owner: OwnerWrite) -> PrivacySettings:
    await models.save_privacy(_redis(request), value)
    return value
