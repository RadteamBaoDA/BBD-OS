# P02-T2 implementation report

## Scope delivered

- Added bounded UUID-path file storage under `Settings.data_dir`, atomic temp-file finalization, SHA-256 receipts, traversal-safe raw retrieval, and hourly-grace orphan cleanup scheduled by the existing ARQ worker.
- Added owner/CSRF-protected `POST /api/v1/documents/upload` and owner-authenticated `GET /api/v1/documents/{id}/raw`. Upload commits the document, immutable initial version, ingestion batch/run/stage, provenance, and outbox event only after raw bytes are finalized. Duplicate source+file hashes reuse the existing run and discard the duplicate bytes.
- Added extension/MIME/format validation for PDF, TXT, Markdown, DOCX, JSON, and CSV. Text validation uses an incremental UTF-8 decoder; PDF and DOCX signatures/structure are checked. Limits default to 25 MiB input, 120 seconds in a killable parser subprocess, 100 MiB expanded DOCX, and 500 PDF pages; values are configurable through settings and `.env.example`.
- Added stdlib TXT/Markdown/JSON/CSV parsers and pypdf/python-docx PDF/DOCX parsers. Scanned PDFs persist `needs_ocr` and do not claim successful text extraction.
- Added deterministic `cl100k_base` token chunks with 750-token targets and 12% overlap. UTF-8 boundaries are preserved; chunk rows store immutable document-version ID, index, content/hash, token count, and metadata. Reprocessing the same content reuses the same revision/chunks. No vector indexing was added.
- Added Alembic revision `0004_document_processing` for document extraction state, `needs_ocr` run status, and version-owned chunks. API and worker share `/data` through the Compose volume and the non-root image can write there.
- Added and locked `pypdf`, `python-docx`, `tiktoken`, and `python-multipart` in `pyproject.toml` and `uv.lock`.

## Changed files

- `.env.example`
- `apps/api/main.py`
- `apps/worker/main.py`
- `core/config.py`
- `core/storage.py`
- `docker-compose.yml`
- `infrastructure/docker/api.Dockerfile`
- `infrastructure/postgres/migrations/env.py`
- `infrastructure/postgres/migrations/versions/0004_document_processing.py`
- `modules/ingestion/chunking.py`
- `modules/ingestion/dispatcher.py`
- `modules/ingestion/files.py`
- `modules/ingestion/models.py`
- `modules/ingestion/parsers.py`
- `modules/ingestion/public.py`
- `modules/ingestion/routes.py`
- `modules/ingestion/schemas.py`
- `modules/ingestion/worker.py`
- `modules/knowledge/documents/descriptor.py`
- `modules/knowledge/documents/models.py`
- `modules/knowledge/documents/public.py`
- `modules/knowledge/documents/routes.py`
- `modules/knowledge/documents/schemas.py`
- `pyproject.toml`
- `uv.lock`
- This report and `docs/superpowers/plans/EXECUTION.md`.

Pre-existing changes to `AGENTS.md`, `CLAUDE.md`, GitNexus skill files, the phase plan, and the ledger were preserved; the GitNexus skill files and those instruction files were not included in this task's edits.

## Impact evidence

GitNexus upstream impact returned UNKNOWN/lower-bound with zero resolved callers for `process_ingestion_event`, `append_content`, and `dispatch_pending_work`; `create_document` was ambiguous between the public service and route, both UNKNOWN with zero resolved callers. `DocumentVersion` was UNKNOWN/lower-bound with a dispatch boundary of 12. No HIGH/CRITICAL risk result was returned. Source tracing covered the FastAPI router, public document/source contracts, Alembic model imports, outbox dispatcher, and ARQ `WorkerSettings`; direct call-site search confirmed current consumers. The stale-index results are not evidence of zero callers.

## Validation

Exact command: `./scripts/dev.ps1 build` from `D:\Project\BBD-OS-phase-2`, with process-only `POSTGRES_PASSWORD=build-only-placeholder`; exit 0. Next.js 16.3.6 production build passed, and Docker web, API, worker, and migrate images built with the locked runtime dependencies. The placeholder was removed from the process environment and was not written to configuration.

No tests or fixtures were created, modified, or run. No lint, standalone typecheck, migration execution, or runtime acceptance was run during this code stage.

## Deferred checks and review

Behavioral acceptance remains deferred until all Phase 1-12 production code is complete: parser coverage for all six formats, malformed/encrypted PDF, DOCX ZIP expansion, Unicode/token boundary preservation, oversized and interrupted uploads, duplicate retries, orphan cleanup, migration execution, and raw-file authorization. Build success does not prove those runtime behaviors. Independent review remains pending.

## Scoped self-review fixes

After the implementation commit, self-review removed a redundant chunk lookup index already provided by the unique `(document_version_id, chunk_index)` constraint, removed an unused chunking variable/import, and made downgrade map `needs_ocr` runs to `failed` before restoring the prior status constraint. The requested build was rerun after these code changes and passed. GitNexus could not find the new `chunk_text` or `DocumentChunk` symbols; `gitnexus_detect_changes` reported LOW and no indexed changed symbols/processes. These are unindexed additions, so source inspection remains the relevant evidence.

The independent review then found three Important issues and they are fixed in the current follow-up:

1. Upload exceptions no longer immediately delete a finalized file. If database commit outcome is ambiguous, the file remains until the grace-period sweep checks whether any document references it.
2. Transactions that need multiple row locks use `source -> run -> stage -> document`. `archive_source` locks the source before bulk deleting documents; uploaded-file processing, normal ingestion processing/failure cleanup, retries, and individual document deletion now acquire overlapping locks in that order. Read-only run lookup may precede the source lock to discover its ID, but no row lock is held during that lookup. The extraction service then locks the document after source/run/stage.
3. A repeated source+content upload checks that the original document still exists. If it was deleted, the request returns 409 instead of reusing a run with no document; the duplicate raw file is reclaimed by orphan cleanup.

Impact evidence for the review fix: after re-index, upstream impact reported `upload_document` LOW/0 callers, `process_uploaded_file` LOW/0, `archive_source` LOW/1 direct route consumer, and `create_document` LOW/0; no HIGH/CRITICAL risk. Additional upstream queries for `retry_run`, `process_ingestion_event`, `_fail_ingestion_stage`, `receive_file`, `delete_document`, and `lock_source_for_document` returned UNKNOWN/lower-bound with zero callers on the available graph. Manual search traced `sources.routes -> archive_source -> delete_source_documents`, `documents.routes -> delete_document`, ingestion retry/status routes, source/document public calls, both worker paths, outbox dispatch, and all lock sites. Treat UNKNOWN as incomplete evidence, not zero blast radius.

Follow-up validation: `./scripts/dev.ps1 build` with process-only `POSTGRES_PASSWORD=build-only-placeholder` exited 0. Next.js production build completed, and Docker built the web, API, worker, and migration images. Staged `gitnexus_detect_changes` reported LOW, 7 indexed symbols, 0 affected processes, and 6 changed files; its symbol list does not fully resolve the touched ingestion paths, so direct source tracing above remains necessary. `git diff --cached --check` passed. No tests were created, modified or run; no lint or standalone typecheck was run. Behavioral acceptance remains deferred to the Phase 1-12 test stage.
