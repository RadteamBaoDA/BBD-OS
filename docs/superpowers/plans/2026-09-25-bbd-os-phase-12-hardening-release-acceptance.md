# BBD-OS Phase 12 — Hardening, Backup, Recovery and Full Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Verify the full approved product on a clean installation and documented mini-host workload with recoverable backups and honest operational limits.

**Architecture:** Implement the backup, export, settings plus cross-module validation capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Functional acceptance from Phases 1–11; actual target hardware and permitted live integrations for final release gate supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 71, 78–94, 108–135, 155, 161–162. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Functional acceptance from Phases 1–11; actual target hardware and permitted live integrations for final release gate.

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

1. A backup that exists is not a verified restore, especially across PostgreSQL, raw files, n8n and graph.
2. Forget must reach vectors/graph/memory/caches and block in-flight recreation.
3. The 2-core/8GB target needs measured concurrent workload, not a Docker startup claim.
4. Drawer focus/viewport/context behavior must hold across desktop, mobile and interrupted streams.
5. Fresh installation and upgrade must preserve owner data; cleanup must never target user volumes.

## File Structure and Boundaries

Module ownership: **backup, export, settings plus cross-module validation**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P12-T1: Consistent backup/restore and export

**Files and responsibilities:** Create modules/backup/manifest.py, modules/backup/service.py, modules/backup/routes.py; modules/export/public.py, modules/export/routes.py; scripts/backup.py and scripts/restore.py; frontend backup/storage settings; tests/integration/test_restore.py; extend Makefile and scripts/dev.ps1.

**Interfaces — consumes/produces:** make backup, make restore BACKUP=... and PowerShell equivalents; authenticated backup/export operation endpoints return operation_id. Manifest includes component/schema versions,checksums,files,creation time,consistency method and required protected key references.

- [ ] **P12-T1.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_restored_document_matches_original(backup_fixture):
    original = await backup_fixture.create_sample()
    archive = await backup_fixture.backup()
    restored = await backup_fixture.restore_into_disposable_instance(archive)
    assert restored["content_hash"] == original["content_hash"]
```

- [ ] **P12-T1.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P12-T1.3 — Implement the minimal production behavior.** Quiesce ingestion/agents/automations and writes for the baseline consistency window; record state and resume even on failure. Snapshot PostgreSQL, raw files, compatible graph backup, n8n data and its encryption key, schedules and configuration; protect secret-bearing archive content and do not log keys. Restore into a separate instance first, validate versions/checksums and database migrations, then verify jobs and workflows. Export JSON/Markdown/CSV per domain through public APIs, excluding credentials. Whole-instance restore onto existing owner data requires explicit destructive confirmation.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"format_version":1,"consistency":"quiesced","components":["postgres","raw_files","graph","n8n","configuration"],"checksums":{}}
```

- [ ] **P12-T1.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Successful restore after simulated host loss, missing raw blob/key, corrupt checksum, incompatible schema and interrupted backup; restored n8n credentials usable without printing them. Export-import roundtrip for supported canonical fields.

- [ ] **P12-T1.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P12-T2: Cross-module deletion, security and recovery audit

**Files and responsibilities:** Extend per-module deletion hooks and operation status; create tests/integration/test_forget_lifecycle.py, tests/integration/test_failure_recovery.py, docs/security.md; revise privacy settings help.

**Interfaces — consumes/produces:** Source deletion modes connector_only|with_data; immediate tombstone denies retrieval, durable purge removes every owned derived copy. DELETE entity/conversation and memory forget preserve unrelated/shared evidence; backup retention is explained separately.

- [ ] **P12-T2.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_forget_excludes_all_retrieval_paths(forget_fixture):
    resource = await forget_fixture.seed_all_derivatives()
    await forget_fixture.forget(resource)
    assert await forget_fixture.search_hits(resource) == []
    assert await forget_fixture.graph_hits(resource) == []
    assert await forget_fixture.memory_hits(resource) == []
```

- [ ] **P12-T2.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P12-T2.3 — Implement the minimal production behavior.** Test source documents/chunks/vectors/graph episodes/memory/citation payloads/cache/queued jobs and trace content against one deletion intent. Keep shared facts only when independent retained evidence supports them. Audit session/CSRF, input size, upload ZIP/PDF, SSRF redirects/DNS/browser requests, prompt injection, MCP grants, approval replay and logs. Recovery matrix covers kill API/worker/Redis/graph/n8n at durable boundaries; external uncertain effects require review. Apply critical fixes at the owning module and rerun affected contracts.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"operation_id":"uuid","status":"running","immediate_access_revoked":true,"remaining_stages":["graph","files"]}
```

- [ ] **P12-T2.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: No deleted content returned while purge pending, no resurrection after worker replay, independent evidence retained, expiry/revocation checks, and recovery without losing acknowledged data. Old backups remain governed by backup retention rather than falsely claimed erased.

- [ ] **P12-T2.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P12-T3: Complete onboarding, demo data and drawer accessibility

**Files and responsibilities:** Extend onboarding route flow and seed modules; create tests/e2e/onboarding.spec.ts, tests/e2e/drawer-accessibility.spec.ts, tests/e2e/offline.spec.ts; docs/ux/today-chat.md and README.md.

**Interfaces — consumes/produces:** Onboarding: owner -> model/privacy -> capability test -> sources -> explicit sample/personal import -> indexing progress -> Today. Each step is resumable; no model or network still permits existing local data access.

- [ ] **P12-T3.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```typescript
import { test, expect } from './fixtures';

test('mobile drawer closes without losing selected day', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?date=2026-09-25');
  await page.getByRole('button', { name: 'Open chat' }).click();
  await expect(page.getByRole('dialog', { name: 'Chat' })).toBeVisible();
  await page.getByRole('button', { name: 'Close chat' }).click();
  await expect(page.getByLabel('Selected day')).toHaveValue('2026-09-25');
});
```

- [ ] **P12-T3.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P12-T3.3 — Implement the minimal production behavior.** Seed fictional projects/events/articles/tasks/entities/relationships/conversations only on explicit command with stable IDs and no user-data overwrite. Verify all navigation/settings screens, language consistency with existing UI, keyboard focus, readable contrast, reduced motion, error states and mobile Today/Ask/Tasks/Notifications. Drawer default closed, right overlay/full-mobile, focus trap/return, preserved draft/context, explicit Stop and citations/history inside drawer; no permanent empty column. Offline guarantees stored data and lexical search; remote-dependent chat/semantic query visibly unavailable. Add safe reset command with named workspace and explicit destructive confirmation, never a successful no-op.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"onboarding_step":"indexing","lexical_ready":true,"semantic_ready":false,"reason":"No permitted embedding model"}
```

- [ ] **P12-T3.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Fresh/resumed onboarding, keyboard-only flow, screen-reader dialog labels, viewport overflow, day switch during stream, drawer/full Ask same conversation, offline mode and demo repeat idempotency.

- [ ] **P12-T3.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P12-T4: Target hardware capacity and service budget

**Files and responsibilities:** Create tests/performance/test_workload.py, tests/fixtures/performance/manifest.json, docs/performance-report.md; update deployment profiles and limits only from measurements.

**Interfaces — consumes/produces:** Report exact hardware/OS/architecture,all versions,enabled profiles,gateway location,model IDs,dataset/concurrency,peak memory,CPU,queue delay and latency distribution. No hardware capacity statement from the development host alone.

- [ ] **P12-T4.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
def test_report_records_concurrent_workload(performance_report):
    assert performance_report["cpu_cores"] == 2
    assert performance_report["ram_gib"] == 8
    assert performance_report["workload"]["ingestion_during_interactive"] is True
    assert performance_report["oom_events"] == 0
```

- [ ] **P12-T4.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P12-T4.3 — Implement the minimal production behavior.** Run controlled workload with 1000 documents/10000 chunks, 2000 entities/5000 relationships and 10000 events, plus the final acceptance dataset, labeling both synthetic and real data. Measure 30 minutes of ingestion while one user searches/asks and one bounded browser task is queued; ensure the global heavy-work lease prevents overlapping heavy browser/parsing/indexing. Base targets: Today initial <2s, normal API <300ms, search <1s, timeline first page <500ms, first agent token <3s excluding separately recorded provider latency. Report p50/p95 with p95 used for acceptance, no OOM/data loss and bounded queue recovery. Prebuild images; tune one-heavy/two-model limits downward first if required.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"target_host_verified":false,"latency":{"provider_ms":null,"application_ms":null},"oom_events":null}
```

- [ ] **P12-T4.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: The performance_report fixture reads measured output, never fabricated metrics; skip with explicit reason when target host absent, leaving this gate blocked. Off-host graph/browser or changing capabilities requires an explicit architecture/deployment decision.

- [ ] **P12-T4.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P12-T5: Clean-install, upgrade and complete-product release gate

**Files and responsibilities:** Create tests/e2e/full-product.spec.ts, docs/release-checklist.md; update README.md, docs/deployment.md, docs/IMPLEMENTATION_STATUS.md, docs/ARCHITECTURE_DECISIONS.md and execution ledger.

**Interfaces — consumes/produces:** Final acceptance uses published documented commands, protected production proxy paths, backup/restore and module enable/disable. Add a test-only module descriptor to prove navigation/settings/widgets/tools are registered without editing unrelated feature logic.

- [ ] **P12-T5.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```typescript
import { test, expect } from './fixtures';

test('approved task appears in Today', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Open chat' }).click();
  await page.getByRole('button', { name: 'Accept proposed tasks' }).click();
  await page.getByRole('button', { name: 'Close chat' }).click();
  await expect(page.getByRole('link', { name: 'Review project updates' })).toBeVisible();
});
```

- [ ] **P12-T5.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P12-T5.3 — Implement the minimal production behavior.** Create an isolated acceptance installation, add three RSS feeds, one GitHub repository, five text-bearing PDFs and several URLs. Verify extraction/chunking/embeddings/entities/events/graph, useful Today, mixed-source Timeline, citations, agent task proposal/acceptance, automatic brief, automations and restore. Fixture the proposed task through a controlled agent run; no assumption that a live model emits exact arbitrary text. Run all required checks, dependency/license audit and production Docker builds. Validate upgrade of a Phase 0 database copy and module enable/disable without editing dashboard internals. Do not mark full product complete with blocked live/hardware/restore checks.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"functional_acceptance":"pending","live_integrations":"pending","target_capacity":"pending","restore_verified":false}
```

- [ ] **P12-T5.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: automated behavior checks; disposable clean migrations, seed, E2E, live connector/model evidence, recovery, and target performance report. Final independent review fixes actionable findings; preserve no-commit/no-push/no-deploy boundary unless separately authorized.

- [ ] **P12-T5.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

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
