from datetime import UTC, datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from redis.asyncio import Redis

from core.config import Settings
from core.model_gateway.cache import capability_alias_pattern, capability_key
from core.model_gateway.schemas import CapabilityResult, ModelMapping
from core.database import Base


class AISettingsRecord(Base):
    __tablename__ = "ai_settings"
    __table_args__ = (
        CheckConstraint("owner_id = 1", name="ck_ai_settings_single_owner"),
        CheckConstraint("configuration_revision > 0", name="ck_ai_settings_revision_positive"),
        CheckConstraint("request_timeout_seconds BETWEEN 5 AND 180", name="ck_ai_settings_timeout"),
    )

    owner_id: Mapped[int] = mapped_column(ForeignKey("owner.id", ondelete="CASCADE"), primary_key=True)
    configuration_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    omniroute_base_url: Mapped[str | None] = mapped_column(Text)
    omniroute_api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    privacy: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    chat_alias: Mapped[str] = mapped_column(String(32), nullable=False, server_default="reasoning-large")
    brief_alias: Mapped[str] = mapped_column(String(32), nullable=False, server_default="reasoning-small")
    web_search_provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default="none")
    web_search_endpoint: Mapped[str | None] = mapped_column(Text)
    web_search_api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    request_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

ALIASES = ("reasoning-large", "reasoning-small", "fast", "embedding", "reranker", "vision", "local-private")
_MAPPINGS = "bbd:settings:model-mappings"


async def legacy_aliases(redis: Redis | None, settings: Settings) -> dict[str, ModelMapping]:
    configured = {name: ModelMapping(model=model, destination="remote") for name, model in settings.omniroute_models.items() if name in ALIASES}
    if redis is not None:
        for alias, value in (await redis.hgetall(_MAPPINGS)).items():
            try:
                if alias in ALIASES:
                    configured[alias] = ModelMapping.model_validate_json(value)
            except ValueError:
                continue
    return configured


async def save_capability(redis: Redis, result: CapabilityResult) -> None:
    ttl = max(1, int((datetime.fromisoformat(result.expires_at) - datetime.now(UTC)).total_seconds()))
    key = capability_key(result.alias, result.model, result.version, result.capability, result.gateway_identity)
    await redis.set(key, result.model_dump_json(), ex=ttl)


async def list_capabilities(redis: Redis, mappings: dict[str, ModelMapping], gateway_identity: str) -> list[CapabilityResult]:
    results: list[CapabilityResult] = []
    for alias, mapping in mappings.items():
        async for key in redis.scan_iter(match=capability_alias_pattern(alias), count=100):
            try:
                value = CapabilityResult.model_validate_json(await redis.get(key))
            except (ValueError, TypeError):
                continue
            if value.gateway_identity == gateway_identity and value.model == mapping.model and value.version == mapping.version:
                results.append(value)
    return results


def new_capability_result(alias: str, mapping: ModelMapping, capability: str, gateway_identity: str, result: str, configuration_revision: int = 0) -> CapabilityResult:
    now = datetime.now(UTC)
    return CapabilityResult(alias=alias, model=mapping.model, version=mapping.version,
        gateway_identity=gateway_identity, configuration_revision=configuration_revision, capability=capability, result=result,
        checked_at=now.isoformat(), expires_at=(now + timedelta(hours=24)).isoformat())
