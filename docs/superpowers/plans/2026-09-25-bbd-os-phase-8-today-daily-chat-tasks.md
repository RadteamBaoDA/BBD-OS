# BBD-OS Phase 8 — Today, Daily Chat Drawer, Tasks and Goals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. The owner authorized continuous progress through ready tasks; use the [master plan](2026-09-25-bbd-os-master-plan.md) and [execution ledger](EXECUTION.md), without repeated phase-scope approval.

**Goal:** Deliver the daily dashboard with an on-demand contextual chat drawer, actionable tasks/goals, ranked news and saved briefs.

**Architecture:** Implement the dashboard, tasks, goals, news, notifications capability using the existing modular monolith, public DTO/service/event boundaries and small frontend feature modules. Phases 1–7 public knowledge, chat, events and tools; source collection already runs in Phase 2 supplies the entry contracts. Reuse the approved OSS components; create only files with a consumer in this phase.

**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, Redis/ARQ, Next.js/React/TypeScript/TanStack Query, pytest and Playwright; phase-specific OSS dependencies are pinned only after their compatibility checks.

**Spec:** [Canonical specification](../../../specs/personal-intelligence-os-spec-v2.md), sections 38, 44–47, 56–59, 66, 95, 115, 138.1/7–9/19–21, 144; owner daily-history/drawer decisions. The [master plan](2026-09-25-bbd-os-master-plan.md) defines common contracts, the drawer decision, test harness and ownership across phases.

**Entry gate:** Phases 1–7 public knowledge, chat, events and tools; source collection already runs in Phase 2.

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

1. Changing dashboard date cannot silently retarget an existing message or running response.
2. A saved historical brief is distinct from lists refreshed using current data.
3. Tasks crossing local midnight and date-only deadlines must render under the selected timezone.
4. Repeated brief/notification jobs cannot spam duplicates or silently replace historical revisions.
5. Stories from one source repeated many times must not fabricate cross-source importance.

## File Structure and Boundaries

Module ownership: **dashboard, tasks, goals, news, notifications**. Backend domain models/services stay in their owning module; frontend components/API clients stay in the matching frontend module. The files listed per task are planned paths; read existing files before editing and extend existing equivalents instead of creating duplicates. Module descriptor, navigation, settings and tool registration must use the common mechanisms from Phase 1/7/8 as applicable. Migrations are sequential after the previous accepted phase; once a revision has shipped, add a revision rather than rewrite history.

## Task P08-T1: Tasks, goals, topics and approved planning

**Files and responsibilities:** Create modules/tasks/models.py, modules/tasks/schemas.py, modules/tasks/public.py, modules/tasks/routes.py, modules/tasks/tools.py; modules/goals/models.py, modules/goals/schemas.py, modules/goals/public.py, modules/goals/routes.py, modules/goals/tools.py; modules/news/topics.py; infrastructure/postgres/migrations/versions/0009_daily_work.py; frontend task/goal/topic modules; tests/integration/test_tasks_goals.py.

**Interfaces — consumes/produces:** CRUD /tasks,/goals,/topics; goals own milestones and linked task/entity references. Task statuses inbox,todo,in_progress,blocked,done,cancelled. POST /goals/{id}/accept-plan atomically materializes an owner-accepted proposal once.

- [ ] **P08-T1.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_tasks_goals.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_accepting_same_plan_does_not_duplicate_tasks(owner_client, goal_proposal):
    path = f"/api/v1/goals/{goal_proposal['goal_id']}/accept-plan"
    body = {"proposal_id":goal_proposal["id"],"expected_revision":1}
    first = await owner_client.post(path, json=body)
    again = await owner_client.post(path, json=body)
    assert first.json()["task_ids"] == again.json()["task_ids"]
```

- [ ] **P08-T1.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_tasks_goals.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P08-T1.3 — Implement the minimal production behavior.** Create goal_proposal via a deterministic Planning Agent fixture with public proposal schema. Implement Inbox/Today/Upcoming/Blocked/Completed and All, due dates with date-only versus instant semantics, completion times and optimistic revisions. Goals contain desired outcome/deadline/progress/milestones; progress from linked completed milestones unless owner explicitly selects manual tracking. Register tools with existing registry; never create proposed tasks before acceptance. Extend global search with tasks/goals and fictional seed.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"title":"Prepare release","status":"todo","due_date":"2026-09-25","due_at":null,"goal_id":"uuid"}
```

- [ ] **P08-T1.4 — Verify the behavior and listed failure cases.** Timezone/DST, completion/reopen, stale update, deleted linked entity, accepted plan replay and no task creation from an unaccepted proposal.

- [ ] **P08-T1.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P08-T2. Do not create a commit automatically.

## Task P08-T2: Story clustering, trends and explainable relevance

**Files and responsibilities:** Create modules/news/models.py, modules/news/stories.py, modules/news/trends.py, modules/news/relevance.py, modules/news/public.py, modules/news/routes.py; tests/test_news_ranking.py; frontend apps/web/src/modules/news/story-list.tsx, apps/web/src/modules/news/story-detail.tsx, apps/web/src/modules/news/topic-settings.tsx.

**Interfaces — consumes/produces:** GET /stories,/trends; score_relevance(signals) -> {score,why_relevant}; cluster candidates preserve article IDs/evidence. Signals normalized [0,1]: topic,entity,goal,project,recency,importance,novelty. Default equal weights; editable owner interests.

- [ ] **P08-T2.1 — Write the failing behavioral test.** Put this case in `tests/test_news_ranking.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
def test_relevance_explains_positive_signals():
    from modules.news.relevance import score_relevance
    result = score_relevance({"topic":1.0,"goal":0.5})
    assert result["score"] > 0
    assert set(result["why_relevant"]) == {"topic","goal"}
```

- [ ] **P08-T2.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/test_news_ranking.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P08-T2.3 — Implement the minimal production behavior.** Use deterministic canonical URL/hash groups first, then bounded embedding/entity/time similarity when embeddings exist. Candidate window default 72h; uncertain matches remain separate. Preserve per-source observations, choose representative evidence, and label auto-generated summaries. Trends compare current 24h activity with preceding 7-day per-day baseline and require at least two distinct sources plus three items before a rising alert; low baseline is flagged rather than infinite growth. Scores derive from recorded signals, no LLM-invented numeric confidence. Keep lexical-only ranking when AI unavailable.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"story_id":"uuid","trend":"rising","source_count":3,"evidence_ids":["uuid"],"why_relevant":["topic","goal"]}
```

- [ ] **P08-T2.4 — Verify the behavior and listed failure cases.** Duplicate articles from one source, unrelated same-name entities, low baseline, stale stories, evidence removal and no-model behavior. Model-dependent summaries require citations and existing egress grants.

- [ ] **P08-T2.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P08-T3. Do not create a commit automatically.

## Task P08-T3: Daily context, revisioned brief and notifications

**Files and responsibilities:** Create modules/dashboard/context.py, modules/dashboard/briefs.py, modules/dashboard/models.py, modules/dashboard/routes.py, modules/dashboard/worker.py; modules/notifications/models.py, modules/notifications/public.py, modules/notifications/routes.py; tests/integration/test_daily_context.py; extend ARQ internal schedules and module widget descriptors.

**Interfaces — consumes/produces:** GET /context/current; GET /context/daily?date=YYYY-MM-DD&timezone=IANA; GET /briefs?date=&timezone=; POST /briefs/generate; GET/PATCH /notifications. DailyContext returns selected_date,timezone,generated_at,brief,widgets; briefs revisioned by date/timezone/input fingerprint.

- [ ] **P08-T3.1 — Write the failing behavioral test.** Put this case in `tests/integration/test_daily_context.py` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```python
async def test_regeneration_preserves_saved_brief(daily_brief_fixture):
    first = await daily_brief_fixture.generate("2026-09-25")
    await daily_brief_fixture.add_event()
    second = await daily_brief_fixture.generate("2026-09-25")
    assert second["revision"] > first["revision"]
    assert await daily_brief_fixture.read_revision(first["id"]) == first
```

- [ ] **P08-T3.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -PytestTarget tests/integration/test_daily_context.py` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P08-T3.3 — Implement the minimal production behavior.** Define fixture against real repositories and deterministic model client. Default brief schedule 07:00 Asia/Ho_Chi_Minh, editable; ARQ owns this internal schedule. During startup catch up once for current day if missing, not every missed historical day. Build context from public module providers, rank, generate cited brief and retain each revision. Historical brief stays saved; widgets use current records filtered to the selected date and show updated_at. Past-day open tasks are not claimed as historical task-state snapshots. Future dates show planned commitments without fabricated generated news. Notifications have dedupe keys and read state; emit only meaningful actionable changes.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"selected_date":"2026-09-25","timezone":"Asia/Ho_Chi_Minh","brief_revision":1,"widgets_updated_at":"2026-09-25T09:00:00Z","history_mode":"saved_brief_current_records"}
```

- [ ] **P08-T3.4 — Verify the behavior and listed failure cases.** Concurrent generation, model outage preserving last brief, notification dedupe, date-only tasks, configured timezone changes, missed schedule and source data deleted after a brief (citations invalidated/brief marked stale).

- [ ] **P08-T3.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to P08-T4. Do not create a commit automatically.

## Task P08-T4: Today dashboard and contextual drawer UX

**Files and responsibilities:** Create apps/web/src/modules/dashboard/today-page.tsx, apps/web/src/modules/dashboard/date-selector.tsx, apps/web/src/modules/dashboard/widget-registry.tsx, apps/web/src/modules/dashboard/daily-brief.tsx; notifications frontend; modify authenticated root routing and chat drawer controller; tests/e2e/today-drawer.spec.ts; docs/ux/today-chat.md.

**Interfaces — consumes/produces:** GET /context/daily drives widgets. ChatContext {kind:'day',date,timezone}; a chosen day conversation stores that immutable context. Drawer inherits the Phase 6 component; no permanent chat column. Widgets register id,module,title,priority,provider,refresh_policy,permissions.

- [ ] **P08-T4.1 — Write the failing behavioral test.** Put this case in `tests/e2e/today-drawer.spec.ts` and implement any named test fixture in the same test package's `conftest.py` (browser fixtures in `tests/e2e/fixtures.ts`) as described below. Fixtures may control test transports/services; they must never introduce production test endpoints.

```typescript
import { test, expect } from './fixtures';

test('day drawer keeps context and frees width when closed', async ({ page }) => {
  await page.goto('/?date=2026-09-25');
  await page.getByRole('button', { name: 'Open chat' }).click();
  await expect(page.getByRole('dialog', { name: 'Chat' })).toContainText('2026-09-25');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'Chat' })).not.toBeVisible();
  await expect(page.getByLabel('Selected day')).toHaveValue('2026-09-25');
});
```

- [ ] **P08-T4.2 — Observe the expected failure.** Run `./scripts/dev.ps1 test -E2eTarget tests/e2e/today-drawer.spec.ts` after P01 establishes the targeted runner. For P01-T1 before targeted-runner support is added, use the existing disposable `./scripts/dev.ps1 test`; subsequent tasks use the targeted command above. Expect the specific missing behavior/import/route assertion; configuration or unrelated fixture failure is not the red test.

- [ ] **P08-T4.3 — Implement the minimal production behavior.** Today becomes authenticated root with previous/next/today/date picker, Daily Brief, Upcoming, Tasks/Goals, important events, stories/trends, knowledge changes and recent activity. No calendar connector means only available manual/imported events, with explicit source status. Desktop chat is right overlay; mobile full-screen Sheet; default closed. History, citations and approvals stay inside the drawer. Selecting another day switches the drawer's selected conversation to that day without modifying an old conversation or cancelling its background run; in-flight output remains associated with its original response. Opening full Ask preserves conversation ID and date badge. Closing restores focus/draft and the main viewport remains full-width.

Concrete contract/configuration shape (illustrative IDs/timestamps are test data, not production defaults):

```json
{"conversationId":"uuid","context":{"kind":"day","date":"2026-09-25","timezone":"Asia/Ho_Chi_Minh"}}
```

- [ ] **P08-T4.4 — Verify the behavior and listed failure cases.** Today/mobile/keyboard, day switching while streaming, cross-midnight, saved brief versus updated widgets labels, accepted tasks from chat, no duplicate chat history, and chat closed consuming zero layout column. Common gate; next P09-T1.

- [ ] **P08-T4.5 — Record evidence and continue.** Record changed files, actual commands/results and any missing external evidence in `EXECUTION.md`; check this task only after its required behavior passes. Continue to the phase acceptance gate, then P09-T1. Do not create a commit automatically.

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
