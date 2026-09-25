# BBD-OS Phase 4 — Entity Knowledge and Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Extract, resolve and browse entities/relationships while preserving evidence and owner corrections.

**Architecture:** Implement the knowledge/entities, knowledge/relationships capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 3 validated structured-output alias, search and public library supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 13, 32, 34–35, 49–51, 95, 128–129, 138.11–14. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 3 validated structured-output alias, search and public library.

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

1. Shared names do not prove two people are the same entity.
2. Model outputs cannot create evidence references to documents outside the permitted input set.
3. Owner merge/split/override decisions survive later extraction runs.
4. Deleting one source removes its support without erasing a fact still supported by other sources.
5. Graph visualization requests must be bounded on the mini host.

## File Structure and Boundaries

Module ownership: **knowledge/entities, knowledge/relationships**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P04-T1: Canonical entities, aliases and evidence-backed relationships

**Files and responsibilities:** Create modules/knowledge/entities/models.py, modules/knowledge/entities/schemas.py, modules/knowledge/entities/public.py, modules/knowledge/entities/routes.py; modules/knowledge/relationships/models.py, modules/knowledge/relationships/schemas.py, modules/knowledge/relationships/public.py, modules/knowledge/relationships/routes.py; infrastructure/postgres/migrations/versions/0005_entities.py; tests/integration/test_entities.py.

**Interfaces — consumes/produces:** CRUD /entities, /relationships; GET /entities/{id}/neighbors?limit<=100; EntityRef(id,type,name), EvidenceRef(document_version_id,chunk_id,observed_at,extracted_at,confidence); EntityAlias includes source_id. Public get_entity/get_neighbors return DTOs, never ORM rows.

- [ ] **P04-T1.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_entities.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_manual_entity_has_no_fabricated_evidence(owner_client):
    response = await owner_client.post("/api/v1/entities",
        json={"type":"person","name":"An","origin":"manual"})
    assert response.status_code == 201
    assert response.json()["origin"] == "manual"
    assert response.json()["evidence"] == []
```

- [ ] **P04-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_entities.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P04-T1.3 — Implement the minimal production behavior.** Match canonical entity types and relationship fields. Manual authoring records owner provenance rather than fabricated document citations. Derived relationships require at least one valid evidence reference and confidence in [0,1]. Use separate evidence links so a shared fact survives removal of one supporting document. Add indexed names/types and both relationship directions. Update deletion consumers and seed examples for real entity/relationship functionality.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"source_entity_id":"uuid","target_entity_id":"uuid","type":"WORKS_AT","origin":"derived","evidence":[{"document_version_id":"uuid","chunk_id":"uuid","confidence":0.9}]}
```

- [ ] **P04-T1.4 — Verify the behavior and listed failure cases.** Real FK/uniqueness validation, invalid confidence/types, missing evidence, bounded neighbors, manual CRUD and source deletion with shared evidence.

- [ ] **P04-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P04-T2. Do not create a commit automatically.

## Task P04-T2: Bounded extraction and conservative resolution

**Files and responsibilities:** Create modules/knowledge/entities/extraction.py, modules/knowledge/entities/resolution.py, modules/knowledge/entities/worker.py; tests/test_entity_resolution.py; tests/integration/test_entity_extraction.py; extend ingestion stage dispatch.

**Interfaces — consumes/produces:** resolve_candidates(candidates,known) -> ResolutionResult(matches,review_candidates); extraction consumes document_version_id + allowed chunk IDs and produces validated evidence-backed facts. Resolution match reasons: external identity, confirmed alias, manual correction.

- [ ] **P04-T2.1 — Write the failing behavioral test.** Put this case in `tests/test_entity_resolution.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_same_name_without_identity_requires_review():
    from modules.knowledge.entities.resolution import resolve_candidates
    result = resolve_candidates(
        candidates=[{"type":"person","name":"Nguyen An","external_id":None}],
        known=[{"id":"p1","type":"person","name":"Nguyen An","external_id":None}])
    assert result.matches == []
    assert len(result.review_candidates) == 1
```

- [ ] **P04-T2.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_entity_resolution.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P04-T2.3 — Implement the minimal production behavior.** Call structured extraction through ModelGateway policy, validate types/references and cap candidates per batch. Key extraction output by document revision + extractor/prompt version to avoid duplicate retries. Prefer explicit provider identity or confirmed aliases; similar names alone create review candidates. Keep extraction failure visible without blocking reading/search of the underlying document. Relevance and extraction prompts never authorize tools.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"matches":[],"review_candidates":[{"candidate_name":"Nguyen An","reason":"ambiguous_identity","possible_entity_ids":["p1"]}]}
```

- [ ] **P04-T2.4 — Verify the behavior and listed failure cases.** Injected deterministic model outputs for unknown chunk IDs, malicious instruction text, invalid JSON, name collisions, rate limit retry and repeated stage execution. Run a permitted live structured-output fixture before claiming extraction integration.

- [ ] **P04-T2.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P04-T3. Do not create a commit automatically.

## Task P04-T3: Persistent corrections, merge and split

**Files and responsibilities:** Create modules/knowledge/entities/corrections.py; extend schemas/routes and correction tables in infrastructure/postgres/migrations/versions/0005_entities.py if not yet released, otherwise a new revision; tests/integration/test_entity_corrections.py.

**Interfaces — consumes/produces:** POST /entities/{id}/merge {into_id,expected_revision}; POST /entities/{id}/split {evidence_ids,new_entity,expected_revision}; PATCH entity with expected_revision; correction decisions include actor,reason,timestamp and evidence membership.

- [ ] **P04-T3.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_entity_corrections.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_stale_entity_edit_is_rejected(owner_client, manual_entity):
    entity_id = manual_entity["id"]
    first = await owner_client.patch(f"/api/v1/entities/{entity_id}",
        json={"name":"Corrected","expected_revision":1})
    stale = await owner_client.patch(f"/api/v1/entities/{entity_id}",
        json={"name":"Old edit","expected_revision":1})
    assert first.status_code == 200
    assert stale.status_code == 409
```

- [ ] **P04-T3.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_entity_corrections.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P04-T3.3 — Implement the minimal production behavior.** Create manual_entity fixture through the Phase 4 API. Apply corrections transactionally and persist them as inputs to subsequent extraction reconciliation. Merge redirects old IDs while preserving evidence and avoiding duplicate relationships; split moves explicitly chosen evidence, not arbitrary inferred facts. Corrections protect names/identity but cannot retain deleted source text. Emit versioned EntityUpdated/KnowledgeChanged through the existing durable dispatch contract.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"entity_id":"uuid","revision":2,"protected_fields":["name"],"correction_reason":"owner_edit"}
```

- [ ] **P04-T3.4 — Verify the behavior and listed failure cases.** Concurrent correction, merge loops, split/merge reference integrity, repeated extraction respecting overrides and forgetting a source removing its evidence.

- [ ] **P04-T3.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P04-T4. Do not create a commit automatically.

## Task P04-T4: Knowledge pages and bounded React Flow graph

**Files and responsibilities:** Create apps/web/src/modules/knowledge/entity-list.tsx, apps/web/src/modules/knowledge/entity-detail.tsx, apps/web/src/modules/knowledge/entity-editor.tsx, apps/web/src/modules/knowledge/relationship-graph.tsx, apps/web/src/modules/knowledge/resolution-review.tsx; route wrappers /knowledge/entities and /knowledge/entities/[entityId]; tests/e2e/knowledge.spec.ts.

**Interfaces — consumes/produces:** Graph UI reads entity/neighbors APIs; graph evidence panel opens document revision. Search registry adds entity results. Public KnowledgeService methods are exported through modules/knowledge/public.py.

- [ ] **P04-T4.1 — Write the failing behavioral test.** Put this case in `tests/e2e/knowledge.spec.ts` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```typescript
import { test, expect } from './fixtures';

test('graph can be navigated without a pointer', async ({ page }) => {
  await page.goto('/knowledge/entities');
  await page.getByRole('link', { name: 'An', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'An', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Related entities' })).toBeVisible();
});
```

- [ ] **P04-T4.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -E2eTarget tests/e2e/knowledge.spec.ts` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P04-T4.3 — Implement the minimal production behavior.** Provide list/detail/create/edit, resolution review and merge/split confirmation. Use React Flow with on-demand neighbors, default 50 nodes and hard response cap 100; include keyboard-accessible relationship list. Show aliases, sources, documents and actual evidence; temporal tabs appear in Phase 5 and memories in Phase 6, not empty fabricated panels.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"nodes":[],"edges":[],"truncated":false,"next_cursor":null}
```

- [ ] **P04-T4.4 — Verify the behavior and listed failure cases.** E2E evidence navigation, correction confirmation, graph zoom/pan/filter/expand and keyboard list alternative. Common phase gate; next P05-T1.

- [ ] **P04-T4.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to the phase acceptance gate, then P05-T1. Do not create a commit automatically.

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
