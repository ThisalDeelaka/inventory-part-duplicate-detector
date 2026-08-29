# GF-12C1-R3 real-data downstream runtime localization

## Decision

The real 5,327-row scan's downstream runtime blocker is **PROVEN** to be GF5
bounded candidate-group generation for dense, still-eligible work units. It is
not character retrieval, GF2/GF3 persistence, GF4, GF6, SQLite write
amplification, or provider work.

The selected next-task category is:

```text
NEXT_GF5_REAL_DATA_WORK_UNIT_CORRECTION
```

The smallest next engineering target is the GF5 candidate-subset construction
and repeated candidate validation performed for dense work units at or below
the existing 20-member safety cap, especially the observed 18-record/130-edge
unit. That future task must preserve the member cap, the 40-check per-work-unit
budget, cannot-link authority, deterministic ordering, and all GF5 outcomes.

```text
NO PRODUCTION OPTIMIZATION WAS PERFORMED IN THIS TASK.
REAL TARGET END-TO-END PRODUCT REMAINS UNVERIFIED UNLESS GF6 COMPLETES.
```

## Protected inputs and execution boundary

- Real CSV: 3,265,800 bytes, 5,327 records, SHA-256
  `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- User-owned XLSX: 1,506,370 bytes, SHA-256
  `b32b5428169dca504c00fdf6df24efd90887044c666a71c991e10ec1c31b29c6`.
- The XLSX contents were not inspected. Neither protected input was modified.
- Execution used explicit `group_first_primary`, policy v2, same-site mode,
  provider `none`, a disposable SQLite database, and the production
  `ScanRunner` path.
- No `.env`, credential, token, authorization header, or provider path was
  accessed. Provider calls were zero.
- Only aggregate counts, durations, safe statuses, and work-shape metrics were
  emitted. No raw business row, description, or neighborhood membership was
  written to evidence.

The old workspace database contains the earlier pre-R2 character failure only.
No disposable database from the stopped corrected 900-second run remained, so:

```text
PRIOR_RUN_STAGE_EVIDENCE = UNAVAILABLE
```

## Actual critical path

| Stage | Entry condition | Exit condition | Major input | Major output | Resource shape | Commit | Existing timing visibility |
|---|---|---|---:|---:|---|---|---|
| validation/input | mapped browser-equivalent CSV | required fields valid | 5,327 rows | 5,327 usable rows | CPU | no | outside orchestration stage rows |
| canonical catalog | valid scan | immutable GF1 rows durable | 5,327 | 5,327 catalog rows | CPU + DB writes | yes | orchestration + diagnostic timer |
| feature bundles | discovery started | one reusable bundle per record | 5,327 | 5,327 bundles | CPU | no | diagnostic timer |
| standard blocking/scoring | feature bundles ready | deterministic pairs scored | 5,327 | 20,000 standard pair objects | CPU | no | diagnostic timer |
| exact-description channel | hybrid retrieval active | bounded exact proposals added | 5,327 | 392 contributing pairs | CPU | no | aggregate channel count |
| part-family channel | hybrid retrieval active | bounded family proposals added | 5,327 | 227 contributing pairs | CPU | no | aggregate channel count |
| lexical channel | lexical matrix ready | exact indexed top-k materialized | 5,327 | 4,081 contributing pairs | CPU | no | vector/query sub-timers |
| character channel | normalized vectors ready | legitimate 0..K neighbors materialized | 5,327 | 3,334 contributing pairs | CPU | cache writes within retrieval transaction | direct character timer |
| technical/conflict channel | character pairs added | technical proposals and conflicts added | 5,327 | 2,270 contributing pairs | CPU | no | aggregate channel count |
| fusion/materialization | all channels ready | capped retrieval result returned | channel proposals | 458 final hybrid candidates | CPU | no | retrieval residual timer |
| GF2 proposals | standard and hybrid results ready | unique proposals persisted | 20,000 + 458 | 20,457 proposal rows | CPU + DB writes | shared discovery commit | diagnostic total/persistence timers |
| GF3 neighborhoods | GF2 proposals present | bounded direct neighborhoods persisted | 20,457 | 1,064 neighborhoods / 10,474 members | CPU + DB writes | shared discovery commit | diagnostic total/persistence timers |
| GF4 evidence | discovery committed | one signed edge per proposal persisted | 20,457 | 20,457 evidence edges | CPU + DB writes | yes | orchestration + diagnostic timer |
| GF5 resolution | GF4 committed | validated immutable resolution persisted | 244 work units | not completed | CPU algorithmic work | RUNNING row committed; result not committed | diagnostic substage timers/counters |
| GF6 projection | completed GF5 required | reconstructed/validated v2 manifest durable | not reached | not reached | not measured | not reached | not reached |
| final publication | GF6 and orchestration ready | visible product ready | not reached | non-authoritative diagnostic only | not measured | not reached | not reached |

## Real stage timing evidence

Only two bounded runs were used, totaling 480 seconds of configured diagnostic
budget, below the single 900-second maximum. The second run was a narrower GF5
work-shape confirmation, not another blind 900-second rerun.

| Observation | Catalog | DISCOVERY | GF4/SIGNED_EVIDENCE | GF5 observed | Terminal state |
|---|---:|---:|---:|---:|---|
| 300-second localization | 3.707 s | 42.562 s | 12.518 s | >241 s; 219.962 s completed inside candidate generation | timed out; GF5 RUNNING |
| 180-second GF5 confirmation | 1.258 s | 33.084 s | 12.105 s | >133 s; one size-18 candidate-generation call active for >129 s | timed out; GF5 RUNNING |

Both stopped states were non-authoritative: scan and orchestration remained
`RUNNING`, `visible_product_ready` was not true, GF6 did not exist, and no
deprecated pair/G1/G2-v1/shadow row was written.

## Discovery decomposition

The 180-second confirmation captured the following nested/aggregate timing.
Nested rows are not added to their containing total.

| Discovery work | Seconds | Work count |
|---|---:|---:|
| feature preparation | 0.446 | 5,327 bundles |
| standard blocking/scoring | 13.597 | 20,000 pairs |
| hybrid retrieval total | 9.926 | 458 final candidates |
| lexical vectorization (nested) | 0.092 | 10,423 features |
| lexical indexed query/rerank (nested) | 0.823 | 6,726,866 exact score evaluations |
| character retrieval (nested) | 6.620 reported / 6.644 wrapper | 1,704,624 exact reranks |
| cache load/save (nested) | 0.019 / 0.362 | 4,367 rows requested for save |
| other retrieval channels, fusion, and materialization (derived nested residual) | about 2.010 | exact/part/technical plus fusion |
| post-retrieval scoring/materialization | 2.105 | 458 hybrid candidates scored |
| GF2 total | 2.882 | 20,457 proposals |
| GF2 persistence (nested) | 0.652 | one bounded batch operation |
| GF3 total | 3.290 | 1,064 neighborhoods / 10,474 members |
| GF3 persistence (nested) | 0.398 | 2,129 ORM insert statements observed |
| discovery final reconstruction/validation (nested) | 2.337 | completed |

Character retrieval completed normally in both runs. Its current contract
fingerprint was stable within this diagnostic and provider calls were zero. No
character optimization was attempted.

## GF2 and GF3 shape

- GF2 proposal count: 20,457.
- GF2 measured total/persistence: 2.882 / 0.652 seconds.
- GF3 neighborhood count: 1,064.
- GF3 measured total/persistence: 3.290 / 0.398 seconds.
- GF3 neighborhood member rows: 10,474.

Neighborhood sizes:

| min | median | p90 | p95 | p99 | max | >10 | >25 | >50 | >100 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 5 | 20 | 20 | 20 | 20 | 448 | 0 | 0 | 0 |

The neighborhood cap is preserved. The relevant downstream shape is not one
neighborhood alone but overlapping-neighborhood work units.

## GF4 shape

- Expected/persisted edges: 20,457 / 20,457.
- Orchestration-stage time: 12.105 seconds in the confirmation.
- Evidence-run persisted start/end time: 10.382 seconds.
- Status: `COMPLETED`.
- Provider calls: zero.

GF4 completed and is not the dominant stage.

## GF5 work-unit and search shape

The real graph formed 244 GF5 work units:

| measure | min | median | p90 | p95 | p99 | max | >10 | >25 | >50 | >100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| records/unit | 2 | 2 | 4 | 8 | 39 | 212 | 9 | 5 | 2 | 1 |
| candidate edges/unit | 1 | 1 | 6 | 21 | 712 | 16,480 | 17 | 11 | 9 | 7 |
| cannot-links/unit | 0 | 0 | 0 | 0 | 4 | 19 | 1 | 0 | 0 | 0 |

Largest aggregate shapes were 212/16,480/19, 85/754/4, 44/946/8,
39/712/0, 33/527/7, and 22/221/0 for records/candidate-edges/cannot-links.
All six exceed the unchanged 20-member limit and therefore defer immediately;
their astronomical theoretical subset counts are not executed.

The important eligible shapes were:

| records | candidate edges | cannot-links | theoretical subsets of size 2..8 | enforced generation bound |
|---:|---:|---:|---:|---:|
| 18 | 130 | 0 | 106,743 | 16,400 |
| 14 | 64 | 4 | 12,896 | 16,400 |
| 12 | 66 | 0 | 3,784 | 16,400 |
| 10 | 24 | 4 | 1,002 | 16,400 |

The targeted-check budget remained 40 per work unit. The confirmation planned
and executed 50 targeted checks across the first reached units before entering
the size-18 unit. The active size-18 candidate generation did not finish before
the remaining 129 seconds elapsed. The 300-second observation independently
recorded 219.962 completed seconds in candidate generation and still did not
complete GF5.

Candidate generation enumerates record subsets down from size eight and builds
and validates every plausible complete-pairwise group until the existing
per-work-unit bound is reached. This is bounded, but the bound is high enough
for dense 12--18 member real work units to dominate wall time. No safety limit
was weakened and no incomplete work became accepted.

GF5 compute did not complete, so final persisted metrics, validation time, and
persistence time are unavailable. GF5 persistence had not started. The active
RUNNING checkpoint contained no accepted output and is non-authoritative.

## GF6

GF6 was not reached in either diagnostic. Reconstruction, projection,
persistence, manifest time, and result counts are all `NOT_REACHED`, not zero.

## CPU, SQL, persistence, and memory classification

Dominant classification:

```text
CPU_COMPUTE
ALGORITHMIC_WORK_EXPLOSION
```

Before pure GF5 resolution, the diagnostic observed one GF5 run insert and
three GF5 service SELECTs, plus eight SELECTs for GF5 input reconstruction.
No SQL statement was issued by the active candidate-generation loop. GF5 result
persistence had not begun. Therefore SQL read/write amplification,
transaction/flush, and serialization are not the measured blocker.

Approximate process RSS peak: `NOT_MEASURED` on this Windows diagnostic.

## Canonical 5k versus real 5,327

The comparison uses the existing completed canonical GF-12A1 v2 5k artifact and
the current aggregate inspector. It does not compare record count alone.

| Shape | Canonical 5k | Real 5,327 |
|---|---:|---:|
| records | 5,000 | 5,327 |
| GF2 proposals | 20,500 | 20,457 |
| GF3 neighborhoods | 1,670 | 1,064 |
| neighborhood median / p90 / p99 / max | 17 / 18 / 20 / 20 | 5 / 20 / 20 / 20 |
| GF4 evidence edges | 20,500 | 20,457 |
| GF5 work units | 172 | 244 |
| largest work unit | 1,250 records / 20,247 edges | 212 records / 16,480 edges |
| largest non-deferred work unit | 11 records / 14 edges | 18 records / 130 edges |
| GF5 status | completed in 37.081 orchestration seconds | nonterminal after both bounds |
| GF5 outcomes | 169 groups, 1 conflict, 3 deferred, 4,595 unassigned | not authoritative / not completed |
| GF6 | 169 groups; completed | not reached |

Canonical 5k completes because its 1,250-record component exceeds the member
cap and is deferred immediately, while its largest work unit still eligible for
candidate generation is only 11 records with 14 edges. The real data instead
contains several dense, near-cap units. The 18-record unit alone exposes a
106,743-subset theoretical space and reaches the 16,400-attempt bound. Thus the
difference is classified as:

```text
REAL_GRAPH_DENSITY
LARGE_CONNECTED/OVERLAPPING_NEIGHBORHOODS
GF5_WORK_UNIT_EXPLOSION
```

The real data is not labeled pathological; it exposes a legitimate work shape
that the synthetic generator did not exercise.

## RT1-RT18

| Test | Result |
|---|---|
| RT1 real CSV fingerprint unchanged | PASS |
| RT2 provider calls zero | PASS |
| RT3 timers do not affect semantic output | PASS; wrappers are restored and production functions are unchanged |
| RT4 character stage completes | PASS |
| RT5 discovery timing captured | PASS |
| RT6 GF2 count/time captured | PASS |
| RT7 GF3 count/time captured | PASS |
| RT8 neighborhood distribution captured | PASS |
| RT9 GF4 work/time captured | PASS |
| RT10 GF5 work-unit shape/time captured | PASS |
| RT11 GF6 timing captured if reached | NOT_REACHED, reported truthfully |
| RT12 stopped diagnostic never authoritative | PASS |
| RT13 no raw real descriptions emitted | PASS |
| RT14 canonical 5k comparison obtained | PASS |
| RT15 dominant stage evidence-backed | PASS / PROVEN |
| RT16 no production semantic change | PASS |
| RT17 no schema/migration/dependency change | PASS |
| RT18 no secret or `.env` access | PASS |

## Status boundary

- Real CSV intake: **VERIFIED**.
- Real character retrieval: **VERIFIED**.
- Real end-to-end group-first product: **NOT VERIFIED**.
- Synthetic showable product: **VERIFIED**, with the real-target qualification.
- GF-11: **IN PROGRESS**.
- GF-11 waiver: **ACTIVE**.
- `GF11-PERF-100K-COLD-FULL`: **OPEN**.
- 300-second target: **NOT MET**.
- GF-12A2: `HUMAN_REVIEW_DATASET_REQUIRED`.
- Deployment/integration remains deferred.

No human-quality, production-deployment, or production-scale graduation claim
is made.
