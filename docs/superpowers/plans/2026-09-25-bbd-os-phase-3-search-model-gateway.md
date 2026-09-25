# BBD-OS Phase 3 — Search and Model Gateway Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Provide lexical/hybrid search with safe OmniRoute access, explicit privacy controls and versioned embedding indexes.

**Architecture:** Implement the search, model_gateway, settings capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 2 chunks/provenance; live model acceptance needs configured endpoint and permitted aliases supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 8, 33–35, 63–65, 76–77, 95, 113–114, 121–123, 157. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 2 chunks/provenance; live model acceptance needs configured endpoint and permitted aliases.

**Implementation status:** Not started. This file is an implementation plan, not evidence of working code.

## Global Constraints

- "Never hardcode secrets."
- "Every schema change must use Alembic."
- "Agents must use defined tools and APIs."
- "Create directories only when used."
- Public APIs use `/api/v1`; preserve single-owner auth, session-bound CSRF, source policy and provenance.
- Target 2 CPU cores/8 GiB with remote inference; never claim measured capacity from a larger host.
- Follow the master's mandatory privacy, module, durable-job, deletion and UI contracts. Keep source data and credentials out of logs.
- No stage/commit/push/deploy, branch change or destructive owner-data operations are authorized by writing this plan.

## Review Focus

1. Local-only content cannot leave via a reasoning or embedding fallback.
2. Changing embedding model or dimensions never mixes vector spaces.
3. No gateway preserves lexical retrieval and explicitly disables remote-dependent search.
4. Deleting content removes it from retrieval even while indexing jobs are running.
5. Search must handle Vietnamese text, filters and empty queries without unsafe SQL.

## File Structure and Boundaries

Module ownership: **search, model_gateway, settings**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P03-T1: Gateway configuration, capability probes and privacy policy

**Files and responsibilities:** Create core/model_gateway/schemas.py, core/model_gateway/client.py, core/model_gateway/policy.py; modules/settings/models.py, modules/settings/schemas.py, modules/settings/routes.py; modules/model_gateway/routes.py; apps/web/src/modules/settings/models.tsx, apps/web/src/modules/settings/privacy.tsx; tests/test_model_policy.py.

**Interfaces — consumes/produces:** ModelGateway.chat, stream, embed, structured, tools, rerank accept an explicit RequestPolicy with reasoning_allowed,embeddings_allowed,local_only, permitted_destinations. POST /settings/models/{alias}/test; GET/PATCH /settings/privacy; secret values are write-only and represented as configured flags. Aliases: reasoning-large,reasoning-small,fast,embedding,reranker,vision,local-private.

- [ ] **P03-T1.1 — Write the failing behavioral test.** Put this case in `tests/test_model_policy.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_local_only_rejects_remote_destination():
    from core.model_gateway.policy import may_send
    assert may_send(local_only=True, destination="remote", opted_in=True) is False
    assert may_send(local_only=False, destination="remote", opted_in=False) is False
```

- [ ] **P03-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_model_policy.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P03-T1.3 — Implement the minimal production behavior.** Implement may_send as a fail-closed predicate and apply it before all outgoing requests, including probes containing owner data. Store secrets in server configuration initially; settings UI edits alias mappings, not provider secrets. Separate capability results per alias/model/version and expire results when mapping changes. Cache no evidence of privacy guarantees from gateway hostname alone; unknown destination denies local-only sends. Add synthetic capability probes, explicit request deadlines, bounded retry only on transient errors, shared two-request concurrency cap with expiring leases across API/worker. Do not install a local LLM by default.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"alias":"embedding","capabilities":{"embeddings":"untested","streaming":"unsupported"},"credential_configured":false}
```

- [ ] **P03-T1.4 — Verify the behavior and listed failure cases.** Unit tests for every privacy/fallback branch using an injected HTTP transport; assert transport sees zero calls when denied. Live probe writes redacted evidence only after endpoint/aliases/opt-in are supplied; unavailable prerequisites block live acceptance, not pure API/UI development.

- [ ] **P03-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P03-T2. Do not create a commit automatically.

## Task P03-T2: Lexical index and embedding generations

**Files and responsibilities:** Create modules/search/models.py, modules/search/indexing.py, modules/search/public.py, modules/search/schemas.py, modules/search/routes.py; infrastructure/postgres/migrations/versions/0004_search.py; tests/integration/test_search_index.py; tests/test_index_generation.py; extend worker and deletion hooks.

**Interfaces — consumes/produces:** POST /search {query,filters,mode,limit,cursor}; SearchHit includes title,excerpt,score,source,observed_at,published_at,document_version_id,chunk_id,citation. IndexGeneration(model_id,dimensions,status); POST /search/reindex -> run_id. Modes lexical|hybrid, with effective_mode and warnings.

- [ ] **P03-T2.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_search_index.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_lexical_search_works_without_embedding(owner_client, searchable_document):
    response = await owner_client.post("/api/v1/search",
        json={"query":"Tiếng Việt","mode":"lexical","limit":10})
    assert response.status_code == 200
    assert response.json()["effective_mode"] == "lexical"
    assert searchable_document["id"] in [x["document_id"] for x in response.json()["items"]]
```

- [ ] **P03-T2.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_search_index.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P03-T2.3 — Implement the minimal production behavior.** Define searchable_document fixture by ingesting a test note and waiting for lexical readiness. Use PostgreSQL simple text-search configuration for Unicode lexical baseline; parameterize query construction. Pin vector dimensions per generation; create a new physical index for new generations, then switch active generation atomically after verification. Keep per-item indexing status so partial failures are visible. Use reciprocal-rank fusion for hybrid results. If query embeddings are unavailable return lexical results with effective_mode=lexical and a warning; never report hybrid success. Gate deleted/private references at retrieval time as well as indexing.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"items":[],"next_cursor":null,"effective_mode":"lexical","warnings":["Semantic search unavailable"]}
```

- [ ] **P03-T2.4 — Verify the behavior and listed failure cases.** Filter combinations, Unicode queries, stale generation, provider dimension mismatch, delete while embedding, failed rebuild preserving current index, and duplicate indexing events. Verify hybrid with a permitted live embedding alias separately from deterministic test transport.

- [ ] **P03-T2.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P03-T3. Do not create a commit automatically.

## Task P03-T3: Search UI and command palette

**Files and responsibilities:** Create apps/web/src/modules/search/api.ts, apps/web/src/modules/search/search-page.tsx, apps/web/src/modules/search/search-results.tsx; apps/web/src/core/command-palette.tsx; tests/e2e/search.spec.ts; thin /search route.

**Interfaces — consumes/produces:** Search UI consumes the response contract without inventing normalized confidence. Ctrl/Cmd+K opens available actions; '/' focuses search except in inputs/editors. Citation links navigate to protected document revision views.

- [ ] **P03-T3.1 — Write the failing behavioral test.** Put this case in `tests/e2e/search.spec.ts` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```typescript
import { test, expect } from './fixtures';

test('search keyboard shortcut preserves input typing', async ({ page }) => {
  await page.goto('/search');
  await page.getByRole('textbox', { name: 'Search' }).fill('path/to/note');
  await expect(page.getByRole('textbox', { name: 'Search' })).toHaveValue('path/to/note');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByRole('status')).toBeVisible();
});
```

- [ ] **P03-T3.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -E2eTarget tests/e2e/search.spec.ts` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P03-T3.3 — Implement the minimal production behavior.** Add query, source/date/type filters and stable pagination; show lexical fallback and indexing progress. Use accessible list results with date/source/excerpt, no fabricated scores or snippets. Register command-palette actions from enabled modules as they appear. Preserve typed search/filter state in URL; never put auth or raw private text in unrelated telemetry.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"query":"project","filters":{"source_ids":[],"date_from":null,"date_to":null,"content_types":[]}}
```

- [ ] **P03-T3.4 — Verify the behavior and listed failure cases.** Keyboard shortcut exclusions, empty results, error/retry, filters, citation navigation and offline lexical access. Common phase gate.

- [ ] **P03-T3.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P03-T4. Do not create a commit automatically.

## Task P03-T4: Search quality baseline and model acceptance record

**Files and responsibilities:** Create tests/fixtures/search/relevance.json, tests/test_search_quality.py, docs/model-compatibility.md; update docs/IMPLEMENTATION_STATUS.md and execution ledger. Create modules/search/evaluation.py.

**Interfaces — consumes/produces:** Fixtures contain query,expected_document_ids and allowed filters; evaluation reports recall@10 and latency, separate provider latency. Current-generation configuration is included in evidence. recall_at_k(ranked_ids: list[str], expected_ids: set[str], k: int) -> float; empty expected set returns 1.0 only for an empty result, otherwise 0.0 for explicit no-answer fixtures.

- [ ] **P03-T4.1 — Write the failing behavioral test.** Put this case in `tests/test_search_quality.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_recall_penalizes_missing_relevant_documents():
    from modules.search.evaluation import recall_at_k
    assert recall_at_k(["a","b"], {"a","c"}, k=10) == 0.5
```

- [ ] **P03-T4.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_search_quality.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P03-T4.3 — Implement the minimal production behavior.** Build at least ten deterministic retrieval questions spanning Vietnamese text, dates, sources and no-answer cases. Require all exact known-term documents in lexical top10 and record hybrid recall without claiming provider quality from stubs. Record endpoint release, tested model identity, dimensions, privacy routing guarantees and capabilities; retain unavailable values as unknown. This record is a dependency for extraction and Graphiti, not an invitation to skip live checks.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"alias":"embedding","model_id":"configured-model","dimensions":1536,"live_verified":false}
```

- [ ] **P03-T4.4 — Verify the behavior and listed failure cases.** Run evaluation against disposable corpus and permitted live provider when available. Dimension above is example data only, never a configured default. Common gate; next P04-T1 only for model-dependent acceptance after the corresponding probe passes.

- [ ] **P03-T4.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to the phase acceptance gate, then P04-T1. Do not create a commit automatically.

## Phase Acceptance and Handoff

- [ ] Run final sequential `./scripts/dev.ps1 lint`, `typecheck`, `test`, `build` (Make equivalents on Linux). Use targeted checks during tasks and the complete gate once after final phase changes.
- [ ] Verify new code is included in Docker/packaging, new tables in Alembic metadata, public APIs in OpenAPI and enabled UI/routes in module descriptors.
- [ ] Complete independent final review under the execution skill, fix actionable findings, and repeat affected checks.
- [ ] Record actual test counts, live integration evidence and capacity limitations; fixtures do not validate live providers or mini-host performance.
- [ ] Update `docs/IMPLEMENTATION_STATUS.md`, this checklist and `EXECUTION.md`. Continue automatically to the next ready approved task; stop only the work that depends on an unresolved external gate or a material unapproved change.

## Plan Self-Review Checklist

- [x] Goal and spec sections mapped to named tasks and public interfaces.
- [x] Five review-focus risks assigned concrete failure checks in the owning tasks.
- [x] Exact file targets, behavioral test examples, expected failure, implementation rules and passing criteria included.
- [x] Module ownership, auth/privacy, safe deletion and retry/resume boundaries preserved.
- [x] Implementation and live/hardware verification are not claimed complete by this plan.
