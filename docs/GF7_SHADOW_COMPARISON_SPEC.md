# GF-7 controlled shadow-comparison specification

## Scope and authority

GF-7 remains one phase in the frozen GF-0 through GF-12 roadmap:

- GF-7A defines pure, immutable v1-to-v2 comparison contracts, agreement
  metrics, structural cases, safety deltas, priorities, and golden cases.
- GF-7B persists and integrates explicitly controlled non-visible comparison
  runs while G2-v1 remains current.

GF-7A compares two system hypotheses. Neither G2-v1 nor G2-v2 is ground truth,
and no unadjudicated comparison metric is a correctness, quality, or promotion
decision. The pure comparison makes no database, repository,
scan-runner, current-selection, API, UI, export, review, advisory, or provider
call.

## Inputs and identity

`compare_g2_v1_v2(ShadowComparisonInput)` consumes a neutral completed v1
snapshot DTO, one completed contract-v2 manifest, the complete immutable GF-1
record catalog, run provenance, and versioned comparison configuration.
Accepted groups normalize to `ComparisonIdentitySet` with source version,
categorical accepted status, stable group/source fingerprint, and canonical
GF-1 member identities.

Matching uses the set of stable GF-1 record identities. Database group IDs,
group ordering, member ordering, part numbers, descriptions, and other business
values cannot establish an exact match. Conflicts, deferred work, and
unassigned records remain separate from accepted groups.

## Agreement metrics

Exact agreement means identical accepted member sets. An exact member set with
a different accepted status is a status change, not an exact status agreement.

Positive co-membership metrics enumerate only N-choose-2 pairs inside accepted
groups:

- v1 and v2 positive-pair counts;
- intersection and version-only positive-pair counts;
- positive-pair Jaccard;
- the proportion of v1 positive membership retained in v2;
- the proportion of v2 positive membership also present in v1.

Empty-versus-empty positive sets have Jaccard `1.0`. These are agreement
ratios, not adjudicated correctness or error-rate measures. The global
inventory negative-pair universe is never enumerated.

Record assignment metrics separately count total records, records grouped by
each or both versions, records grouped by only one version, and records
unassigned by both accepted-group sets. V2 conflict/deferred involvement
remains explicit in cases and summary counts.

## Overlap graph and structural taxonomy

The comparison builds a membership-indexed bipartite graph. A v1 and v2 group
share an edge only when their member intersection is nonempty. Every graph edge
records intersection, union, Jaccard, and containment ratios. Connected
components scope comparison cases only and never infer identity.

Every accepted group belongs to exactly one primary case:

- `EXACT_MATCH`;
- `STATUS_CHANGE`;
- `V1_GROUP_SPLIT_IN_V2`;
- `V2_GROUP_MERGE_OF_V1`;
- `PARTIAL_REASSIGNMENT`;
- `V1_ONLY_GROUP`;
- `V2_ONLY_GROUP`;
- `COMPLEX_OVERLAP`.

A one-to-many component is a split and a many-to-one component is a merge.
One-to-one non-identical overlap is partial reassignment, except a strict
subset with all residual v1 members explicitly unassigned/conflicted/deferred
in v2 remains one split case. Many-to-many is partial reassignment only when
both sides have equal group counts, identical record union, and every group
overlaps at least two groups on the other side; otherwise it is complex.
Zero-degree groups are version-only cases and are never double-counted from a
larger component.

## Safety deltas and evidence provenance

Typed safety/explanation deltas cover:

- v1 accepted co-membership intersecting directly referenced protected v2
  conflict evidence;
- a v1 split backed by directly referenced v2 cannot-link evidence;
- v2 accepted positive pairs absent from v1;
- v2 targeted evidence unavailable to v1;
- v2 deferred or conflict outcomes involving a v1 accepted hypothesis;
- v1 accepted records left v2-unassigned.

A split alone is never a protected-conflict delta. Protected wording requires
an authoritative protected conflict category, direct protected-evidence
references, and an affected v1 accepted pair. Targeted resolution evidence is
an explanatory input difference and is never presumed superior.

## Adjudication priority

Priority is categorical and deterministic, not correctness:

- `CRITICAL`: protected cannot-link or authority conflict affects accepted
  co-membership;
- `HIGH`: likely membership is split, merged, reassigned, conflicted, or
  deferred;
- `MEDIUM`: review-level structural differences, exact-member status changes,
  or review hypotheses accepted by only one version;
- `LOW`: explanatory evidence or positive-membership differences without a
  stronger structural rule;
- `NONE`: exact membership and status agreement without a material delta.

Each immutable case retains its groups, involved record identities, overlap
metrics, status transitions, related conflict/deferred/unassigned context,
safety deltas, priority reasons, and semantic fingerprint. It contains no
correctness verdict.

## Determinism and boundedness

SHA-256 fingerprints use canonical stable members, categorical statuses,
source fingerprints, overlap/case semantics, deltas, algorithm version, and
configuration identity. They exclude timestamps, providers, secrets,
randomness, input order, run IDs, and avoidable group/database IDs.

Pair work is proportional to positive pairs inside accepted groups. Overlap
construction uses record-to-group membership indexes rather than comparing
every group pair or every inventory-record pair. GF-7A makes no 100k-readiness
claim; GF-7B/GF-11 own persisted execution and measured scale work.

## GF-7B controlled persistence

`GROUP_FIRST_SHADOW_COMPARISON_ENABLED` is the only automatic normal-scan
enablement gate and defaults to `false`. A disabled scan creates no comparison
run. When enabled, an eligible scan runs in this exact order:

```text
GF-1 -> GF-2/GF-3 -> GF-4 -> GF-5C -> GF-6B non-current G2-v2
     -> legacy pair persistence -> G1 -> current G2-v1 -> GF-7B
     -> visible scan completion
```

GF-7B reuses the existing current-v1 selector after G2-v1 persistence. It
requires an explicit completed same-scan v1 run, a completed same-scan v2 run,
and that v2 run's completed GF-5C resolution provenance. Ineligible automatic
work is skipped without fabricating a comparison. The direct internal service
accepts explicit eligible run identities for controlled tests or operations.

One immutable `shadow_comparison_run` owns normalized case, case-group,
case-record, safety-delta, and case-to-delta rows. The run stores exact v1/v2
and source-resolution provenance, algorithm/configuration/input/result
fingerprints, lifecycle timestamps, the complete GF-7A summary, a critical
safety-delta count, and a bounded safe failure category. Cases preserve exact
source group references, source statuses/fingerprints, memberships, overlap
and status-transition metrics, conflict/deferred/unassigned context,
adjudication priority/reasons, and semantic fingerprints. Safety deltas retain
canonical involved records, direct evidence references/fingerprints, related
group/outcome references, explanation, priority, and fingerprint. These are
comparison evidence and adjudication priorities, never winner, correctness,
accuracy, or promotion fields.

The semantic input fingerprint includes GF-1 stable record references/source
fingerprints, v1 accepted memberships/statuses/source fingerprint, the v2
manifest and conflict/deferred/unassigned semantics, and the comparison
algorithm/configuration. It excludes timestamps, randomness, secrets,
providers, and avoidable database identities. Identical eligible input reuses
the same completed run and child graph. Changed semantic input or configuration
creates a distinct run; completed and failed history is never overwritten.

RUNNING metadata commits before pure comparison execution. Case/delta children
and summary persist in one transaction, reload through a fixed set of bulk
queries, reconstruct the exact typed `ShadowComparisonResult`, and must equal
the pure GF-7A output before COMPLETED commits. A failure rolls back every
child, records FAILED safely, and leaves v1, v2, and visible scan results
unchanged. Terminal runs and all children reject update/delete through normal
ORM paths.

The comparison tables have no current/promotion flag and no public route.
`snapshot_available`, G3 list/detail, G5 exports, G6 review targets, G7
advisory eligibility, and current/latest selection continue to query v1-only
tables. Historical scans are not backfilled and reads create no comparison.
Provider calls remain zero.

## GF-7 boundary

GF-7A remains pure. GF-7B adds only controlled internal persistence and the
post-v1 normal-scan hook described above. G2-v1 remains the only current and
visible product result. GF-7 adds no promotion, public route, frontend, export,
review, advisory, pair deprecation, provider behavior, or secret access. GF-8
owns any future group-first orchestration or current-result promotion.
