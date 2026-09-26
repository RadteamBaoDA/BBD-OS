# BBD-OS Phase 11 — Observability and Operational Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Make runs, failures, quality, usage and system capacity inspectable without leaking secrets or turning monitoring into a runtime dependency.

**Architecture:** Implement the observability, settings capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phases 1–10 already emit run IDs, events, status and timing supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 69–70, 95, 110, 126–127, 130, 138.21/23/28, 161. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phases 1–10 already emit run IDs, events, status and timing.

**Implementation status:** Not started. This file is an implementation plan, not evidence of working code.

Test execution is deferred until all Phase 1-12 production code is complete. Acceptance examples and test file paths below are specifications; do not create, modify or run test files during this implementation stage.

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

1. Missing token/cost values remain unknown rather than zero.
2. Private content and credentials must not be copied into telemetry by default.
3. A telemetry backend outage must not fail a knowledge write or agent result.
4. Retention jobs cannot delete canonical documents, raw files or version history.
5. A no-change poll should not generate repetitive operational logs or notifications.

## File Structure and Boundaries

Module ownership: **observability, settings**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P11-T1: Structured traces, metrics and data minimization

**Files and responsibilities:** Create core/telemetry.py; modules/observability/schemas.py, modules/observability/public.py, modules/observability/routes.py; tests/test_telemetry_redaction.py; wire existing ingestion/agent/gateway request hooks.

**Interfaces — consumes/produces:** TraceContext(request_id,ingestion_run_id?,agent_run_id?,tool_call_id?); GET /system/metrics and /system/runs with owner protection. Usage(tokens_in?,tokens_out?,cost?,model_identity?) nullable when unavailable.

- [ ] **P11-T1.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
def test_redaction_removes_credential_fields():
    from core.telemetry import redact
    result = redact({"authorization":"Bearer secret","api_key":"secret","run_id":"r1"})
    assert result["authorization"] == "[redacted]"
    assert result["api_key"] == "[redacted]"
    assert result["run_id"] == "r1"
```

- [ ] **P11-T1.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P11-T1.3 — Implement the minimal production behavior.** Reuse installed logging/structlog and stable run IDs. Instrument API latency/errors, queue delay, ingest stages, embeddings, models and tool duration with bounded-cardinality labels. Redact auth headers, cookie values, credential URLs and provider keys; raw prompts/documents disabled by default. Unknown usage stays null; price estimates carry model/rate timestamp and never substitute for authoritative billing. Optional telemetry sink errors are isolated from application transactions.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"model_identity":null,"tokens_in":null,"tokens_out":null,"estimated_cost":null,"latency_ms":120}
```

- [ ] **P11-T1.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Nested secrets, URLs with credentials, telemetry failure, absent model usage, unbounded-label rejection and API protection.

- [ ] **P11-T1.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P11-T2: Operations and data-quality screens

**Files and responsibilities:** Create apps/web/src/modules/observability/operations-page.tsx, apps/web/src/modules/observability/run-table.tsx, apps/web/src/modules/observability/quality-panel.tsx, apps/web/src/modules/observability/usage-panel.tsx; extend /settings/system and /settings/storage; tests/e2e/operations.spec.ts.

**Interfaces — consumes/produces:** GET /system/quality returns document counts,duplicate rate,unresolved entities,failed ingestion/extraction,stale sources,orphan chunks,graph lag; GET /system/queue returns bounded job summaries, not raw payloads.

- [ ] **P11-T2.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```typescript
import { test, expect } from './fixtures';

test('unknown usage is not displayed as free', async ({ page }) => {
  await page.goto('/settings/system');
  await page.getByRole('tab', { name: 'Model usage' }).click();
  await expect(page.getByText('Usage unavailable', { exact: true })).toBeVisible();
});
```

- [ ] **P11-T2.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P11-T2.3 — Implement the minimal production behavior.** Build filterable runs/failures with links to evidence and run details; expose queue state, retry eligibility and actual worker health. Aggregate quality with bounded SQL queries and pagination; do not load every document into memory. Source stale thresholds use configured cadence. Existing UI errors remain visible even when observability profile is disabled.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"orphan_chunks":0,"graph_sync_lag_seconds":null,"usage_state":"unavailable"}
```

- [ ] **P11-T2.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Large synthetic run history paging, no raw payload leak, link to correct failed step, gateway unknown state, worker/graph/n8n outage and disabled optional metrics.

- [ ] **P11-T2.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P11-T3: Retention, maintenance and module lifecycle

**Files and responsibilities:** Create modules/observability/retention.py; extend worker maintenance and module settings; tests/integration/test_retention.py; docs/operations.md.

**Interfaces — consumes/produces:** GET/PATCH /settings/retention; defaults agent traces 90 days,raw sources retain,document history retain; maintenance run summaries include deleted counts and next eligible time. Module disable removes schedules/navigation/tools while preserving data.

- [ ] **P11-T3.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_trace_retention_preserves_document_history(retention_fixture):
    await retention_fixture.seed_old_trace_and_document()
    await retention_fixture.prune()
    assert await retention_fixture.old_trace_count() == 0
    assert await retention_fixture.document_version_count() == 1
```

- [ ] **P11-T3.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P11-T3.3 — Implement the minimal production behavior.** Define fixture with DB timestamps beyond configured cutoff. Delete expired telemetry and temporary data in bounded batches, with indexes and time limits; never run blocking vacuum/full-database maintenance from a UI request. Emit no log for unchanged polls/zero work; warn on actionable failure and debug on actual maintenance. Disable modules through descriptor dependency checks so dependents become unavailable consistently without cascade deletion.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"agent_trace_days":90,"raw_source_retention":"retain","document_history_retention":"retain"}
```

- [ ] **P11-T3.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Cutoff boundary, retry/idempotency, no-op log capture, module disable during pending job, dependency conflicts and preservation of stored knowledge.

- [ ] **P11-T3.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P11-T4: Optional Langfuse and complete operational acceptance

**Files and responsibilities:** Create infrastructure/observability/compose.yml and docs/observability.md; tests/integration/test_observability_outage.py; update docs/deployment.md and status.

**Interfaces — consumes/produces:** Optional Langfuse integration is configured by deployment profile; public application APIs and core persistence are unchanged when unavailable. Egress of telemetry containing content requires explicit owner policy.

- [ ] **P11-T4.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_sink_failure_does_not_fail_document_write(telemetry_outage_fixture):
    response = await telemetry_outage_fixture.create_document()
    assert response.status_code == 201
```

- [ ] **P11-T4.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P11-T4.3 — Implement the minimal production behavior.** Keep Langfuse off on the base 8GB deployment. Pin integration dependency only if profile implemented; provide scrubbed trace summaries and owner-selected content policy. Record measurements with and without optional telemetry. Document troubleshooting from UI error to run to correlation ID, health boundaries and no-op logging semantics.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"telemetry_sink":"disabled","content_capture":false}
```

- [ ] **P11-T4.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Start core stack without sink, simulate sink timeout, verify healthy writes and readable prior logs. Common gate; next P12-T1.

- [ ] **P11-T4.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Phase Acceptance and Handoff

- [ ] Build the phase deliverables with `./scripts/dev.ps1 build` (or `make build`); no tests, lint or typecheck run during the code stage.
- [ ] Verify new code is included in Docker/packaging, new tables in Alembic metadata, public APIs in OpenAPI and enabled UI/routes in module descriptors.
- [ ] Complete independent final review under the execution skill, fix actionable findings, and repeat affected checks.
- [ ] After all Phase 1-12 production code is complete, run the deferred test stage from the master plan; record results, live integration evidence and capacity limitations.
- [ ] Update `docs/IMPLEMENTATION_STATUS.md`, this checklist and `EXECUTION.md`. Continue automatically to the next ready approved task; stop only the work that depends on an unresolved external gate or a material unapproved change.

## Plan Self-Review Checklist

- [x] Goal and spec sections mapped to named tasks and public interfaces.
- [x] Five review-focus risks assigned concrete failure checks in the owning tasks.
- [x] Exact file targets, acceptance examples, deferred test criteria, implementation rules and build criteria included.
- [x] Module ownership, auth/privacy, safe deletion and retry/resume boundaries preserved.
- [x] Implementation and live/hardware verification are not claimed complete by this plan.
