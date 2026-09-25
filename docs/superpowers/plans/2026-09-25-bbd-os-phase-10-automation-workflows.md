# BBD-OS Phase 10 — Automation Rules and Workflow Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Let the owner configure bounded scheduled/event-driven rules without duplicating connector schedule ownership or inventing a workflow language.

**Architecture:** Implement the automations capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phase 2 durable events/n8n; Phase 7 approvals; Phase 8 tasks/brief/notifications supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 10, 60–61, 95, 138.18, 158–159. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phase 2 durable events/n8n; Phase 7 approvals; Phase 8 tasks/brief/notifications.

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

1. An automation must not trigger itself forever or fan out without bounds.
2. Duplicate events and retries must not repeat a completed action.
3. Pausing a rule invalidates queued work without deleting its history.
4. Preview must not send a webhook, create a task or spend model tokens.
5. External actions retain approval and uncertain-outcome semantics even when scheduled.

## File Structure and Boundaries

Module ownership: **automations**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P10-T1: Rule schema, deterministic conditions and dry preview

**Files and responsibilities:** Create modules/automations/models.py, modules/automations/schemas.py, modules/automations/conditions.py, modules/automations/public.py, modules/automations/routes.py; infrastructure/postgres/migrations/versions/0010_automations.py; tests/test_automation_conditions.py; tests/integration/test_automation_rules.py.

**Interfaces — consumes/produces:** CRUD /automations; POST /automations/preview. Automation(trigger,conditions,actions,enabled,revision). Conditions limited to whitelisted field/operator/value comparisons; no eval, scripts or arbitrary expressions. Preview returns matched/reasons/planned_actions only.

- [ ] **P10-T1.1 — Write the failing behavioral test.** Put this case in `tests/test_automation_conditions.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_condition_engine_does_not_evaluate_code():
    import pytest
    from modules.automations.conditions import evaluate
    with pytest.raises(ValueError):
        evaluate({"field":"__import__('os')","operator":"eq","value":"x"}, {})
```

- [ ] **P10-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_automation_conditions.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P10-T1.3 — Implement the minimal production behavior.** Use Pydantic discriminated unions for supported triggers schedule,new_event,new_document,entity_changed,task_due,goal_deadline,webhook,connector_sync_result and actions run_agent/create_task/create_notification/generate_brief/call_webhook. Fields must be declared in the selected trigger schema; supported operators eq,ne,in,gt,gte,lt,lte only. Store immutable rule revisions for runs; validate module dependencies and allowlist webhook targets. Preview reads fixtures/current authorized metadata without queueing work or calling models.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"trigger":{"type":"new_document"},"conditions":[{"field":"source_id","operator":"eq","value":"uuid"}],"actions":[{"type":"create_notification","message":"New source document"}]}
```

- [ ] **P10-T1.4 — Verify the behavior and listed failure cases.** Invalid operators/fields, unknown action, missing module, preview side-effect count zero, revision conflicts and read/write authorization.

- [ ] **P10-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P10-T2. Do not create a commit automatically.

## Task P10-T2: Dispatch, scheduling and durable execution

**Files and responsibilities:** Create modules/automations/scheduler.py, modules/automations/worker.py, modules/automations/execution.py; tests/integration/test_automation_execution.py; extend ARQ and n8n adapter bindings.

**Interfaces — consumes/produces:** POST /automations/{id}/run; GET /automations/{id}/runs; execution identity=(rule_id,revision,trigger_event_id or scheduled_slot). Scheduled rules have explicit timezone, next slot and misfire policy.

- [ ] **P10-T2.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_automation_execution.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_duplicate_trigger_runs_action_once(automation_fixture):
    await automation_fixture.enable_notification_rule()
    await automation_fixture.deliver("event-1")
    await automation_fixture.deliver("event-1")
    assert await automation_fixture.notification_count() == 1
```

- [ ] **P10-T2.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_automation_execution.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P10-T2.3 — Implement the minimal production behavior.** Use the Phase 2 durable event/outbox and ARQ mechanisms. n8n remains sole owner of collection schedules; internal rule schedules use ARQ/DB slots and never recreate source polling. Default missed internal slot policy coalesces to one catch-up run; no unbounded replay. Add causation IDs, max chain depth 5, max 10 actions per run, per-rule cooldown default 60s and concurrency 1. Check current enabled/revision/grants before dispatch; persist each action outcome. External webhook actions use the Phase 7 approval/effect ledger and shared SSRF safeguards.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"rule_id":"uuid","revision":1,"trigger_id":"event-1","causation_depth":1,"status":"queued"}
```

- [ ] **P10-T2.4 — Verify the behavior and listed failure cases.** Duplicate event, loop A-to-B-to-A, worker restart, pause between enqueue/execute, bounded catch-up, timezone/DST slots, 429 and uncertain webhook timeout.

- [ ] **P10-T2.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P10-T3. Do not create a commit automatically.

## Task P10-T3: Automation Agent and configuration UI

**Files and responsibilities:** Create apps/web/src/modules/automations/api.ts, apps/web/src/modules/automations/rule-editor.tsx, apps/web/src/modules/automations/rule-list.tsx, apps/web/src/modules/automations/run-detail.tsx; route /automations; extend modules/agents/specialists.py; tests/e2e/automations.spec.ts.

**Interfaces — consumes/produces:** Automation Agent creates proposals using registered schemas; owner accept creates a disabled draft rule, separate explicit enable starts it. UI offers Trigger/Conditions/Actions with preview, enable/disable, run history and manual Run now.

- [ ] **P10-T3.1 — Write the failing behavioral test.** Put this case in `tests/e2e/automations.spec.ts` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```typescript
import { test, expect } from './fixtures';

test('preview does not activate a rule', async ({ page }) => {
  await page.goto('/automations');
  await page.getByRole('button', { name: 'New automation' }).click();
  await page.getByLabel('Trigger').selectOption('new_document');
  await page.getByLabel('Action').selectOption('create_notification');
  await page.getByLabel('Message').fill('New document received');
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByText('Preview only — no actions executed')).toBeVisible();
  await expect(page.getByRole('switch', { name: 'Enabled' })).not.toBeChecked();
});
```

- [ ] **P10-T3.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -E2eTarget tests/e2e/automations.spec.ts` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P10-T3.3 — Implement the minimal production behavior.** Use schema-backed ordinary forms rather than a node-canvas or custom DSL. Show estimated scope and exact external targets, validation errors, preview reasons and action outcomes. Allow opening related approval inside chat drawer/run detail. Clear disabled/unavailable actions when their owning module is disabled. Keep source schedule editing in Sources/n8n and link to it.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"proposal_id":"uuid","accepted":true,"rule_enabled":false}
```

- [ ] **P10-T3.4 — Verify the behavior and listed failure cases.** Keyboard authoring, preview, proposal acceptance, enable/disable, protected Run now, pending approval, history and failed action retry.

- [ ] **P10-T3.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P10-T4. Do not create a commit automatically.

## Task P10-T4: Operational rule pack and end-to-end checks

**Files and responsibilities:** Create tests/fixtures/automations/rules.json; docs/automations.md; tests/integration/test_automation_workflows.py; update seed and implementation status.

**Interfaces — consumes/produces:** Optional fictional examples: new source document -> notification; due task -> notification; scheduled brief -> existing generate-brief action; owner-approved run_agent. Examples install disabled.

- [ ] **P10-T4.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_automation_workflows.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_disabled_sample_does_not_schedule(automation_fixture):
    await automation_fixture.install_samples(enabled=False)
    await automation_fixture.advance_scheduler()
    assert await automation_fixture.execution_count() == 0
```

- [ ] **P10-T4.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_automation_workflows.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P10-T4.3 — Implement the minimal production behavior.** Document schedule ownership, missed-run behavior, permission model, action limits and recovery. Ensure sample rules never duplicate the existing Phase 8 brief schedule when enabled: selecting an automation-owned brief slot transfers ownership explicitly in the schedule record. Retain one scheduler owner per logical job.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"logical_job":"daily_brief","schedule_owner":"internal_brief","automation_id":null}
```

- [ ] **P10-T4.4 — Verify the behavior and listed failure cases.** Full source->event->rule->notification flow, due-task reminder, agent proposal approval, no duplicate brief and disabled sample no-op. Common gate; next P11-T1.

- [ ] **P10-T4.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to the phase acceptance gate, then P11-T1. Do not create a commit automatically.

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
