# BBD-OS Approved Delivery Master Plan â€” Phases 0â€“12

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for task-by-task execution. Follow the phase files linked below and maintain [EXECUTION.md](EXECUTION.md). The owner approved the product scope and requested continuous progress through ready tasks; do not ask for repeated phase-scope approval.

**Goal:** Deliver the entire approved single-owner Personal Intelligence OS, including daily dashboard, contextual chat drawer, collection, knowledge, agents and operational recovery.

**Architecture:** Python/FastAPI modular monolith; PostgreSQL is authoritative for canonical knowledge and durable work; Redis/ARQ executes bounded jobs. Reuse n8n for external collection scheduling, OmniRoute for permitted model access, LangGraph for agent checkpoints/interrupts, Graphiti for temporal knowledge, Crawlee for collection and browser-use for AI-directed browsing. Next.js composes module-owned screens and an on-demand chat drawer.

**Tech Stack:** The approved stack and Phase 0 lockfiles. Add and pin dependencies when the owning task uses them; capability/backend compatibility is checked against the installed versions.

**Spec:** [Approved product/engineering specification](../../../specs/personal-intelligence-os-spec-v2.md), including sections 156â€“164. This plan translates the approved scope into executable phase plans; it does not declare their implementations complete.

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
- Commit each completed phase as authorized. Merge Phase 1 into main after its implementation and review are complete. Do not push, deploy, reset, change branches or perform destructive owner-volume operations without explicit direction.
- n8n is source-available/fair-code; do not label the entire stack exclusively OSI open source.

## Review Focus

1. Durable acknowledgment must survive Redis/worker failure and duplicate delivery (P02, P07, P10).
2. Egress grants, source isolation, model fallback and tools must fail closed (P03, P06, P07).
3. Corrections, revisions and deletion propagate across every derived representation (P01, P04â€“P06, P12).
4. The daily drawer retains the correct date/conversation through navigation and reconnect (P06, P08, P12).
5. A fresh install, upgrade, verified restore and measured target workload are separate release gates (P12).

## Plan Index and Dependencies

Phase 0 is implemented: [existing Phase 0 plan](2026-09-25-bbd-os-phase-0.md). Preserve its acceptance evidence; do not rerun its implementation.

| Phase | Local implementation plan | Entry dependency | Tasks | Implementation |
| --- | --- | --- | --- | --- |
| 1 | [Core Data Platform](2026-09-25-bbd-os-phase-1-core-data-platform.md) | Phase 0 acceptance | 4 | Code implemented; final review/acceptance handoff pending; tests deferred |
| 2 | [Ingestion and Packaged Connectors](2026-09-25-bbd-os-phase-2-ingestion-connectors.md) | Phase 1 sources/documents public contracts | 4 | Not started |
| 3 | [Search and Model Gateway Foundation](2026-09-25-bbd-os-phase-3-search-model-gateway.md) | Phase 2 chunks/provenance; live model acceptance needs configured endpoint and permitted aliases | 4 | Not started |
| 4 | [Entity Knowledge and Corrections](2026-09-25-bbd-os-phase-4-entity-knowledge.md) | Phase 3 validated structured-output alias, search and public library | 4 | Not started |
| 5 | [Temporal Knowledge and Timeline](2026-09-25-bbd-os-phase-5-temporal-knowledge.md) | Phase 4 entities/evidence; Phase 3 permitted chat/structured/embedding capabilities | 4 | Not started |
| 6 | [Ask, Chat Drawer and Selective Memory](2026-09-25-bbd-os-phase-6-ask-chat-drawer-memory.md) | Phase 3 retrieval/gateway, Phase 4 entities, Phase 5 temporal public APIs | 4 | Not started |
| 7 | [Agent Harness, Tools, MCP and Approvals](2026-09-25-bbd-os-phase-7-agent-harness-tools.md) | Phase 6 chat/memory; Phase 3 capabilities; Phase 2 isolated browser runtime | 4 | Not started |
| 8 | [Today, Daily Chat Drawer, Tasks and Goals](2026-09-25-bbd-os-phase-8-today-daily-chat-tasks.md) | Phases 1â€“7 public knowledge, chat, events and tools; source collection already runs in Phase 2 | 4 | Not started |
| 9 | [GitHub Collection and Project Knowledge](2026-09-25-bbd-os-phase-9-github-integration.md) | Phase 2 connector contract; Phases 4â€“8 entity/event/project presentation | 4 | Not started |
| 10 | [Automation Rules and Workflow Management](2026-09-25-bbd-os-phase-10-automation-workflows.md) | Phase 2 durable events/n8n; Phase 7 approvals; Phase 8 tasks/brief/notifications | 4 | Not started |
| 11 | [Observability and Operational Controls](2026-09-25-bbd-os-phase-11-observability-operations.md) | Phases 1â€“10 already emit run IDs, events, status and timing | 4 | Not started |
| 12 | [Hardening, Backup, Recovery and Full Acceptance](2026-09-25-bbd-os-phase-12-hardening-release-acceptance.md) | Functional acceptance from Phases 1â€“11; actual target hardware and permitted live integrations for final release gate | 5 | Not started |

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

Security, evidence, lifecycle logs and safe deletion are implemented with their owning feature; Phases 11â€“12 consolidate and audit them.

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

1. Read this master, the phase plan, current code and `EXECUTION.md`. Reconcile drift before editing and preserve user changes.
2. The implementation stage covers Phases 1-12. Implement production code and run production builds only. Do not create, modify or run test files or fixtures, or run tests, lint, or standalone typechecks. The plans keep behavioral acceptance in a separately labeled deferred test-stage section.
3. Keep one task active. Record its ID, scope, code changes, exact build command/result, review findings, unresolved external gates and next task in `EXECUTION.md`.
4. Each task implements its production behavior and builds the affected deliverable. At phase completion, run `./scripts/dev.ps1 build` (or `make build`) and fix build failures before advancing. Do not use a test result to mark any task or phase complete during implementation.
5. Keep all test authoring and execution out of phase implementation checklists. Preserve behavioral acceptance requirements separately for the later test stage. Do not add production test-only routes or change security boundaries to accommodate future tests.
6. Continue through every ready task in P01-P12. A blocked live integration does not stop independent code work; record missing external evidence and do not mark it verified.
7. After all Phase 1-12 production code is complete and all phase builds succeed, begin a separate test stage. First add/update the planned test files and fixtures, then run focused tests, integration/E2E suites, lint/typecheck, and the complete suite in the order defined by the relevant plans. Run destructive/reset/volume operations only against a verified disposable project/database.
8. At the end of the test stage, run the final build again, complete independent whole-branch review, fix findings and rerun the affected tests/builds, then update `docs/IMPLEMENTATION_STATUS.md`, the phase plans, architecture decisions when material, and `EXECUTION.md`.
9. Record exact commands and results; never invent evidence. Keep live-provider, target-hardware, restore and mini-host capacity gates separate from local tests/builds. Material architecture decisions and destructive owner operations require owner direction.
10. Continuous execution means continuing within an active run or resuming from this ledger. Markdown files do not create a scheduler/background process.
## Delivery Files and Current Checkpoint

- This master is the execution index.
- Twelve phase plans provide **49 task-level checklists**, production-code/build steps, and deferred test acceptance criteria.
- `EXECUTION.md` persists active/next task, gate status, evidence and handoff notes.
- `docs/IMPLEMENTATION_STATUS.md` distinguishes plan availability from implementation completion.
- Phase 0 and Phase 1 code/build delivery are complete. Phase 2 P02-T1 and P02-T2 are reviewed and complete; P02-T2 commits are `cfe481b`, `e57ea74`, and `14b0f41`. P02-T3 is next. Behavioral acceptance remains deferred until all Phase 1-12 production code is complete. Phases 3-12 have not started.
- Next implementation task: **P02-T3** using `superpowers:subagent-driven-development`. Existing owner authorization covers continuing ready tasks/phase scope; no new approval loop is added.

## External Integration Evidence and Release Gates

Use primary project documentation and verify the versions installed at execution:
- [OmniRoute](https://github.com/diegosouzapw/OmniRoute): configured endpoint/aliases; per-capability testing and destination policy are BBD-OS responsibilities.
- [Graphiti](https://github.com/getzep/graphiti): start compatibility testing with FalkorDB; keep it separate from queue Redis, and do not infer 8GB suitability from backend support.
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts): persist checkpoints and resume only after tool permissions/approval state are revalidated.
- [n8n Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/): use explicit timezone and verify the pinned runtime's scheduling behavior.

Final acceptance imports three RSS feeds, one GitHub repository, five text-bearing PDFs and several URLs; verifies all primary screens, search/citations, entity/event/graph updates, approved tasks, automated briefs, recovery and backup/restore. Measure the target 2-core/8GiB workload; available larger-host evidence remains labeled separately.
