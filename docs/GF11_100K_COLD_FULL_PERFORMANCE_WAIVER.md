# GF-11 100k Cold-Full Performance Waiver

## Governance status

- Waiver: **ACTIVE**
- Authority: explicit **supervising architect / product-owner decision**
- GF-11: **IN PROGRESS**
- GF-12: **NOT STARTED; START AUTHORIZED** under this bounded waiver
- Debt: `GF11-PERF-100K-COLD-FULL` — **OPEN**
- Performance criterion: `DISCOVERY <=300.000000 s` — **TARGET NOT MET**

This document authorizes bounded roadmap progression. It does not declare
GF-11 complete, revise the performance target, or grant final production
graduation.

## Exact waiver scope

The waiver applies only to COLD_FULL 100,000-record group-first, provider-none,
policy-v2 DISCOVERY performance on fresh/disposable state. It waives the
requirement to satisfy the frozen 300-second criterion before starting
independent GF-12 production-validation work. It does not waive any other
performance contract or any functional, safety, security, privacy, or data-
integrity requirement.

## Frozen criterion and measured evidence

The target remains `DISCOVERY <=300.000000 s`.

| Statistic | Current three-run sample |
| --- | ---: |
| Minimum | 304.764270 s |
| Median | 323.791250 s |
| Maximum | 324.468367 s |
| Mean | 317.674629 s |
| Coefficient of variation | 2.8750% |
| Status | **TARGET NOT MET** |

The two discovery-only controls and the completed diagnostic retained 20,500
proposals, 20,687 neighborhoods, canonical fingerprints, and zero provider
calls. This evidence supports a bounded governance decision; it does not turn
the failed criterion into a pass.

## Rationale

The sample is close enough to the frozen target to permit independent GF-12
validation to expose quality, safety, operational, and product risks while the
performance debt remains explicit. Functional correctness, deterministic
output, group safety, provider isolation, and later-stage integrity have
separate verified evidence. Continuing those independent validation streams is
useful and does not require claiming the cold-full performance target was met.

## Requirements not waived

The waiver does not relax:

- correctness or determinism;
- cannot-link enforcement or accepted-group membership uniqueness;
- provider isolation and zero provider calls in deterministic execution;
- GF-4, GF-5, or GF-6 integrity;
- source immutability or the prohibition on automatic merge, delete, or writeback;
- deprecated pair/G1/G2-v1/shadow write prohibitions for explicit group-first scans;
- security or privacy controls;
- truthful evidence, coverage, failure, and status reporting.

## Duration and expiry

The waiver expires at the earliest of:

1. the GF-12 final decision;
2. a formal replacement or split of the performance SLO;
3. evidence that 300 seconds is an external hard requirement; or
4. a material performance regression.

Expiry does not silently close the debt or confer graduation. A new explicit
governance decision is required.

## GF-12 work authorized to start

The following independent production-validation categories may begin:

- quality evaluation, including false positives and false negatives;
- group correctness and human-reviewed case validation;
- safety validation;
- privacy and security validation;
- recovery and failure-mode validation;
- observability validation;
- operational and rollback runbooks;
- user acceptance testing;
- deployment-readiness assessment;
- reference-hardware definition;
- warm and resume benchmark design; and
- workflow and SLO evidence collection.

This authorization permits the smallest independent GF-12 validation units; it
does not authorize final GF-12 graduation.

## Claims and work still blocked

The following claims remain prohibited:

- GF-11 performance graduation or GF-11 completion;
- achievement of the `<=300.000000 s` target;
- one-million-record readiness;
- existence of incremental execution;
- complete resume behavior;
- a defined warm-runtime SLO; and
- final production signoff or graduation.

This waiver also does not authorize new identity semantics, new retrieval or
resolution budgets or thresholds, weakened safety gates, a major architectural
redesign, or provider use without separate authorization.

## Regression guard

Any material retrieval, discovery, or orchestration change must rerun the
canonical 100k benchmark before GF-12 final signoff. Results must be compared
with the current three-run sample recorded above. No new numeric regression
threshold is invented by this waiver; a material regression triggers expiry
and requires explicit review.

## Future workload contracts

COLD_FULL, WARM_FULL, INCREMENTAL, and RESUME are separate workload classes.
Future SLOs for those classes require independently justified contracts and
evidence. This waiver neither defines nor implies numeric targets for them.

## Decision boundary

The authoritative state is:

- GF-11: **IN PROGRESS**, performance waiver **ACTIVE**, 300-second target
  **NOT MET**.
- GF-12: **NOT STARTED**, **START AUTHORIZED** under the bounded waiver.
- `GF11-PERF-100K-COLD-FULL`: **OPEN** and due for review no later than the
  GF-12 final decision.

No production code, test, schema, migration, dependency, provider, backend, or
frontend change is authorized by this decision.
