# BBD-OS Execution Ledger

## Owner authorization and current checkpoint

- Approved scope: master specification plus the approved Phase 1–12 breakdown and chat drawer clarification.
- Execution method: Subagent-driven as previously requested; continuous progression through ready tasks and phases. Implementation stage is code plus builds only; tests begin after all Phase 1-12 code is complete.
- Current action: Phase 1 is merged into main as `d425057`; P02-T1 through P02-T3 code/build/review are complete in `codex/bbd-os-phase-2`. P02-T2 commits are `cfe481b`, `e57ea74`, and `14b0f41`; P02-T3 follow-up commit is `9114775`. P02-T4 code/build and independent review are complete; four review findings were fixed and scoped re-review approved. Phase 2 merged to `main` as `2f7c409`. P03-T1 has started in `codex/bbd-os-phase-3`. Tests remain deferred until all Phase 1-12 production code is complete.
- Current implementation phase: 3.
- Active implementation task: **P03-T1 - Gateway configuration, capability probes and privacy policy**.
- Next task: finish P03-T1 code/build/review/commit, then continue to P03-T2.
- Read [master plan](2026-09-25-bbd-os-master-plan.md) before implementation.
- Preserve Phase 0 and user changes. Commit each completed phase; merge Phase 1 into main after implementation and review. Do not push or deploy.

## Phase checkpoints

| Phase | Plan | Implementation | Next task | Evidence |
| --- | --- | --- | --- | --- |
| 0 | Existing | Complete | None | See ../../IMPLEMENTATION_STATUS.md |
| 1 | [Ready](2026-09-25-bbd-os-phase-1-core-data-platform.md) | Code/build and review complete; merged to main | P02-T1 | Build and whole-branch review passed; commit `da2baee`, merge `d425057`; deferred behavioral acceptance remains |
| 2 | [Ready](2026-09-25-bbd-os-phase-2-ingestion-connectors.md) | Complete; merged to main | P03-T1 | Commit `2f7c409`; T4 build passed and independent review approved; acceptance deferred |
| 3 | [Ready](2026-09-25-bbd-os-phase-3-search-model-gateway.md) | In progress | P03-T1 | Started on `codex/bbd-os-phase-3` from `2f7c409`; code/build stage only |
| 4 | [Ready](2026-09-25-bbd-os-phase-4-entity-knowledge.md) | Not started | P04-T1 | Not executed |
| 5 | [Ready](2026-09-25-bbd-os-phase-5-temporal-knowledge.md) | Not started | P05-T1 | Not executed |
| 6 | [Ready](2026-09-25-bbd-os-phase-6-ask-chat-drawer-memory.md) | Not started | P06-T1 | Not executed |
| 7 | [Ready](2026-09-25-bbd-os-phase-7-agent-harness-tools.md) | Not started | P07-T1 | Not executed |
| 8 | [Ready](2026-09-25-bbd-os-phase-8-today-daily-chat-tasks.md) | Not started | P08-T1 | Not executed |
| 9 | [Ready](2026-09-25-bbd-os-phase-9-github-integration.md) | Not started | P09-T1 | Not executed |
| 10 | [Ready](2026-09-25-bbd-os-phase-10-automation-workflows.md) | Not started | P10-T1 | Not executed |
| 11 | [Ready](2026-09-25-bbd-os-phase-11-observability-operations.md) | Not started | P11-T1 | Not executed |
| 12 | [Ready](2026-09-25-bbd-os-phase-12-hardening-release-acceptance.md) | Not started | P12-T1 | Not executed |

## External acceptance gates

| Gate | Required evidence | Owning phase | State |
| --- | --- | --- | --- |
| OmniRoute | Endpoint/release, allowed aliases/capabilities, owner egress policy; configure secrets securely | 3–7 | Not verified |
| Graphiti/backend | Pinned compatibility, episode lifecycle/restart and measured footprint | 5 | Not verified |
| n8n workflows | Imported pinned templates, credentials, pagination/cursor/recovery against controlled sources | 2, 9–10 | Not verified |
| Browser | Network isolation, resource limits and actual model tool compatibility for AI browsing | 2, 7 | Not verified |
| Mini host | OS/architecture and measured 2-core/8GiB concurrent workload | 12 | Not verified |
| Restore | Consistent backup and verified restore into separate instance | 12 | Not verified |

## Recording each task

Append one real execution entry when work starts. During Phases 1-12 coding, include task ID, affected files, exact build command/result, review findings, unresolved gates, and next task. Do not run or record tests before all phase code is complete. After code completion, add test-stage evidence separately. Do not prefill invented results. After a context reset, inspect files and current tests before resuming; completed evidence is not permission to overwrite newer user changes.

## Planning delivery

The owner asked to save every phase plan locally and use an on-demand drawer for chat to preserve screen space. This ledger tracks implementation readiness, not a background scheduler. Closing a chat drawer does not cancel a run; the UI Stop action does. Today day-context and saved-brief/current-records semantics are defined by P06 and P08.

Plan rewrite on 2026-09-26: all 12 phase files now keep implementation task checklists to production code, affected builds, and recording/committing results. Behavioral acceptance is prose-only under deferred test-stage sections and starts only after all Phase 1-12 production code is complete. The Phase 1-12 files preserve 49 task IDs and current historical statuses. `git diff --check` passed after the rewrite. Phase 0's completed plan is unchanged.


## P01-T1 start

Started 2026-09-25 in isolated worktree codex/bbd-os-phase-1. Starting tree clean. Scope: public owner/read-write auth dependencies, test harness targets, domain module packaging, and integration/browser fixtures. Existing session cookie, expiration, Origin and CSRF semantics are authoritative.

Completed 2026-09-25. See `../../../.superpowers/sdd/2026-09-25-bbd-os-phase-1/task-1-report.md` for changed files, exact validation, and the staged GitNexus risk summary. Full disposable proof passed: 16 unit tests (4 skipped), owner race 1, auth integration 3, E2E 2; API image import and repeat migration passed. `scripts/dev.ps1 lint` and `typecheck` passed. The auth tests now pin their test origin to avoid `.env` contamination; E2E owner state is saved after the final login so the session remains valid for dependent projects.

Task P01-T1 complete: 9aab3d5 auth dependencies/test packaging; e0bd5a4 distinct Linux test ports. Independent review approved after one minor fix. Full unit/integration/E2E runner, lint, typecheck, image import and repeat migration passed. GitNexus staged detection: HIGH for the auth task (expected shared-auth flows); LOW for the Bash-only fix.


P01-T2 start 2026-09-25: source/document schemas, authenticated CRUD, migration 0002_library, immutable revisions and bounded cursors.

P01-T2 complete 2026-09-26 (review clean). Added canonical nullable source/document fields, strict request/read schemas, owner/CSRF CRUD and version routes, row-lock serialization across source lifecycle/document creation, safe archive/data deletion, <=100 cursor pagination for all list APIs, strict canonical URL-safe cursors (malformed/empty -> 422), module registry/descriptors, no-store API responses and Alembic migration 0002_library. Independent code review findings were fixed and scoped re-reviews approved. GitNexus could not index the new uncommitted symbols; create_app/install_error_handling returned UNKNOWN/lower-bound with zero resolved callers, and source inspection confirmed the current call chain.

Build evidence: `./scripts/dev.ps1 build` passed after the final fix (Next.js production build and all four Docker images: web, api, worker, migrate). No tests, lint or standalone typecheck were run during the code stage. Runtime and migration acceptance, including an earlier pre-fix source-create 500, remain deferred until all Phase 1-12 production code is complete.

Task P01-T2 complete (review clean). Next task: P01-T3 - Library UI and first real module consumers.

P01-T3 implementation complete 2026-09-26; awaiting independent review before P01-T4. Added workspace shell/module navigation, explicit manual-source UI, document list/create/detail/version history/metadata editing/content revision and confirmed deletion; moved Phase 0 health to `/settings/system` and redirected `/app` to documents. Changed production files and review notes are in `../../../.superpowers/sdd/2026-09-25-bbd-os-phase-1/task-3-report.md`.

Final build command: `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-1` — exit 0. Next.js 16.3.6 production build listed all new routes; Docker web, api, worker and migrate images built. No tests, lint or standalone typecheck run. Existing untracked test drafts preserved. Browser behavior, Phase 0 navigation assertion update, P01-T2 runtime/migration acceptance and independent review remain unresolved until their assigned stages. Next ready task after review: P01-T4.

P01-T3 independent review found theme reset on route navigation: each route remounted `WorkspaceShell`. Moved theme state/body effect into root `QueryProvider` and consumed its context in the shell. GitNexus impact: `QueryProvider` UNKNOWN/lower-bound, zero resolved callers; `WorkspaceShell` not found/unindexed. Current-source search confirmed the root and four route consumers. `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-1` passed again (exit 0; Next.js production routes and all four Docker images). No tests, lint or standalone typecheck run. Awaiting scoped re-review before P01-T4.

P01-T3 scoped re-review approved the theme persistence fix; no new findings. Task review is clean.


P01-T4 code/build complete 2026-09-26. Added `modules/knowledge/documents/seed.py`; changed `Makefile`, `scripts/dev.ps1`, `README.md`, `docs/development.md`, `docs/IMPLEMENTATION_STATUS.md`, this ledger and the Phase 1 plan checklist. `seed_demo(session) -> SeedReport(created, existing)` uses PostgreSQL, a fixed `bbd-os.demo.phase-1` namespace and stable UUIDs for one fictional manual source plus two notes/initial revisions. Creation is transactional. Repeated seed does not write an existing source or document, including edited or archived records. Deleted notes remain deleted while the source exists; source deletion with data archives the identity and deletes documents, so a later seed leaves that source alone. The CLI prints counts and propagates database/migration errors. `make seed` and `./scripts/dev.ps1 seed` invoke it explicitly through Compose; there is no startup seed.

Exact build: `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-1` — exit 0. Next.js 16.3.6 production build and Docker web, api, worker and migrate images built; the API image copied the new module. No tests, lint, standalone typecheck or seed execution were run during this code stage. Code review corrected an initial documentation error about source deletion; the documented archive behavior now matches `archive_source`. GitNexus impact was not required for P01-T4 because no existing function, class or method was edited; the new seed symbols are not in the current index. No high/critical risk warning was returned. Independent task review found and fixed one stale implementation-status line in the Phase 1 plan; scoped re-review approved with no other findings. Whole-branch Phase 1 review remains open.

Deferred acceptance: use the existing disposable PostgreSQL `db_session` fixture and test-only runner when the Phase 1-12 code stage ends; add `tests/integration/test_seed.py` then. Seed twice, preserve an edited note and a deletion, migrate a copy of an existing Phase 0 database, and run the common lint/typecheck/test/build gate at the assigned stage. The `sources`, `documents` and `document_versions` schemas are from migration `0002_library`; no schema change was needed for this seed. Other fictional demo categories are owned by later phases. Next ready task after Phase 1 review: P02-T1.

## Phase 1 whole-branch review fix wave

Completed the six actionable review fixes on 2026-09-26; scoped final re-review approved with no new findings. No commit was made in this fix wave.

1. CSRF expiry: `require_owner_write` marks only its authenticated invalid-CSRF rejection with `X-CSRF-Error: invalid`. The shared browser API wrapper refreshes `/api/v1/auth/session`, shares concurrent refreshes, updates the workspace session query through its root listener, and retries the original mutation once with the same body. Origin failures and 401 do not enter this retry. The existing form state remains mounted during token renewal.
2. Windows ports: API port selection retries independently on a web-port collision; PostgreSQL then retries against both chosen ports, matching the Linux runner.
3. Shared cursors: decoded JSON must be exactly a two-element list of strings before timestamp/UUID parsing; malformed shapes return 422.
4. Document version inputs: cursor values and route path numbers are bounded to 1..2147483647. Cursor validation now precedes document lookup; invalid versions never reach the version query.
5. Module ownership: source locking/validation belongs to `sources.public.lock_source_for_document`; document deletion belongs to `documents.public.delete_source_documents`. Both receive the caller's session without committing or returning ORM models. Creation still locks the source before insert; archival locks the source, deletes owned data when requested, then commits both effects together. The two lifecycle modules import public module objects and resolve operations only inside function bodies; neither reads partially initialized cross-module attributes at import time. Direct cross-module ORM imports were removed from these lifecycle modules. The explicit demo composition entrypoint remains unchanged.
6. Delivery docs: the master phase table and checkpoint now reflect implemented Phase 1 code, final review/acceptance handoff and P02-T1 next; AGENTS documents the implemented explicit seed command.

Files changed in this wave: `core/auth/dependencies.py`, `core/pagination.py`, `modules/sources/public.py`, `modules/knowledge/documents/public.py`, `modules/knowledge/documents/routes.py`, `apps/web/src/core/api.ts`, `apps/web/src/core/app-shell/workspace-shell.tsx`, `scripts/dev.ps1`, `AGENTS.md`, `docs/superpowers/plans/2026-09-25-bbd-os-master-plan.md`, and this ledger.

Impact evidence: upstream checks for the modified existing symbols returned UNKNOWN/not found in the older index, except `apiRequest`, which resolved zero callers with lower-bound status. The added checks for `decode_version_cursor`, `list_versions` and `get_version` also returned UNKNOWN/not found. Source inspection covered API consumers, source lifecycle, document creation/history, shared cursor users, auth errors and workspace/form state. No HIGH/CRITICAL warning was returned for this wave. `gitnexus_detect_changes(scope="all", worktree="D:\\Project\\BBD-OS-phase-1")` reported MEDIUM, 122 changed symbols, 29 tracked files and four indexed frontend flows across the accumulated branch; it does not fully cover the new/untracked Phase 1 symbols. The source review remains necessary for those files.

Exact validation: `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-1` exited 0. Next.js 16.3.6 production build (including its integrated TypeScript compilation) succeeded, and Docker web/api/worker/migrate images built. No tests were created, modified or run in this wave; no lint, standalone typecheck, migration, seed, or behavioral checks were run.

Deferred acceptance remains explicit: expired-CSRF recovery and one-retry behavior, Origin/401 denial, draft preservation, malformed and oversized cursor/path cases, concurrent source archive/document creation and transaction rollback, Windows port collisions, module import/runtime behavior, and all existing Phase 1 browser/database/seed/upgrade gates must be exercised in the separate test stage after Phase 1-12 production code is complete. Build success is not behavioral acceptance. Next: commit/merge the reviewed Phase 1 branch, then start P02-T1.

## P02-T1 start

Started 2026-09-26 in isolated worktree `codex/bbd-os-phase-2` at merged Phase 1 commit `d425057`. Scope: durable ingestion receipt/batch/run/stage and source-observation/cursor state, scoped collector authentication, PostgreSQL pending-work/outbox reconciliation into the existing ARQ worker, retry/status APIs, migration 0003, and event contract. No tests, test fixtures, lint or typecheck during code stage; build only.

Pre-edit GitNexus impact was requested for `WorkerSettings`, `startup`, `create_app`, and the migration environment. The MCP index continued to report 5 commits behind after CLI re-index; all results were UNKNOWN/lower-bound with no resolved callers and no HIGH/CRITICAL warning. Current-source inspection confirmed `WorkerSettings` is consumed by docker-compose, `startup` by ARQ configuration, `create_app` in apps/api/main.py, and Alembic imports model modules directly; full `rg` caller search remains necessary.

P02-T1 production implementation and build completed 2026-09-26; independent review and behavioral acceptance remain pending. Added `core/events.py`, `modules/ingestion/{__init__,models,schemas,public,routes,dispatcher}.py`, migration `0003_ingestion.py`, API route registration, Alembic model imports, and ARQ worker dispatch/stage execution. One transaction persists source-scoped batch identity, run/stage, distinct record observations, cursor CAS, renewable 15-minute source lease, collector grant hash and PostgreSQL outbox event before returning 202. Owner endpoints issue/rotate source collector grants, read redacted run/stage status, and retry failed runs. The dispatcher recovers pending/stale outbox rows from PostgreSQL into the existing ARQ Redis queue using deterministic job IDs; worker execution uses a 120-second timeout, one initial attempt plus four bounded jittered retries, and terminal status reporting. Payload content and credentials are not returned in status responses or logged.

GitNexus upstream impact for `startup`, `WorkerSettings`, and `create_app` returned UNKNOWN/lower-bound with zero resolved callers because the index was stale; no HIGH/CRITICAL warning. Manual wiring review confirmed ARQ dotted-path loading, FastAPI factory wiring, and Alembic metadata imports. New ingestion symbols were not indexed. No commit was made.

`gitnexus_detect_changes(scope="all")` returned LOW, two changed files, zero indexed changed symbols, and no affected flows. This only covers indexed files; newly added ingestion modules and the migration are absent from the current index, so source review remains the authority for their scope.

Exact final build: `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-2`, with process-only `POSTGRES_PASSWORD=build-only-placeholder` for Compose interpolation; exit 0. Next.js 16.3.6 production build (including its integrated TypeScript compilation) and Docker web, api, worker, and migrate images built. The first build attempt lacked `node_modules`; `npm.cmd ci` installed from the existing lockfile without changing it. A second build reached Compose but lacked `POSTGRES_PASSWORD`; the final build used the temporary process environment only. No tests, fixtures, lint, standalone typecheck, migration execution, or runtime acceptance were run.

Deferred acceptance: duplicate batches and changed-key conflicts, transaction rollback/commit-before-202, cursor CAS, source lease concurrency/expiry, Redis loss/recovery, ARQ at-least-once behavior and retry timing, grant rotation/denial/source isolation, pause during worker execution, migration upgrade/downgrade, and run retry/status behavior. The current `receive` worker stage verifies accepted observations and marks the durable receipt stage complete; document parsing/indexing belongs to P02-T2 and is not claimed here. Next ready task: P02-T2 after independent P02-T1 review.

P02-T1 scoped review fix wave: extended the source lease to 15 minutes (greater than five 120-second attempts plus maximum retry backoff), renew it whenever a worker attempt starts or schedules a retry, and reject delayed outbox work whose lease expired or was superseded. This lets recovery dispatch retry an active run without allowing a second source batch to overlap; abandoned runs become visible failures after the bounded lease. Retry only timeouts, OS errors and SQLAlchemy operational errors; unexpected exceptions now fail the run/outbox and release its lease. Exact validation: `./scripts/dev.ps1 build` with process-only `POSTGRES_PASSWORD=build-only-placeholder` — exit 0; Next.js build and Docker web/api/worker/migrate images succeeded. No tests, lint or standalone typecheck. GitNexus impact for `process_ingestion_event` and `retry_run` remained UNKNOWN/not found in the stale index; staged change detection returned zero indexed changes because these files/symbols are absent from the index. Manual call path review remains authoritative. Fix wave files: `apps/worker/main.py`, `modules/ingestion/models.py`, `modules/ingestion/public.py`, this ledger, and the task report.

P02-T1 is complete for the code/build stage. The initial independent review found two medium findings (lease could expire during the retry budget; unexpected worker exceptions could leave runs in `running`). Fix commits `3738ef7` and scoped re-review addressed both; no new Critical/Important findings. Feature commit `8aa1ec7`; fix commit `3738ef7`. Tests and runtime/migration acceptance remain deferred. Next: P02-T2.

## P02-T2 start

Started 2026-09-26 after P02-T1 code/build and scoped review completed. Scope: UUID-backed local file storage, bounded PDF/TXT/Markdown/DOCX/JSON/CSV parsing, deterministic chunking, upload/raw retrieval, and durable processing integration. No test files or fixtures during the implementation stage; build only. P02-T1 behavior and its runtime/migration acceptance remain deferred to the final test stage.

P02-T2 production code/build completed 2026-09-26; independent review is pending. Added UUID-named atomic raw storage under `Settings.data_dir`, authenticated upload/raw routes, source+SHA-256 idempotency, durable file parse events through the existing PostgreSQL outbox/ARQ dispatcher, bounded subprocess parsing, and orphan cleanup after a configurable grace period. Added stdlib TXT/Markdown/JSON/CSV parsing plus locked pypdf, python-docx, tiktoken, and multipart dependencies. Defaults: 25 MiB input, 120-second parser timeout, 100 MiB DOCX expanded bytes, 500 PDF pages, deterministic 750-token chunks with 12% overlap. Scanned PDFs report `needs_ocr`; there is no vector indexing. Alembic revision `0004_document_processing` adds extraction status and document-version-owned chunks; API and worker share the `/data` Compose volume.

Changed production files: `.env.example`, `apps/api/main.py`, `apps/worker/main.py`, `core/config.py`, `core/storage.py`, `docker-compose.yml`, `infrastructure/docker/api.Dockerfile`, `infrastructure/postgres/migrations/env.py`, `infrastructure/postgres/migrations/versions/0004_document_processing.py`, `modules/ingestion/{chunking,dispatcher,files,models,parsers,public,routes,schemas,worker}.py`, `modules/knowledge/documents/{descriptor,models,public,routes,schemas}.py`, `pyproject.toml`, and `uv.lock`. Full file list and review caveats: `.superpowers/sdd/2026-09-25-bbd-os-phase-2/task-2-report.md`.

GitNexus upstream impact for `process_ingestion_event`, `append_content`, and `dispatch_pending_work` was UNKNOWN/lower-bound with zero resolved callers. `create_document` was ambiguous between route/service candidates; both results were UNKNOWN with zero resolved callers. `DocumentVersion` was UNKNOWN/lower-bound with dispatch boundary 12. No HIGH/CRITICAL result appeared. Manual source tracing covered API/public contracts, source locking, migration metadata, outbox dispatch, and ARQ registration; the stale index does not establish zero blast radius.

Exact build: `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-2`, with process-only `POSTGRES_PASSWORD=build-only-placeholder`; exit 0. Next.js 16.3.6 production build and Docker web/API/worker/migrate image builds succeeded with locked dependencies. No tests, fixtures, lint, standalone typecheck, migration execution, or runtime acceptance ran. Tests remain deferred until all Phase 1-12 production code is complete. Next: independent P02-T2 review, then P02-T3 after review findings are resolved.

P02-T2 review fix wave committed as `14b0f41` on 2026-09-26. The upload route leaves finalized files for grace-period orphan cleanup when a database outcome may be ambiguous; repeated upload after its document was deleted returns explicit 409; archive, retry and worker lifecycle transactions now follow consistent source→run→stage→document lock ordering where applicable. `./scripts/dev.ps1 build` passed (Next.js and all four Docker images). GitNexus staged detection was LOW, 7 indexed symbols and 0 affected processes; index coverage is limited. No tests, lint, or standalone typecheck ran. Scoped re-review approved: all three prior Important findings addressed, no new Critical/Important finding.

P02-T2 complete (commits `cfe481b..14b0f41`, review clean). Next: P02-T3 - packaged n8n workflows and bounded browser collection.

P02-T3 complete for the production-code/build stage on 2026-09-26; commit `9114775` contains the scoped review fixes and report. URL crawl submission now returns a durable run ID before collection; the worker persists observations and advances the cursor after successful collection. HTTP and Playwright collectors enforce the aggregate 25 MiB response budget while streaming. REST pagination is same-origin with redirects disabled, and REST source URLs are restricted to default HTTP(S) ports. n8n is isolated from PostgreSQL/Redis behind an API-only `/32` firewall exception; transient sidecar 408/425/429/5xx responses use bounded retries. Independent review approved after three scoped fix rounds. GitNexus impact: `crawl` LOW (one caller/flow); `_collect_web_job` LOW (one caller); `registry.validate` CRITICAL (6 callers/10 flows), with the new check limited to API sources; shared `validate_public_url` CRITICAL (12 callers/14 flows) was not changed. `./scripts/dev.ps1 build` passed; merged Compose `build browser n8n` passed. No tests, fixtures, lint, or standalone typecheck ran. Workflow import, credential mapping, live network filtering and provider pagination remain deferred runtime acceptance gates. Next: P02-T4.

P02-T4 independent-review fix wave completed 2026-09-26; awaiting scoped re-review before commit. Kept `Delete all data` available for archived sources; wired the RSS no-change branch to the collector-authenticated `/no-changes` receipt so scheduled and manual no-change syncs update source diagnostics; fenced transient ingestion retries by the event's source generation; and made the shared document-write lock reject paused as well as archived sources. The shared lock has two callers (`create_document` and `receive_file`), covering manual document creation and uploads. GitNexus impacts were UNKNOWN/lower-bound for `SourceList`, `process_ingestion_event`, and `lock_source_for_document`; `acknowledge_no_changes` was not indexed, and route impact lookup failed because the index has no Route table. Lock context resolved both callers and their create/upload flows. No HIGH/CRITICAL impact warning was returned. See `.superpowers/sdd/2026-09-25-bbd-os-phase-2/task-4-report.md` for exact changed files and build evidence. `./scripts/dev.ps1 build` passed with process-only `POSTGRES_PASSWORD=build-only-placeholder`: Next.js 16.3.6 build and Docker web, api, worker, migrate images succeeded. No tests, fixtures, lint, or standalone typecheck ran. No commit made; next: scoped independent re-review.


P02-T4 complete for the production-code/build stage on 2026-09-26; independent review and scoped re-review approved after four fixes. Connector setup now creates and validates RSS/web/REST sources while exposing a one-time scoped collector token for n8n; Sync now, no-change acknowledgement, pause/resume, run retry/status, upload processing progress, raw provenance and durable source purge are wired. Source health distinguishes collection and processing state; indexing/embedding remain explicitly unavailable. Purge commits an archive/generation fence and operation/outbox record before worker deletion; collection/upload workers reject stale generations. Archived sources retain a purge action, RSS no-change runs update diagnostics, stale collector retries are fenced, and document/upload writes reject paused sources.

Exact final build: `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-2`, with process-only `POSTGRES_PASSWORD=build-only-placeholder`; exit 0. Next.js 16.3.6 build (including integrated TypeScript) generated 9 static pages; Docker web, api, worker, and migrate images built. First build exposed two TypeScript issues (`result_count` type and a status comparison); both were fixed before the passing build. No tests, fixtures, lint, standalone typecheck, migration execution, or runtime acceptance ran. GitNexus staged change detection reported HIGH across 33 staged files and 8 affected flows, primarily expected source lifecycle/delete and document/source UI flows; stale/new symbols have incomplete index coverage. No high/critical symbol impact was found for the scoped review fixes; source tracing was used where index coverage was missing. Review gates: initial review findings all addressed; re-review found no new Important/Critical issue. Tests remain deferred until all Phase 1-12 production code is complete. Next: merge Phase 2 to `main`, then P03-T1.


## P03-T1 start

Started 2026-09-26 in isolated worktree `codex/bbd-os-phase-3` at Phase 2 merge `2f7c409`. Scope: fail-closed model send policy, configured alias/settings APIs and UI, redacted capability probes, bounded model requests, and a shared two-request concurrency cap with expiring leases. Production code and affected builds only; do not create, modify, or run tests, lint, or standalone typecheck until all Phase 1-12 production code is complete.

### Phase 3 plan pre-flight scan

| Tasks | Shared files/interface | Scan result |
| --- | --- | --- |
| P03-T1 / P03-T2 | `ModelGateway.embed`, alias/capability results, shared API/worker concurrency lease | T1 must define stable embed/policy contracts before indexing consumes them; T2 owns search migration and worker job wiring. No same-file conflict listed. |
| P03-T1 / P03-T3 | Settings model/privacy APIs and frontend settings route/navigation | Search UI may link to settings; T1 owns settings navigation and API types, T3 consumes them. No same-file conflict listed. |
| P03-T1 / P03-T4 | Model alias/version/capability identity and compatibility record | T4 records configured compatibility evidence; unknown live endpoint guarantees must stay unknown. No same-file conflict listed. |
| P03-T2 / P03-T3 | Search request/response, effective mode, citation, indexing run status | T2 produces search/reindex contracts; T3 consumes them. Keep ranking and fallback state server-authored. |
| P03-T2 / P03-T4 | Ranking IDs, generation model identity/dimensions | T4 evaluation and compatibility record consume T2's generation and result contracts; no direct source overlap listed. |
| P03-T3 / P03-T4 | Search UI route and quality report outputs | T4 writes offline evaluation/compatibility artifacts; T3 reads only API contracts. No same-file conflict listed. |
| P03-T1 self-check | Settings + gateway files, outbound request policy, capability probes | Internally consistent if probes pass the same privacy gate and do not persist owner payloads/secrets. Deferred tests remain post-code. |
| P03-T2 self-check | Search models/indexer/routes, migration, worker/deletion hook | Plan revision was stale (`0004_search`) after Phase 2 migration `0005`; corrected to `0006_search` with down revision `0005_source_purge_operations`. Ruling: preserve sequential Alembic history; using `0004` would duplicate an existing migration. |
| P03-T3 self-check | Search route/API, command palette and frontend route | UI depends on T2 contracts; shortcut exclusions and URL-state details remain within this task. Deferred tests stay post-code. |
| P03-T4 self-check | Evaluation helper and compatibility document | `recall_at_k` follows the specified empty expected-set behavior; compatibility unknowns stay explicitly unknown. This task does not substitute a stub for live-provider evidence. |

No other plan conflict found. The task sequence is retained; plan corrected before P03-T1 dispatch.

### P03-T1 implementation checkpoint - 2026-09-26

Production code now includes a fail-closed model policy/client, alias and privacy settings APIs backed by Redis, protected synthetic per-capability probes, model/privacy settings pages, and a Redis two-lease request cap shared by API/worker gateway clients. Remote reasoning and embeddings require separate opt-ins; unconfigured/unknown destinations deny sends; local mappings and `local-private` are blocked because this phase has no local transport. Probe evidence is scoped by alias/model/configured version/capability and expires after 24 hours; mapping edits delete prior evidence. Secrets remain server-side. No local model was installed.

GitNexus pre-edit impact: `Settings`, `create_app`, and `WorkerSettings` each returned risk `UNKNOWN` with zero resolved upstream callers and a lower-bound/partial-index warning; the search tool reported FTS degraded. The module-registry symbol lookup did not resolve. Source `rg` checks confirmed Settings call sites in API, worker, connector crawler and seed; `create_app` is the Docker uvicorn factory; `WorkerSettings` is ARQ's configured entry point. No HIGH/CRITICAL risk was returned. The new API routes have no previous callers.

The initial production build attempt exited 1 because `next` was not installed in the worktree. After `npm.cmd ci` installed the lockfile dependencies, `./scripts/dev.ps1 build`, with process-only `POSTGRES_PASSWORD=build-only-placeholder`, exited 0. Next.js 16.3.6 generated all 11 routes, and Docker built web, api, worker, and migrate images. Pre-commit GitNexus staged detection was LOW across 22 files, with 3 indexed changed symbols and 0 affected flows; newly added modules are not represented in the index. No tests, fixtures, lint, or standalone typecheck were created or run. Independent review requested three Important fixes and one Minor clarification; commits `efac142` and `3bbfb91` addressed them, and scoped re-reviews approved both fix rounds. Task P03-T1 is complete (commits `4d1af2e..3bbfb91`, review clean). Next: P03-T2.

## P03-T2 start

Started 2026-09-26 in `codex/bbd-os-phase-3` at `bf41d7a`. Scope: lexical search/indexing, versioned embedding generations, hybrid ranking, safe deletion filtering, and worker integration. Production code and affected builds only; do not create, modify, or run tests, lint, or standalone typecheck until all Phase 1-12 production code is complete.

P03-T2 implementation complete (commits `006f053..3783b11`, independent review clean after two scoped fix rounds). Added PostgreSQL `simple` lexical search with GIN index, hybrid reciprocal-rank fusion, cursor/filter/citation contracts, durable per-item generation tracking, model/dimension/provider-identity pinning, per-generation physical HNSW indexes, and worker backfill/indexing through P03-T1's privacy-gated ModelGateway. Document manual writes now create chunks; shared chunking moved to `core/chunking.py` for reuse by ingestion and knowledge modules. Deleted, stale-revision, archived and local-only content is excluded from remote embedding indexing; search applies source/revision/deletion fences again after provider calls. Hybrid requests return lexical results with an explicit warning when remote embeddings or vector search are unavailable. Build passed with process-only `POSTGRES_PASSWORD=build-only-placeholder`; Next.js and Docker web/API/worker/migrate images succeeded. No tests, lint, or standalone typecheck ran.

Review found four initial issues: ARQ byte Redis keys, ignored returned embedding identity, obsolete pending items blocking generation activation, and vector-query errors bypassing lexical fallback. Fix commits normalized alias keys, pinned provider-resolved model identity for indexing and query calls, pruned ineligible items, and rolled back failed vector queries before fallback. One scoped review found provider identity handling too strict; `3783b11` now persists a stable returned provider ID distinct from the configured route ID and requires exact identity presence/value consistency through the generation and query. Both scoped re-reviews approved. GitNexus impacts after reindex showed CRITICAL for `get_mappings` (4 callers) and `embedding_values` (2 callers), LOW for `index_pending_chunks`; caller paths were reviewed. Staged detection found 10 symbols/11 flows for the first fix wave and 3 symbols/9 flows for the identity fix; HIGH scope matched the settings/search/indexing changes. No material review findings remain. Deferred runtime migration/provider acceptance remains open.

Task P03-T2: complete (commits `006f053..3783b11`, review clean after two scoped fix rounds). Next task: P03-T3 - search UI and command palette.

## P03-T3 start

Started 2026-09-26 in `codex/bbd-os-phase-3` after P03-T2 review completion. Scope: search UI route, filters/pagination/citation navigation, indexing status/fallback messaging, and command-palette keyboard behavior. Production code and affected builds only; do not create, modify, or run tests, lint, or standalone typecheck until all Phase 1-12 production code is complete.
