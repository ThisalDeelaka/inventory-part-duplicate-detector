# GF-11 scale baseline

## Scope

GF-11 remains the frozen 100k scale-hardening phase. Its bounded internal
delivery units are:

- GF-11A: scale contracts, deterministic corpus, instrumentation, and baseline;
- GF-11B: first evidence-driven bottleneck hardening;
- GF-11C: second measured bottleneck or resumability hardening, as required;
- GF-11D: 100k graduation benchmark and scale acceptance.

GF-11A changes no production identity rule, retrieval threshold, generic guard,
resolver rule, G2-v2 contract, schema, migration, product read, review, export,
provider, or default orchestration mode.

## Benchmark contract and method

The developer entry point is:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.benchmarks.group_first_scale `
  --records 5000 --seed 1101 --output gf11.json `
  --markdown gf11.md --timeout-seconds 600
```

Each command generates a fixed-seed corpus, creates a uniquely named SQLite
database inside a temporary directory, runs explicit
`group_first_primary`/policy-v2 with provider `none`, captures the result, and
removes the temporary database. The configured/default application database is
never opened by the harness. Result JSON contains no hostname, username,
absolute path, source payload, benchmark truth, provider material, or secret.

The canonical mixed corpus version is `group-first-scale-corpus-v1`, seed 1101.
It combines clean unique records, duplicate sets, generic hubs, technical
conflicts, cross-site identities, sparse data, bridge ambiguity, and repeated
families. Truth remains in a separate benchmark object and never enters the
scan DataFrame or runtime decisions. Generation is O(records) and creates no
global negative-pair matrix.

Measurement environment: Windows AMD64, Python 3.11.9, SQLite 3.45.1, eight
logical CPUs. Cross-platform peak RSS was not available from the standard
library on this Windows runtime and is reported as `UNAVAILABLE`.

## MEASURED

### Baseline results

| Records | Bound | Status | Last stage | Total wall | SQLite bytes | Queries |
|---:|---:|---|---|---:|---:|---:|
| 500 | 120 s | `COMPLETED` | completion | 79.12 s | 62,750,720 | 5,114 |
| 5,000 | 600 s | `FAILED` | `GROUP_RESOLUTION` | 140.59 s | 77,312,000 | 15,467 |
| 20,000 | 300 s | `TIMED_OUT` | `GROUP_RESOLUTION` running | 300.03 s | 117,661,696 | unavailable after forced stop |
| 100,000 | 300 s | `TIMED_OUT` | `DISCOVERY` running | 300.03 s | 46,690,304 partial | unavailable after forced stop |

The 5k failure is the bounded safe category
`IDENTITYRESOLUTIONVALIDATIONERROR`; it occurred after catalog, discovery, and
evidence completed. The 20k process had a durable RUNNING resolution checkpoint
when the bound expired. The 100k process had completed GF1 and had a durable
RUNNING discovery checkpoint when stopped. Interrupted runs are not reported as
completed.

### Stage time and generated work

| Records | Catalog | Discovery | Evidence | Resolution | Proposals | Evidence edges | Neighborhoods | Truncated | Max neighborhood | Max work unit |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 0.78 s | 44.16 s | 22.19 s | 7.64 s | 19,328 | 19,328 | 500 | 500 | 20 | 189 |
| 5,000 | 1.47 s | 73.99 s | 24.47 s | 41.27 s, failed | 20,500 | 20,500 | 1,672 | 52 | 20 | 1,250 |
| 20,000 | 11.81 s | 219.86 s | 29.03 s | running at timeout | 20,500 | 20,500 | 5,586 | 4 | 20 | 5,006 |
| 100,000 | 53.45 s | incomplete at timeout | not started | not started | 0 committed | 0 | 0 | 0 | unavailable | unavailable |

Proposal and evidence volume reaches the configured bounded plateau of 20,500
by 5k. That cap bounds durable edges, but it does not bound the work performed
by brute-force lexical/vector nearest-neighbor construction before final
selection. Connected resolution work units grow from 189 to 1,250 to 5,006,
despite 20-member persisted neighborhoods.

### Persistence and safety

The completed 500 run persisted 500 GF1 records, 19,328 GF2 proposals, 500 GF3
neighborhoods/10,000 memberships, 19,328 GF4 edges, six GF5 deferred work
units, and one completed GF6 run. It produced no accepted group and safely
deferred all 60 synthetic true duplicate sets.

All measured and partial runs recorded zero accepted cannot-link violations,
duplicate accepted memberships, singleton accepted groups, cross-scan
contamination, provider calls, legacy pair/rejection rows, G2-v1 rows, and
shadow rows. G1 has no separate durable artifact in this path and its policy-v2
stage remained not applicable. Safety-zero observations on failed/interrupted
runs describe persisted partial state; they are not completion claims.

### Synthetic quality

The completed 500 mixed run covered 0 of 60 truth sets, missed 60, deferred all
60, detected five conflict outcomes, and over-merged/split zero accepted sets.
The result is an intentionally stressful synthetic baseline, not a production
accuracy estimate. The failed/interrupted 5k, 20k, and 100k runs publish no
completed quality result.

## INFERRED

1. Discovery is the dominant measured bottleneck. Its audited implementation
   uses brute-force nearest-neighbor queries for TF-IDF and dense 384-value
   character vectors. The final 20,500 proposal cap is applied after this work.
2. Proposal/evidence persistence is also material at small sizes: it consumed
   about 66 seconds of the 79-second 500 run, including discovery computation.
3. The 20-member neighborhood cap bounds each persisted neighborhood but does
   not bound unions of overlapping neighborhoods. Work-unit growth to 1,250 at
   5k and 5,006 at 20k exposes a separate resolver-scale risk.
4. The 5k validation failure is a truthful existing resolver boundary. GF-11A
   does not change resolver semantics merely to make the benchmark pass.
5. No conclusion about production precision, recall, 100k readiness, ANN, or a
   particular future index follows from this synthetic baseline alone.

## NEXT-HYPOTHESIS

GF-11B should target one measured bottleneck: **discovery retrieval/fanout**.
It should first isolate lexical, dense-vector, exact-family, and persistence
costs; then test a bounded-before-materialization discovery implementation
behind the frozen discovery contract. ANN or learned embeddings are not an
automatic choice. Any candidate must preserve proposal semantics, deterministic
ordering/fingerprints, generic-family safety, cap accounting, and downstream
GF4-GF6 output on golden corpora.

The oversized overlapping-work-unit and 5k resolver validation observations
remain measured candidates for GF-11C only after GF-11B is benchmarked.
