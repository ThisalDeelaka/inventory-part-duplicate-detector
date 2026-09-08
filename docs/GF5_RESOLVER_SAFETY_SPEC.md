# GF-5 constrained resolver safety specification

## Scope

GF-5 remains one phase in the frozen GF-0 through GF-12 roadmap. It is split
internally to make the new decision core reviewable:

- GF-5A: immutable resolver contracts, validators, and golden safety cases;
- GF-5B: pure constrained resolver algorithm;
- GF-5C: resolver lifecycle/persistence and non-visible scan integration.

GF-5A defines executable boundaries only. It does not resolve production
scans, persist resolution runs or hypotheses, publish G2, change normal scan
orchestration, or involve a provider.

GF-5B implements `resolve_identity_groups(resolution_input,
targeted_evidence_provider)` as a pure library function. It remains
independently testable and has no persistence side effects.

GF-5C persists that exact typed output and invokes it as a non-visible shadow
stage during new scans. It does not publish G2 or change current APIs, UI,
exports, pair decisions, or provider behavior.

## Deterministic resolver v1 algorithm

The resolver canonicalizes record, neighborhood, evidence, constraint, and
member ordering before applying the strict GF-5A validators. It then creates
work units by unioning overlapping neighborhood membership, available GF-4
edge scope, and explicit must-link scope. A work unit is only a bounded search
scope; connectivity never becomes an identity conclusion.

For each work unit the resolver builds separate in-memory machine evidence,
effective cannot-link, compatible must-link, generic-evidence, and discovery
provenance lookups. Machine or human cannot-link remains a hard veto. A direct
human must-link against machine cannot-link emits
`HUMAN_MACHINE_AUTHORITY_CONFLICT`. A transitive must-link closure crossing a
protected cannot-link emits `INCOMPATIBLE_MUST_LINK_CONSTRAINTS`. Original
machine evidence is never mutated.

Strong support and compatible must-links form the preferred positive
backbone. Review support may propose membership but cannot force a merge.
`NON_GROUPABLE` stays neutral. The resolver identifies articulation records,
single-edge branches, missing or neutral cross-branch relationships, and
generic-only hubs before accepting broader membership.

For a bounded work unit, missing internal evidence is scheduled in this
deterministic safety order:

1. `BRIDGE_CROSS_CHECK`;
2. `OWNERSHIP_AMBIGUITY_CHECK`;
3. `LIKELY_GROUP_COMPLETENESS_CHECK`;
4. `PARTITION_CROSS_CHECK`.

Pairs are canonical, deduplicated, cached per invocation, and evaluated no
more than once. The narrow provider protocol accepts one request and returns
one typed result. The built-in adapter calls only the pure GF-4 canonical
evaluator. Missing providers, evaluator exceptions, invalid results, or
unfinished checks cause safe deferral. Exceeding the targeted-check budget
causes `TARGETED_EVIDENCE_BUDGET_EXHAUSTED` without partial acceptance.

Candidate groups are generated only up to
`complete_pairwise_member_limit`. Each candidate must have complete internal
evidence and pass the GF-5A group validator. All-strong complete candidates
may be likely. Other candidates may be review only when they have meaningful
cohesion and no unresolved bridge, generic-hub, neutral-gap, ownership, or
protected-conflict risk. Progressive likely is not emitted in v1.

Candidate generation and disjoint set-partition exploration use a deterministic
cap derived from the configured member and targeted-check bounds. Partition
selection is lexicographic: maximize safely assigned records, then likely
membership, then retained strong evidence, then minimize review dependence and
fragmentation. It never uses an averaged similarity objective. Groups common
to all equally best partitions may be salvaged; differing ownership is
deferred as `UNRESOLVED_OWNERSHIP_AMBIGUITY` instead of being tie-broken
arbitrarily.

Work units exceeding `max_resolution_members`, materially truncated work,
targeted-budget exhaustion, evaluator failure, and exhausted bounded search
produce typed deferred units. Protected conflicts remain visible even when the
same work unit is deferred. Every source record outside accepted membership is
reported as unassigned, including records involved in conflict or deferred
work; this is never a non-duplicate classification.

Execution metrics record work-unit count, candidate/partition states explored,
targeted requests/results, and cache reuse. These are bounded implementation
observations, not a 100k-production-readiness claim.

## Input boundary

`IdentityResolutionInput` contains exactly:

- `scan_id`, `discovery_run_id`, and `evidence_run_id`;
- canonically ordered immutable GF-1 `canonical_records`;
- canonically ordered normalized GF-3 `identity_neighborhoods`;
- canonically ordered normalized GF-4 `machine_evidence_edges`;
- canonically ordered normalized `human_constraints`;
- `resolver_algorithm_version` and validated `resolver_configuration`.

It excludes pair business status, pair LLM results, pair feedback as identity
authority, G1/G2 results, and reviewed identity sets. Neighborhoods remain
overlapping discovery work units, not identity conclusions.

The normalized machine edge keeps scan/run ownership, canonical record-ID
endpoints, `IdentityEdgeClass`, stable reason codes, the GF-4 evidence
fingerprint, and a generic-only indicator. The normalized human constraint
keeps canonical endpoints, `MUST_LINK` or `CANNOT_LINK`, source authority, and
source reference. The adapter from the current G6 effective-constraint read
contract maps immutable record-ref keys to GF-1 record IDs without changing G6
persistence.

Human `CANNOT_LINK` prohibits accepted co-membership. Human `MUST_LINK` is
positive authority but cannot override machine `CANNOT_LINK`; that combination
is represented as `HUMAN_MACHINE_AUTHORITY_CONFLICT` and is never forced into
one accepted group.

## Targeted evidence

`TargetedEvidenceRequest` contains scan ID, canonical record endpoints, one
allowlisted reason, the requesting work-unit reference, and a deterministic
request fingerprint. Reasons are limited to:

- `BRIDGE_CROSS_CHECK`;
- `PARTITION_CROSS_CHECK`;
- `LIKELY_GROUP_COMPLETENESS_CHECK`;
- `OWNERSHIP_AMBIGUITY_CHECK`.

`TargetedEvidenceResult` retains the exact request, GF-4 `IdentityEdgeClass`,
stable reasons/summary, evaluator version, evidence fingerprint, and
generic-only flag. A pure adapter consumes the existing GF-4 canonical
evaluator result without reclassification or persistence.

## Accepted group hypothesis

`IdentityGroupHypothesis` contains:

- deterministic hypothesis ID and fingerprint;
- scan ID, canonical unique member record IDs, and their parallel stable GF-1
  record-ref keys;
- `LIKELY_DUPLICATE_GROUP` or `POSSIBLE_DUPLICATE_GROUP_REVIEW`;
- `COMPLETE_PAIRWISE` or `PROGRESSIVE_TARGETED` validation mode;
- typed group evidence, bridge-risk, genericity-risk, and missing-evidence
  summaries;
- canonical source-neighborhood references.

Accepted membership has at least two records, is disjoint across one result,
and contains no known machine or human cannot-link.

`COMPLETE_PAIRWISE` means every possible internal relationship has evaluated
deterministic evidence. A missing internal relationship makes the claim
invalid. `PROGRESSIVE_TARGETED` means a support backbone and every safety-
required targeted check are complete, although not every internal pair need be
materialized. GF-5A intentionally authorizes no permissive progressive likely
rule; GF-5B must prove equivalent protection before that can be emitted.

For GF-5 v1, a complete-pairwise likely group requires every internal pair to
be `STRONG_SUPPORT`, no conflict, no missing required evidence, no unresolved
bridge or ownership ambiguity, no material truncation, and no generic-only
cohesion claim. Average pair score is never used.

A review group requires plausible positive evidence, zero cannot-links, and
completed minimum safety checks. A support chain with neutral cross-branch
gaps is not sufficient group cohesion. A three-or-more-member generic-only
review chain is also insufficient. A safe two-record generic pair may remain a
review hypothesis but can never become likely from generic evidence alone.

## Evidence and risk summaries

`GroupEvidenceSummary` records member, possible/evaluated pair, signed-class,
generic-evidence, generic-member, protected-conflict, missing-evidence,
required-check, source-neighborhood, bridge-risk, degradation, and truncation
counts/flags. It includes nullable descriptive support densities and a nullable
technical-consensus summary. These are evidence-shape metrics, not numeric
group confidence.

`BridgeRiskSummary` records articulation records, single-edge branches,
neutral or missing cross-branch pairs, generic hubs, competing-partition
evidence, and whether risk remains unresolved. `GenericityRiskSummary` records
generic burden, review-only support, hub dependency, and insufficient
independent evidence. `MissingEvidenceSummary` records missing pairs,
incomplete reasons, membership-affecting discovery truncation, and unresolved
ownership ambiguity.

Thus:

- `A STRONG B`, `B STRONG C`, `A CANNOT_LINK C` can never accept `{A,B,C}`;
- `A SUPPORT B`, `B SUPPORT C`, unknown `A-C` requires a bridge cross-check
  before likely acceptance;
- `A REVIEW B`, `B REVIEW C`, `A-C NON_GROUPABLE` is neither likely nor an
  automatic review group merely because the support graph is connected.

Safe subgroup salvage is permitted only when the subgroup independently
satisfies every acceptance rule, is disjoint, and retains traceability to the
original conflict/work unit. The excluded record is not thereby classified as
globally non-duplicate.

## Conflict, deferred, result, and bounds

`IdentityConflict` contains a deterministic ID/fingerprint, scan and involved
record IDs, conflict type, protected evidence and source-neighborhood
references, and a bounded summary. Conflict types are limited to protected
cannot-link, human/machine authority conflict, incompatible must-links, and
overlapping accepted membership conflict.

`DeferredIdentityWorkUnit` contains a deterministic ID/fingerprint, scan and
record IDs, an allowlisted bound/evidence/ambiguity reason, unfinished evidence
summary, and source-neighborhood references. Bounds, missing evidence,
truncation, and unresolved bridge/ownership work are deferred rather than
misreported as deterministic contradiction.

`IdentityResolutionResult` contains accepted groups, conflicts, deferred work,
unassigned record IDs, targeted requests/results used, exact reconciled
metrics, resolver version, and deterministic fingerprint. Conflict/deferred
records may coexist with a salvaged accepted subgroup. Unassigned means no
safe accepted assignment was made; it never means "not duplicate."

`ResolverConfiguration` validates `max_resolution_members`,
`max_targeted_checks_per_work_unit`, and `complete_pairwise_member_limit`, plus
a version. Values are configurable, fingerprinted operational controls, not
permanent product truth. No global all-pairs behavior is introduced.

## Fingerprints

SHA-256 fingerprints use canonical JSON, contract version, semantic artifact
kind, stable GF-1 record-ref/work-unit references, resolver/evaluator versions,
and configuration identity. Contracts carry database record IDs for same-run
validation together with parallel record-ref keys; required artifact
fingerprints use the record-ref keys and exclude those avoidable database IDs.
Collections are normalized so input permutation does not alter identity.
Fingerprints exclude timestamps, randomness, secrets, provider data, and LLM
content.

## GF-5C persistence and lifecycle

One `IdentityResolutionRun` owns one stable combination of scan, completed
discovery run, completed evidence run, resolver algorithm, configuration, and
canonical input fingerprint. Its lifecycle is `RUNNING`, `COMPLETED`, or
`FAILED`; terminal rows and all child snapshots are immutable.

The input fingerprint includes stable GF-1 record references and source
fingerprints, GF-3 neighborhood fingerprints and membership, GF-4 evidence
fingerprints/classes, normalized effective G6 constraints and provenance, and
resolver algorithm/configuration. It excludes timestamps, avoidable database
IDs, pair business state, provider material, and secrets.

Accepted hypotheses, conflicts, deferred work, explicit unassigned records,
and their ordered members are separate queryable snapshot rows. Targeted
evidence requests and results have dedicated resolver-owned rows and never
alter GF-2 proposals or GF-4 evidence. Effective constraint inputs preserve
stable endpoint references, authority, and source reference.

RUNNING metadata commits before resolution. All child rows and completion
counters commit atomically only after the persisted graph reconstructs the
typed result, passes the GF-5 validators, and equals the pure output. A failure
rolls back partial children and records a bounded safe failure category.

Normal scan ordering is GF-1, GF-2/GF-3, GF-4, internal GF-5C, then legacy pair
writes and G1/G2-v1 projection. GF-5C failure alone does not fail the scan or
suppress legacy visible results. Resolution remains deterministic and
provider-free, with provider request count constrained to zero.

## Golden GF-5B acceptance cases

| Case | Required safety outcome |
|---|---|
| G1 all-strong triangle | Complete-pairwise `{A,B,C}` may be likely. |
| G2 contradiction triangle | `{A,B,C}` forbidden; conflict stays visible; safe subgroup salvage allowed. |
| G3 missing bridge | Request `A-C BRIDGE_CROSS_CHECK`; likely forbidden before its result. |
| G4 neutral cross-branch | No likely or automatic review from connectivity; split or defer safely. |
| G5 generic review chain | Record generic-hub risk; require evidence, split, or defer. |
| G6 generic pair | `{A,B}` may be review, never generic-only likely. |
| G7 human cannot-link | Human constraint blocks accepted co-membership. |
| G8 human must-link versus machine cannot-link | Emit authority conflict; co-membership forbidden. |
| G9 overlapping ownership | Never emit both `{A,B}` and `{B,C}`; choose one safe partition or defer. |
| G10 separate groups | Disjoint `{A,B}` and `{C,D}` may both be accepted without broad-context merge. |
| G11 site/UOM differences | Context differences alone do not force conflict; use the GF-4 edge class. |
| G12 protected technical variant | `CANNOT_LINK` prevents accepted co-membership. |
| G13 truncated discovery | Incomplete discovery cannot become likely; explicitly safe review or defer. |
| G14 no proposal | Record remains unassigned, not classified as non-duplicate. |
| G15 identical source values | Distinct GF-1 record IDs remain distinct members; no business-value collapse. |

The executable table records each case's records, neighborhoods, machine
evidence, optional human constraints, required targeted checks, allowed
outcomes, and forbidden outcomes. Validator fixtures prove the corresponding
construction rules without embedding a fake resolver algorithm.
