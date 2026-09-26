# BBD-OS Phase 9 — GitHub Collection and Project Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Collect repositories, issues, pull requests, commits and releases through packaged workflows and expose their evidence in knowledge, Timeline and Today.

**Architecture:** Implement the connectors/github capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 2 connector contract; Phases 4–8 entity/event/project presentation supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 53, 95, 115, 138.5, 159. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 2 connector contract; Phases 4–8 entity/event/project presentation.

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

1. Bootstrap must visit all provider pages without skipping records that update mid-sync.
2. A webhook can be duplicated, out of order or forged.
3. Provider IDs survive repository rename and are not replaced by mutable URLs.
4. Rate limiting is different from authentication failure and must not cause tight retry loops.
5. Unsupported deletion discovery is shown honestly rather than silently retaining stale certainty.

## File Structure and Boundaries

Module ownership: **connectors/github**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P09-T1: Versioned GitHub workflows and connection setup

**Files and responsibilities:** Create modules/connectors/github/adapter.py, modules/connectors/github/schemas.py, modules/connectors/github/normalization.py; infrastructure/n8n/workflows/github.json; tests/test_github_mapping.py; docs/connectors/github.md; extend source setup UI.

**Interfaces — consumes/produces:** GitHubSourceConfig(repository,include_issues,include_pulls,include_commits,include_releases); provider credentials remain n8n-owned references. Connector registry exposes validate/sync/normalize/health without GitHub-specific imports in ingestion.

- [ ] **P09-T1.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
def test_repository_identity_does_not_depend_on_name():
    from modules.connectors.github.normalization import repository_key
    assert repository_key({"id":123,"full_name":"old/name"}) == repository_key(
        {"id":123,"full_name":"new/name"})
```

- [ ] **P09-T1.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P09-T1.3 — Implement the minimal production behavior.** Map stable numeric/node IDs to canonical external_id; document repository scope and permissions. Package real n8n export with credential references, source binding, batch receipt and response checking. Expose read-only collection only; no issue/comment writes implied. Validate selected repo and enabled resource types; display actual last successful validation.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"provider":"github","repository":"owner/repo","include_issues":true,"include_pulls":true,"include_commits":true,"include_releases":true}
```

- [ ] **P09-T1.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Mapping tests for all required resources, repository rename, missing fields, multiline Unicode and private credential redaction. Import the workflow in the pinned n8n and validate against a controlled test repository.

- [ ] **P09-T1.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P09-T2: Pagination, incremental sync and verified webhooks

**Files and responsibilities:** Create modules/connectors/github/sync.py, modules/connectors/github/webhooks.py; tests/integration/test_github_sync.py; extend protected connector webhook routes and n8n template.

**Interfaces — consumes/produces:** POST /connectors/github/webhook verifies delivery signature and unique delivery ID; per-resource cursor persisted by BBD-OS only after durable batch acknowledgment. Source runs share the Phase 2 lease.

- [ ] **P09-T2.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_duplicate_webhook_has_one_effect(github_webhook_fixture):
    payload = github_webhook_fixture.signed_issue_update()
    await github_webhook_fixture.deliver(payload)
    await github_webhook_fixture.deliver(payload)
    assert await github_webhook_fixture.count_observations() == 1
```

- [ ] **P09-T2.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P09-T2.3 — Implement the minimal production behavior.** Create fixture with real receipt store and locally signed payloads. Follow provider pagination, use bounded history plus updated-time overlap, dedupe by stable identity/version and prevent stale cursors replacing newer ones. Verify signatures over original bytes with constant-time comparison before parsing/trusting events; reject unsupported oversized events. Honor Retry-After/reset times, bound retries, and distinguish invalid permissions. Document which deletion/visibility changes can be discovered by webhook or reconciliation and mark unobservable records stale/unverified when access disappears.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"delivery_id":"provider-id","source_id":"uuid","resource":"issue","provider_id":"123","updated_at":"2026-09-25T03:00:00Z"}
```

- [ ] **P09-T2.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Multiple pages, edits during scan, forged signature, out-of-order events, duplicate deliveries, permission revoke, 429/403 semantics and restart mid-page. No external writes during tests.

- [ ] **P09-T2.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P09-T3: Canonical mapping and incremental knowledge updates

**Files and responsibilities:** Extend modules/connectors/github/normalization.py and registry mappings; create tests/integration/test_github_knowledge.py; add project relationships via public entity/event APIs.

**Interfaces — consumes/produces:** Normalized GitHub documents retain source URL/provider identity/version. Repository is an entity; commits/issues/pulls/releases contribute typed events and relationships through public contracts, not direct table writes.

- [ ] **P09-T3.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_issue_edit_appends_document_version(github_collection_fixture):
    issue = await github_collection_fixture.collect_issue(title="Before", updated_at="2026-09-25T01:00:00Z")
    await github_collection_fixture.collect_issue(title="After", updated_at="2026-09-25T02:00:00Z")
    history = await github_collection_fixture.document_versions(issue["document_id"])
    assert len(history) == 2
```

- [ ] **P09-T3.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P09-T3.3 — Implement the minimal production behavior.** Implement collection fixture against receipt+pipeline with deterministic provider pages. Separate issue and pull-request normalization to avoid duplicate issue-like records; preserve commit SHA and release identifiers. Update entities/events only for changed versions; project relationships keep evidence. Deletions invalidate derived content through the common deletion workflow. Register github read tools for Project Agent using canonical services.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"external_id":"github:issue:123","canonical_url":"https://github.com/owner/repo/issues/1","event_type":"github_issue","repository_entity_id":"uuid"}
```

- [ ] **P09-T3.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Edited/closed/reopened issue, PR changes, repeated commit observations, release edits, repository rename and deleted source evidence. Verify search/entity/timeline indexing reflects edits without duplicates.

- [ ] **P09-T3.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P09-T4: GitHub UI and end-to-end acceptance

**Files and responsibilities:** Extend apps/web/src/modules/sources/ connector setup and sync history; project widgets in apps/web/src/modules/dashboard; tests/e2e/github.spec.ts; docs/model-compatibility.md only when model use is exercised.

**Interfaces — consumes/produces:** Sources renders GitHub scope, run state, fetched/indexed timestamps and separate errors. Project views and drawer context use existing entity/source IDs.

- [ ] **P09-T4.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```typescript
import { test, expect } from './fixtures';

test('GitHub source explains its collected scope', async ({ page }) => {
  await page.goto('/sources');
  await page.getByRole('link', { name: 'GitHub fixture repository' }).click();
  await expect(page.getByText('Issues, pull requests, commits and releases')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sync now' })).toBeEnabled();
});
```

- [ ] **P09-T4.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P09-T4.3 — Implement the minimal production behavior.** Guide credentials in n8n and return validation, not an invented credentials editor. Show live run counts/status and links to provider evidence; surface project changes in Today and Timeline via existing providers. Test with a controlled repository populated with all five required resource classes; fixtures alone prove mapping, not live permissions/connectivity.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"resource_counts":{"repositories":1,"issues":2,"pull_requests":1,"commits":3,"releases":1},"live_verified":false}
```

- [ ] **P09-T4.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Packaged workflow, initial collection, incremental edit, restart, project display and cited Ask about a known repository fact. Common gate; next P10-T1.

- [ ] **P09-T4.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

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
