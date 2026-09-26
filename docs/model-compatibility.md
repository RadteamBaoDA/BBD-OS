# Model compatibility record

This record separates repository configuration and source-verified safeguards from facts that require a live OmniRoute/provider check. No live provider probe or prompt was sent for this record.

## Current record

| Field | Value | Evidence |
|---|---|---|
| Gateway/provider | OmniRoute-compatible remote gateway (`omniroute`) | `modules/search/indexing.py`; `.env.example` |
| Configured endpoint URL | Unknown at runtime; `.env.example` leaves `OMNIROUTE_BASE_URL` blank | Environment-specific; no local `.env` value is recorded here |
| OmniRoute release | Unknown | Not established by repository configuration |
| Configured embedding model ID/version | Unknown in this checkout's runtime | `OMNIROUTE_MODELS` is `{}` in `.env.example`; settings can override mappings in Redis |
| Provider-returned embedding model identity | Unknown until a successful embedding response supplies the identity and indexing persists it; if the response omits it, it remains unknown | Search indexing stores a supplied response identity on the index generation |
| Embedding dimensions | Unknown until a successful embedding response supplies a vector and indexing persists its dimensions | Search indexing pins response dimensions on the index generation |
| Remote embedding consent | Disabled by default; owner opt-in is required | `PrivacySettings.allow_remote_embeddings` defaults to `false` |
| Source privacy routing | Search indexing excludes `local_only` sources and only sends through the configured OmniRoute destination | `modules/search/indexing.py`, `core/model_gateway/policy.py` |
| Endpoint data handling / residency / retention guarantees | Unknown | A configured gateway URL does not establish provider-side guarantees |
| Embeddings capability | Unknown until a successful capability probe is recorded for the configured alias/model/version | Model gateway requires supported capability evidence before requests |
| Other capabilities (chat, streaming, structured output, tools, reranking) | Unknown until separately probed | Capabilities are recorded independently and expire after 24 hours |

## Compatibility rules

- Pin embedding model identity and dimensions to each index generation. Reindex after model changes; do not mix models or silently fall back.
- Treat configured model names and stub responses as configuration/evidence only. They do not prove endpoint release, privacy routing, data handling, or capability support.
- Keep unverified values `unknown`. Record live verification separately with the check time and the exact gateway/model configuration it covered.
- If the endpoint's destination guarantees cannot be established, do not route local-only data to it.

## Update procedure

After an authorized live compatibility check, record the gateway release, endpoint identity, configured and returned model IDs, dimensions, privacy/data-handling evidence, and each capability result with its check time. Do not record credentials, prompts, source text, or personal data here.
