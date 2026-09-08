# IQR-1C Bicycle Resolver-Disposition Audit

## Classification and baseline

`IQR1C_GENERIC_FAMILY_SAFETY_DEFERRAL`

- Branch: `llm-assisted-mvp`.
- Starting HEAD: `7e6ada5c051415af668868d275c88ab80a36c722`.
- Protected tag `deterministic-demo-v1` remained at
  `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Initial status contained only the authorized unrelated
  `?? List_20260709_093045.xlsx`; it was not inspected, changed, staged, hashed,
  or otherwise touched.
- Provider requests were 0. No environment file or secret was accessed. Docker,
  backend, and frontend were not started.

This task changed no runtime behavior. It audited the current pure GF5 resolver
and added characterization tests for its existing decisions.

## Authoritative Bicycle input

The 118 persisted Scan-33 canonical records were read from SQLite in read-only
mode and rerun in a temporary database with the persisted bounded retrieval
configuration. The protected XLSX was not used. Runtime was 3.449 seconds; this
is bounded diagnostic evidence, not production-scale performance evidence.

The seven Bicycle records are record IDs `73, 85, 101, 102, 110, 111, 113`,
with references `AB-BICYCLE`, `SD-BICYCLE`, `JS-BICYCLE`, `TD BICYCLE`,
`HM-BICYCLE`, `SJ-BICYCLE`, and `UH-BICYCLE`. They span seven sites (`AB-SA`,
`SD-SA`, `JS-SA`, `TD-SA`, `HM-SA`, `SJ-SA`, `UH-SA`) and all use `PCS`.
Their 21 possible relationships are all present, cross-site,
`REVIEW_SUPPORT`, and marked generic-only. They have no site rejection,
technical contradiction, protected cannot-link, neutral/non-groupable edge, or
missing relationship.

The persisted phrase "seven-record work unit" is an imprecision. Overlapping
neighborhoods place the seven-record complete Bicycle subset in one ten-record
GF5 work unit with `DEMO-INTERSITE`, `AB-LIGHT`, and `AB-TAIL LIGHT`. This does
not cause the Bicycle disposition: the isolated exact seven-record evidence
shape produces the same generic-family rejection and deferral.

## Exact GF5 decision trace

### Seven-record Bicycle subset

| Decision variable | Verified value |
|---|---|
| Members | 7 |
| Validation mode for any candidate group | `COMPLETE_PAIRWISE` |
| Required / completed pairs | 21 / 21 |
| Positive / strong / review support | 21 / 0 / 21 |
| Neutral / non-groupable / cannot-link | 0 / 0 / 0 |
| Missing or unresolved pairs | 0 |
| Support / strong / review density | 1.0 / 0.0 / 1.0 |
| Articulation / single-edge branch flags | 0 / 0 |
| Generic hubs | all 7 records |
| Generic evidence edges / members | 21 / 7 |
| Independent identity evidence | insufficient: every positive edge is generic-only |
| Technical contradictions | 0 |
| Attribute-conflict index | no separate resolver index is materialized; the typed protected-conflict count is 0 |
| Site spread / UOM | 7 sites / all `PCS` |
| Missing-data burden | 0 missing pairs; no separate field-level missing-data score is used by GF5 |
| Truncation / degradation | false / true; degradation is carried as provenance and is not the rejecting branch |
| Oversized | false (`7 <= 20`) |
| Targeted checks | none needed for the already-complete isolated subset |
| Candidate generation / partition search | not exhausted / not exhausted |
| Valid full-family candidate | no |
| Candidate partitions explored | 1,730 in the isolated generic-shape characterization |
| Equal best partitions | 105 three-pair matchings, each covering 6 members |
| Partition stability | none; no pair is common to all best partitions |
| Final reason | `UNRESOLVED_OWNERSHIP_AMBIGUITY` |
| Final summary | equally supported disjoint partitions leave ownership unresolved |

The 105 count follows directly from seven choices of unmatched record and 15
perfect matchings of the remaining six records. It is an explanatory count;
GF5 persists ambiguity, not the full alternative-partition collection.

### Actual ten-record work unit

The actual work unit has 10 members, 10 source neighborhoods, and 45 possible
pairs. Twenty `PARTITION_CROSS_CHECK` requests were planned and completed,
within the configured per-work-unit budget of 40. The resulting lookup was
complete: 21 Review, 23 non-groupable, one protected cannot-link (Head/Tail),
and zero missing pairs. Candidate generation and partition search were not
exhausted. The scan-wide resolver reported 9 work units, 20 targeted requests
and results, 2,789 candidate partitions explored, no accepted candidate for
this work unit, and ambiguity. The persisted artifact was:

- deferred ID:
  `gf5b-deferred-reference-fe9512aac31e68a06fe46d4943d0ca4f01a54c4b1d2ce27610737e0cb4880fff`;
- fingerprint:
  `db7254ed9418762c327002998e94c40c4d94745959ce2673c04b37f1c566dbd4`;
- reason: `UNRESOLVED_OWNERSHIP_AMBIGUITY`;
- summary: equally supported disjoint partitions leave ownership unresolved.

GF5 has no separate persistent work-unit ID. The deferred ID/fingerprint and
sorted member/neighborhood references are its deterministic work-unit identity.
Reason precedence was verified in code: member cap, discovery truncation,
targeted budget/completion, candidate-generation exhaustion, partition-search
exhaustion, then ownership ambiguity. None of the earlier branches fired.

## First causal resolver rule

The first branch preventing the seven records from becoming one Review group
is in `backend/app/resolution/validation.py`, `validate_group_hypothesis`:

```text
len(members) >= 3
and strong_support_count == 0
and review_support_count > 0
and generic_evidence_edge_count == review_support_count
```

With inputs `7`, `0`, `21`, and `21`, respectively, validation rejects the
candidate with `multi-record generic-only review connectivity is not group
cohesion`. `_build_group` in `backend/app/resolution/resolver.py` catches that
validation error and returns no full-family candidate. This happens after all
pair evidence is complete, inside GF5 candidate classification, and before
partition selection. The same shape sets all members as generic hubs and
`insufficient_independent_identity_evidence=true`.

The rule originated in commit `d31a5bb9` (`Define constrained resolver safety
contracts`) and is stated in `docs/GF5_RESOLVER_SAFETY_SPEC.md`. It implements
the SSOT rule that generic description alone is not enough to establish
identity. The final deferred reason is the later consequence of many equally
ranked generic two-record hypotheses; it is not the first causal rule.

## Current group contract comparison

- `LIKELY_DUPLICATE_GROUP` requires complete strong cohesion, zero cannot-links,
  complete safety checks, no unresolved ownership/bridge risk, no material
  truncation, and no generic-only cohesion.
- `POSSIBLE_DUPLICATE_GROUP_REVIEW` requires plausible positive identity
  evidence, zero cannot-links, completed minimum safety checks, and sufficient
  cohesion. Review edges propose membership but do not prove it. A generic-only
  group of three or more lacks independent identity cohesion; a safe generic
  pair may remain Review.
- `CONFLICT` preserves protected cannot-links and contradictory authority.
- `DEFERRED` preserves unresolved membership, validation, bounds, truncation,
  evidence, or partition ambiguity without inventing a group.

Therefore, 21/21 Review edges and complete validation are not by themselves
constitutionally sufficient for this seven-member group because every edge is
derived from the same low-information generic description. The additional
evidence needed is trusted, non-generic independent identity evidence (or
bounded human labels establishing the intended relationship), while preserving
complete cannot-link safety. Client-known truth is a diagnostic control, not
machine evidence and not permission to generalize identical descriptions.

## Strong-support requirement audit

There is no explicit or implicit rule that every Review group must contain one
Strong edge. A two-member generic Review edge is accepted, and a complete
seven-member non-generic Review clique is valid at `_build_group` before the
current partition objective. Adding one Strong edge to the non-generic
seven-member matrix does not resolve its bounded exhaustive partition search,
but that is a search/selection outcome, not a Review-classification prerequisite.

## Validation and generic-family audit

The configured limits are 20 resolution members, 40 targeted checks per work
unit, and 8 members for complete-pairwise candidates. Seven is within both
member bounds. All 21 Bicycle pairs are accounted for and no targeted check is
incomplete. The generic guard comes from GF4's persisted
`generic_guard_reason=GENERIC_DESCRIPTION`; GF5 consumes that as `generic_only`.
It rejects the complete generic candidate after evidence evaluation. No
validation-state defect, missing coverage, or exhausted budget caused the
disposition.

## Synthetic characterization matrix

| Case | Evidence | Current result |
|---|---|---|
| A | 7, complete non-generic Review | no group; `INSUFFICIENT_PARTITION_STABILITY`; 16,521 partitions explored |
| B | A plus one Strong | no group; `INSUFFICIENT_PARTITION_STABILITY` |
| C | 20 Review plus one non-groupable/neutral | no group; `INSUFFICIENT_PARTITION_STABILITY` |
| D | 20 Review plus one cannot-link | protected conflict, no group; `INSUFFICIENT_PARTITION_STABILITY` |
| E | 4, complete non-generic Review | no group; `UNRESOLVED_OWNERSHIP_AMBIGUITY`; 104 partitions explored |
| F | 2, one Review | accepted `POSSIBLE_DUPLICATE_GROUP_REVIEW` |
| Bicycle control | 7, complete generic-only Review | full candidate rejected; `UNRESOLVED_OWNERSHIP_AMBIGUITY`; 1,730 explored |

The matrix also exposes a secondary, non-causal policy question: partition
selection currently uses `(covered, likely_members, strong, -review,
-group_count)`, whereas the architecture ADR describes maximizing Review
support after Strong support. Non-generic Cases A and E demonstrate surprising
selection behavior. This does not authorize a correction here and does not
change the Bicycle conclusion: its full-family candidate has already failed the
deliberate generic-only cohesion guard before that objective is applied.

## Historical regression evidence

Focused resolver, GF5 contract/golden-case, targeted-budget, dense-work-unit,
and IQR-1C characterization tests passed: **83 passed** with one existing pytest
configuration warning. This covers the two-member Review case, all-Strong
groups, connected Review controls, transitivity traps, protected cannot-link
co-membership, oversized-family deferral, and Review non-promotion behavior.

The full backend suite passed: **1,737 passed, 15 skipped, 1 xfailed** with one
existing pytest configuration warning in 241.89 seconds. The sole
copied/generic-text quality control remained xfailed as required.

## Decision and next task

Primary diagnosis: `IQR1C_GENERIC_FAMILY_SAFETY_DEFERRAL`.

Secondary consequences are generic-hub risk and equal partition ambiguity. The
ten-record overlap is a data-shape clarification, not a missing-evidence defect.
The non-generic partition objective merits future governance review but is not
the first causal Bicycle rule.

Correction recommendation: `NO_RUNTIME_CHANGE`. Weakening generic-description
trust would contradict the current safety contract and the R17 evidence that
heuristic generalization can damage legitimate positives.

`NEXT = R18_HUMAN_LABEL_EXECUTION`. IQR-1C does not execute it. External demo
readiness remains `BLOCKED_BY_IDENTITY_OUTPUT_QUALITY`; copied/generic-description
trust remains open. Group confidence, LLM advisory, XLSX vNext, deployment, and
GF11 remain out of scope. Provider calls remained 0.
