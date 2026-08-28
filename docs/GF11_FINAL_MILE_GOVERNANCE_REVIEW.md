# GF-11 final-mile governance review

## Decision boundary

> **NO GRADUATION CRITERION CHANGED BY THIS REVIEW.**  
> **NO WAIVER WAS ENACTED BY THIS REVIEW.**  
> **GF-11 REMAINS IN PROGRESS UNTIL THE SUPERVISING ARCHITECT APPROVES A GOVERNANCE DECISION.**  
> **GF-12 REMAINS NOT STARTED.**

This document is an evidence and recommendation artifact. It is not a product
requirement, architecture decision, waiver, graduation record, or authorization
to resume optimization.

The one recommendation is:

```text
PRODUCT_OWNER_DECISION_REQUIRED
```

Repository evidence proves that the current implementation consistently misses
the 300-second cold-full DISCOVERY gate on the measured runtime. It does not
prove that 300 seconds is an externally grounded hard product requirement, and
it does not provide enough workflow, hardware, warm-state, or incremental-state
evidence to select a replacement requirement or enact a waiver.

## Authority and repository state

The review used the repository authority order in `PROJECT_SSOT.md` and read:

- `PROJECT_SSOT.md`;
- `docs/GROUP_FIRST_IDENTITY_ARCHITECTURE_ADR.md`;
- `docs/GROUP_FIRST_DOMAIN_CONTRACTS.md`;
- `docs/GROUP_FIRST_MIGRATION_ROADMAP.md`;
- `docs/GF11_SCALE_BASELINE.md`;
- `docs/CURRENT_PROJECT_ASSESSMENT.md`;
- `docs/CHATGPT_ARCHITECT_WORKFLOW.md`.

The review started from branch `llm-assisted-mvp` at
`71025f5f121dabfa1bdcbe754d010e5ce2d6e74d`, subject
`Rerun 100k graduation after cache hardening`. The protected tag
`deterministic-demo-v1` remained at
`d510cf3c18b3a8448d0f79be3e59c398efb32eae`. The worktree and staging area
were clean.

## Origin and classification of the 300-second number

The exact GF-11D benchmark constant `GRADUATION_TIMEOUT_SECONDS = 300.0` first
appeared in commit `ac23b09eb440a56e0628d14c3c0a521d0f5c269e`, dated
2026-08-25, subject `Measure 100k group-first graduation limits`, in
`backend/app/benchmarks/production_graduation.py`. That commit introduced the
canonical 100k graduation harness and tests asserting the 300-second timeout.
It recorded the timeout as the official graduation gate, but supplied no
customer, CEO, user-interaction, contractual, or production-hardware rationale
for choosing 300 rather than another value.

Commit `0ea3d212b63712a05ee4cf45de2d01591b9beaed`, dated 2026-08-20,
subject `Establish 100k scale baseline`, had already used 300-second execution
bounds for 20k and 100k characterization. Those were benchmark bounds, not a
documented product SLO. The explicit wording `DISCOVERY <=300-second gate` was
later committed in `1c27ee539beeac78b783be1368933eff0dec72af`, dated
2026-08-27, after the benchmark constant was already governing GF-11D.

The authoritative ADR states that benchmark owners must establish declared
hardware, representative data shapes, baselines, and explicit pass thresholds,
and that no timing threshold is approved by the ADR without those measurements.
The repository has a deterministic synthetic data shape and measured baseline,
but no declared minimum/reference production hardware and no written external
latency need.

The strongest justified taxonomy is therefore:

```text
GRADUATION_GATE
```

It is also a useful `TARGET_SLO`, but repository evidence does not elevate it
to `HARD_REQUIREMENT`. It is not merely an observability metric because it
currently blocks phase graduation. Its origin is best classified as an
engineering benchmark/graduation target with an undocumented numeric rationale.

## Production workflow evidence

The implemented upload route awaits CSV parsing, validation, and `run_scan(...)`
inside the request before returning the scan response. Current large scans are
therefore operationally synchronous HTTP work: the caller waits for deterministic
scan completion or failure. Only optional LLM triage is scheduled as a FastAPI
background task.

The target architecture is different: it calls for a resumable background-job
seam, durable stage checkpoints, bounded progress, and later durable work queues.
`docs/production_readiness_testing.md` explicitly says large synchronous scans
should move to a background worker. Thus the current request behavior is not
evidence that five minutes is an approved interactive user requirement.

Repository evidence about operating expectations is:

| Question | Evidence-backed answer |
|---|---|
| Expected scan frequency | `UNSPECIFIED` |
| Operator-triggered or scheduled | Upload/operator-triggered is implemented; scheduling is `UNSPECIFIED` |
| User waits synchronously | Yes in the current upload API |
| Partial progress surfaced to that caller | No durable live progress contract is exposed by the upload response |
| Results persisted/snapshotted | Yes: canonical catalog, discovery, evidence, resolution, and G2 snapshots |
| Retry/resume | Partial stage/idempotency seam; failed primary discovery requires a new scan |
| Full 100k recomputation expected every time | Current upload path recomputes; long-term expectation is `UNSPECIFIED` |
| Cache/index reuse across scans | Embedding vectors persist by fingerprint/model; lexical/LSH discovery indexes do not |

## Workload classes

| Workload | Implemented | Benchmarked | Authoritative current semantics | Architectural work required |
|---|---|---|---|---|
| `COLD_FULL` | Yes | Yes | Yes | Performance/governance remains unresolved |
| `WARM_FULL` | Partial embedding-cache reuse only | No canonical warm-full benchmark | No distinct workload contract | Yes |
| `INCREMENTAL` | No | No | No | Yes |
| `RESUME` | Partial persisted stages/checkpoints | No production-faithful 100k resume SLO | Partial failure/idempotency semantics | Yes |

The frozen benchmark is specifically `COLD_FULL`: a new disposable SQLite
database and no reusable scan state. It cannot establish warm, incremental, or
resume latency.

## Hardware and runtime contract

The measured environment available without adding dependencies was:

| Item | Value |
|---|---|
| OS | Windows AMD64, reported runtime `Windows-10-10.0.26200-SP0` |
| Python | 3.11.9 |
| Logical CPUs | 8 |
| Physical cores | `UNAVAILABLE` |
| CPU model | `UNAVAILABLE` |
| RAM | `UNAVAILABLE` |
| NumPy | 2.4.6 |
| SciPy | 1.17.1 |
| scikit-learn | 1.7.0 |
| SQLite | 3.45.1 |
| BLAS | scipy-openblas/OpenBLAS 0.3.31, 64-bit integers, dynamic architecture, `MAX_THREADS=24` build |
| Runtime BLAS thread configuration | `UNAVAILABLE` as an explicit repository contract |

The repository defines no minimum or reference production CPU, core count,
memory, storage, SQLite/PostgreSQL class, or BLAS-thread configuration against
which the 300-second gate is normative.

## Committed 100k scale milestones

Timings below are not assumed comparable when implementation or harness scope
changed.

| Milestone | DISCOVERY evidence | GF4 | GF5 | GF6 | Principal result |
|---|---|---|---|---|---|
| Initial GF-11A (`0ea3d212`) | Timed out with DISCOVERY running at 300.03s | Not reached | Not reached | Not reached | Established baseline only |
| Post GF-11B/GF-11C | 100k normal path still timed out; bounded lexical-only later completed in 98.300s | Not established by lexical-only run | Not reached | Not reached | Retrieval became bounded; no full graduation |
| Initial GF-11D (`ac23b09e`) | Extended diagnostic DISCOVERY 721.191s | Succeeded | Timed out | Not reached | CHAR and cache were dominant |
| Post CHAR1 (`d7028232`) | Extended diagnostic DISCOVERY 571.720s | Succeeded | Typed validation failure | Skipped | CHAR semantics-preserving speedup verified |
| Post GF5 fix (`1c27ee53`) | Extended diagnostic DISCOVERY 379.361s | Succeeded | Succeeded | Succeeded | End-to-end correctness/safety achieved |
| Post CACHE1/current (`71025f5f`) | Extended diagnostic DISCOVERY 324.468s | Succeeded | Succeeded | Succeeded | Current complete safe baseline; 300s still missed |

The current complete result persisted 20,500 proposals, 20,687 neighborhoods,
41,706 neighborhood members, 20,500 evidence edges, 247 groups/494 grouped
members, 13 conflicts, five deferred units, and 99,506 unassigned records.
Provider and deprecated pair-path writes were zero, as were accepted cannot-link,
duplicate-membership, singleton, cross-scan, and source-mutation violations.

## Current-HEAD variance and throughput

Only one comparable complete current-HEAD 100k result was committed, so this
review ran the two additional controls authorized by the governance task. Both
used current committed code, the canonical corpus and seed, provider none,
policy-v2 group-first mode, unique disposable SQLite databases, no Python
profiler, and stopped immediately after completed persisted DISCOVERY.

| Sample | Harness | DISCOVERY seconds | Gate distance | Semantic result |
|---|---|---:|---:|---|
| Committed baseline | Full-pipeline diagnostic instrumentation | 324.468367 | +24.468367 | Complete; downstream GF4-GF6 also completed |
| Control 1 | Discovery-only residual harness | 304.764270 | +4.764270 | 20,500 proposals; 20,687 neighborhoods; canonical fingerprints |
| Control 2 | Discovery-only residual harness | 323.791250 | +23.791250 | 20,500 proposals; 20,687 neighborhoods; canonical fingerprints |

The harness-scope difference is disclosed; the controls do not prove the
full-pipeline harness would have identical overhead. All three are same-HEAD,
same-corpus, same-seed, production-path DISCOVERY observations.

| Statistic | Seconds |
|---|---:|
| Minimum | 304.764270 |
| Median | 323.791250 |
| Maximum | 324.468367 |
| Mean | 317.674629 |
| Population standard deviation | 9.133187 |
| Population coefficient of variation | 2.8750% |

Every observation misses the gate. The miss is therefore not erased by current
variance, although its magnitude ranges from 4.764 to 24.468 seconds.

At the median, throughput is 308.841 records/second and 32.379 seconds per
10,000 records. No 1M completion time is inferred from this value.

## GF-12 dependency analysis

GF-12 includes several different classes of work:

| Relationship to unresolved 100k performance | GF-12 evidence work |
|---|---|
| Blocked | Final 100k threshold acceptance and a production-ready scale claim |
| Independent | Human-reviewed precision/recall evaluation, split/merge adjudication, cannot-link/exclusivity/writeback-zero audits, privacy, tenancy, authorization, export review, and release/rollback preparation |
| Useful to the decision | Recovery exercises, operational workflow/user-acceptance research, representative dataset shapes, and declared hardware measurements |

Keeping every GF-12 activity blocked reduces evidence gathering and engineering
progress without automatically increasing deterministic safety. However, the
roadmap currently places GF-12 after GF-11, so beginning even independent work
requires an explicit supervising-architect phase/governance decision. This
review does not start GF-12 or alter that order.

## One-million-record seam

The 24.5-second current cold-full gap is not the dominant architectural risk to
eventual 1M support. The approved 1M seam expects distributed/external ANN,
durable queues, sharded evidence, incremental index maintenance, changed-record
resolution, and storage suitable for large analytical manifests. Current code
still has per-scan in-memory vectors, hundreds of millions of posting/bucket
visits at 100k, a 20,113-record maximum GF5 work unit, synchronous request
execution, SQLite persistence, no reusable lexical/LSH index, and no incremental
discovery implementation. These concerns dominate any unsupported linear
extrapolation. The repository makes no 1M readiness claim.

## Governance options

### Option A — `KEEP_300_HARD_AND_REDESIGN`

Benefit: preserves a clear bound and may force architecture that also improves
future scale. Risk and scope are high: persistent retrieval indexes,
incremental discovery, or a new native/vectorized execution architecture require
new contracts, migrations/storage decisions, failure/rebuild behavior, extensive
semantic equivalence, and representative hardware validation. Current evidence
proves a repeatable miss, but not that an externally required 300-second benefit
justifies this cost.

### Option B — `FORMAL_PERFORMANCE_WAIVER`

Benefit: allows independent production-validation evidence to proceed while
retaining visible performance debt. Risk: a waiver can become an implicit
graduation or indefinite exception. The current authority documents contain no
defined waiver mechanism, approver, duration, or phase-transition rule. A waiver
is therefore possible only through an explicit supervising-architect/product
decision and must not call GF-11 performance complete.

If later authorized, a defensible waiver would need to state: cold-full 100k
only; the current three-result range and median; all completed safety/correctness
evidence; the unmet 300-second criterion; approved hardware and workload scope;
an expiry no later than a named release/roadmap milestone; mandatory stage-time,
resource, failure, and queue-latency observability; which independent GF-12
evidence work may proceed; prohibition on a 300-second compliance claim; and
exit by either measured compliance or a separately approved replacement SLO.
This review does not enact that contract.

### Option C — `SPLIT_COLD_AND_STEADY_STATE_SLOS`

Benefit: aligns measurements with the target background/resumable architecture
and prevents fresh-database cost from being mislabeled as ordinary user latency.
Risk: warm or incremental semantics can hide rebuild, invalidation, staleness,
and safety failures unless rigorously specified. The repository conceptually
supports this option, but WARM_FULL, INCREMENTAL, and production RESUME workloads
are not implemented or benchmarked. Numeric SLOs therefore require a product and
architecture decision followed by separate cold rebuild, warm cache/index,
change-set, and failure-resume benchmarks on declared hardware.

### Option D — `REVISE_300_GATE`

Benefit: removes an ungrounded round-number blocker if 300 seconds is not a real
operational need. Risk: selecting 325 or another value merely because current
code fits would be goalpost movement. Repository history supports classifying
300 as an internal graduation target, but provides no justified replacement
number. Revision requires approved workflow, hardware, workload distribution,
user tolerance, and operational cost evidence.

## Required decision

```text
PRODUCT_OWNER_DECISION_REQUIRED
```

The supervising architect/product owner must explicitly choose whether 300
seconds is a hard cold-full requirement, authorize and bound a waiver, authorize
separate workload SLO contracts, or commission evidence for a replacement gate.
Until then, 300 seconds remains the operative unmet graduation criterion,
GF-11 remains IN PROGRESS, and GF-12 remains NOT STARTED.
