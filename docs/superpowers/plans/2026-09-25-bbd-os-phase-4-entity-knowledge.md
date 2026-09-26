# BBD-OS Phase 4 — Entity Knowledge and Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Extract, resolve and browse entities/relationships while preserving evidence and owner corrections.

**Architecture:** Implement the knowledge/entities, knowledge/relationships capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 3 validated structured-output alias, search and public library supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 13, 32, 34–35, 49–51, 95, 128–129, 138.11–14. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 3 validated structured-output alias, search and public library.

**Implementation status:** Not started. This file is an implementation plan, not evidence of working code.

Code stage: implement production code and run affected production builds only. Do not create, modify or run tests, lint, or standalone typecheck until production code for all Phase 1-12 is complete. Behavioral acceptance is listed separately in the deferred test-stage section.

## Global Constraints

- "Never hardcode secrets."
- "Every schema change must use Alembic."
- "Agents must use defined tools and APIs."
- "Create directories only when used."
- Public APIs use `/api/v1`; preserve single-owner auth, session-bound CSRF, source policy and provenance.
- Target 2 CPU cores/8 GiB with remote inference; never claim measured capacity from a larger host.
- Follow the master's mandatory privacy, module, durable-job, deletion and UI contracts. Keep source data and credentials out of logs.
- The owner has authorized committing completed work and merging a completed phase into `main`; do not push, deploy, change branches outside planned worktrees, or perform destructive owner-data operations.

## File Structure and Boundaries

Module ownership: **knowledge/entities, knowledge/relationships**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P04-T1: Canonical entities, aliases and evidence-backed relationships


**Production files and responsibilities:** Create modules/knowledge/entities/models.py, modules/knowledge/entities/schemas.py, modules/knowledge/entities/public.py and modules/knowledge/entities/routes.py; modules/knowledge/relationships/models.py, modules/knowledge/relationships/schemas.py, modules/knowledge/relationships/public.py and modules/knowledge/relationships/routes.py; infrastructure/postgres/migrations/versions/0005_entities.py.

**Interfaces — consumes/produces:** CRUD /entities, /relationships; GET /entities/{id}/neighbors?limit<=100; EntityRef(id,type,name), EvidenceRef(document_version_id,chunk_id,observed_at,extracted_at,confidence); EntityAlias includes source_id. Public get_entity/get_neighbors return DTOs, never ORM rows.

- [ ] **P04-T1.1 - Implement production behavior.** Match canonical entity types and relationship fields. Manual authoring records owner provenance rather than fabricated document citations. Derived relationships require at least one valid evidence reference and confidence in [0,1]. Use separate evidence links so a shared fact survives removal of one supporting document. Add indexed names/types and both relationship directions. Update deletion consumers and seed examples for real entity/relationship functionality.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"source_entity_id":"uuid","target_entity_id":"uuid","type":"WORKS_AT","origin":"derived","evidence":[{"document_version_id":"uuid","chunk_id":"uuid","confidence":0.9}]}
```

- [ ] **P04-T1.2 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`) and fix production build failures before proceeding.

- [ ] **P04-T1.3 - Record build evidence, commit and continue.** Record changed files, the exact production build command/result, review findings and unresolved gates in `EXECUTION.md`; commit the completed task and continue to the next ready task.

## Task P04-T2: Bounded extraction and conservative resolution


**Production files and responsibilities:** Create modules/knowledge/entities/extraction.py, modules/knowledge/entities/resolution.py and modules/knowledge/entities/worker.py; extend ingestion stage dispatch.

**Interfaces — consumes/produces:** resolve_candidates(candidates,known) -> ResolutionResult(matches,review_candidates); extraction consumes document_version_id + allowed chunk IDs and produces validated evidence-backed facts. Resolution match reasons: external identity, confirmed alias, manual correction.

- [ ] **P04-T2.1 - Implement production behavior.** Call structured extraction through ModelGateway policy, validate types/references and cap candidates per batch. Key extraction output by document revision + extractor/prompt version to avoid duplicate retries. Prefer explicit provider identity or confirmed aliases; similar names alone create review candidates. Keep extraction failure visible without blocking reading/search of the underlying document. Relevance and extraction prompts never authorize tools.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"matches":[],"review_candidates":[{"candidate_name":"Nguyen An","reason":"ambiguous_identity","possible_entity_ids":["p1"]}]}
```

- [ ] **P04-T2.2 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`) and fix production build failures before proceeding.

- [ ] **P04-T2.3 - Record build evidence, commit and continue.** Record changed files, the exact production build command/result, review findings and unresolved gates in `EXECUTION.md`; commit the completed task and continue to the next ready task.

## Task P04-T3: Persistent corrections, merge and split


**Production files and responsibilities:** Create modules/knowledge/entities/corrections.py; extend schemas/routes and correction tables in infrastructure/postgres/migrations/versions/0005_entities.py if unreleased, otherwise create a new revision.

**Interfaces — consumes/produces:** POST /entities/{id}/merge {into_id,expected_revision}; POST /entities/{id}/split {evidence_ids,new_entity,expected_revision}; PATCH entity with expected_revision; correction decisions include actor,reason,timestamp and evidence membership.

- [ ] **P04-T3.1 - Implement production behavior.** Apply corrections transactionally and persist them as inputs to subsequent extraction reconciliation. Merge redirects old IDs while preserving evidence and avoiding duplicate relationships; split moves explicitly chosen evidence, not arbitrary inferred facts. Corrections protect names/identity but cannot retain deleted source text. Emit versioned EntityUpdated/KnowledgeChanged through the existing durable dispatch contract.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"entity_id":"uuid","revision":2,"protected_fields":["name"],"correction_reason":"owner_edit"}
```

- [ ] **P04-T3.2 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`) and fix production build failures before proceeding.

- [ ] **P04-T3.3 - Record build evidence, commit and continue.** Record changed files, the exact production build command/result, review findings and unresolved gates in `EXECUTION.md`; commit the completed task and continue to the next ready task.

## Task P04-T4: Knowledge pages and bounded React Flow graph


**Production files and responsibilities:** Create apps/web/src/modules/knowledge/entity-list.tsx, apps/web/src/modules/knowledge/entity-detail.tsx, apps/web/src/modules/knowledge/entity-editor.tsx, apps/web/src/modules/knowledge/relationship-graph.tsx and apps/web/src/modules/knowledge/resolution-review.tsx; route wrappers /knowledge/entities and /knowledge/entities/[entityId].

**Interfaces — consumes/produces:** Graph UI reads entity/neighbors APIs; graph evidence panel opens document revision. Search registry adds entity results. Public KnowledgeService methods are exported through modules/knowledge/public.py.

- [ ] **P04-T4.1 - Implement production behavior.** Provide list/detail/create/edit, resolution review and merge/split confirmation. Use React Flow with on-demand neighbors, default 50 nodes and hard response cap 100; include keyboard-accessible relationship list. Show aliases, sources, documents and actual evidence; temporal tabs appear in Phase 5 and memories in Phase 6, not empty fabricated panels.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"nodes":[],"edges":[],"truncated":false,"next_cursor":null}
```

- [ ] **P04-T4.2 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`) and fix production build failures before proceeding.

- [ ] **P04-T4.3 - Record build evidence, commit and continue.** Record changed files, the exact production build command/result, review findings and unresolved gates in `EXECUTION.md`; commit the completed task and continue to the next ready task.

## Phase Acceptance and Handoff

- [ ] Build the phase deliverables with `./scripts/dev.ps1 build` (or `make build`).
- [ ] Confirm packaging, Alembic metadata, API routes and module descriptors are included in affected production builds.
- [ ] Complete independent source review and fix actionable findings, then repeat affected production builds.
- [ ] Update `docs/IMPLEMENTATION_STATUS.md`, this checklist and `EXECUTION.md`; advance to the next ready task.

Production-code completion for all Phases 1-12 is the gate to begin the separate deferred test stage.

## Deferred test-stage acceptance

This section is informational only during the code stage. Do not create or modify tests until production code for all Phase 1-12 is complete.

- Shared names do not prove two people are the same entity.
- Model outputs cannot create evidence references to documents outside the permitted input set.
- Owner merge/split/override decisions survive later extraction runs.
- Deleting one source removes its support without erasing a fact still supported by other sources.
- Graph visualization requests must be bounded on the mini host.

### P04-T1

Planned test-stage files: `tests/integration/test_entities.py`.

- Manual entity authoring records owner provenance and has no fabricated evidence. Cover FK/uniqueness constraints, invalid confidence/types, missing evidence, bounded neighbors, manual CRUD, and source deletion while another source still supports a shared fact.

### P04-T2

Planned test-stage files: `tests/test_entity_resolution.py`, `tests/integration/test_entity_extraction.py`.

- Same-name candidates without explicit identity remain review candidates. Cover unknown chunk IDs, malicious instruction text, invalid JSON, name collisions, rate-limit retry and repeated stage execution; run a permitted live structured-output fixture before claiming extraction integration.

### P04-T3

Planned test-stage files: `tests/integration/test_entity_corrections.py`.

- A stale entity edit is rejected with 409. Cover concurrent corrections, merge loops, split/merge reference integrity, repeated extraction respecting overrides, and forgetting a source removing its evidence.

### P04-T4

Planned test-stage files: `tests/e2e/knowledge.spec.ts`.

- Cover keyboard navigation, evidence navigation, correction confirmation, and graph zoom/pan/filter/expand with the keyboard-accessible relationship-list alternative.

## Plan Self-Review Checklist

- [x] Goal and spec sections mapped to named tasks and public interfaces.
- [x] Deferred acceptance risks retained for the post-code test stage.
- [x] Exact production file targets, deferred acceptance criteria, implementation rules and build criteria included.
- [x] Module ownership, auth/privacy, safe deletion and retry/resume boundaries preserved.
- [x] Implementation and live/hardware verification are not claimed complete by this plan.
