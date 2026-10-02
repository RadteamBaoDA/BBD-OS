from core.model_gateway.schemas import ModelMapping, RequestPolicy


def may_send(
    policy: RequestPolicy,
    alias: str,
    mapping: ModelMapping | None,
    destination_id: str,
    credential_configured: bool,
    capability: str,
) -> bool:
    """Decide whether a configured remote capability may be sent under destination, credential, and privacy policy."""
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
    if capability in {"embeddings", "reranking"}:
        destinations = policy.embedding_destinations or policy.permitted_destinations
        return policy.embeddings_allowed and destination_id in destinations
    if capability in {"web_search", "search"}:
        return policy.web_search_allowed and destination_id in policy.web_search_destinations
    destinations = policy.reasoning_destinations or policy.permitted_destinations
    return policy.reasoning_allowed and destination_id in destinations
