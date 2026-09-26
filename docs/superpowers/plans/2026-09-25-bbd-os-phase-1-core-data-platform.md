# BBD-OS Phase 1 — Core Data Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Persist and manage sources and documents with provenance, immutable revisions, authenticated APIs, and useful library screens.

**Architecture:** Implement the sources, knowledge/documents capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 0 acceptance supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 2.3, 13, 73–85, 95, 110–112, 139–156. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 0 acceptance.

**Implementation status:** Phase 1 production code/build and whole-branch source review are complete. P01-T1 was completed and tested before the owner changed the sequence; its historical evidence is retained. P01-T2 through P01-T4 task reviews and the final Phase 1 review are clean. Behavioral acceptance is deferred until all Phase 1-12 production code is complete.

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

1. Expired sessions and cross-origin mutations remain denied after extracting shared auth dependencies.
2. Concurrent content updates cannot overwrite revisions or create duplicate version numbers.
3. Deleting a connector preserves evidence unless the owner explicitly requests data removal.
4. A deployment image must include new modules and Alembic must discover their metadata.
5. Tests must not depend on owner-setup test order or erase a non-test database.

## File Structure and Boundaries

Module ownership: **sources, knowledge/documents**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P01-T1: Public auth boundary and runnable domain packaging

**Files and responsibilities:** Modify core/auth/routes.py, core/system/routes.py, apps/api/main.py, pyproject.toml, infrastructure/docker/api.Dockerfile, infrastructure/postgres/migrations/env.py, Makefile, scripts/dev.ps1, scripts/test.sh, .github/workflows/ci.yml; create core/auth/dependencies.py, tests/integration/conftest.py, tests/integration/test_library_auth.py. Also modify docker-compose.test.yml; create tests/e2e/fixtures.ts and modules/__init__.py for domain-package discovery.

**Interfaces — consumes/produces:** require_owner(request, session) -> AuthSession and require_owner_write(request, session, origin, csrf_token) -> AuthSession; preserve existing cookie/signature/expiry semantics. owner_client: authenticated httpx.AsyncClient fixture with Origin and current CSRF headers; anonymous_client: same origin without auth cookies.

- [x] **P01-T1.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_library_auth.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
from core.auth.dependencies import require_owner, require_owner_write

async def test_public_auth_dependency_keeps_system_private(anonymous_client):
    assert callable(require_owner) and callable(require_owner_write)
    response = await anonymous_client.get("/api/v1/system/health")
    assert response.status_code == 401
```

- [x] **P01-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_library_auth.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [x] **P01-T1.3 — Implement the minimal production behavior.** Move the shared session, Origin and CSRF checks behind the public auth dependency without copying implementations into feature modules. Include modules in wheel packaging, Docker COPY, Alembic metadata imports, Ruff/mypy and CI. Run the existing owner-race integration first against the fresh test instance, then other API cases with a fixture that logs in using the test owner. Before browser bootstrap reset all application tables except alembic_version only after verifying the unique disposable Compose project and database bbd_test. Add optional -PytestTarget/-E2eTarget arguments with Make/Linux parity as specified in the master. Expose PostgreSQL only on a temporary loopback port in the disposable test profile and pass TEST_DATABASE_URL to DB fixtures after checking database/user bbd_test. db_session uses a transaction/savepoint boundary for test isolation. Browser fixtures create/login the disposable owner and provision named test resources; reuse browser storage state after the existing setup flow instead of relying on test file order.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"authenticated":true,"csrfToken":"test-session-token"}
```

- [x] **P01-T1.4 — Verify the behavior and listed failure cases.** uv run pytest tests/test_auth_session.py tests/test_auth_setup.py -q; ./scripts/dev.ps1 test. Include missing Origin, expired CSRF, wrong session token and unrelated integrity-error cases. Build the API image and import modules inside it.

- [x] **P01-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P01-T2. Do not create a commit automatically.

## Task P01-T2: Source/document schema and authenticated CRUD

**Files and responsibilities:** Create modules/sources/__init__.py, modules/sources/models.py, modules/sources/schemas.py, modules/sources/public.py, modules/sources/routes.py, modules/sources/descriptor.py; modules/knowledge/documents/__init__.py, modules/knowledge/documents/models.py, modules/knowledge/documents/schemas.py, modules/knowledge/documents/public.py, modules/knowledge/documents/routes.py; required Python package markers; core/modules.py; infrastructure/postgres/migrations/versions/0002_library.py; tests/integration/test_library_api.py.

**Interfaces — consumes/produces:** SourceCreate(type,name,provider?), SourceRead(id,type,name,status,local_only,created_at,updated_at); DocumentCreate(source_id,title,content,external_id?,metadata?); DocumentRead includes current_version. GET/POST /sources and /documents; GET/PATCH/DELETE /sources/{id}, /documents/{id}; PUT /documents/{id}/content accepts expected_version; GET /documents/{id}/versions and /versions/{number}. Lists use limit<=100 and opaque next_cursor.

- [x] **P01-T2.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_revision_keeps_original(owner_client):
    source = (await owner_client.post("/api/v1/sources",
        json={"type":"manual","name":"Revision fixture"})).json()
    doc = (await owner_client.post("/api/v1/documents",
        json={"source_id":source["id"],"title":"Note","content":"first"})).json()
    changed = await owner_client.put(f"/api/v1/documents/{doc['id']}/content",
        json={"expected_version":1,"content":"second"})
    assert changed.status_code == 200
    old = await owner_client.get(f"/api/v1/documents/{doc['id']}/versions/1")
    assert old.json()["content"] == "first"
```

- [x] **P01-T2.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [x] **P01-T2.3 — Implement the minimal production behavior.** Use UUIDs, JSONB and UTC timestamps; map the SQL column metadata through an ORM attribute such as metadata_json (DeclarativeBase reserves metadata). Match canonical fields; optional imported attributes start null. Keep source config server-managed and secret-free. Add unique non-null (source_id,external_id), unique (document_id,version_number), relevant FK/date indexes. Use a row lock and expected_version for append; stale input returns 409, identical content returns the current revision. Cap manual content at 1 MiB UTF-8 and metadata at 64 KiB; reject unknown fields and non-object metadata. Keep hashes server-derived. Implement core/modules.py with descriptors for these real source/knowledge consumers; reject duplicate IDs/missing dependencies and provide navigation/settings metadata. Source lifecycle active/paused/archived is separate from connector health. Connector-only deletion archives identity and retains documents; with_data deletes the owned documents/versions transactionally in this phase. Later phases extend this exact deletion intent to their derived data.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"source_id":"uuid","title":"Manual note","content":"Original text","metadata":{},"external_id":null}
```

- [x] **P01-T2.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: automated behavior checks, simultaneous revision writes (one winner/one 409), unknown IDs, stable cursor ordering, protected reads/writes, upgrade from 0001_auth and repeat upgrade without auth loss. Downgrade checks only on disposable data.

- [x] **P01-T2.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P01-T3: Library UI and first real module consumers

**Files and responsibilities:** Create apps/web/src/core/app-shell/workspace-shell.tsx, apps/web/src/core/module-registry.ts; apps/web/src/modules/sources/api.ts, apps/web/src/modules/sources/source-form.tsx, apps/web/src/modules/sources/source-list.tsx; apps/web/src/modules/knowledge/api.ts, apps/web/src/modules/knowledge/document-form.tsx, apps/web/src/modules/knowledge/document-detail.tsx; app route wrappers for /sources, /knowledge/documents, /knowledge/documents/[documentId], /settings/system; modify apps/web/src/app/app/page.tsx; create tests/e2e/library.spec.ts.

**Interfaces — consumes/produces:** Frontend DTOs mirror the API. Thin Next route wrappers import their owning frontend module. /app becomes a compatibility redirect to /knowledge/documents; /settings/system preserves Phase 0 health. Root auth routing remains valid; Today takes over authenticated / in Phase 8.

- [x] **P01-T3.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```typescript
import { test, expect } from './fixtures';

test('manual document survives reload', async ({ page }) => {
  await page.goto('/knowledge/documents');
  await page.getByRole('button', { name: 'New document' }).click();
  await page.getByLabel('Title').fill('Remember this');
  await page.getByLabel('Content').fill('A durable local note');
  await page.getByRole('button', { name: 'Save' }).click();
  await page.reload();
  await expect(page.getByText('A durable local note', { exact: true })).toBeVisible();
});
```

- [x] **P01-T3.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [x] **P01-T3.3 — Implement the minimal production behavior.** Make manual sources explicit in the product UI; browser fixture creation and Phase 0 navigation assertion updates are deferred to the test stage. Build sources/documents list, detail, version history, metadata edit and confirmed deletion using existing form/query/UI libraries. Preserve drafts on 409; invalidate affected query keys on success; clear private caches on logout/401. Module descriptors supply navigation/settings; do not show future screens. Reuse existing semantic colors and add proper empty/loading/error states.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"id":"knowledge","label":"Knowledge","href":"/knowledge/documents","enabled":true}
```

- [x] **P01-T3.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred browser checks: document creation and reload, keyboard submission, revision conflict with draft preservation, delete cancel/confirm, source retirement, and small viewport. No tests are run during code implementation.

- [x] **P01-T3.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P01-T4: Seed, contracts and delivery record

**Files and responsibilities:** Create modules/knowledge/documents/seed.py, tests/integration/test_seed.py; modify Makefile, scripts/dev.ps1, README.md, docs/development.md, docs/IMPLEMENTATION_STATUS.md.

**Interfaces — consumes/produces:** make seed and ./scripts/dev.ps1 seed explicitly import fictional Phase 1 fixtures; seed_demo(session) -> SeedReport(created,existing). No startup seeding or silent successful no-op commands.

- [x] **P01-T4.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_seed_is_idempotent(db_session):
    from modules.knowledge.documents.seed import seed_demo
    first = await seed_demo(db_session)
    second = await seed_demo(db_session)
    assert first.created > 0
    assert second.created == 0
```

- [x] **P01-T4.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [x] **P01-T4.3 — Implement the minimal production behavior.** Use stable fixture identities in a dedicated demo namespace and never update user-edited records on repeat seed. The disposable PostgreSQL `db_session` fixture and test-only runner integration are deferred until the test stage; do not modify test files during code implementation. Record schema and deletion behavior now, then add exact test evidence during deferred acceptance. Do not classify the rest of the canonical catalog as omitted—its owning phases are in the master.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"created":3,"existing":0}
```

- [x] **P01-T4.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Seed twice on disposable data, preserve a modified demo note, migrate an existing Phase 0 DB copy and run the common gate. Update the execution ledger, then advance to P02-T1 during execution.

- [x] **P01-T4.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Phase Acceptance and Handoff

- [x] Build the phase deliverables with `./scripts/dev.ps1 build` (or `make build`); no tests, lint or typecheck run during the code stage.
- [ ] Verify new code is included in Docker/packaging, new tables in Alembic metadata, public APIs in OpenAPI and enabled UI/routes in module descriptors.
- [x] Complete independent final review under the execution skill, fix actionable findings, and repeat affected checks.
- [ ] After all Phase 1-12 production code is complete, run the deferred test stage from the master plan; record results, live integration evidence and capacity limitations.
- [x] Update `docs/IMPLEMENTATION_STATUS.md`, this checklist and `EXECUTION.md`. Continue automatically to the next ready approved task; stop only the work that depends on an unresolved external gate or a material unapproved change.

## Plan Self-Review Checklist

- [x] Goal and spec sections mapped to named tasks and public interfaces.
- [x] Five review-focus risks assigned concrete failure checks in the owning tasks.
- [x] Exact file targets, acceptance examples, deferred test criteria, implementation rules and build criteria included.
- [x] Module ownership, auth/privacy, safe deletion and retry/resume boundaries preserved.
- [x] Implementation and live/hardware verification are not claimed complete by this plan.
