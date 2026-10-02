import base64
import hashlib
import json

_CAPABILITIES = "bbd:model-gateway:capability:"


def _component(value: str) -> str:
    """Escape a key component so separators cannot change the Redis capability-key structure."""
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def capability_key(alias: str, model: str, version: str | None, capability: str, gateway_identity: str = "legacy") -> str:
    """Build the Redis capability cache key from alias, model/version, capability, and gateway identity."""
    return ":".join((_CAPABILITIES.rstrip(":"), _component(alias), _model_identity(model, version), _component(capability), gateway_identity))


def capability_alias_pattern(alias: str) -> str:
    """Build a Redis pattern matching all capability entries for one alias."""
    return f"{_CAPABILITIES}{_component(alias)}:*"


def capability_model_pattern(alias: str, model: str, version: str | None) -> str:
    """Build a Redis pattern matching capability entries for one alias and model identity."""
    return f"{_CAPABILITIES}{_component(alias)}:{_model_identity(model, version)}:*"


def _model_identity(model: str, version: str | None) -> str:
    """Hash the model/version tuple into a stable cache-key component."""
    identity = json.dumps((model, version), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
