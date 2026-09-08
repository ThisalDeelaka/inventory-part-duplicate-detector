# GF-12C1-R4 GF5 dense real-work-unit correction

## Decision

GF-12C1-R4 is **VERIFIED**. The real 5,327-record target now completes the
provider-none group-first path through authoritative GF6 with
`visible_product_ready=true`.

The correction is `GF5-FIX-D`: enforce the already-authorized exhaustive
candidate-generation budget before performing candidate construction that the
resolver necessarily discards. The bound, strict boundary behavior, metrics,
defer reason, resolver ordering, candidate semantics, evidence thresholds,
cannot-link authority, group-size limits, and downstream outcomes are
unchanged.

## Protected inputs and execution boundary

- Real CSV SHA-256 before and after:
  `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- User-owned XLSX: 1,506,370 bytes; SHA-256 before and after:
  `b32b5428169dca504c00fdf6df24efd90887044c666a71c991e10ec1c31b29c6`.
- The XLSX contents were not inspected. Neither protected input was modified.
- All real runs used disposable SQLite, explicit group-first policy v2,
  same-site mode, and provider `none`.
- Provider calls were zero. No `.env`, key, token, credential, authorization
  header, provider adapter, Docker path, or raw business description was used.

## Frozen GF5 semantic contract

For resolver v1, one candidate identity group is a canonical subset of a
bounded work unit satisfying all of the following:

1. Membership is 2 through `complete_pairwise_member_limit` records; the
   unchanged default limit is 8 inside a work unit capped at 20 records.
2. Every internal pair has evaluated evidence.
3. No internal pair is machine or human `CANNOT_LINK`.
4. At least one internal pair is `STRONG_SUPPORT` or `REVIEW_SUPPORT`.
5. A likely group requires every internal pair to be `STRONG_SUPPORT` and all
   bridge, truncation, missing-evidence, and genericity safety checks to pass.
6. A review group requires positive cohesion, cannot be a generic-only
   multi-record chain, cannot be a support chain with neutral gaps, and cannot
   retain unresolved bridge or missing-evidence risk.
7. Complete candidate subsets are considered in descending size and canonical
   member order only while the existing deterministic generation budget permits.
8. Candidate hypotheses retain canonical membership, exact categorical evidence
   counts, evidence summaries, fingerprints, and hypothesis-ID ordering.
9. Disjoint partition selection is lexicographic by covered members, likely
   members, retained strong evidence, fewer review edges, fewer groups, then
   canonical fingerprints. Materially equal ownership is deferred.
10. Candidate-generation or partition-search exhaustion produces
    `INSUFFICIENT_PARTITION_STABILITY`; it never authorizes partial acceptance.

The candidate-generation budget remains:

```text
max_resolution_members^2 * (max_targeted_checks_per_work_unit + 1)
= 20^2 * 41
= 16,400
```

The historical implementation visits one additional state to prove exhaustion,
so the preserved metric is 16,401.

## Exact blocker profile

The actual isolated 18-record/130-edge work unit has 106,743 canonical subsets
of sizes 2 through 8. The historical reference path was profiled below the
candidate-generator boundary:

| Operation | Calls | Self seconds | Cumulative seconds |
|---|---:|---:|---:|
| candidate group construction | 16,400 | 6.070 | 140.079 |
| group validation | 6,256 | 0.444 | 119.129 |
| canonical fingerprint payload | 12,512 | 0.060 | 8.072 |
| group fingerprint construction | 6,256 | 0.084 | 7.448 |
| bridge summary | 6,256 | 0.167 | 0.672 |

Reference result: 140.613600 seconds, 16,401 states visited, zero candidates
retained by the caller, and `generation_exhausted=true`.

The dominant inner operation was repeated construction followed by full group
validation and canonical fingerprint work for partial candidates that cannot
affect the resolver result once the unchanged generation limit is exceeded.
There was no SQL in this loop.

## Exact production correction

Before enumeration, GF5 now computes the exact count
`sum(comb(member_count, size), size=2..complete_pairwise_member_limit)`.
When that count is greater than the unchanged generation budget, it advances
the existing metric by `budget + 1` and returns the same exhausted signal with
no candidates. The caller follows the unchanged path and emits the same typed
deferred work unit.

When the exact subset count is below or equal to the budget, the historical
generator executes unchanged. It remains in production source as the bounded
reference oracle. This is an exact fast-forward, not heuristic pruning: on an
exhausted path the caller always discards every materialized candidate before
partition selection.

## Equivalence proof

- Below-cap and at-cap fixtures execute the historical generator directly.
- Sparse, dense-10, bounded dense-14, many-cannot-link, few-cannot-link,
  below-cap, and at-cap outputs matched the reference exactly for candidate
  dataclasses, membership, evidence summaries, scores, fingerprints, ordering,
  exhaustion, and explored-state counters.
- Above-cap reference execution and the corrected path both report exhaustion
  at `limit + 1`; the only omitted objects are partial candidates the resolver
  contractually discards.
- Full resolver tests preserve accepted/review/conflict/deferred outcomes,
  targeted evidence, cannot-link decisions, unassigned membership, metrics,
  and final resolution fingerprints.
- Three corrected executions of the actual isolated 18-record unit had
  identical empty candidate sequences, `exhausted=true`, and 16,401 visited
  states.

## Forbidden-shortcut audit

| Guard | Result |
|---|---|
| lower or reinterpret the 16,400 bound | PASS; unchanged |
| reduce max work-unit or group size | PASS; 20 and 8 unchanged |
| change evidence thresholds/classes | PASS; unchanged |
| weaken machine/human cannot-link | PASS; unchanged |
| skip any legal within-budget candidate | PASS; reference path unchanged |
| choose first-found instead of canonical best | PASS; selector unchanged |
| add race/nondeterministic ordering | PASS; no concurrency added |
| change outcome classification for speed | PASS; existing exhausted path only |
| change targeted-check budget | PASS; 40 per work unit unchanged |
| increase any safety cap | PASS; none changed |

## Structural fixture results

| Fixture | Shape | Reference seconds | Corrected seconds | Result |
|---|---|---:|---:|---|
| D1 | sparse 6 | 0.001049 | 0.000817 | exact equality |
| D2 | dense 10 | 0.341067 | 0.321085 | 1,002 candidates; exact equality |
| D3 | dense 14, bounded size-3 oracle | 0.121710 | 0.168279 | 455 candidates; exact equality |
| D4 | dense 18 near-cap | 140.613600 real reference | median 0.000011600 | same exhausted defer signal |
| D5 | dense 10, many cannot-links | 0.155719 | 0.150555 | absolute prohibition retained |
| D6 | dense 9, one cannot-link | 0.107306 | 0.123666 | 374 candidates; exact equality |
| D7 | equal-score ownership tie | bounded | bounded | identical ambiguity defer |
| D8 | 12 records below boundary | 0.533819 | 0.579466 | 1,573 candidates; exact equality |
| D9 | 13 records exactly at boundary | 0.771991 | 0.884143 | 2,366 candidates; exact equality |
| D10 | 14 records above boundary | 0.933080 | 0.002329 | same exhaustion/counter; discarded partial materialization omitted |

Times are local engineering observations, not product SLOs.

## Isolated actual-unit acceptance

Corrected actual 18-record call durations were 0.000011600,
0.000015300, and 0.000002400 seconds; median 0.000011600 seconds.
The measured reference-to-median speedup is approximately 12.1 million times.
Relative to the frozen prior `>129 s` lower bound, the demonstrated minimum
speedup is greater than 11.1 million times. The `>=5x` and `<=25 s` gates pass.

## Whole real GF5 and end-to-end acceptance

The final unprofiled disposable run completed in 146.090129 seconds:

| Stage/work | Result |
|---|---:|
| canonical catalog orchestration | 0.987028 s |
| discovery orchestration | 21.023408 s |
| GF2 proposals | 20,457 |
| GF3 neighborhoods / memberships | 1,064 / 10,474 |
| signed evidence orchestration | 7.916387 s |
| GF4 edges | 20,457 |
| GF5 orchestration | 111.230318 s |
| GF5 persisted resolution | 104.130252 s |
| GF5 work units | 244 |
| GF5 candidate generation | 80.889372 s |
| GF5 partition selection | 0.036709 s |
| GF5 persistence | 0.559464 s |
| GF5 final validation | 4.103298 s |
| targeted requests/results | 125 / 125 |
| GF6 orchestration | 4.667641 s |
| GF6 persisted projection | 0.649005 s |
| total wall time | 146.090129 s |

GF5 started all 244 work units; 237 reached partition selection. Six units
deferred immediately under the existing 20-member cap and the 18-record unit
used the unchanged generation-exhaustion defer path. Other deferred outcomes
remain governed by existing resolver semantics.

Authoritative outcomes:

```text
scan status: COMPLETED
orchestration status: COMPLETED
visible_product_ready: true
GF5/GF6 groups: 214
likely: 0
review: 214
conflicts: 12
deferred: 22
unassigned: 4,879
provider calls: 0
```

This run establishes execution and authority readiness, not human accuracy.

## GF5-R1 through GF5-R28

| Gates | Result |
|---|---|
| GF5-R1 through R3 shape/profile/contract | PASS |
| GF5-R4 through R6 reference semantics | PASS |
| GF5-R7 dense-18 completion | PASS |
| GF5-R8 through R14 semantic guards | PASS |
| GF5-R15 through R17 boundary behavior | PASS |
| GF5-R18/R19 unchanged caps/sizes | PASS |
| GF5-R20 isolated performance | PASS |
| GF5-R21 determinism | PASS |
| GF5-R22 whole real GF5 <=300 s | PASS |
| GF5-R23 provider zero | PASS |
| GF5-R24/R25 protected inputs unchanged | PASS |
| GF5-R26 no schema/migration/dependency/frontend | PASS |
| GF5-R27 adjacent-stage semantics unchanged | PASS |
| GF5-R28 no secret or `.env` access | PASS |

Focused GF5/GF6/orchestration verification: 147 passed. Full backend:
1,427 passed, 15 skipped, with one pre-existing pytest configuration warning.

## 100k and governance boundary

No global all-pairs stage, unbounded enumeration, safety-cap relaxation, or
GF11 target change was introduced. GF-11 remains **IN PROGRESS**, its waiver
remains **ACTIVE**, `GF11-PERF-100K-COLD-FULL` remains **OPEN**, and the
300-second 100k target remains **NOT MET**.

GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`; no human-reviewed quality,
production deployment, or final production-graduation claim is made.
