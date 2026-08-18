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
