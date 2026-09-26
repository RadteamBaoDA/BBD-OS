from core.model_gateway.schemas import ModelMapping, RequestPolicy


def may_send(
    policy: RequestPolicy,
    alias: str,
    mapping: ModelMapping | None,
    destination_id: str,
    credential_configured: bool,
    capability: str,
) -> bool:
    if mapping is None or not mapping.model.strip():
        return False
    if (
        not credential_configured
        or policy.local_only
        or alias == "local-private"
        or mapping.destination != "remote"
        or destination_id not in policy.permitted_destinations
    ):
        return False
    return policy.embeddings_allowed if capability in {"embeddings", "reranking"} else policy.reasoning_allowed
