import asyncio
import json
import secrets
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError

from core.model_gateway.policy import may_send
from core.model_gateway.schemas import ModelMapping, RequestPolicy

_LEASE_PREFIX = "bbd:model-gateway:slot:"
_CAPABILITY_PREFIX = "bbd:model-gateway:capability:"
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


class ModelGatewayError(RuntimeError):
    pass


class PrivacyPolicyDenied(ModelGatewayError):
    pass


class CapabilityUnsupported(ModelGatewayError):
    pass


class ModelGateway:
    def __init__(
        self,
        redis: Redis,
        base_url: str | None,
        api_key: str,
        destination_id: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.redis = redis
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.destination_id = destination_id
        self.timeout_seconds = timeout_seconds

    @asynccontextmanager
    async def _slot(self) -> AsyncIterator[None]:
        token = secrets.token_urlsafe(18)
        key = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                while key is None:
                    for slot in range(2):
                        candidate = f"{_LEASE_PREFIX}{slot}"
                        if await self.redis.set(candidate, token, nx=True, ex=int(self.timeout_seconds) + 10):
                            key = candidate
                            break
                    if key is None:
                        await asyncio.sleep(0.05)
                yield
        except (RedisError, TimeoutError) as exc:
            raise ModelGatewayError("Model capacity is unavailable") from exc
        finally:
            if key is not None:
                try:
                    await self.redis.eval(_RELEASE, 1, key, token)
                except RedisError:
                    pass

    async def _with_slot(self, call: Callable[[], Awaitable[Any]]) -> Any:
        async with self._slot():
            return await call()

    async def _request(
        self,
        alias: str,
        mapping: ModelMapping | None,
        policy: RequestPolicy,
        capability: str,
        path: str,
        payload: dict[str, Any],
        probe: bool = False,
    ) -> Any:
        if not may_send(policy, alias, mapping, self.destination_id, bool(self.api_key), capability):
            raise PrivacyPolicyDenied("Model request denied by privacy policy")
        if self.base_url is None or mapping is None:
            raise ModelGatewayError("Model gateway is not configured")
        if not probe:
            key = f"{_CAPABILITY_PREFIX}{alias}:{mapping.model}:{mapping.version or 'unknown'}:{capability}"
            stored = await self.redis.get(key)
            try:
                capability_result = json.loads(stored) if stored else {}
            except (TypeError, json.JSONDecodeError):
                capability_result = {}
            if capability_result.get("result") != "supported":
                raise ModelGatewayError("Model capability is not supported")
        endpoint = f"{self.base_url}/{path.lstrip('/')}" if self.base_url.endswith("/v1") else f"{self.base_url}/v1/{path.lstrip('/')}"
        body = {**payload, "model": mapping.model}

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        async def send() -> Any:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                for attempt in range(2):
                    try:
                        response = await client.post(
                            endpoint,
                            json=body,
                            headers=headers,
                        )
                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        if attempt == 0:
                            continue
                        raise ModelGatewayError("Model gateway request failed") from exc
                    if response.status_code in {408, 425, 429} or response.status_code >= 500:
                        if attempt == 0:
                            await asyncio.sleep(0.1)
                            continue
                    if response.status_code >= 400:
                        if response.status_code in {400, 404, 405, 422}:
                            raise CapabilityUnsupported("The configured gateway rejected this capability")
                        raise ModelGatewayError(f"Model gateway returned HTTP {response.status_code}")
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ModelGatewayError("Model gateway returned invalid JSON") from exc
            raise ModelGatewayError("Model gateway request failed")

        return await self._with_slot(send)

    async def chat(self, alias: str, mapping: ModelMapping | None, policy: RequestPolicy, messages: list[dict[str, Any]], probe: bool = False) -> Any:
        return await self._request(alias, mapping, policy, "chat", "chat/completions", {"messages": messages}, probe)

    async def stream(self, alias: str, mapping: ModelMapping | None, policy: RequestPolicy, messages: list[dict[str, Any]], probe: bool = False) -> AsyncIterator[str]:
        if not may_send(policy, alias, mapping, self.destination_id, bool(self.api_key), "streaming") or self.base_url is None or mapping is None:
            raise PrivacyPolicyDenied("Model request denied by privacy policy")
        if not probe:
            stored = await self.redis.get(f"{_CAPABILITY_PREFIX}{alias}:{mapping.model}:{mapping.version or 'unknown'}:streaming")
            try:
                capability_result = json.loads(stored) if stored else {}
            except (TypeError, json.JSONDecodeError):
                capability_result = {}
            if capability_result.get("result") != "supported":
                raise ModelGatewayError("Streaming capability has not been verified")
        endpoint = f"{self.base_url}/chat/completions" if self.base_url.endswith("/v1") else f"{self.base_url}/v1/chat/completions"
        async with self._slot():
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                for attempt in range(2):
                    try:
                        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                        async with client.stream("POST", endpoint, json={"model": mapping.model, "messages": messages, "stream": True}, headers=headers) as response:
                            if response.status_code in {408, 425, 429} or response.status_code >= 500:
                                if attempt == 0:
                                    continue
                            if response.status_code >= 400:
                                if response.status_code in {400, 404, 405, 422}:
                                    raise CapabilityUnsupported("The configured gateway rejected streaming")
                                raise ModelGatewayError(f"Model gateway returned HTTP {response.status_code}")
                            async for line in response.aiter_lines():
                                if line:
                                    yield line
                            return
                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        if attempt == 1:
                            raise ModelGatewayError("Model gateway stream failed") from exc

    async def embed(self, alias: str, mapping: ModelMapping | None, policy: RequestPolicy, inputs: list[str], probe: bool = False) -> Any:
        return await self._request(alias, mapping, policy, "embeddings", "embeddings", {"input": inputs}, probe)

    async def structured(self, alias: str, mapping: ModelMapping | None, policy: RequestPolicy, messages: list[dict[str, Any]], schema: dict[str, Any], probe: bool = False) -> Any:
        return await self._request(alias, mapping, policy, "structured", "chat/completions", {"messages": messages, "response_format": {"type": "json_schema", "json_schema": schema}}, probe)

    async def tools(self, alias: str, mapping: ModelMapping | None, policy: RequestPolicy, messages: list[dict[str, Any]], tools: list[dict[str, Any]], probe: bool = False) -> Any:
        return await self._request(alias, mapping, policy, "tools", "chat/completions", {"messages": messages, "tools": tools}, probe)

    async def rerank(self, alias: str, mapping: ModelMapping | None, policy: RequestPolicy, query: str, documents: list[str], probe: bool = False) -> Any:
        return await self._request(alias, mapping, policy, "reranking", "rerank", {"query": query, "documents": documents}, probe)
