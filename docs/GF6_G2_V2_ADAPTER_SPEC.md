# GF-6 G2-v2 adapter specification

## Scope and version boundary

GF-6 remains one phase in the frozen GF-0 through GF-12 roadmap:

- GF-6A defines the pure G2-v2 manifest, mapping, validation, and fingerprint
  contracts.
- GF-6B may later add immutable non-current persistence and compatibility
  isolation.

GF-6A performs no database I/O and changes no visible behavior. G2-v1 remains
the selected historical/current projection format and permanently retains its
complete N-choose-2 internal-evidence semantics. A v1 row is never interpreted
as v2.

G2-v2 is resolver-derived. Its source is one completed GF-5C resolution run,
and every accepted group explicitly declares `COMPLETE_PAIRWISE` or
`PROGRESSIVE_TARGETED` validation.

## Pure manifest

`build_g2_v2_manifest(...)` consumes:

- a completed typed GF-5C `IdentityResolutionResult`;
- immutable GF-1 canonical records;
- GF-4 proposal-derived deterministic evidence;
- GF-5C targeted deterministic evidence;
- typed discovery/evidence/resolution provenance; and
- a versioned adapter configuration.

It returns an immutable `G2V2SnapshotManifest`. The function has no session,
repository, ORM, provider, pair-business-result, G1, or G2-v1 dependency.

The manifest retains source run references, contract and adapter versions,
accepted groups, conflicts, deferred work, exact unassigned identities,
reconciled counts, and a deterministic fingerprint. It is a system-hypothesis
manifest, not a human-reviewed identity set.

## Group and evidence mapping

Each accepted GF-5 hypothesis maps exactly once without status or membership
change. Members remain distinct by GF-1 record identity even when their source
values are identical.

Internal machine evidence has one effective item per canonical group pair and
records:

- canonical IDs and stable GF-1 references;
- signed edge class;
- `PROPOSAL_EVIDENCE` or `TARGETED_RESOLUTION_EVIDENCE` origin;
- source and supplemental provenance references;
- bounded reasons/summary and evaluator version;
- deterministic evidence fingerprint; and
- whether it is required for validation.

If proposal and targeted evidence overlap, they must have the same class,
evaluator version, and evidence fingerprint. Proposal evidence is the primary
item under the v1 adapter configuration and targeted request provenance is
retained supplementally. Incompatible overlap fails mapping.

## Validation coverage

Every group records member and possible-pair counts, evaluated and required
evidence counts, signed-class counts, missing-nonrequired pairs, and proposal
versus targeted counts. No numeric group confidence is introduced.

`COMPLETE_PAIRWISE` requires exactly N-choose-2 unique deterministic evidence
items and zero missing pairs. GF-5-v1 likely groups additionally remain
complete all-strong groups.

`PROGRESSIVE_TARGETED` explicitly has evaluated evidence below the possible
pair count and a positive missing-nonrequired count. Materialized evidence is
never synthesized for unevaluated pairs. All resolver-targeted checks within
accepted membership must have their exact completed result represented.

GF-5B-v1 currently emits no progressive likely group. GF-6A includes a pure
progressive review contract and fixture so a later resolver version cannot
silently reuse v1 completeness semantics.

## Other outcomes and provenance

GF-5 conflicts map to conflict snapshots, never accepted groups. Deferred work
maps to deferred snapshots and is never collapsed into conflict. Unassigned
records preserve exact GF-1 identities and mean only that no safe accepted
assignment was made; singleton groups are not synthesized.

The audit chain is:

```text
scan -> GF-1 record -> GF-2/GF-3 discovery -> GF-4 evidence
     -> GF-5C resolution/targeted evidence -> GF-6 v2 manifest
```

Group, conflict, deferred, and manifest fingerprints use stable record/source
fingerprints, effective evidence, coverage, and adapter versions. They exclude
timestamps, randomness, secrets, provider material, and avoidable database IDs.

## GF-6A safety boundary

Pure validation rejects cross-scan or source-run drift, duplicate/overlapping
membership, singleton groups, cannot-link acceptance, false complete coverage,
missing required targeted results, duplicate or out-of-group evidence,
proposal/targeted disagreement, source-status changes, count drift, and
fingerprint drift.

GF-6A adds no schema, migration, scan orchestration, persistence, current-result
selection, API, UI, export, review, advisory, pair-deprecation, or provider work.
