# P04-T3 correction owner rulings

Accepted entry: P04-T2 commit `4f5ee2e19a01422cc935076d28c853d163ee64b3`, following integrated T1/RN1 `56b4e0d`. Production patch SHA256 `CC9BE22C6590502E4CBF01891682A21CF6645933A933DF6B7A83DB233CBDCF49` matches the reviewed freeze. The original task/spec remains authoritative.

## Relationship supports

Extend existing citation support uniqueness to the exact source/target evidence membership pair. Preserve distinct pairs with the same version/chunk; no second binding table is needed. Define legacy NULL semantics in the forward migration and owner queries. Unknown endpoint bindings require a controlled split conflict. Update actual manual/extraction writers, reassignment, cleanup and DTO readers together. Count distinct version/chunk citations for corroboration; confidence remains SQL MAX over valid support. No historical migration rewrites.

## Persistent decisions and selectors

Persist consumed owner assignment/suppression decisions and canonical redirects. New extracted memberships receive a deterministic nonplaintext fingerprint from actual normalized candidate type/value with explicit source/document/evidence dependencies. Response-local keys and current mutable entity names are not historical selectors. Missing legacy fingerprints remain unknown, without fabricated backfill.

Default selection is the explicitly chosen immutable evidence. Applying a rule to future document revisions requires explicit owner confirmation of document scope and a usable fingerprint or bounded owner-provided selector. Do not silently broaden it to other sources/documents or promote names to verified identity. Conflicting rules, same-selector candidate ambiguity and changed post-lock decisions return review/conflict. Store hashes/IDs without copying source text; dependent rules are removed with document/source forgetting. Independent owner identity and redirect IDs may survive without cached source text.

Consume decisions/redirects before sorted entity locking and during authoritative post-lock refresh, plus relevant publication. Changed targets never acquire late entity locks. External identity is unavailable without actual verified namespaced owner/source facts; document/provider IDs are not entity identity.

## Correction transaction

Discover a bounded complete closure before mutation: memberships, aliases/field supports, relationship supports/equality candidates, neighbors and document/source dependencies. Fit initial atomic limits to the existing owner caps (100 entity/evidence refs, 200 membership refs); oversized operations return conflict, never partial correction. Lock globally sorted source/document dependencies through the document owner, then the complete sorted entities, then relationships/supports. Revalidate revisions, retained evidence and closure completeness. Paused/archived historical evidence follows owner library policy, not remote extraction gates.

Merge preserves membership UUIDs, target owner-selected identity and redirectable old IDs. Unresolved protected-value/alias conflicts and self edges return explicit conflict. Split moves only selected UUIDs and their actual support bindings. Use noncommitting relationship-owner commands, authenticated `AuthSession.owner_id`, bounded reason/server UTC and one final `commit_with_replay`. Evidence/preview/conflict DTOs serve T4; no new service or generic policy engine.

Add a forward migration after `0008_entity_extraction`; register actual models. Code/build and independent review precede commit. Tests/runtime/migration execution/provider/capacity acceptance remain deferred.
