# BBD-OS Approved Delivery Master Plan — Phases 0–12

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native task-by-task execution. Follow the phase files linked below and maintain [EXECUTION.md](EXECUTION.md). The owner approved the product scope and requested continuous progress through ready tasks; do not ask for repeated phase-scope approval.

**Goal:** Deliver the entire approved single-owner Personal Intelligence OS, including daily dashboard, contextual chat drawer, collection, knowledge, agents and operational recovery.

**Architecture:** Python/FastAPI modular monolith; PostgreSQL is authoritative for canonical knowledge and durable work; Redis/ARQ executes bounded jobs. Reuse n8n for external collection scheduling, OmniRoute for permitted model access, LangGraph for agent checkpoints/interrupts, Graphiti for temporal knowledge, Crawlee for collection and browser-use for AI-directed browsing. Next.js composes module-owned screens and an on-demand chat drawer.

**Tech Stack:** The approved stack and Phase 0 lockfiles. Add and pin dependencies when the owning task uses them; capability/backend compatibility is checked against the installed versions.

**Spec:** [Approved product/engineering specification](../../../specs/personal-intelligence-os-spec-v2.md), including sections 156–164. This plan translates the approved scope into executable phase plans; it does not declare their implementations complete.

## Global Constraints

- "Support exactly one owner profile."
- "Never hardcode secrets."
- "Every schema change must use Alembic."
- "Agents must use defined tools and APIs."
- "Do not introduce a Go backend or a second application language for backend services without measured need and a separate decision."
- "Create directories only when used."
- "Public APIs use /api/v1; earlier unversioned resource examples are shorthand, except /health."
- "Every derived piece of knowledge must be traceable back to its source."
- Preserve raw-source and document-history retention unless the owner explicitly deletes the relevant data.
- Python: four spaces; TypeScript: two spaces. Use existing dependencies before adding a framework.
- Target 2 cores/8 GiB/SSD with no mandatory local inference; distinguish available development hardware from target acceptance.
- No commit, push, reset, branch change, production deployment or destructive owner-volume operation without explicit direction.
- n8n is source-available/fair-code; do not label the entire stack exclusively OSI open source.

## Review Focus

1. Durable acknowledgment must survive Redis/worker failure and duplicate delivery (P02, P07, P10).
2. Egress grants, source isolation, model fallback and tools must fail closed (P03, P06, P07).
3. Corrections, revisions and deletion propagate across every derived representation (P01, P04–P06, P12).
4. The daily drawer retains the correct date/conversation through navigation and reconnect (P06, P08, P12).
5. A fresh install, upgrade, verified restore and measured target workload are separate release gates (P12).

## Plan Index and Dependencies

Phase 0 is implemented: [existing Phase 0 plan](2026-09-25-bbd-os-phase-0.md). Preserve its acceptance evidence; do not rerun its implementation.

| Phase | Local implementation plan | Entry dependency | Tasks | Implementation |
| --- | --- | --- | --- | --- |
| 1 | [Core Data Platform](2026-09-25-bbd-os-phase-1-core-data-platform.md) | Phase 0 acceptance | 4 | Not started |
| 2 | [Ingestion and Packaged Connectors](2026-09-25-bbd-os-phase-2-ingestion-connectors.md) | Phase 1 sources/documents public contracts | 4 | Not started |
| 3 | [Search and Model Gateway Foundation](2026-09-25-bbd-os-phase-3-search-model-gateway.md) | Phase 2 chunks/provenance; live model acceptance needs configured endpoint and permitted aliases | 4 | Not started |
| 4 | [Entity Knowledge and Corrections](2026-09-25-bbd-os-phase-4-entity-knowledge.md) | Phase 3 validated structured-output alias, search and public library | 4 | Not started |
| 5 | [Temporal Knowledge and Timeline](2026-09-25-bbd-os-phase-5-temporal-knowledge.md) | Phase 4 entities/evidence; Phase 3 permitted chat/structured/embedding capabilities | 4 | Not started |
| 6 | [Ask, Chat Drawer and Selective Memory](2026-09-25-bbd-os-phase-6-ask-chat-drawer-memory.md) | Phase 3 retrieval/gateway, Phase 4 entities, Phase 5 temporal public APIs | 4 | Not started |
| 7 | [Agent Harness, Tools, MCP and Approvals](2026-09-25-bbd-os-phase-7-agent-harness-tools.md) | Phase 6 chat/memory; Phase 3 capabilities; Phase 2 isolated browser runtime | 4 | Not started |
| 8 | [Today, Daily Chat Drawer, Tasks and Goals](2026-09-25-bbd-os-phase-8-today-daily-chat-tasks.md) | Phases 1–7 public knowledge, chat, events and tools; source collection already runs in Phase 2 | 4 | Not started |
| 9 | [GitHub Collection and Project Knowledge](2026-09-25-bbd-os-phase-9-github-integration.md) | Phase 2 connector contract; Phases 4–8 entity/event/project presentation | 4 | Not started |
| 10 | [Automation Rules and Workflow Management](2026-09-25-bbd-os-phase-10-automation-workflows.md) | Phase 2 durable events/n8n; Phase 7 approvals; Phase 8 tasks/brief/notifications | 4 | Not started |
| 11 | [Observability and Operational Controls](2026-09-25-bbd-os-phase-11-observability-operations.md) | Phases 1–10 already emit run IDs, events, status and timing | 4 | Not started |
| 12 | [Hardening, Backup, Recovery and Full Acceptance](2026-09-25-bbd-os-phase-12-hardening-release-acceptance.md) | Functional acceptance from Phases 1–11; actual target hardware and permitted live integrations for final release gate | 5 | Not started |

Default execution order is P01 through P12. A blocked live integration does not prohibit independent schema/UI/test work, but dependent live acceptance stays blocked. Never mark a phase complete while its mandatory acceptance remains unverified.

## Decisions Preserved from the Owner

### Chat is a drawer

- The owner's "more space" request means viewport space; it does not introduce multi-workspace accounts.
- Chat is a right-side overlay drawer, closed by default; closing it reserves no column and gives the underlying feature the full viewport.
- Desktop width is `min(440px, 100vw)`; mobile uses a full-screen dialog. Use an accessible existing Sheet/Dialog primitive with Escape, focus trapping and focus return.
- Drawer header: context/date badge, conversation history, expand to Ask and close. Transcript/composer are primary; citations, history, activity and approvals are subviews inside the drawer.
- `/ask` remains the expanded experience using the same conversation/session component. Opening it must not create a duplicate conversation.
- Closing the drawer only changes presentation. An explicit Stop cancels generation. Draft survives closing within the session; private drafts are not written to persistent browser storage.
- Drawer state is UI state; server transcript is TanStack Query data. Response IDs and replayable event IDs prevent duplicate sends on reconnect.

### Today and previous days

- Date picker, previous/next/today navigation; timezone defaults to `Asia/Ho_Chi_Minh` and is owner-editable.
- A day conversation is bound to date + timezone. Changing the selected date selects that day's conversation; existing messages/runs retain their original context.
- Saved Daily Brief revisions are preserved. Historical dashboard lists reflect currently retained data filtered to that date and show their update time.
- The UI must not imply that current task state is a historical snapshot. Re-generation adds a new brief revision.
- No imported calendar provider is required for v1: upcoming information comes from available manual/imported events/tasks and the UI states the connected sources honestly.

## Public Contracts and Ownership

- Sources/connectors own collection identity, source policy and cursor references. Documents own revisions and raw-content references; derived modules retain evidence links.
- Event time, observation time and validity time are separate. Persist UTC; use IANA timezone for date ranges with half-open boundaries.
- IDs are UUIDs internally; stable provider IDs are deduplicated within their source. Requests use validated schemas with unknown fields rejected on mutation.
- Read endpoints require owner authentication. Mutations require owner + Origin + session-bound CSRF. Collectors use separate source-scoped ingestion grants, never owner browser cookies.
- Lists use bounded limits and opaque cursors; input errors 422, missing resource 404, stale revision/known conflicts 409. Protected data responses are not shared-cacheable.
- Models own their tables in `modules/<capability>`. `core/` contains only consumed shared infrastructure/contracts. APIs/worker compose modules and never duplicate domain logic.
- The module descriptor provides id, name, version, description, enabled, dependencies, provides/requires, routes, emitted/consumed events, tools and settings schema. Add each field's consumer when used; no arbitrary plugin loader.
- Frontend module components/hooks/API clients stay under `apps/web/src/modules` with thin Next route wrappers. Shared shell, query/auth and drawer controller stay in frontend core.
- Domain events have id/type/version/time/producer/payload. PostgreSQL pending work/outbox is the durable bridge to ARQ; do not build a generic workflow engine or add Kafka.
- Every heavy parsing/indexing/browser job acquires the same cross-process lease; every model request uses the shared model concurrency limit. Lease failure never bypasses limits. Waiting approvals consume no worker capacity.
- Phase 1 supplies public auth dependencies; feature modules must not import private helpers from `core.auth.routes`.
- Phase 1 also updates Docker, wheel packaging, Alembic discovery, Make/PowerShell and CI to include real `modules`. The original Phase 0 configuration only includes `apps/core`.

## Canonical Model Coverage

| Models/capabilities | Owning implementation phase |
| --- | --- |
| Source, Document, DocumentVersion; private library and seed | 1 |
| Chunk, IngestionRun/Batch/Stage, source observations/cursors, raw storage | 2 |
| IndexGeneration, embeddings, search and model/privacy settings | 3 |
| Entity, EntityAlias, Relationship, evidence and corrections | 4 |
| Event, EventParticipant, temporal sync and graph mapping | 5 |
| Conversation, Message, response stream, Memory lifecycle | 6 |
| AgentRun, ToolCall, ApprovalRequest, effect ledger and MCP | 7 |
| Task, Goal, milestone, Topic, Story, Trend, DailyBrief, Notification | 8 |
| GitHub normalized records and repository relationships | 9 |
| Automation, rule revision, execution/action outcomes | 10 |
| Aggregated telemetry, quality/usage and retention settings | 11 |
| Backup manifest, export/recovery and full deletion acceptance | 12 |

Security, evidence, lifecycle logs and safe deletion are implemented with their owning feature; Phases 11–12 consolidate and audit them.

## Feature/UI Coverage and Scope Boundaries

| Feature | UI and functionality owner |
| --- | --- |
| Sources, manual notes/documents, version history | P01; sync/upload/configuration P02; GitHub P09 |
| News collection / story clustering / trends / relevance | P02 / P08 |
| Search and keyboard command palette | P03; later modules register their search/action providers |
| Knowledge entities/graph / Timeline | P04 / P05 |
| Ask and contextual chat drawer / selective Memory | P06 |
| Agent management, tool activity, approvals, browser-use | P07; task/goal tools P08; Automation specialist P10 |
| Today, saved daily brief, day-context drawer, Tasks/Goals | P08 |
| Notifications and owner interests | P08; operational producers start in their owning phases |
| Automation rules and run history | P10; n8n collection schedules already ship in P02 |
| System operations, data quality, usage and module lifecycle | P11; useful health exists from P00 |
| Model/privacy settings / storage/retention / backup | P03 / P11 / P12 |
| General/timezone/appearance / agent settings / module settings | P01/P02/P08 as consumed / P07 / descriptors from P01 |
| First-run guided flow and complete fictional seed | Incremental with features; full acceptance P12 |
| Export, forget, backup/restore, offline and accessibility | Feature-local lifecycle first; complete P12 verification |

Required initial connectors: RSS/Atom, URL, file, REST, GitHub. Required file formats: PDF, TXT, Markdown, DOCX, JSON, CSV. Required GitHub resources: repositories, issues, pull requests, commits, releases.

Gmail/Calendar/Drive/Notion/Slack and named social/community providers remain later adapters per the spec. The news/social extension boundary is supported; this does not pretend those providers ship in the initial product. Optional Kanban, local inference and Langfuse are not silently enabled on the mini host. A scanned PDF without text is explicitly needs_ocr, not successfully indexed.

## Task Execution and Verification Protocol

1. Read this master, the phase plan, current code and `EXECUTION.md`. Reconcile drift before editing; preserve user changes and the approved behavior.
2. Mark exactly one active task; record start state and acceptance cases. Native execution is the selected default.
3. Write the task's failing behavioral test, observe the expected failure, implement the bounded change, then run focused checks.
4. Each phase task supplies files, public interfaces, a concrete test, implementation rules and acceptance scenarios. Code examples are planned tests/contracts, not evidence of existing implementation.
5. For every named test fixture in a task, create it in that task's test package/conftest and implement the explicitly described behavior. Production API never gains test-only routes.
6. P01 adds optional test targets to the existing runners: `./scripts/dev.ps1 test -PytestTarget tests/...py` or `-E2eTarget tests/e2e/...spec.ts`; Linux parity via `make test PYTEST_TARGET=...` / `E2E_TARGET=...`. Without a target, run the complete suite. Targeted unit tests need no containers; targeted API/browser cases use disposable Compose and the required auth setup.
7. API fixtures use unique per-test resources and owner credentials from the disposable test environment. Owner race runs once first on an empty DB. Reset data before the browser bootstrap only after verifying the ephemeral project/database; preserve Alembic revision. Never truncate or down-volumes on an owner deployment.
8. Unit model tests inject deterministic transports; integration fixtures may substitute models only within test configuration. Record live-provider checks separately. Never claim functional provider support from a stub.
9. At task completion record exact commands/results and mark the task checkbox; continue directly to the next ready task without another scope approval.
10. At phase completion run sequential common gates: `./scripts/dev.ps1 lint`, `typecheck`, `test`, `build` (or Make equivalents), then independent final code review under the execution skill. Fix findings and rerun affected checks.
11. Update `docs/IMPLEMENTATION_STATUS.md`, the phase plan, architecture decisions when material and `EXECUTION.md`. Advance to the next ready phase without repeating brainstorming for the approved scope.
12. If credentials/hardware/provider compatibility block a required check, record exact missing evidence and the next independent task. Do not invent values or label that gate complete. Material architecture changes and destructive owner operations still require the owner's decision.
13. Continuous execution means continuing within an active run or resuming from this ledger. These Markdown files do not create a scheduler/background process.

Common checks are phase acceptance, not a demand to rerun every expensive suite after each trivial edit. Preserve focused evidence, broaden once after final phase changes, and repeat only for relevant new changes/failures.

## Delivery Files and Current Checkpoint

- This master is the execution index.
- Twelve phase plans provide **49 task-level checklists**, test examples and public contracts.
- `EXECUTION.md` persists active/next task, gate status, evidence and handoff notes.
- `docs/IMPLEMENTATION_STATUS.md` distinguishes plan availability from implementation completion.
- Phase 0 remains complete. Phase 1–12 implementation is not started by writing these plans.
- Next implementation task: **P01-T1**, after loading `superpowers:executing-plans`. Existing owner authorization covers continuing ready tasks/phase scope; no new approval loop is added.

## External Integration Evidence and Release Gates

Use primary project documentation and verify the versions installed at execution:
- [OmniRoute](https://github.com/diegosouzapw/OmniRoute): configured endpoint/aliases; per-capability testing and destination policy are BBD-OS responsibilities.
- [Graphiti](https://github.com/getzep/graphiti): start compatibility testing with FalkorDB; keep it separate from queue Redis, and do not infer 8GB suitability from backend support.
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts): persist checkpoints and resume only after tool permissions/approval state are revalidated.
- [n8n Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/): use explicit timezone and verify the pinned runtime's scheduling behavior.

Final acceptance imports three RSS feeds, one GitHub repository, five text-bearing PDFs and several URLs; verifies all primary screens, search/citations, entity/event/graph updates, approved tasks, automated briefs, recovery and backup/restore. Measure the target 2-core/8GiB workload; available larger-host evidence remains labeled separately.
