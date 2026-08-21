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

## GF-11B-PRE Character Retrieval Contract Decision

### Current contract and tie stability

The current character channel is a `HashingVectorizer` with 384 bins,
`char_wb` 3..5-grams, nonnegative contributions, and L2 normalization. It uses
exact brute-force cosine retrieval, requests configured top-k plus one for the
self result, excludes self afterward, rounds retained scores to two decimals,
and reconstructs reciprocal pairs. No contract or test previously selected a
canonical member when multiple records tie at the kth boundary. The observed
membership is therefore implementation-dependent on scikit-learn 1.7.0,
NumPy 2.4.6, input position, and its internal selection behavior.

Repeated runs and query batches of 64 versus 256 were identical. Shuffling the
same records while preserving their original references changed 767 undirected
character-pair memberships at 500 records and 9,195 at 5,000. There were 279
and 2,826 anchors respectively with kth-boundary ties. A deterministic
score-descending/reference-ascending selector changed 715 and 8,526 pair
memberships. Every changed membership was at the exact kth-boundary cosine
score; no unequal-score difference occurred. The current top-k-plus-self
mechanism can also retain one extra neighbor when an equal-vector record is
selected in place of the anchor itself.

Freezing canonical tie semantics alone does not address scale. Every 5k hashed
anchor still has positive overlap with all other 4,999 records, requiring
24,995,000 exact comparisons.

### Sparse character experiment

The benchmark-only alternative uses normalized descriptions, deterministic
token-bounded character 3..5-grams, TF-IDF from the existing scikit-learn
dependency, exact sparse cosine accumulation over shared postings, and
score-descending/reference-ascending top-k. It is classified
`SEMANTICALLY_CHANGED_RETRIEVAL`; it is not equivalent to the collision-heavy
384-bin channel.

| Records | Current dense | Deterministic dense | Sparse feature + query | Current/sparse pairs | Jaccard | Sparse exact evaluations | Zero comparisons avoided |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 27.32 ms | 78.36 ms | 95.20 ms | 1,834 / 1,871 | 0.216749 | 160,118 | 89,382 |
| 5,000 | 2,973.05 ms | 8,286.36 ms | 2,627.93 ms | 19,029 / 18,089 | 0.151124 | 16,024,184 | 8,970,816 |

At 5k the sparse index contained 22,785 features and 349,832 posting entries;
maximum/p95 posting sizes were 2,500/20, maximum anchor accumulation was 4,374,
and feature-posting traversal counted 268,947,350 contributions. It reduced
unique exact similarities by 35.89%, but 64.11% of all directed pairs still
overlapped. Holding that measured density constant would imply roughly 6.4
billion exact evaluations at 100k, so this experiment is not a credible 100k
graduation design by itself.

Current, deterministic-tie, and sparse variants each covered all synthetic
truth sets at both measured sizes: 60/60 and 591/591 overall, 31/31 and 312/312
protected-conflict fixtures, 20/20 and 204/204 cross-site sets, and 21/21 and
208/208 bridge sets. Sparse generic-hub pair volume was lower (300 versus 357
at 500; 3,110 versus 3,729 at 5k) without suppression. Truth remained outside
runtime inputs.

A disposable normal GF1-through-GF6 comparison at 64 records was identical for
all three variants: 285 proposals/evidence edges, 64 neighborhoods and 634
memberships, five accepted groups/13 members, six conflicts/42 members, three
deferred work units/32 members, 51 unassigned records, maximum neighborhood and
work-unit size 16, and three targeted checks. All runs completed with zero
cannot-link violations, duplicate accepted memberships, singleton groups,
cross-scan contamination, legacy pair/G1/G2-v1/shadow rows, and provider calls.

### Decision matrix

| Option | Semantic change | Determinism / exactness | Measured value | Risk/dependency | 100k plausibility |
|---|---|---|---|---|---|
| A. 384-bin/current selector | none | repeatable only at fixed order; exact brute force | 27 ms / 2.97 s at 500/5k; full overlap | current library-dependent ties; no new dependency | no |
| B. 384-bin/canonical tie | equal-boundary membership only | deterministic and exact | coverage/safety unchanged; 78 ms / 8.29 s experimental selector | low semantic risk; no new dependency | no; still full overlap |
| C. sparse exact character | material retrieval change | deterministic and exact over shared n-grams | 35.89% fewer 5k exact comparisons; coverage unchanged on synthetic corpus | explicit architecture authorization required; no new dependency | insufficient evidence; measured overlap remains high |
| D. bounded blocking scope | unknown/material | could be deterministic/exact only inside declared scope | not implemented or measured | recall and protected-coverage contract risk | unknown |
| E. future approximate index | material | deterministic configuration possible; not exact | not implemented or measured | separate architecture/dependency/quality decision | potentially credible, unproven |

### Decision

GF-11B-PRE establishes that current tie membership is unspecified, and option B
is safe on the measured fixtures, but B is not scale hardening. Option C changes
retrieval semantics and does not reduce the measured exact work enough to make
100k plausible. Options D and E were not implemented. The next action is a
separate ANN/approximate-retrieval architecture decision with explicit recall,
protected-conflict, dependency, determinism, and rollback gates. GF-11B remains
blocked and is not verified.

## GF-11B-PRE2 Deterministic Tie Contract

GF-11B-PRE2 rejects input-position-dependent character-neighbor membership as
incompatible with deterministic, auditable discovery. Production `CHAR_VECTOR`
selection now retains the frozen 384-bin nonnegative `char_wb` 3..5 hashing,
L2 normalization, exact cosine, configured top-k, two-decimal retained scores,
reciprocal reconstruction, fusion, and caps. Self is excluded first. Raw cosine
similarity orders candidates descending; only candidates with exactly equal raw
similarity use immutable GF-1 `record_ref_key` ascending. Missing, blank, or
duplicate canonical references fail closed. DataFrame position and source-row
ordinal are not tie keys. `LEXICAL` and every other channel retain their prior
selector and semantics.

Focused clear-gap, below-boundary-tie, exact-boundary-tie, self-exclusion,
duplicate-valued-row, reverse-order, fixed-shuffle, repeatability, reciprocal,
cap, and non-character fixtures passed. The historical-versus-canonical
validator observed zero unequal-score substitutions.

### Measured canonical comparisons

| Records | Historical character time | Deterministic character time | Historical/new character pairs | Tie substitutions | Unequal-score substitutions | Permutation differences |
|---:|---:|---:|---:|---:|---:|---:|
| 500 | 35.78 ms | 358.22 ms | 1,834 / 1,781 | 889 | 0 | 0 across reverse + seeds 7/19/1101 |
| 5,000 | 1.22 s | about 21.35 s | 19,029 / 18,416 | 9,063 | 0 | 0 across reverse + seeds 7/19/1101 |

The 500 character-proposal fingerprints changed from
`988c415feeb108696952daeaf6ece6088d9b8b4e53ae2f1b14454349ad7b2818`
to `a6e5cec3493633b1761789af6a13cd7cfe87f1f1e241a68b33afccd1f77bb2b5`.
Character discovery coverage remained 60/60 truth sets, 31/31 protected
conflicts, 20/20 cross-site sets, and 21/21 bridge sets. Generic-hub character
pairs changed from 357 to 300 through exact boundary-tie selection only.

After normal fusion and unchanged caps, both 500 runs retained 388 hybrid
candidates and covered 54/60 truth sets, 20/20 cross-site sets, and 21/21 bridge
sets; protected-conflict pairs remain intentionally blocked before final hybrid
selection. The fused fingerprints changed from
`759e2479b4fae176f2340cd2e8d02608215caac1ce0932150eb1adda3a14fb3c`
to `a460b9f832003ee46c38e1ee5e17c79998ea573719911a0242ec8eada4c772c9`.
There were 48 final pair substitutions. Nine displaced cap-boundary rows did
not themselves carry `CHAR_VECTOR`; their displacement was a downstream effect
of the authorized character rank substitutions, not a change to their source
channels or to the cap algorithm.

The disposable 64-record historical/deterministic normal GF1-through-GF6 runs
remained identical: 285 proposals/evidence edges, 64 neighborhoods/634 members,
five groups/13 members, six conflicts/42 members, three deferred work units/32
members, 51 unassigned, maximum neighborhood/work-unit size 16, and three
targeted checks. Both completed with zero accepted cannot-link violations,
duplicate accepted memberships, singleton groups, cross-scan contamination,
legacy pair/G1/G2-v1/shadow rows, and provider calls.

This prerequisite does not reduce structural work. The 5k 384-bin character
matrix still has 24,995,000 positive-overlap directed comparisons, and the
canonical full-neighbor tie resolution is slower than the historical incidental
selector. GF-11B remains blocked and unverified. The next required unit is a
separate approximate character-retrieval architecture decision; no ANN,
approximate index, or sparse production representation is introduced here.
