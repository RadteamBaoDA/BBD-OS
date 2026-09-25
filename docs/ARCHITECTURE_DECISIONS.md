# BBD-OS architecture decisions

Design revision: 2026-09-25. Architecture approved by the owner on 2026-09-25, including OmniRoute. Phase 0 implementation and acceptance checks are complete; validation on the target mini PC and later-phase integrations remain open. The execution plan is in `docs/superpowers/plans/2026-09-25-bbd-os-phase-0.md`.

| Decision | Reason | Alternatives | Consequences |
| --- | --- | --- | --- |
| Keep Python/FastAPI, ARQ, and LangGraph; no Go backend initially | Reuse existing queue and agent frameworks to accelerate delivery | Go core plus Python AI worker; custom Go harness | One backend ecosystem; application-specific permissions, idempotency, and recovery integration remain necessary |
| Replace LiteLLM with OmniRoute | Owner already intends to use OmniRoute for multiple AI sources | LiteLLM; direct provider SDKs | Validate actual model capabilities; keep logical aliases and enforce privacy across fallback |
| Use n8n for external collection schedules and packaged workflows | Reuse connectors rather than write every provider integration | Native connectors for all sources | n8n required for these sources; source-available licensing must be represented accurately; mapping/cursor integration still required |
| Crawlee first, browser-use only when needed | Minimize browser/AI work on a small host | Crawl4AI; Browserless; all-browser crawling | One bounded browser task; browser isolation and source provenance remain mandatory |
| Retain Graphiti; choose backend after validation | Preserve temporal knowledge scope without making unsupported compatibility or RAM claims | PostgreSQL-only graph; remote graph backend | Backend selection is a pre-implementation gate for graph work, not permission to omit the feature |
| Target 2 cores and 8 GB with remote inference | Match the owner's hardware | Larger host; remote graph/browser services | Bound jobs, prebuild images, measure the complete enabled stack; no unmeasured capacity guarantee |
| Use Next.js 16.3.6 in Phase 0 | The initially selected Next.js 15 dependency tree resolved a vulnerable PostCSS version; the pinned Next 16 release supports the installed Node 24 runtime and `npm audit` reports no vulnerabilities | Override nested dependencies; defer framework setup | Revisit with scheduled dependency updates and rerun security/build checks |

The canonical updated design is `specs/personal-intelligence-os-spec-v2.md`, especially sections 156–163. The proposed PostgreSQL-only queue, custom Go agent runtime, and PostgreSQL replacement for Graphiti were not selected.
