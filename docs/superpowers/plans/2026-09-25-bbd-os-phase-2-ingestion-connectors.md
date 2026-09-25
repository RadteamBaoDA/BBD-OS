# BBD-OS Phase 2 — Ingestion and Packaged Connectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Durably ingest supported files and collect RSS/Atom, URL and REST data with provenance, bounded jobs and recoverable progress.

**Architecture:** Implement the ingestion, connectors, news capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 1 sources/documents public contracts supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 30–31, 52–55, 67–68, 89, 95, 138.3–6, 158–161. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 1 sources/documents public contracts.

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

1. Duplicate batch delivery preserves one provider record and all distinct observations.
2. Redis loss after receipt does not lose accepted data or advance an uncommitted cursor.
3. Imported bytes and browser redirects cannot escape storage or reach protected internal networks.
4. Source pause/delete racing with a worker prevents new processing or reappearance of forgotten data.
5. An unsupported/scanned document must report extraction limits rather than indexing success.

## File Structure and Boundaries

Module ownership: **ingestion, connectors, news**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P02-T1: Durable receipt, run stages and dispatch

**Files and responsibilities:** Create modules/ingestion/models.py, modules/ingestion/schemas.py, modules/ingestion/public.py, modules/ingestion/routes.py, modules/ingestion/dispatcher.py; core/events.py; next Alembic revision infrastructure/postgres/migrations/versions/0003_ingestion.py; modify apps/worker/main.py; create tests/integration/test_ingestion.py.

**Interfaces — consumes/produces:** POST /ingestion/batches -> 202 Receipt(batch_id,run_id,status); GET /ingestion/runs/{id}; POST /ingestion/runs/{id}/retry. Collector credentials are restricted to ingestion and allowed source IDs. ReceiveBatch contains source_id,batch_key,cursor_before,cursor_after,records; record identity is provider_id + version/hash. DomainEvent(id,type,version,occurred_at,producer,payload).

- [ ] **P02-T1.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_ingestion.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_duplicate_batch_returns_same_run(collector_client, batch_payload):
    first = await collector_client.post("/api/v1/ingestion/batches", json=batch_payload)
    again = await collector_client.post("/api/v1/ingestion/batches", json=batch_payload)
    assert first.status_code == again.status_code == 202
    assert first.json()["run_id"] == again.json()["run_id"]
```

- [ ] **P02-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_ingestion.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P02-T1.3 — Implement the minimal production behavior.** Add scoped collector_client and batch_payload fixtures to tests/integration/conftest.py, creating a source and credential only in disposable storage. Persist batch identity, observations, expected cursor and pending stage rows in one PostgreSQL transaction; acknowledge only after commit. Use PostgreSQL pending-work/outbox records and ARQ execution, not a second queue implementation. Compare-and-set cursor advancement, one source collection lease with expiry, idempotent stage keys, explicit timeouts and 4 transient retries with backoff/jitter; permanent auth/schema errors fail visibly. A dispatcher reconciles pending rows after Redis restart.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"source_id":"uuid","batch_key":"provider-page-version","cursor_before":null,"cursor_after":"page-2","records":[{"provider_id":"item-1","content":"text","observed_at":"2026-09-25T02:00:00Z"}]}
```

- [ ] **P02-T1.4 — Verify the behavior and listed failure cases.** ./scripts/dev.ps1 test: duplicate receipt, crash after DB commit/before enqueue, stale cursor writer, overlapping sync, cancellation and scoped token denial. Operational logs identify run/stage without full payloads.

- [ ] **P02-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P02-T2. Do not create a commit automatically.

## Task P02-T2: File storage, parsers and chunking

**Files and responsibilities:** Create core/storage.py; modules/ingestion/files.py, modules/ingestion/parsers.py, modules/ingestion/chunking.py, modules/ingestion/worker.py; tests/test_parsers.py; tests/fixtures/ingestion/; modify Docker data mounts, pyproject.toml and uv.lock.

**Interfaces — consumes/produces:** POST /documents/upload -> Receipt; GET /documents/{id}/raw authenticated download; parse_file(path,mime) -> ParsedDocument(text,metadata,warnings); chunk_text(text,target_tokens=750,overlap_ratio=0.12) -> list[ChunkDraft]. Chunk stores document_version_id,index,content,token_count,metadata; vector indexing arrives Phase 3.

- [ ] **P02-T2.1 — Write the failing behavioral test.** Put this case in `tests/test_parsers.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_csv_parser_preserves_unicode_and_headers(tmp_path):
    from modules.ingestion.parsers import parse_file
    path = tmp_path / "sample.csv"
    path.write_text("name,note\nAn,Tiếng Việt\n", encoding="utf-8")
    parsed = parse_file(path, "text/csv")
    assert "Tiếng Việt" in parsed.text
    assert "name" in parsed.text
```

- [ ] **P02-T2.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_parsers.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P02-T2.3 — Implement the minimal production behavior.** Use stdlib for TXT/JSON/CSV, maintained pypdf and python-docx for text-bearing PDF/DOCX, and a maintained tokenizer for deterministic bounded chunks. Lock dependencies before use. Default input cap 25 MiB, parser deadline 120s, expanded DOCX cap 100 MiB and PDF page cap 500; configurable deployment limits. Verify file signatures, reject traversal, generated UUID storage names, atomic file finalize + durable DB receipt and orphan cleanup after grace period. Retain original bytes and extraction provenance. Scanned PDFs return needs_ocr, not success; OCR is not promised by this text parser. Clamp boundaries so small documents terminate without looping.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"status":"needs_ocr","warnings":["No extractable text"],"document_id":"uuid"}
```

- [ ] **P02-T2.4 — Verify the behavior and listed failure cases.** Unit fixtures for all six formats, malformed/encrypted PDF, ZIP expansion, Unicode, oversized input and interrupted writes. Run upload E2E and verify raw-file authorization; chunk count/hash stable across retries.

- [ ] **P02-T2.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P02-T3. Do not create a commit automatically.

## Task P02-T3: n8n workflows and Crawlee collection

**Files and responsibilities:** Create modules/connectors/public.py, modules/connectors/registry.py, modules/connectors/n8n.py, modules/connectors/crawl.py, modules/connectors/routes.py; infrastructure/n8n/workflows/rss.json, infrastructure/n8n/workflows/url.json, infrastructure/n8n/workflows/rest.json; infrastructure/docker/browser.Dockerfile; docker-compose.connectors.yml; tests/integration/test_collectors.py; docs/connectors.md.

**Interfaces — consumes/produces:** Connector.validate(source), sync(source,cursor), normalize(record), health(source); POST /sources/{id}/validate, /sync; PATCH source pause/resume; crawl submissions return run_id. BBD-OS controls source identity/cursors; n8n owns external schedules/credentials.

- [ ] **P02-T3.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_collectors.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_paused_source_rejects_collection(owner_client, paused_source):
    response = await owner_client.post(f"/api/v1/sources/{paused_source['id']}/sync")
    assert response.status_code == 409
```

- [ ] **P02-T3.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_collectors.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P02-T3.3 — Implement the minimal production behavior.** Create paused_source fixture using the Phase 1 API. Package importable n8n workflow exports using credential references and protected receipt endpoints; include RSS/Atom pagination/overlap, URL and REST mappings. Add source timezone default Asia/Ho_Chi_Minh. Validate the pinned n8n missed-schedule behavior; implement bounded overlap catch-up from last acknowledged cursor, not replay of every missed cron tick. Use Crawlee HTTP with BeautifulSoup first and PlaywrightCrawler for configured JS pages. One browser job, default 10 pages/depth2/60s and 25MiB aggregate download; network-level egress restrictions plus URL/redirect/DNS checks. No model-driven navigation until Phase 7.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"source_id":"uuid","mode":"http","max_pages":10,"max_depth":2,"timeout_seconds":60}
```

- [ ] **P02-T3.4 — Verify the behavior and listed failure cases.** Run actual packaged workflows against a local disposable fixture provider; SSRF tests cover redirects/DNS changes/private addresses and browser subresources. n8n outage leaves manual upload and existing knowledge usable. Verify pause stops schedules and rejects queued stale runs.

- [ ] **P02-T3.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P02-T4. Do not create a commit automatically.

## Task P02-T4: Collection UI, deletion lifecycle and diagnostics

**Files and responsibilities:** Extend apps/web/src/modules/sources/ with connector-setup.tsx and sync-history.tsx; create apps/web/src/modules/ingestion/upload.tsx; tests/e2e/ingestion.spec.ts; extend source deletion service and docs/privacy.md.

**Interfaces — consumes/produces:** Source health exposes collected_at,indexed_at and distinct collection/processing errors; data removal may return 202 with operation_id, completed synchronous removals remain 204. GET /system/operations/{id} tracks deletions; SourceRead includes retirement state.

- [ ] **P02-T4.1 — Write the failing behavioral test.** Put this case in `tests/e2e/ingestion.spec.ts` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```typescript
import { test, expect } from './fixtures';

test('upload reports processing progress', async ({ page }) => {
  await page.goto('/knowledge/documents');
  await page.getByLabel('Import file').setInputFiles('tests/fixtures/ingestion/note.txt');
  await expect(page.getByRole('status')).toContainText('Processing');
  await expect(page.getByText('Ready for search')).not.toBeVisible();
});
```

- [ ] **P02-T4.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -E2eTarget tests/e2e/ingestion.spec.ts` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P02-T4.3 — Implement the minimal production behavior.** The browser fixture holds the processing stage at a test-controlled worker barrier until the progress assertion, then releases it; do not rely on a fast transient status being visible. Show received/parsed/chunked separately from embedded/indexed—Phase 2 never claims semantic readiness. Guide credential setup to n8n and return validation; allow Sync now, pause/resume, retries and raw provenance inspection. Implement durable purge tombstones before deleting files/chunks/outbox work; workers check current source/document generation before writes. Prevent in-flight jobs recreating deleted content. Empty search/AI states remain explicit.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"collection":"succeeded","processing":"chunked","embedding":"not_configured","last_error":null}
```

- [ ] **P02-T4.4 — Verify the behavior and listed failure cases.** End-to-end upload, RSS update, duplicate delivery, pause/resume, delete-during-processing and source connector-only removal. Extend reset harness to clean Phase 2 resources only inside disposable projects. Common phase gate; next P03-T1.

- [ ] **P02-T4.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to the phase acceptance gate, then P03-T1. Do not create a commit automatically.

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
