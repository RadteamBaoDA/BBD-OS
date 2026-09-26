import base64
import hashlib
import json

_CAPABILITIES = "bbd:model-gateway:capability:"


def _component(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def capability_key(alias: str, model: str, version: str | None, capability: str) -> str:
    return ":".join(
        (_CAPABILITIES.rstrip(":"), _component(alias), _model_identity(model, version), _component(capability))
    )


def capability_alias_pattern(alias: str) -> str:
    return f"{_CAPABILITIES}{_component(alias)}:*"


def capability_model_pattern(alias: str, model: str, version: str | None) -> str:
    return f"{_CAPABILITIES}{_component(alias)}:{_model_identity(model, version)}:*"


def _model_identity(model: str, version: str | None) -> str:
    identity = json.dumps((model, version), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
