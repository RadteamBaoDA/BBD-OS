# BBD-OS Phase 7 — Agent Harness, Tools, MCP and Approvals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Run bounded specialist agents using shared LangGraph orchestration, registered tools and durable approvals.

**Architecture:** Implement the agents, tools capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 6 chat/memory; Phase 3 capabilities; Phase 2 isolated browser runtime supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 9, 39–40, 62, 87–88, 95, 138.16–17, 140–150, 158, 160. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 6 chat/memory; Phase 3 capabilities; Phase 2 isolated browser runtime.

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

1. A model-requested tool is not authorization to execute it.
2. An approval is bound to immutable arguments and expires; replay must not repeat effects.
3. A checkpoint resumes nodes, so external side effects need their own idempotency/reconciliation.
4. Cancellation/module disablement must be checked before every next tool.
5. MCP output and browser content remain untrusted regardless of server registration.

## File Structure and Boundaries

Module ownership: **agents, tools**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P07-T1: Tool registry, permissions and MCP adapters

**Files and responsibilities:** Create core/tools/schemas.py, core/tools/registry.py, core/tools/policy.py; modules/tools/mcp.py, modules/tools/routes.py; tests/test_tool_policy.py; tests/integration/test_mcp_tools.py.

**Interfaces — consumes/produces:** ToolDefinition(name,version,input_schema,output_schema,risk,confirmation,timeout,permissions,module); invoke_tool(actor,definition,args,grant) -> ToolResult. READ_ONLY automatic; INTERNAL_WRITE configurable; EXTERNAL_WRITE/DESTRUCTIVE require approval. MCP server config is explicit owner-managed allowlist.

- [ ] **P07-T1.1 — Write the failing behavioral test.** Put this case in `tests/test_tool_policy.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_external_write_requires_approval():
    from core.tools.policy import requires_approval
    assert requires_approval("EXTERNAL_WRITE", internal_write_auto=True)
    assert requires_approval("DESTRUCTIVE", internal_write_auto=True)
    assert not requires_approval("READ_ONLY", internal_write_auto=True)
```

- [ ] **P07-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_tool_policy.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P07-T1.3 — Implement the minimal production behavior.** Register public Knowledge/Search/Source tools from enabled modules with schemas, not hardcoded tool lists in the supervisor. Validate input and output, resource scope, module state, egress policy and timeout at dispatch. Use maintained MCP SDK; deny arbitrary stdio command execution from model input, pin allowed server configurations, and enforce grants on MCP calls like native tools. Only expose implemented tools; tasks/goals register in Phase 8.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"name":"knowledge.get_document","version":"1","risk":"READ_ONLY","timeout_seconds":10,"module":"knowledge"}
```

- [ ] **P07-T1.4 — Verify the behavior and listed failure cases.** Malformed arguments, output schema mismatch, disabled module, missing grant, hostile MCP content and timeout. Test registry duplicate names/version compatibility.

- [ ] **P07-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P07-T2. Do not create a commit automatically.

## Task P07-T2: LangGraph execution, checkpointing and run limits

**Files and responsibilities:** Create modules/agents/models.py, modules/agents/schemas.py, modules/agents/harness.py, modules/agents/worker.py, modules/agents/public.py, modules/agents/routes.py; infrastructure/postgres/migrations/versions/0008_agents.py; tests/integration/test_agent_runs.py; extend chat response/activity events.

**Interfaces — consumes/produces:** POST /agents/{id}/runs -> run_id; GET /agent-runs/{id}; POST /agent-runs/{id}/cancel; states queued,running,waiting_approval,succeeded,failed,cancelled. Limits default 20 steps,10 tool calls,300s active execution, configurable token budget when usage exists.

- [ ] **P07-T2.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_agent_runs.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_cancel_prevents_next_tool(agent_run_fixture):
    await agent_run_fixture.start()
    await agent_run_fixture.pause_before_tool()
    await agent_run_fixture.cancel()
    await agent_run_fixture.resume_worker()
    assert agent_run_fixture.executed_tool_count == 0
```

- [ ] **P07-T2.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_agent_runs.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P07-T2.3 — Implement the minimal production behavior.** Define agent_run_fixture with real PostgreSQL checkpoints, injected deterministic model/tool boundary and controlled worker scheduling. Use LangGraph PostgreSQL checkpointer; integrate shared ModelGateway budget/concurrency/permissions. Check cancellation and limits before each model/tool. Save outputs/evidence, not hidden reasoning. Waiting approval releases the ARQ job; separate resume job revalidates permissions. Version prompts/workflows; incompatible old runs are explicitly migrated or cancelled, never silently run with new semantics.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"status":"waiting_approval","steps":3,"tool_calls":1,"active_seconds":12,"token_usage":null}
```

- [ ] **P07-T2.4 — Verify the behavior and listed failure cases.** Checkpoint restart, transient provider failures, hard step/time limits, worker duplicate delivery, cancellation before/after tool and missing usage treated as unknown.

- [ ] **P07-T2.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P07-T3. Do not create a commit automatically.

## Task P07-T3: Immutable approvals and effect reconciliation

**Files and responsibilities:** Create modules/agents/approvals.py, modules/agents/effects.py; tests/integration/test_approvals.py; frontend apps/web/src/modules/agents/approval-card.tsx; chat activity integration.

**Interfaces — consumes/produces:** POST /approvals/{id}/approve or /deny; approval stores tool version,normalized argument hash,action payload,expires_at,resolved_at. Effect ledger stores action_id,provider_key,state,result_reference; uncertain outcome state is requires_review.

- [ ] **P07-T3.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_approvals.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_resolved_approval_cannot_be_used_twice(approval_fixture):
    approved = await approval_fixture.approve_once()
    await approval_fixture.dispatch(approved)
    await approval_fixture.dispatch(approved)
    assert approval_fixture.external_effect_count == 1
```

- [ ] **P07-T3.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_approvals.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P07-T3.3 — Implement the minimal production behavior.** Define approval_fixture around the actual approval/effect repositories and a counted test transport. Display exact action/target/arguments before decision; use one atomic pending-to-approved transition and configurable expiry default 24h. Never pause after an irreversible side effect inside a replayed node without recording its outcome. Use provider idempotency keys or reconciliation; timeout with unknown outcome becomes requires_review rather than automatic retry. Destructive tool actions cannot be auto-approved by retrieved text or ordinary source permissions.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"risk":"EXTERNAL_WRITE","status":"pending","tool":"webhook.send","arguments":{"target":"configured-hook"},"expires_at":"2026-09-26T03:00:00Z"}
```

- [ ] **P07-T3.4 — Verify the behavior and listed failure cases.** Changed args, expired/denied approval, duplicate approval/resume, permission revocation while waiting and ambiguous HTTP timeout. Approval UI accessible inside the drawer and on run detail.

- [ ] **P07-T3.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P07-T4. Do not create a commit automatically.

## Task P07-T4: Specialists, browser-use and management UI

**Files and responsibilities:** Create modules/agents/specialists.py, modules/tools/browser.py; apps/web/src/modules/agents/agent-list.tsx, apps/web/src/modules/agents/agent-settings.tsx, apps/web/src/modules/agents/run-detail.tsx; routes /agents and /agents/[agentId]; tests/e2e/agents.spec.ts; docs/agents.md.

**Interfaces — consumes/produces:** Supervisor,Knowledge,Research,Personal,Project,News,Planning share one harness; Automation specialist is activated Phase 10. Browser tool submits bounded jobs to Phase 2 runtime; receives run_id/results through protected API.

- [ ] **P07-T4.1 — Write the failing behavioral test.** Put this case in `tests/e2e/agents.spec.ts` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```typescript
import { test, expect } from './fixtures';

test('run shows approval before an external action', async ({ page }) => {
  await page.goto('/agents');
  await page.getByRole('link', { name: 'Research' }).click();
  await page.getByRole('button', { name: 'Run' }).click();
  await expect(page.getByRole('heading', { name: 'Approval required' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve' })).toBeEnabled();
});
```

- [ ] **P07-T4.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -E2eTarget tests/e2e/agents.spec.ts` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P07-T4.3 — Implement the minimal production behavior.** The browser fixture provisions a deterministic Research run that requests a registered external-write action against a disposable fixture provider, so the approval test does not depend on a live model deciding to request one. Configure specialists by prompts, model aliases and allowed tools; start sequentially. Show unavailable dependent capabilities rather than fabricated task/goal actions before Phase 8. Add browser-use only after actual OmniRoute browser/tool capability probes, with per-job page/action/time/download limits and a separate credential-isolated browser worker. Preserve session state only in protected source-specific storage. Model assignment, prompt revision, permissions, recent runs and failures are editable in Agents UI; drawer activity shows concise tool status.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"agent":"research","enabled":true,"tools":["knowledge.search","browser.read"],"model_alias":"reasoning-large"}
```

- [ ] **P07-T4.4 — Verify the behavior and listed failure cases.** Browser network isolation, collection grant vs external write, exhausted browser budget, provider tool-format compatibility, run history and drawer approvals. Common gate; next P08-T1.

- [ ] **P07-T4.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to the phase acceptance gate, then P08-T1. Do not create a commit automatically.

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
