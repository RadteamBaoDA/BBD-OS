from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

Capability = Literal["chat", "streaming", "embeddings", "structured", "tools", "reranking"]


class RequestPolicy(BaseModel):
    reasoning_allowed: bool = False
    embeddings_allowed: bool = False
    web_search_allowed: bool = False
    local_only: bool = False
    permitted_destinations: frozenset[str] = frozenset()
    reasoning_destinations: frozenset[str] = frozenset()
    embedding_destinations: frozenset[str] = frozenset()
    web_search_destinations: frozenset[str] = frozenset()
    configuration_revision: int = 0


class ModelMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(default="", max_length=200)
    version: str | None = Field(default=None, max_length=200)
    destination: Literal["unknown", "remote"] = "unknown"


class PrivacySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_remote_reasoning: bool = False
    allow_remote_embeddings: bool = False
    allow_remote_web_search: bool = False
    reasoning_destinations: list[str] = Field(default_factory=list, max_length=8)
    embedding_destinations: list[str] = Field(default_factory=list, max_length=8)
    web_search_destinations: list[str] = Field(default_factory=list, max_length=8)


class AISettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    omniroute_base_url: AnyHttpUrl | None = None
    omniroute_credential_action: Literal["unchanged", "replaced", "removed"] = "unchanged"
    omniroute_api_key: str | None = Field(default=None, max_length=4096)
    web_search_provider: Literal["none", "tavily", "brave"] = "none"
    web_search_endpoint: AnyHttpUrl | None = None
    web_search_credential_action: Literal["unchanged", "replaced", "removed"] = "unchanged"
    web_search_api_key: str | None = Field(default=None, max_length=4096)
    chat_alias: Literal["reasoning-large", "reasoning-small", "fast"] = "reasoning-large"
    brief_alias: Literal["reasoning-large", "reasoning-small", "fast"] = "reasoning-small"
    aliases: dict[str, ModelMapping] = Field(default_factory=dict)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    request_timeout_seconds: int = Field(default=20, ge=5, le=180)
    expected_revision: int = Field(ge=1)


class ConnectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: AnyHttpUrl
    api_key: str = Field(default="", max_length=4096)


class DraftProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: AnyHttpUrl
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=200)
    capability: Capability


class ConnectionCheck(BaseModel):
    connected: bool
    model_ids: list[str]


class AIExecutionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    configuration_revision: int
    gateway_identity: str
    endpoint_destination_id: str | None
    endpoint_policy_denied: bool = False
    endpoint_allowed_cidrs: tuple[str, ...] = ()
    omniroute_base_url: str | None
    omniroute_api_key: str
    omniroute_credential_configured: bool = False
    aliases: dict[str, ModelMapping]
    privacy: PrivacySettings
    chat_alias: str
    brief_alias: str
    request_timeout_seconds: int
    web_search_provider: str
    web_search_endpoint: str | None
    web_search_api_key: str
    web_search_credential_configured: bool = False


class CapabilityResult(BaseModel):
    alias: str
    model: str
    version: str | None = None
    gateway_identity: str
    configuration_revision: int = 0
    capability: Capability
    result: Literal["supported", "unsupported", "failed"]
    checked_at: str
    expires_at: str


class AISettingsRead(BaseModel):
    configuration_revision: int
    omniroute_base_url: AnyHttpUrl | None = None
    endpoint_destination_id: str | None = None
    endpoint_policy_denied: bool = False
    omniroute_credential_configured: bool
    web_search_provider: Literal["none", "tavily", "brave"]
    web_search_endpoint: AnyHttpUrl | None = None
    web_search_destination_id: str | None = None
    web_search_credential_configured: bool
    chat_alias: Literal["reasoning-large", "reasoning-small", "fast"]
    brief_alias: Literal["reasoning-large", "reasoning-small", "fast"]
    aliases: dict[str, ModelMapping]
    capabilities: list[CapabilityResult]
    privacy: PrivacySettings
    request_timeout_seconds: int


class ProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: Capability


class ModelSettingsRead(BaseModel):
    aliases: dict[str, ModelMapping]
    capabilities: list[CapabilityResult]
    credential_configured: bool
