# P04-T4 repair 1 — source dispositions

## Scope

This repair completes the P04-T4 production source changes for entity review, correction, evidence, graph, search, and owner UI. The accepted staged T3 baseline was preserved. Production files changed in this repair include the entity/document public contracts and schemas; knowledge API/client, entity list/detail/review/graph and search page; the shared guarded-navigation provider; and the English/Vietnamese message catalog. The controller owns the canonical full-source and repair diff snapshots and hashes for the final frozen tree.

## Finding dispositions

1. **Review cursor validation and imports — repaired.** Added the missing JSON support and strict bounded cursor decoding, including index validation, for owner review pagination.
2. **Durable review decisions — repaired.** Review assignment and relationship resolution update a detached `review_json` value and persist it, so terminal decision state is not lost through JSON mutation tracking.
3. **Terminal candidates and pagination — repaired.** Resolved, assigned, and suppressed review candidates are omitted from the actionable queue; pagination advances through candidates and work rows without exposing terminal items as pending work.
4. **Exact selectors and generation fencing — repaired.** Candidate selectors are scoped to the same extraction result and cited document version/chunk. Assignment rechecks the complete selector before and after writes. The owner source generation is a distinct request fence; extraction generation remains intact.
5. **Entity drafts and corrections — repaired.** Identity PATCHes send changed fields only against a captured base revision. Stale drafts can be explicitly kept/rebased or discarded; canonical changes require an explicit action. Merge/split previews are bound to source/target revisions, reason, and selected evidence; stale selections cannot confirm. Successful corrections navigate to their canonical/replacement result.
6. **Evidence-backed review and relationships — repaired.** Review projections include bounded retained evidence citations and endpoint assignment state. Relationship evidence is selectable in detail and opens the cited document revision; missing, ambiguous, or changed endpoint membership blocks resolution.
7. **Bounded accessible graph — repaired.** The graph pages on demand with a focus node, caps nodes, unique edges, and retained rows at 100, exposes truncation, supports pan/zoom/refocus/expand and focused keyboard controls, and provides an accessible relationship list and localized React Flow labels.
8. **Entity search — repaired.** Entity results use the owner API and query bound, preserve document filter semantics, and localize entity type presentation. API page size is passed through for graph continuation.
9. **Owner UI, localization, and navigation — repaired.** Entity creation and review/correction forms use RHF/Zod and shadcn controls. Entity types, graph controls, loading and validation labels are available in both locales. Dirty entity drafts register with guarded navigation; leaving a dirty page asks before discarding, accepted leave clears form/selection state, and an entity detail reached through SPA navigation is promoted to a full document before editable UI mounts. Sources navigation/document behavior remains supported.

## Impact evidence and limits

Pre-edit GitNexus impact calls for `EntityDetail`, `EntityList`, `EntityReviewCard`, `EntityGraph`, and `navigate` did not resolve the target. `SearchPage` and `GuardedNavigationProvider` resolved with zero callers, but both results were `UNKNOWN`, partial/lower-bound; the index reported four commits behind HEAD for `SearchPage`. No HIGH or CRITICAL result was returned. These are not safe-zero conclusions. The edited routes, imported components, API calls, and provider consumers were traced in current source to supplement the incomplete graph evidence.

## Verification boundary

No build, test, lint, standalone typecheck, service, migration, provider probe, browser acceptance, commit, or merge was run in this source-repair turn. The production source is ready for the controller's frozen snapshot and prescribed serialized build slot. Independent source review and build evidence remain outstanding.
