---
name: implementing-bbd-os
description: Use when preparing, implementing, resuming, or reviewing BBD-OS Personal Intelligence OS tasks from personal-intelligence-os-spec-v2.md or docs/superpowers/plans, including phase dependencies, acceptance gates, and execution handoffs.
---

# Implementing BBD-OS

Repository-local reference for the approved specification and every implementation plan. The source documents own requirements and progress; this skill supplies navigation, not a second specification or completion ledger.

## Start here

Paths below are relative to the repository root unless linked. Locate the checkout containing `specs/personal-intelligence-os-spec-v2.md`; run commands there.

1. Read `AGENTS.md` and run `git status --short`. Preserve existing edits.
2. Read `docs/IMPLEMENTATION_STATUS.md`, `docs/ARCHITECTURE_DECISIONS.md`, and `docs/superpowers/plans/EXECUTION.md`.
3. Read the [master plan](../../../docs/superpowers/plans/2026-09-25-bbd-os-master-plan.md), then use [plan-map.md](plan-map.md) to select the phase and specification sections. Read the selected plan completely, including its entry gate, interfaces, fixtures and failure cases; inspect current code before editing.
4. Resolve requirements against the canonical [specification](../../../specs/personal-intelligence-os-spec-v2.md), especially revisions 156–164. Later explicit clarifications govern earlier examples. Report unresolved material contradictions rather than silently changing architecture.

Preparation/review requests produce readiness findings only. When implementation is requested, use **superpowers:executing-plans** as required by the plans, with native execution and the existing approval scope. This skill does not start background execution.

## Quick reference

| Need | Read |
| --- | --- |
| Current/next task, blocked evidence | `docs/superpowers/plans/EXECUTION.md` |
| Phase dependency and shared contracts | Master plan |
| Exact task files, tests and acceptance | Selected phase plan |
| Product behavior and architectural constraints | Specification + architecture decisions |
| All phases and feature routing | [plan-map.md](plan-map.md) |

## Implementation handoff

Record task ID, prerequisite evidence, affected contracts/files, failing behavioral check, passing commands/results, unresolved gates, and next ready task in `EXECUTION.md`. Keep one task active. Check plan boxes only after their required verification; update implementation status at phase boundaries. Follow the master's test/review protocol and continue authorized ready work without repeated scope approval.

On Windows, phase gates run sequentially:

```powershell
./scripts/dev.ps1 lint
./scripts/dev.ps1 typecheck
./scripts/dev.ps1 test
./scripts/dev.ps1 build
```

Use Make equivalents on Linux/macOS. Inspect runner support first: P01-T1 introduces targeted test flags; its initial failing check uses the existing full disposable test runner. Test resets/volume removal belong only to verified disposable projects.

## Common mistakes

- Treating plan examples as existing code: verify imports, packaging, fixtures and runner flags.
- Freezing the next task in this skill: always reread the ledger and reconcile with current code.
- Equating mocks or larger-host checks with acceptance: keep live-provider, graph, browser, n8n, target-hardware and restore gates explicit; continue independent work.
- Rebuilding completed Phase 0 or re-planning approved scope: use current evidence and phase dependencies.
- Treating a checklist as Git/deployment authorization: no automatic commit, push, branch change or deployment.
