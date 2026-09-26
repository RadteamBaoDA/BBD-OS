# BBD-OS Phase 6 — Ask, Chat Drawer and Selective Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Answer questions with citations and reusable chat in an on-demand drawer that preserves screen space.

**Architecture:** Implement the chat, memory capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 3 retrieval/gateway, Phase 4 entities, Phase 5 temporal public APIs supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 34–43, 65, 95, 111–114, 138.2/15/24, 157; owner drawer decision 2026-09-25. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 3 retrieval/gateway, Phase 4 entities, Phase 5 temporal public APIs.

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

1. The drawer never reserves a permanent empty column when closed.
2. Closing the drawer does not lose the draft, conversation or a server-side response.
3. Retrieved instructions cannot override permissions or create fake citation IDs.
4. History storage, memory creation and remote processing are independent privacy choices.
5. Evidence deletion invalidates stored citation access and derived memory retrieval.

## File Structure and Boundaries

Module ownership: **chat, memory**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P06-T1: Grounded retrieval and citation validation

**Files and responsibilities:** Create modules/chat/retrieval.py, modules/chat/citations.py, modules/chat/public.py, modules/chat/schemas.py; modules/knowledge/public.py extensions; tests/test_citations.py; tests/integration/test_ask_retrieval.py.

**Interfaces — consumes/produces:** AnswerContext(query,source_scope,entity_ids,date_context?,policy); Citation(sourceType,sourceId,documentId,documentVersionId,chunkId,title,url,observedAt,quote). build_context returns bounded permitted evidence; validate_citations(answer,evidence) rejects references not in the retrieved set.

- [ ] **P06-T1.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
def test_unknown_citation_is_rejected():
    import pytest
    from modules.chat.citations import validate_citations
    with pytest.raises(ValueError):
        validate_citations({"citation_ids":["unretrieved"]},
                           {"allowed":{"text":"Evidence"}})
```

- [ ] **P06-T1.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P06-T1.3 — Implement the minimal production behavior.** Retrieve lexical/hybrid + relevant temporal/entity context via public APIs; deduplicate and fit a context budget before model calls. Add a configured permitted reranker where available; if unavailable preserve retrieval ranking and label rerank unavailable rather than invent scores. Require exact evidence IDs/quotes from available revisions; answers without sufficient evidence explicitly say so. Treat documents/web text as untrusted data and never execute embedded instructions.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"answer":"Supported answer","citations":[{"sourceType":"document","sourceId":"uuid","documentId":"uuid","documentVersionId":"uuid","chunkId":"uuid","title":"Note","url":null,"observedAt":"2026-09-25T03:00:00Z","quote":"Evidence"}]}
```

- [ ] **P06-T1.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Grounded known answers, insufficient-evidence answer, invented/removed citation, mixed source privacy, prompt injection, quote bounds, unavailable reranker and provider failures. Record live response acceptance separately.

- [ ] **P06-T1.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P06-T2: Persistent conversations, responses and replayable stream

**Files and responsibilities:** Create modules/chat/models.py, modules/chat/routes.py, modules/chat/worker.py, modules/chat/stream.py; infrastructure/postgres/migrations/versions/0007_chat_memory.py; tests/integration/test_conversations.py; tests/test_stream_events.py.

**Interfaces — consumes/produces:** CRUD /conversations; POST /conversations/{id}/messages accepts client_request_id,content,context; returns message_id,response_id. GET /responses/{id}/events uses SSE event IDs; POST /responses/{id}/cancel. Message metadata holds model identity, usage unknown when absent, and citation references.

- [ ] **P06-T2.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_repeated_send_does_not_create_second_response(owner_client, conversation):
    path = f"/api/v1/conversations/{conversation['id']}/messages"
    body = {"client_request_id":"same-request","content":"Summarize my note"}
    first = await owner_client.post(path, json=body)
    second = await owner_client.post(path, json=body)
    assert first.json()["response_id"] == second.json()["response_id"]
```

- [ ] **P06-T2.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P06-T2.3 — Implement the minimal production behavior.** Create conversation fixture using POST /conversations; deterministic tests inject ModelGateway transport, never call a live provider implicitly. Persist user message and pending response before dispatch. Worker owns generation independently of browser connection; persist bounded stream events and final text so reconnect resumes by event ID. Refresh auth on reconnect; no response text after permission is revoked. Store partial/cancelled/failed states distinctly. With history storage off, retain only active-run state needed for delivery, then purge within 24h or earlier explicit delete; never turn it into memory automatically.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"event":"message.delta","id":"response-id:12","data":{"text":"partial"}}
```

- [ ] **P06-T2.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Disconnect/reconnect, repeated POST, worker crash, cancel, token expiry, history opt-out cleanup and deletion while streaming. No raw chain-of-thought is stored or shown.

- [ ] **P06-T2.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P06-T3: Reusable accessible chat drawer and full Ask route

**Files and responsibilities:** Create apps/web/src/modules/chat/api.ts, apps/web/src/modules/chat/chat-drawer.tsx, apps/web/src/modules/chat/chat-session.tsx, apps/web/src/modules/chat/chat-transcript.tsx, apps/web/src/modules/chat/chat-composer.tsx, apps/web/src/modules/chat/chat-history.tsx, apps/web/src/modules/chat/citation-panel.tsx; apps/web/src/core/app-shell/chat-controller.tsx; route /ask; tests/e2e/chat-drawer.spec.ts.

**Interfaces — consumes/produces:** ChatDrawer.open({conversationId?,context?}); ChatContext {kind:'general'|'document'|'entity'|'day',resource_id?,date?,timezone?}. Same ChatSession component powers /ask and the drawer; one server conversation per chosen ID, no duplicate transcript store.

- [ ] **P06-T3.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```typescript
import { test, expect } from './fixtures';

test('drawer returns focus and keeps its draft', async ({ page }) => {
  await page.goto('/knowledge/documents');
  const trigger = page.getByRole('button', { name: 'Open chat' });
  await trigger.click();
  await page.getByRole('textbox', { name: 'Message' }).fill('Draft to keep');
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue('Draft to keep');
});
```

- [ ] **P06-T3.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P06-T3.3 — Implement the minimal production behavior.** Use the existing UI ecosystem's accessible Sheet/Dialog primitive, not a custom focus trap. Right-side overlay drawer, closed by default, width min(440px,100vw), full viewport on mobile; underlying page gets full width when closed. Escape/close restores focus and closes presentation only, not the server run. Stop is a separate explicit action. Keep draft in local in-memory UI state, not persistent browser storage of private content; server transcript remains TanStack Query state. Header has title/context, history, expand to /ask and close. Sources/activity/history are tabs or subviews inside the drawer, not additional permanent columns. Show current context and preserve conversation ID when expanding.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"conversationId":"uuid","context":{"kind":"document","resource_id":"uuid"}}
```

- [ ] **P06-T3.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Keyboard open/close/focus trap, focus return, mobile viewport, no horizontal overflow, retained draft, close during stream/reopen, citation view without extra sidebar, and expand preserving transcript. Cover all async/error/empty states.

- [ ] **P06-T3.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

## Task P06-T4: Selective memory and privacy management

**Files and responsibilities:** Create modules/memory/models.py, modules/memory/schemas.py, modules/memory/public.py, modules/memory/routes.py, modules/memory/selection.py; apps/web/src/modules/knowledge/memory-list.tsx; apps/web/src/modules/settings/memory-privacy.tsx; tests/integration/test_memory.py; extend deletion/export hooks.

**Interfaces — consumes/produces:** CRUD /memories; POST /memories/{id}/invalidate, /supersede, /forget; MemoryCandidate(content,type,provenance,confidence,reason). Lifecycle and memory policy are independent of conversation-history policy.

- [ ] **P06-T4.1 - Review the behavior contract.** The acceptance example below is for the final test stage; do not create or modify test files during implementation.

```python
async def test_forget_removes_memory_from_retrieval(owner_client, saved_memory):
    response = await owner_client.post(f"/api/v1/memories/{saved_memory['id']}/forget")
    assert response.status_code in (202,204)
    results = (await owner_client.get("/api/v1/memories")).json()
    assert saved_memory["id"] not in [x["id"] for x in results["items"]]
```

- [ ] **P06-T4.2 - Implement the production behavior.** Follow task interfaces; defer all test work until Phases 1-12 code is complete.

- [ ] **P06-T4.3 — Implement the minimal production behavior.** Add saved_memory fixture using explicit owner create. Evaluate novelty/usefulness/confidence for suggestions and record why selected; default automatic permanent memory off until owner enables it. Differentiate manual facts from model-derived candidates. Forget marks content unavailable immediately and removes vector/graph/cache copies through durable deletion; purge stored candidate payloads containing removed evidence. Update KnowledgeService.get_memories and reusable context methods.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"store_conversation_history":true,"store_agent_memory":false,"auto_accept_memory":false}
```

- [ ] **P06-T4.4 - Build the affected deliverable.** Run `./scripts/dev.ps1 build` (or `make build`); fix build failures before proceeding. Deferred acceptance criteria: Memory opt-out, source-linked forget, selective candidate dedupe, superseded fact exclusion and explicit manual memory creation. Common gate includes drawer E2E; next P07-T1.

- [ ] **P06-T4.5 - Record build evidence and continue.** Record changed files, exact build command/result, review findings and unresolved gates in `EXECUTION.md`; then continue. Do not run tests during implementation.

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
