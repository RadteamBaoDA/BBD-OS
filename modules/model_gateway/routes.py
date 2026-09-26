from typing import Annotated
import json

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.auth.dependencies import require_owner_write
from core.auth.models import AuthSession
from core.config import Settings
from core.model_gateway.client import CapabilityUnsupported, ModelGateway, ModelGatewayError, PrivacyPolicyDenied
from core.model_gateway.schemas import ProbeRequest, RequestPolicy
from modules.settings import models as settings_models

router = APIRouter(prefix="/api/v1/settings/models", tags=["models"])
OwnerWrite = Annotated[AuthSession, Depends(require_owner_write)]


def _capability_proved(capability: str, response: object) -> bool:
    if not isinstance(response, dict):
        return False
    if capability == "embeddings":
        rows = response.get("data")
        return bool(rows) and isinstance(rows, list) and all(
            isinstance(row, dict) and isinstance(row.get("embedding"), list) and bool(row["embedding"])
            for row in rows
        )
    if capability == "reranking":
        return bool(response.get("results")) and isinstance(response.get("results"), list)
    if capability == "streaming":
        return response.get("streamed") is True
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return False
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return False
    if capability == "tools":
        return bool(message.get("tool_calls"))
    if capability == "structured":
        try:
            return isinstance(json.loads(message.get("content", "")), dict)
        except (TypeError, json.JSONDecodeError):
            return False
    return isinstance(message.get("content"), str)


@router.post("/{alias}/test")
async def probe_model(
    request: Request,
    _owner: OwnerWrite,
    alias: Annotated[str, Path(pattern=r"^(reasoning-large|reasoning-small|fast|embedding|reranker|vision|local-private)$")],
    body: ProbeRequest,
) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    redis: Redis = request.app.state.redis
    mappings = await settings_models.get_mappings(redis, settings)
    mapping = mappings.get(alias)
    if mapping is None:
        raise HTTPException(status_code=409, detail="Configure this model alias first")
    privacy = await settings_models.get_privacy(redis)
    client = ModelGateway(
        redis, str(settings.omniroute_base_url) if settings.omniroute_base_url else None,
        settings.omniroute_api_key.get_secret_value(), "omniroute", timeout_seconds=15,
    )
    policy = RequestPolicy(
        reasoning_allowed=privacy.allow_remote_reasoning,
        embeddings_allowed=privacy.allow_remote_embeddings,
        permitted_destinations=frozenset({"omniroute"}),
    )
    probe_message = [{"role": "user", "content": "Reply with the word ready."}]
    try:
        if body.capability == "embeddings":
            response = await client.embed(alias, mapping, policy, ["Synthetic capability probe."], probe=True)
        elif body.capability == "reranking":
            response = await client.rerank(alias, mapping, policy, "synthetic probe", ["synthetic probe document"], probe=True)
        elif body.capability == "streaming":
            streamed = False
            total_chars = 0
            async for line in client.stream(alias, mapping, policy, probe_message, probe=True):
                total_chars += len(line)
                if line.startswith("data:"):
                    streamed = True
                if total_chars >= 16384 or line.strip() == "data: [DONE]":
                    break
            response = {"streamed": streamed}
        elif body.capability == "structured":
            response = await client.structured(alias, mapping, policy, probe_message, {"name": "probe", "schema": {"type": "object"}}, probe=True)
        elif body.capability == "tools":
            response = await client.tools(alias, mapping, policy, [{"role": "user", "content": "Call the probe tool now."}], [{"type": "function", "function": {"name": "probe", "description": "Return a synthetic readiness signal.", "parameters": {"type": "object", "properties": {}}}}], probe=True)
        else:
            response = await client.chat(alias, mapping, policy, probe_message, probe=True)
        supported = _capability_proved(body.capability, response)
        result = settings_models.new_capability_result(alias, mapping.model, mapping.version, body.capability, "supported" if supported else "unsupported")
    except PrivacyPolicyDenied as exc:
        raise HTTPException(status_code=403, detail="Probe denied by privacy policy") from exc
    except CapabilityUnsupported:
        result = settings_models.new_capability_result(alias, mapping.model, mapping.version, body.capability, "unsupported")
    except ModelGatewayError:
        result = settings_models.new_capability_result(alias, mapping.model, mapping.version, body.capability, "failed")
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Model capability storage is unavailable") from exc
    await settings_models.save_capability(redis, result)
    return result.model_dump(mode="json")
