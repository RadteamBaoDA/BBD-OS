from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from core.config import Settings
from core.model_gateway.cache import capability_alias_pattern, capability_key, capability_model_pattern
from core.model_gateway.schemas import CapabilityResult, ModelMapping, PrivacySettings

ALIASES = ("reasoning-large", "reasoning-small", "fast", "embedding", "reranker", "vision", "local-private")
_MAPPINGS = "bbd:settings:model-mappings"
_PRIVACY = "bbd:settings:privacy"
CAPABILITY_TTL_SECONDS = 86400


async def get_mappings(redis: Redis, settings: Settings) -> dict[str, ModelMapping]:
    configured = {name: ModelMapping(model=model) for name, model in settings.omniroute_models.items() if name in ALIASES}
    stored = await redis.hgetall(_MAPPINGS)
    for alias, value in stored.items():
        try:
            if isinstance(alias, bytes):
                alias = alias.decode("utf-8")
            if alias not in ALIASES:
                continue
            configured[alias] = ModelMapping.model_validate_json(value)
        except (ValueError, UnicodeDecodeError):
            continue
    return configured


async def update_mappings(redis: Redis, settings: Settings, updates: dict[str, ModelMapping]) -> dict[str, ModelMapping]:
    current = await get_mappings(redis, settings)
    pipe = redis.pipeline(transaction=True)
    for alias, mapping in updates.items():
        if alias not in ALIASES:
            continue
        if current.get(alias) != mapping:
            async for key in redis.scan_iter(match=capability_alias_pattern(alias)):
                pipe.delete(key)
        pipe.hset(_MAPPINGS, alias, mapping.model_dump_json())
    await pipe.execute()
    current.update(updates)
    return current


async def get_privacy(redis: Redis) -> PrivacySettings:
    value = await redis.get(_PRIVACY)
    if value:
        try:
            return PrivacySettings.model_validate_json(value)
        except ValueError:
            pass
    return PrivacySettings()


async def save_privacy(redis: Redis, value: PrivacySettings) -> None:
    await redis.set(_PRIVACY, value.model_dump_json())


async def save_capability(redis: Redis, result: CapabilityResult) -> None:
    await redis.set(
        capability_key(result.alias, result.model, result.version, result.capability),
        result.model_dump_json(),
        ex=CAPABILITY_TTL_SECONDS,
    )


async def list_capabilities(redis: Redis, mappings: dict[str, ModelMapping]) -> list[CapabilityResult]:
    output = []
    for alias, mapping in mappings.items():
        async for key in redis.scan_iter(match=capability_model_pattern(alias, mapping.model, mapping.version)):
            value = await redis.get(key)
            if value:
                try:
                    output.append(CapabilityResult.model_validate_json(value))
                except ValueError:
                    continue
    return output


def new_capability_result(alias: str, model: str, version: str | None, capability: str, result: str) -> CapabilityResult:
    now = datetime.now(UTC)
    return CapabilityResult(
        alias=alias,
        model=model,
        version=version,
        capability=capability,
        result=result,
        checked_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=CAPABILITY_TTL_SECONDS)).isoformat(),
    )
