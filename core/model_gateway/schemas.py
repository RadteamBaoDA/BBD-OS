from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Capability = Literal["chat", "streaming", "embeddings", "structured", "tools", "reranking"]


class RequestPolicy(BaseModel):
    reasoning_allowed: bool = False
    embeddings_allowed: bool = False
    local_only: bool = False
    permitted_destinations: frozenset[str] = frozenset()


class ModelMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(default="", max_length=200)
    version: str | None = Field(default=None, max_length=200)
    destination: Literal["unknown", "remote"] = "unknown"


class PrivacySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_remote_reasoning: bool = False
    allow_remote_embeddings: bool = False


class CapabilityResult(BaseModel):
    alias: str
    model: str
    version: str | None = None
    capability: Capability
    result: Literal["supported", "unsupported", "failed"]
    checked_at: str
    expires_at: str


class ProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Capability


class ModelSettingsRead(BaseModel):
    aliases: dict[str, ModelMapping]
    capabilities: list[CapabilityResult]
    credential_configured: bool
