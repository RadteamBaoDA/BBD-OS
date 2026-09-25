# BBD-OS Phase 1 Core Data Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an authenticated, usable local library for managing Sources and Documents, preserving document content history and source provenance for later ingestion and search phases.

**Architecture:** Add a `modules/library` domain module that owns SQLAlchemy models, schemas, service logic, and `/api/v1` routes; `apps/api` only mounts its public router. Add an Alembic migration after the Phase 0 auth schema. Store document body revisions as immutable `DocumentVersion` rows and keep the current version addressable from the document API. The Next.js workspace gains source and document list/detail forms while retaining the existing system health screen. Phase 1 does not connect providers, ingest URLs/files, create chunks/embeddings, or implement later entity, timeline, Today, or Ask modules.

**Tech Stack:** Existing Python 3.12, FastAPI, Pydantic, SQLAlchemy async, Alembic, PostgreSQL/pgvector, Next.js/React/TypeScript, TanStack Query, pytest, Playwright, Docker Compose.

**Spec:** `specs/personal-intelligence-os-spec-v2.md`, sections 2.2–2.3, 13 (Source, Document, DocumentVersion), 95 Phase 1, 139–143, 156, and 162.

## Global Constraints

- “Personal data should remain local unless an explicitly configured external AI provider is used.”
- “Every derived piece of knowledge must be traceable back to its source.”
- “Never create an irreversible knowledge record without retaining: source; source identifier; original content reference; ingestion timestamp; extraction timestamp; confidence where appropriate.”
- “Public APIs use /api/v1; earlier unversioned resource examples are shorthand, except /health.”
- “Every schema change must use Alembic.”
- “Agents must use defined tools and APIs.”
- Keep module internals private; expose the library through its router and typed request/response contracts.
- Keep credentials out of `Source.configuration`, API responses, browser storage, and logs. Phase 1 has no provider credential UI or connector execution.
- Preserve local workspace changes; do not stage, commit, reset, delete user data, or change branches without explicit direction.
- Use pytest and Playwright checks; frontend changes must pass ESLint, TypeScript, and production build.

## Review Focus

1. An unauthenticated request or a cross-origin write cannot read or mutate personal library data; test every route through the existing session and CSRF contract.
2. Duplicate non-null provider identifiers cannot create ambiguous source documents; test the PostgreSQL uniqueness constraint and map only that conflict to HTTP 409.
3. Editing document content preserves the previous version and allocates exactly one next version; test sequential edits and concurrent updates.
4. Invalid source types, malformed metadata, empty titles, oversized content, and invalid timestamps fail with field-level 422 responses and do not partially persist rows.
5. Deleting a source with documents is rejected; deleting a document requires explicit UI confirmation and removes only its own version rows.

---

## Scope and Completion Boundary

The Phase 1 deliverable is the first real user data surface: create, view, update, and delete Sources and Documents, with immutable content versions and provenance. A user creates a Source before adding a Document; there is no implicit source record or fabricated connector state. Source types follow the canonical values in section 13, but this phase does not claim that any provider is connected. `configuration` is stored as non-secret JSON metadata and is not editable in the UI; provider credentials remain out of this phase.

`DocumentVersion.content_hash` is SHA-256 over UTF-8 content. Creating a document stores version 1. Updating title/metadata does not create a content version; changing content appends the next version and never overwrites an earlier version. `observed_at` identifies when BBD-OS recorded that version. API document detail returns the latest version and a version list endpoint returns prior revisions.

Out of scope: file upload, URL/RSS fetching, parsing, normalization pipelines, queueing, chunks, embeddings, search, entities/relationships, events/timeline, tasks/goals, memory, conversations, agent runs, graph, n8n, and model gateway calls. Those remain with their owning phases. No generic CRUD framework, module registry, demo records, or fake connector status is added.

## Planned Files and Ownership

| Files | Responsibility |
| --- | --- |
| `modules/__init__.py`, `modules/library/__init__.py` | Python package markers required for the used module |
| `modules/library/models.py` | Source, Document, and DocumentVersion SQLAlchemy tables and constraints |
| `modules/library/schemas.py` | Validated create/update/list/detail/version contracts |
| `modules/library/service.py` | Transactional source/document operations and immutable version append |
| `modules/library/routes.py` | Authenticated `/api/v1/sources` and `/api/v1/documents` HTTP boundary |
| `apps/api/main.py` | Mount the library public router without domain logic |
| `infrastructure/postgres/migrations/versions/0002_library.py` | Add the three Phase 1 tables and indexes; downgrade only these tables |
| `tests/test_library_schemas.py`, `tests/test_library_service.py` | Validation, hash/version rules, conflict mapping, and domain behavior |
| `tests/integration/test_library_api.py` | Real PostgreSQL migration, authorization, CRUD, provenance, and delete constraints |
| `apps/web/src/app/app/page.tsx`, `apps/web/src/app/app/system/page.tsx` | Library landing route and preserved system status route |
| `apps/web/src/app/app/sources/page.tsx`, `apps/web/src/app/app/documents/page.tsx`, `apps/web/src/app/app/documents/[documentId]/page.tsx` | Source list/form, document list/create, and document detail/version history |
| `apps/web/src/components/workspace-shell.tsx`, `apps/web/src/components/source-form.tsx`, `apps/web/src/components/document-form.tsx` | Shared authenticated navigation and focused forms |
| `apps/web/src/core/library.ts` | Typed API calls and UI contracts for library resources |
| `tests/e2e/library.spec.ts` | Browser acceptance for source/document create, edit, history, and delete confirmation |
| `docs/development.md`, `docs/IMPLEMENTATION_STATUS.md` | Document Phase 1 behavior, test commands, and completion evidence |

Keep the existing authentication and database session dependencies. Do not move auth models or add a second session factory. Add a single Alembic revision with `down_revision = "0001_auth"`.

## Task 1: Library Schema, Models, and Migration

**Files:**
- Create: `modules/__init__.py`, `modules/library/__init__.py`, `modules/library/models.py`
- Create: `infrastructure/postgres/migrations/versions/0002_library.py`
- Create: `tests/test_library_schemas.py`, `tests/test_library_service.py` (initial migration/model tests live in `tests/test_library_service.py` only if they test mapping-independent constraints; otherwise use `tests/test_library_schemas.py`)
- Modify: `tests/test_migrations.py`

**Interfaces:**
- `Source`: UUID `id`; `type`, `name`, optional `provider`, `status`; non-secret JSONB `configuration`; nullable sync timestamps reserved for Phase 2; `created_at`, `updated_at`.
- `Document`: UUID `id`; required `source_id`; optional `external_id`, `content_type`, `mime_type`, `raw_uri`, `canonical_url`, `author`, `published_at`, `language`; `title`, `observed_at`, `content_hash`, JSONB `metadata`; `created_at`, `updated_at`.
- `DocumentVersion`: UUID `id`; `document_id`, positive `version_number`, `content`, SHA-256 `content_hash`, `observed_at`, `created_at`; unique `(document_id, version_number)`.
- Source type values: `rss`, `web`, `file`, `github`, `calendar`, `email`, `api`, `mcp`, `manual`, `other`. Phase 1 may store these labels without claiming provider support.
- Source status values in Phase 1: `active` and `disabled`. Phase 2 owns syncing/error health states.

- [ ] **Step 1: Add failing schema and offline migration assertions**

Add tests asserting valid canonical source types and rejection of unknown types, empty/overlong names, and malformed metadata. Extend `test_empty_database_migration_emits_single_owner_and_session_schema` to assert `CREATE TABLE source`, `document`, `document_version`, foreign keys, uniqueness, and required indexes in Alembic offline SQL.

- [ ] **Step 2: Run the focused tests and confirm the missing-schema failure**

Run: `uv run pytest tests/test_library_schemas.py tests/test_migrations.py -q`

Expected: FAIL because Phase 1 schemas and migration tables do not exist yet.

- [ ] **Step 3: Implement the smallest model and migration set**

Use PostgreSQL UUID, JSONB, timezone-aware timestamps, and server-side timestamp defaults. Add a partial unique index on `(source_id, external_id)` only where `external_id IS NOT NULL`. Add an index for source recency and document version lookup. Set document-to-source `ON DELETE RESTRICT` and version-to-document `ON DELETE CASCADE`. Keep chunk/vector schema out of this revision.

- [ ] **Step 4: Run focused schema and offline migration tests**

Run: `uv run pytest tests/test_library_schemas.py tests/test_migrations.py -q`

Expected: PASS; `alembic upgrade head --sql` emits revision `0002_library` after `0001_auth` and does not alter auth tables.

- [ ] **Step 5: Run real PostgreSQL migration and downgrade checks**

Add integration checks that upgrade an empty disposable database to head, inspect the three tables and constraints, downgrade to `0001_auth`, then upgrade to head again. Run: `./scripts/dev.ps1 test`.

Expected: migration round trip passes using only the disposable Phase 1 test project and database.

## Task 2: Authenticated Source CRUD API

**Files:**
- Create: `modules/library/schemas.py`, `modules/library/service.py`, `modules/library/routes.py`
- Create: `tests/test_library_service.py` (source service cases)
- Create: `tests/integration/test_library_api.py`
- Modify: `apps/api/main.py`

**Interfaces:**
- `POST /api/v1/sources` accepts `type`, `name`, optional `provider`; returns `201 SourceRead`.
- `GET /api/v1/sources?limit=50&offset=0` returns `SourcePage(items, limit, offset, total)`; enforce `1 <= limit <= 100`, `offset >= 0`.
- `GET /api/v1/sources/{source_id}` returns `SourceRead` or 404.
- `PATCH /api/v1/sources/{source_id}` updates `name`, `provider`, or `status` (`active|disabled`); return 404 if absent and 422 on invalid values.
- `DELETE /api/v1/sources/{source_id}` returns 204 only when no Documents reference it; return 409 if referenced.
- `SourceRead` never includes raw credentials. Its `configuration` is omitted in Phase 1 responses; the service initializes it to `{}`.

- [ ] **Step 1: Write source CRUD integration tests**

Cover create/read/list order and totals, patch, delete unused source, 404, 409 when a document exists, invalid query bounds, unauthenticated 401, write without CSRF 403, and missing Origin 403. Bootstrap the owner through the existing test setup flow; use only the disposable test database.

- [ ] **Step 2: Verify the new source route tests fail**

Run: `./scripts/dev.ps1 test`

Expected: FAIL because the library router and source tables do not exist.

- [ ] **Step 3: Implement source schemas and transactional service methods**

Implement `create_source(session, data)`, `get_source(session, source_id)`, `list_sources(session, limit, offset)`, `update_source(session, source_id, data)`, and `delete_source(session, source_id)`. For delete, check referenced documents and return a domain conflict; do not catch unrelated `IntegrityError` exceptions as 409.

- [ ] **Step 4: Add routes and mount the router**

Create `router = APIRouter(prefix="/api/v1", tags=["library"])`; put source routes under `/sources`. Require the existing authenticated-owner dependency for every source route and existing CSRF/origin rules for writes. `apps/api/main.py` includes only `modules.library.routes.router` and contains no SQL or business rules.

- [ ] **Step 5: Run the source integration test group**

Run: `./scripts/dev.ps1 test`

Expected: source CRUD, authorization, migration, and Phase 0 regression tests pass.

## Task 3: Document CRUD, Provenance, and Immutable Versions

**Files:**
- Modify: `modules/library/schemas.py`, `modules/library/service.py`, `modules/library/routes.py`
- Modify: `tests/test_library_service.py`, `tests/integration/test_library_api.py`

**Interfaces:**
- `POST /api/v1/documents` accepts required `source_id`, `title`, `content`; optional canonical metadata fields `external_id`, `content_type`, `mime_type`, `canonical_url`, `author`, `published_at`, `language`, and JSON `metadata`; returns `201 DocumentRead` with version 1.
- `GET /api/v1/documents?source_id=&q=&limit=50&offset=0` returns an owner-only `DocumentPage`; `q` searches title only in Phase 1.
- `GET /api/v1/documents/{document_id}` returns document metadata and current version content, or 404.
- `PATCH /api/v1/documents/{document_id}` changes title and metadata only; it never changes content.
- `PUT /api/v1/documents/{document_id}/content` accepts `{ "content": "...", "expected_version": N }`; append revision `N+1` only if N is still current, otherwise return 409.
- `GET /api/v1/documents/{document_id}/versions` returns versions ordered by `version_number DESC`, without duplicating full content in the document list response.
- `DELETE /api/v1/documents/{document_id}` deletes that document and its own versions after the UI confirms; return 204 or 404.

- [ ] **Step 1: Add failing document/provenance tests**

Assert create stores source ID and observed time and produces version 1 with a SHA-256 hash of UTF-8 content; content update appends version 2 while version 1 remains byte-for-byte intact; same content does not create a redundant version; stale `expected_version` returns 409; duplicate `(source_id, external_id)` maps to 409; deleting a document removes its versions but retains its source. Assert invalid source IDs return 404 and over-limit payloads return 413 or 422 before commit.

- [ ] **Step 2: Run the failing focused tests**

Run: `./scripts/dev.ps1 test`

Expected: FAIL on missing document endpoints, version append logic, and uniqueness handling.

- [ ] **Step 3: Implement document service with concurrency-safe append**

Create the document and first version in one transaction. For content updates, load the document with `SELECT ... FOR UPDATE`, compare `expected_version` with the current maximum, insert the next revision, and update the Document's current content hash and observed time in the same transaction. Hash with `hashlib.sha256(content.encode("utf-8")).hexdigest()`. Cap content at 1 MiB and metadata at 64 KiB serialized; report field-specific validation errors.

- [ ] **Step 4: Add owner-only document routes and safe conflict mapping**

Use typed request/response schemas. Map only the known unique index violation for `(source_id, external_id)` and stale version to 409. Keep SQLAlchemy models and exception text out of responses. Do not add upload, fetch, extraction, chunking, or provider logic.

- [ ] **Step 5: Run integration tests including repeat migration**

Run: `./scripts/dev.ps1 test`

Expected: source/document CRUD, immutable version, provenance, conflict, and auth tests pass against disposable PostgreSQL; repeated `alembic upgrade head` remains safe.

## Task 4: Workspace Navigation and Source Management UI

**Files:**
- Create: `apps/web/src/components/workspace-shell.tsx`, `apps/web/src/components/source-form.tsx`, `apps/web/src/core/library.ts`, `apps/web/src/app/app/sources/page.tsx`, `apps/web/src/app/app/system/page.tsx`
- Modify: `apps/web/src/app/app/page.tsx`, `apps/web/src/app/globals.css`, `apps/web/src/app/layout.tsx`
- Modify: `tests/e2e/library.spec.ts`

**Interfaces:**
- `apps/web/src/core/library.ts` exports `Source`, `SourcePage`, `listSources`, `createSource`, `updateSource`, and `deleteSource` using `apiRequest` and `csrfHeaders` from `@/core/api`.
- Workspace routes are `/app`, `/app/sources`, `/app/documents`, and `/app/system`; the shell keeps the existing session check and redirects 401 to `/login`.
- Move the current system status screen to `/app/system` without changing its health semantics. `/app` becomes a concise library landing screen with links to Sources and Documents; no Today widgets or placeholder chat.

- [ ] **Step 1: Add failing Playwright source management flow**

Add browser flow that signs in, opens Sources, creates a `manual` source, confirms it appears, edits its name, disables it, and deletes it. Add checks for empty/loading/API error states and keyboard focus on the primary form controls.

- [ ] **Step 2: Run Playwright to verify the route and controls are absent**

Run: `./scripts/dev.ps1 test`

Expected: the new source flow fails because the workspace navigation and screen do not exist.

- [ ] **Step 3: Add the shared workspace shell and route structure**

Implement a narrow responsive sidebar/navigation for Library, Sources, Documents, and System. Use existing semantic colors and focus styles from `globals.css`; use the existing Button/Input/Label primitives. Keep the current light/dark theme toggle and apply active-route semantics. `layout.tsx` changes the document language to `en` only if retaining the existing English UI; do not add a localization framework.

- [ ] **Step 4: Implement the Source list and form**

Use TanStack Query for owner-only source data. Provide create/edit and active/disabled controls, a confirmed delete action, loading/empty/error states, and accessible field errors. Do not add JSON configuration editing, credential fields, connectivity checks, or fabricated last-sync values.

- [ ] **Step 5: Run frontend checks and browser source flow**

Run: `./scripts/dev.ps1 lint; ./scripts/dev.ps1 typecheck; ./scripts/dev.ps1 test`

Expected: source creation/edit/disable/delete works in the disposable production Compose app and passes keyboard-oriented assertions.

## Task 5: Document Library UI and Version History

**Files:**
- Create: `apps/web/src/components/document-form.tsx`, `apps/web/src/app/app/documents/page.tsx`, `apps/web/src/app/app/documents/[documentId]/page.tsx`
- Modify: `apps/web/src/core/library.ts`, `tests/e2e/library.spec.ts`, `apps/web/src/app/globals.css`

**Interfaces:**
- Add `Document`, `DocumentPage`, `DocumentVersion`, `listDocuments`, `createDocument`, `getDocument`, `updateDocument`, `updateDocumentContent`, `listDocumentVersions`, and `deleteDocument` to `@/core/library`.
- Document creation requires an existing source and initial content. Document list displays title, source, latest observed time, and version number. Detail displays current content and a readable prior-version history.

- [ ] **Step 1: Add failing document browser flow**

Extend Playwright: create a document under the manual source, edit its title, change content, verify version history preserves the original text, reload the page and confirm persistence, then cancel one delete confirmation and confirm the document remains before confirming deletion.

- [ ] **Step 2: Run the new browser flow and confirm it fails on missing pages**

Run: `./scripts/dev.ps1 test`

Expected: FAIL because document routes and controls do not exist.

- [ ] **Step 3: Implement typed API functions and source-aware document forms**

Bind forms to the API contracts from Task 3. Disable document creation when no source exists and show a direct link to create one. Send the loaded current version as `expected_version`; on HTTP 409 preserve the draft and explain that the document changed and should be reloaded before retrying.

- [ ] **Step 4: Implement document list/detail and explicit delete confirmation**

The list supports text search by title, source filtering, and bounded pagination. Detail allows metadata/title edits separately from content revisions and renders version timestamps and content as escaped text, never HTML. All mutations invalidate only affected TanStack Query keys.

- [ ] **Step 5: Run browser and frontend checks**

Run: `./scripts/dev.ps1 lint; ./scripts/dev.ps1 typecheck; ./scripts/dev.ps1 test`

Expected: Playwright validates create/edit/version/delete behavior at the production browser origin; `npm run build --workspace apps/web` passes.

## Task 6: Phase 1 Acceptance, Documentation, and Handoff

**Files:**
- Modify: `docs/development.md`, `docs/IMPLEMENTATION_STATUS.md`, `README.md`
- Review: all files introduced or changed in Tasks 1–5

- [ ] **Step 1: Document the library contract and phase boundary**

Describe Source and Document CRUD routes, version history behavior, delete restrictions, manual-only sources, and the fact that URL/file ingestion, connectors, search, and Today/Ask are not implemented by Phase 1. Document how to start the stack and run library integration/browser tests using `./scripts/dev.ps1` and `make` where available.

- [ ] **Step 2: Run the complete local acceptance set**

Run:

```powershell
./scripts/dev.ps1 lint
./scripts/dev.ps1 typecheck
./scripts/dev.ps1 test
./scripts/dev.ps1 build
```

Expected: Ruff, mypy, ESLint, TypeScript, unit/integration tests, disposable Compose + Playwright, Next.js production build, and production Docker image builds all pass. `npm audit --audit-level=low` has zero findings or any new finding is recorded with the exact affected package and path.

- [ ] **Step 3: Verify isolation and repository state**

Confirm test cleanup removed only its unique Compose project and volumes; confirm the owner development volume was not targeted. Run `git diff --check` and `git status --short`; do not stage or commit.

- [ ] **Step 4: Record evidence and remaining boundaries**

Update `docs/IMPLEMENTATION_STATUS.md` with test counts, migration/API/UI acceptance, and any unavailable checks. Keep target 2-core/8-GB capacity unverified until measured on that host. Mark Phase 1 complete only when all acceptance checks pass.

## Coverage and Deferred Phase Map

| Requirement | Owner |
| --- | --- |
| Source, Document, DocumentVersion persistence and CRUD | Phase 1 Tasks 1–5 |
| Data provenance and immutable content history | Phase 1 Tasks 1 and 3 |
| File/URL/RSS ingestion, normalization, dedupe, chunks, and worker recovery | Phase 2 |
| Search, embeddings, and global search UI | Phase 3 |
| Entity resolution, relationship corrections, and graph UI | Phase 4 |
| Event timeline, temporal history, and Graphiti | Phase 5 |
| Conversations, Ask, retrieval, citations, streaming, memories | Phase 6 |
| Agent runs, tool calls, approvals, and resume | Phase 7 |
| Today dashboard, daily brief, tasks, and goals | Phase 8 |
| GitHub collection | Phase 9 |
| n8n scheduling and automation UI | Phase 10 |
| Traces, token usage, and operational views | Phase 11 |
| Security/performance, 2-core/8-GB capacity, backup/restore, full E2E hardening | Phase 12 |

## Self-Review

- Spec coverage: Sections 95 and 13 map to Tasks 1–3; local-first provenance maps to Task 3; UI modularity and authenticated routes map to Tasks 4–5; Phase 1 acceptance and regression gates map to Task 6. Later product areas are assigned to their owning phases in the table above.
- Scope: Phase 1 is one coherent data-library vertical slice (schema, authenticated CRUD, minimal UI), not independent future subsystems. It deliberately excludes ingestion, graph, Ask, Today, agents, and automation.
- Type consistency: `SourceRead`, `SourcePage`, `DocumentRead`, `DocumentPage`, `DocumentVersionRead`, `expected_version`, and route signatures are named once in Tasks 1–5 and reused consistently.
- Security/failure review: unauthenticated and cross-origin writes, foreign source IDs, duplicate provider identity, stale document updates, oversized payloads, and restrictive deletion are assigned tests in Tasks 2–3 and 5.
- No placeholders: every task names files, public interfaces, commands, expected results, scope exclusions, and domain-specific assertions. No new product dependency is required.

## Execution Handoff

Phase 0 used native execution, but no execution method has been selected for Phase 1. Please review this plan and choose **Native** or **Subagent-driven** before implementation. Native is recommended: the six tasks share migration, API, and frontend contracts; one implementer can preserve those interfaces with a single independent review at the end. The 2-core/8-GB host remains a Phase 12 measurement gate and is not claimed as validated by this plan.
