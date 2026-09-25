# BBD-OS Phase 5 — Temporal Knowledge and Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Track events and time-varying facts through Graphiti with inspectable provenance, synchronization and a useful Timeline.

**Architecture:** Implement the timeline, knowledge/temporal capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 4 entities/evidence; Phase 3 permitted chat/structured/embedding capabilities supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 7, 13 Event, 34, 48, 95, 138.12–14, 158, 161–162. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 4 entities/evidence; Phase 3 permitted chat/structured/embedding capabilities.

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

1. Occurred time, observation time and fact validity are distinct timestamps.
2. Late events and contradictory facts retain history instead of overwriting evidence.
3. Graph synchronization can retry without duplicate episodes or loss of manual corrections.
4. Graphiti must not bypass OmniRoute privacy or use its own ungoverned provider fallback.
5. The selected graph backend has no presumed 8GB resource guarantee.

## File Structure and Boundaries

Module ownership: **timeline, knowledge/temporal**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P05-T1: Graphiti/FalkorDB compatibility and resource gate

**Files and responsibilities:** Create docs/graph-compatibility.md; tests/integration/test_graph_compatibility.py; infrastructure/graph/compose.yml; modules/knowledge/temporal/adapter.py; update pyproject.toml/uv.lock only for validated dependencies.

**Interfaces — consumes/produces:** TemporalGraph.initialize, upsert_episode, search_at, delete_episode, health; adapter accepts ModelGateway policy-aware clients and canonical entity ID mappings. FalkorDB is the first candidate, isolated from the ARQ Redis instance.

- [ ] **P05-T1.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_graph_compatibility.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_episode_upsert_is_idempotent(temporal_graph):
    episode = {"id":"fixture-episode","content":"An joined Project A",
        "observed_at":"2026-09-25T03:00:00Z"}
    await temporal_graph.upsert_episode(episode)
    await temporal_graph.upsert_episode(episode)
    assert await temporal_graph.count_episodes("fixture-episode") == 1
```

- [ ] **P05-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_graph_compatibility.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P05-T1.3 — Implement the minimal production behavior.** Define temporal_graph fixture against a disposable backend and expose count_episodes only on its test inspection helper, not public API. Pin a compatible Graphiti/FalkorDB pair using official sources, verify init/upsert/search/delete/restart, and route all Graphiti model calls through the controlled clients. Measure resident/peak memory on the available host and label host specs. If compatibility or resource checks fail, record a blocked gate; do not silently swap backend, drop Graphiti or claim mini-host capacity. Never share the queue Redis volume with FalkorDB.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"backend":"falkordb","release_record":"docs/graph-compatibility.md","live_models_verified":false,"target_host_verified":false}
```

- [ ] **P05-T1.4 — Verify the behavior and listed failure cases.** Complete the documented compatibility probe before enabling the runtime profile. The compatibility record must contain actual locked versions and observed results. If target hardware is unavailable, functionality can be accepted separately while capacity remains unverified.

- [ ] **P05-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P05-T2. Do not create a commit automatically.

## Task P05-T2: Events, participants and time semantics

**Files and responsibilities:** Create modules/timeline/models.py, modules/timeline/schemas.py, modules/timeline/public.py, modules/timeline/routes.py, modules/timeline/extraction.py; infrastructure/postgres/migrations/versions/0006_temporal.py; tests/test_time_windows.py; tests/integration/test_timeline.py.

**Interfaces — consumes/produces:** CRUD /events; GET /timeline?date_from=&date_to=&timezone=&source_id=&entity_id=&cursor=; timeline uses occurred time, preserving observed_at and optional valid_from/valid_to. day_window(date,timezone) -> (UTC start,UTC end) with half-open intervals.

- [ ] **P05-T2.1 — Write the failing behavioral test.** Put this case in `tests/test_time_windows.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_vietnam_day_window_is_half_open_utc():
    from modules.timeline.public import day_window
    start, end = day_window("2026-09-25", "Asia/Ho_Chi_Minh")
    assert start.isoformat() == "2026-09-24T17:00:00+00:00"
    assert end.isoformat() == "2026-09-25T17:00:00+00:00"
```

- [ ] **P05-T2.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_time_windows.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P05-T2.3 — Implement the minimal production behavior.** Persist Event/EventParticipant and evidence references; do not mix operational ingestion logs with personal events. Extract structured events from documents through validated model policy; accept manual events with explicit manual origin. Handle unknown dates without inventing a timestamp, and distinguish date-only from timed events. Sort timeline by stable (occurred_at,id), UTC storage plus IANA timezone at query/display, including DST zones. Manual corrections use expected revision and survive reprocessing.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"type":"manual_event","started_at":null,"observed_at":"2026-09-25T03:00:00Z","date_precision":"unknown","origin":"manual","evidence":[]}
```

- [ ] **P05-T2.4 — Verify the behavior and listed failure cases.** Timezone/DST boundaries, same-time cursor pagination, late arrivals, unknown dates, source filters, manual correction and invalid date ranges. Derived-event fixtures must supply valid evidence; manual events record owner provenance.

- [ ] **P05-T2.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P05-T3. Do not create a commit automatically.

## Task P05-T3: Durable graph sync and knowledge changes

**Files and responsibilities:** Create modules/knowledge/temporal/models.py, modules/knowledge/temporal/public.py, modules/knowledge/temporal/worker.py; tests/integration/test_graph_sync.py; extend data deletion and ingestion stage handlers.

**Interfaces — consumes/produces:** GraphSync(document_version_id,canonical_entity_ids,episode_id,status); KnowledgeService.get_entity_timeline, get_timeline, get_events, find_changes. POST /system/graph/reconcile -> run_id.

- [ ] **P05-T3.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_graph_sync.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_deleted_document_is_not_resurrected_by_graph_retry(graph_sync_fixture):
    await graph_sync_fixture.enqueue()
    await graph_sync_fixture.delete_document()
    await graph_sync_fixture.replay_pending()
    assert await graph_sync_fixture.visible_episode_count() == 0
```

- [ ] **P05-T3.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_graph_sync.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P05-T3.3 — Implement the minimal production behavior.** Implement graph_sync_fixture with disposable PostgreSQL/backend and failure injection at adapter boundary. PostgreSQL owns canonical IDs, corrections and sync status; Graphiti owns derived temporal representation. Store stable episode mappings, tombstones and source policy on each sync request. Reconciliation repairs missed writes and applies evidence removal without deleting facts still supported elsewhere. Emit KnowledgeChanged after canonical changes; UI can show graph pending/failed without hiding the underlying record.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"document_version_id":"uuid","episode_id":"stable-id","status":"pending","last_error":null}
```

- [ ] **P05-T3.4 — Verify the behavior and listed failure cases.** DB commit/graph timeout, restart, duplicate episode submission, correction replay, shared evidence removal and explicit graph outage; no unbounded global graph rebuild on startup.

- [ ] **P05-T3.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P05-T4. Do not create a commit automatically.

## Task P05-T4: Timeline and historical entity UI

**Files and responsibilities:** Create apps/web/src/modules/timeline/api.ts, apps/web/src/modules/timeline/timeline-page.tsx, apps/web/src/modules/timeline/event-detail.tsx; extend knowledge entity-detail.tsx and relationship-graph.tsx; route /timeline; tests/e2e/timeline.spec.ts.

**Interfaces — consumes/produces:** Timeline displays occurred/observed/validity labels separately. Graph date filtering uses validity windows; historical truth is not implied by the dashboard date filter.

- [ ] **P05-T4.1 — Write the failing behavioral test.** Put this case in `tests/e2e/timeline.spec.ts` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```typescript
import { test, expect } from './fixtures';

test('timeline date selection is preserved on reload', async ({ page }) => {
  await page.goto('/timeline?date_from=2026-09-25&date_to=2026-09-26');
  await expect(page.getByLabel('From date')).toHaveValue('2026-09-25');
  await page.reload();
  await expect(page.getByLabel('From date')).toHaveValue('2026-09-25');
});
```

- [ ] **P05-T4.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -E2eTarget tests/e2e/timeline.spec.ts` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P05-T4.3 — Implement the minimal production behavior.** Provide source/type/entity/date filters, pagination, event details and links to evidence/entity pages; render local time with explicit timezone. Display late-arrival and graph-sync status truthfully. Add entity history tabs only when their APIs exist and accessible relationship history controls.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"date_from":"2026-09-25","date_to":"2026-09-26","timezone":"Asia/Ho_Chi_Minh"}
```

- [ ] **P05-T4.4 — Verify the behavior and listed failure cases.** Mixed-source timeline, event correction, evidence links, graph unavailable mode and date filters. Common phase gate; next P06-T1, retaining any target-hardware capacity gate in the ledger.

- [ ] **P05-T4.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to the phase acceptance gate, then P06-T1. Do not create a commit automatically.

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
