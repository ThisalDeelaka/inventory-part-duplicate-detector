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

## GF-11B-ANN Approximate Character Retrieval Architecture Decision

### Frozen two-stage boundary

The architecture decision authorizes only candidate generation, never an ANN
score as discovery output:

```text
current normalized 384-bin char vectors
  -> fixed-seed random-hyperplane LSH candidate generation
  -> bounded candidate pool
  -> exact cosine over current vectors in that pool
  -> exact score descending / GF1 record_ref_key ascending on ties
  -> existing character top-k and reciprocal reconstruction
  -> unchanged fusion, provenance, family/tier/per-record/global caps
```

The selected benchmark contract is
`fixed-seed-cosine-lsh-exact-rerank-v1`: eight tables, 12 bits/table,
NumPy PCG64 seed 1101, deterministic Hamming-radius-two probing, canonical
GF1 insertion/query identity, bucket-read bound `2 * candidate_pool_k`, gather
bound `4 * candidate_pool_k`, `candidate_pool_k=320`, and current final
character `top_k=5`. Approximate bit agreement selects the pool only. Final
scores are exact dot products of the frozen L2-normalized vectors, which are
exact cosine values, and ANN-native ordering is discarded.

Every future discovery fingerprint must include algorithm contract version,
backend name/version, vector representation version, seed, stable insertion
policy, table/bit/probe/bucket/gather parameters, candidate pool, exact-rerank
version, final top-k, NumPy version, and scikit-learn version.

`EXACT_DESCRIPTION`, `PART_NUMBER_FAMILY`, `TECHNICAL_IDENTITY`,
`STANDARD_BLOCKING`, and exact `LEXICAL` behavior remain safety-sensitive exact
channels. No benchmark truth, scenario code, duplicate-set identity, conflict
label, or bridge label enters LSH build/query/rerank input.

### Candidate-pool and parameter sweep

The canonical 5k pool sweep used eight tables. Recall is directed exact
character-neighbor recall after exact rerank; pair Jaccard compares undirected
character pairs with the deterministic exact reference.

| Pool | Multiple of top-k | Recall | Pair Jaccard | Exact reranks | Selector time |
|---:|---:|---:|---:|---:|---:|
| 5 | 1x | 31.848% | 18.286% | 25,000 | 0.525 s |
| 10 | 2x | 34.512% | 20.205% | 50,000 | 0.641 s |
| 20 | 4x | 39.004% | 24.035% | 100,000 | 0.974 s |
| 40 | 8x | 45.652% | 29.718% | 200,000 | 1.371 s |
| 80 | 16x | 56.404% | 40.133% | 400,000 | 2.033 s |
| 160 | 32x | 71.496% | 56.368% | 800,000 | 3.964 s |
| 320 | 64x | 87.144% | 77.593% | 1,600,000 | 7.537 s |

Pool 80 missed seven 5k truth sets and 35 protected-conflict fixtures. Pool
160 recovered all truth/cross-site/bridge sets but still missed 2/312 protected
fixtures. Pool 320 was therefore the smallest measured pool satisfying every
coverage gate. At 500/pool 80, four/eight/twelve tables produced directed recall
of 93.88%/97.84%/98.04% and pair Jaccard of 88.88%/95.82%/96.09%; eight tables
was retained as the smaller near-Pareto configuration. Pool 320 at 500 produced
97.88% directed recall, 97.98% pair recall, 97.87% pair precision, 95.93%
Jaccard, 449/500 fully recovered anchors, 0.106 mean missing neighbors, and
0.60 worst-anchor recall.

At 5k/pool 320, pair recall was 88.17%, precision 86.61%, Jaccard 77.59%,
2,869/5,000 anchors recovered their complete exact top-k, mean missing exact
neighbors was 0.6428, and worst-anchor recall was zero. Those raw retrieval
losses are material and are not hidden; authorization follows only because all
mandatory truth/safety gates and downstream hybrid comparisons passed.

### Coverage and final hybrid results

Character-pair discovery coverage was unchanged:

| Records | Truth sets exact/LSH | Protected exact/LSH | Cross-site exact/LSH | Bridge exact/LSH | Generic-hub pairs exact/LSH |
|---:|---:|---:|---:|---:|---:|
| 500 | 60/60 / 60/60 | 31/31 / 31/31 | 20/20 / 20/20 | 21/21 / 21/21 | 300 / 300 |
| 5,000 | 591/591 / 591/591 | 312/312 / 312/312 | 204/204 / 204/204 | 208/208 / 208/208 | 3,110 / 3,110 |

After unchanged fusion and caps, the 500 exact/LSH runs both retained 388
proposals, had 98.4655% pair Jaccard and six substitutions, and identically
covered 54/60 truth sets, 20/20 cross-site sets, 21/21 bridge sets, and 0/31
protected fixtures (protected contradictions are intentionally blocked before
final hybrid selection). Both retained 25 generic-hub pairs. At 5k the final
exact and LSH hybrid outputs were identical: 500 proposals, 100% overlap,
231/591 truth coverage, 61/204 cross-site, 115/208 bridge, 0/312 protected, and
zero generic-hub proposals. Provider calls were zero.

Repeated runs, reversed input, and shuffles 7/19/1101 produced identical
post-rerank semantic fingerprints at both 500 and 5k. Canonical insertion order,
fixed seed, fixed parameters, and current-library versions are mandatory parts
of the future contract; incidental parallel build order is not allowed.

### Scale, memory, and crossover observations

Selector-only timings exclude the shared O(n) vector construction and are
comparable with the PRE2 exact-selector observation.

| Records | Exact deterministic | Selected LSH + exact rerank | Candidate enumerations | Exact reranks | Vector bytes | Index-array bytes |
|---:|---:|---:|---:|---:|---:|---:|
| 500 | 0.152 s | 0.596 s | bounded | at most 160,000 | 768,000 | 159,456 |
| 1,000 | 0.600 s | 1.189 s | bounded | at most 320,000 | 1,536,000 | 171,456 |
| 2,000 | 2.584 s | 2.366 s | bounded | 640,000 | 3,072,000 | 195,456 |
| 5,000 | 15.185 s | 7.433 s | 15,287,982 | 1,600,000 | 7,680,000 | 267,456 |
| 20,000 | not rerun; quadratic reference | 31.987 s | 46,493,221 | 6,400,000 | 30,720,000 | 627,456 |
| 100,000 | prior discovery still running at 300 s | 308.493 s | 320,810,636 | 32,000,000 | 153,600,000 | 2,547,456 |

The 100k prototype completed and is plausibly executable, but exceeded the
preferred 300-second evidence target by 8.493 seconds. This authorizes bounded
production implementation and optimization, not GF-11B or 100k graduation.
Measured peak RSS remains unavailable on this Windows runtime. Reported array
bytes exclude Python bucket-object overhead; batched exact rerank may add about
31.5 MB of transient float32 candidate-vector storage at pool 320.

The measured crossover is approximately 2,000 eligible records. Proposed
future policy: exact deterministic character retrieval for `N < 2,000`; the
approved LSH candidate path for `N >= 2,000`. The threshold is a proposed
production contract input, not activated by this decision commit and never
selected from incidental machine load.

### Option/Pareto matrix

| Architecture | Deterministic/auditable | Dependency | Measured quality/safety | 20k/100k | Memory/implementation risk | Decision |
|---|---|---|---|---|---|---|
| Exact brute force | yes after PRE2 | current only | reference truth | structurally quadratic; 100k baseline timed out | dense full-neighbor work | reference below threshold only |
| Fixed-seed LSH + exact rerank | yes with frozen canonical build/config | current NumPy/scikit-learn | pool 320 passes every measured coverage gate; 5k final hybrid identical | 31.987 s / 308.493 s | bounded arrays; moderate new adapter risk | selected |
| HNSW + exact rerank | unproven locally; requires fixed seed, canonical single-thread build and self-check | absent; likely `hnswlib` approval/pin | not benchmarked | potentially strong | native dependency and graph-build reproducibility risk | reject for this decision |
| FAISS-style + exact rerank | backend-specific; FAISS HNSW multi-thread add is not reproducible | absent; FAISS/BLAS approval/pin | not benchmarked | potentially strong | heaviest packaging/runtime surface, especially Windows | reject for this decision |
| Sparse exact character n-grams | deterministic but semantic change | current only | prior synthetic coverage passed | measured 64.11% pair overlap makes 100k implausible | large posting traversal | reject |

[`hnswlib`](https://github.com/nmslib/hnswlib) supports cosine, an explicit
random seed and thread controls and is
[Apache-2.0 licensed](https://github.com/nmslib/hnswlib/blob/master/LICENSE),
but it is not installed or locally reproducibility-tested. [FAISS supports
cosine through normalized dot product and is MIT
licensed](https://github.com/facebookresearch/faiss/blob/main/README.md), but
is also absent; [its reproducibility documentation identifies HNSW insertion
as a multithreaded exception](https://github.com/facebookresearch/faiss/wiki/Threads-and-asynchronous-calls).
No dependency is approved or added by this decision.

### Failure semantics and decision

A future LSH index-build failure, query failure, empty/undersized pool,
unsupported/fingerprint-mismatched configuration, or determinism self-check
failure must produce a typed discovery capability failure. Exact fallback is
allowed only when the declared eligible-record count is below the approved
exact threshold. A scan requiring LSH must never silently run brute force,
silently return fewer candidates, or adapt parameters from machine load.
Interrupted experiments/runs cannot report completion.

A1-A16 passed: stable exact reference; repeated and shuffled LSH determinism;
canonical exact rerank; pool/top-k validation; frozen 384-bin exact cosine;
ANN-native score isolation; protected/cross-site/bridge gates; truth isolation;
zero provider calls; no database/default database; truthful interruption;
complete algorithm fingerprint; and explicit unavailable/unsupported backend
failure. HNSW and FAISS quality benchmarks were N/A because no such dependency
is locally installed and installation was prohibited.

Decision: authorize **fixed-seed random-hyperplane LSH candidate generation plus
exact current-cosine reranking**, with the measured pool-320 contract as the
only production implementation target. GF-11B production hardening remains
blocked and unverified until that separate production implementation,
fingerprinting, typed failure handling, and scale regression pass.

## GF-11B Production Fixed-Seed LSH Hardening

Status: **INSUFFICIENT / NOT VERIFIED**. The production adapter, deterministic
strategy boundary, fingerprinting, typed failures, and bounded work metrics are
implemented and pass their focused and 5k quality gates. The required 20k
normal-discovery gate does not pass, so GF-11B cannot be marked verified.

The frozen production contract is `character-retrieval-strategy-v1`. Scans
below 2,000 records retain the PRE2 exact selector; scans at or above 2,000 use
`fixed-seed-cosine-lsh-exact-rerank-v1`: eight tables, 12 bits/table, NumPy
PCG64 seed 1101, Hamming radius two, bucket-read bound 640, gather bound 1,280,
candidate pool 320, and current final top-k five. Candidate retention is bit
agreement descending then GF1 `record_ref_key` ascending. Final selection is
exact current cosine descending then the same canonical tie key. No approximate
score becomes output, and exact/safety channels and downstream fusion/caps are
unchanged.

The discovery configuration moved to `identity-discovery-config-v3` and the
algorithm to `identity-discovery-v3-character-strategy`. Its configuration JSON
includes selected strategy, activation threshold, LSH/vector/rerank versions,
NumPy and scikit-learn versions, seed, tables, bits, probe/bucket/gather bounds,
pool, top-k, and stable ordering policies. The observed large-scan production
contract fingerprint was
`4b76491de0baafcf5b147ccb2a6f69c7c44395b73f83c62cb36c8f845e092557`.
Historical runs remain immutable.

Large-scan failures are typed as `LSH_INDEX_BUILD_FAILED`, `LSH_QUERY_FAILED`,
`LSH_CANDIDATE_POOL_INSUFFICIENT`, `LSH_CONFIGURATION_INVALID`, or
`LSH_DETERMINISM_VALIDATION_FAILED`. They propagate as failed discovery; there
is no large-scan brute-force fallback and no partial-success result.

Measured production quality and work:

| Records | Strategy | Character result | Final hybrid | Bucket reads | Exact reranks | Character time |
|---:|---|---|---|---:|---:|---:|
| 500 | exact | 60/60 truth, 31/31 protected, 20/20 cross-site, 21/21 bridge | exact reference 388/388 | N/A | exact reference | 0.144 s |
| 5,000 | LSH | 591/591 truth, 312/312 protected, 204/204 cross-site, 208/208 bridge | exact reference 500/500, 100% overlap | 15,287,982 | 1,600,000 | 8.259 s |
| 20,000 | LSH | isolated selector completed | combined hybrid retained 500 | 46,493,221 | 6,400,000 | 34.639 s in the combined final observation |

The 5k normal policy-v2 pipeline completed discovery in 57.731 seconds versus
the 73.99-second GF-11A baseline, persisted 20,500 proposals and 20,500 signed
edges, formed 1,684 neighborhoods with maximum resolver work unit 1,250, then
reached the same truthful `IDENTITYRESOLUTIONVALIDATIONERROR` in GF-5. Every
persisted safety count remained zero, including provider, pair, G1, G2-v1, and
shadow writes.

The 20k normal run failed the acceptance gate twice: under the unchanged
300-second bound it timed out in discovery after a final 11.630-second catalog,
with zero proposals committed. This is worse than GF-11A's completed
219.86-second discovery and therefore is not a material improvement. Isolated
20k exact lexical construction/query took 72.181 seconds; the full in-memory
hybrid retriever took 99.804 seconds, including 34.639 seconds for character
LSH. The remaining greater-than-188-second discovery cost is outside the
combined hybrid retriever and is the measured dominant residual.

The canonical 100k normal attempt also timed out in discovery at 300.030
seconds after a 61.289-second catalog, with zero proposals committed. No 100k
production character-completion claim is made. Partial-state safety observations
were all zero. The bound was not increased.

P1-P20 passed. Canonical 5k production LSH repeat, reverse, and shuffles
7/19/1101 all produced semantic fingerprint
`e98e5a1ac481b6c586eea1acc26b78643bc834011d74e4b6c560ae5e59f67c96`
with exactly 1,600,000 reranks per run. Production code imports no benchmark
truth and has no provider surface. No schema, migration, or dependency changed.

GF-11B is insufficient against its acceptance contract because full 20k
discovery did not materially improve and 100k discovery did not complete.
The next evidence-driven work must isolate and bound the measured non-hybrid
discovery/cache/persistence path before any GF-11C definition or readiness claim.

## GF-11B Residual Discovery Attribution

Status: **GF-11B-RESIDUAL VERIFIED; GF-11B remains INSUFFICIENT / NOT
VERIFIED**. This measurement-only prerequisite used the exact production
`ScanRunner` discovery path on disposable SQLite databases and stopped at the
GF-4 boundary. It changed no production algorithm, configuration, persistence,
schema, migration, dependency, identity rule, or provider behavior.

### MEASURED

All times are seconds. The 500 and 5k observations include cProfile. The 20k
attribution observation disables cProfile to separate profiler overhead; a
separate cProfile-enabled 20k run completed production DISCOVERY at 289.867
seconds but hit the 300.102-second bound while finalizing the benchmark report.
That bounded run therefore supplies completed bucket/query evidence, not a
production discovery timeout claim.

| Non-overlapping bucket | 500 | 5k | 20k |
|---|---:|---:|---:|
| Discovery fingerprinting | 0.011 | 0.022 | 0.039 |
| Standard blocking/scoring | 34.725 | 41.239 | 14.157 |
| Retrieval total | 2.687 | 69.464 | 121.674 |
| Post-retrieval proposal materialization | 0.069 | 1.659 | 0.754 |
| GF-2 proposal materialization | 3.188 | 3.692 | 1.355 |
| GF-2 proposal persistence | 0.959 | 0.891 | 0.882 |
| GF-2 commit | 0.007 | 0.009 | 0.009 |
| GF-3 neighborhood construction | 1.670 | 3.386 | 2.841 |
| GF-3 neighborhood persistence | 0.363 | 1.042 | 1.283 |
| GF-3 commit | 0.018 | 0.024 | 0.026 |
| Final validation/reconstruction | 0.907 | 2.309 | 2.527 |
| Other unattributed | 0.375 | 1.149 | 1.265 |
| **Discovery total** | **44.977** | **124.886** | **146.811** |
| Total attributed | 99.167% | 99.080% | 99.138% |
| Post-retrieval total | 7.200 | 13.036 | 9.696 |
| Post-retrieval attributed | 99.610% | 99.743% | 99.702% |

The 20k retrieval decomposition was cache load 0.072, cache save 15.133,
character LSH 31.754, lexical vectorization 1.173, lexical nearest neighbors
30.373, and other channels/fusion/materialization 43.169. The final retrieval
cap remained 500.

| Count | 500 | 5k | 20k |
|---|---:|---:|---:|
| Standard pair objects | 19,326 | 20,000 | 20,000 |
| GF-2 proposal rows | 19,328 | 20,500 | 20,500 |
| Embedding-cache rows requested | 352 | 3,509 | 14,041 |
| GF-3 neighborhoods | 500 | 1,684 | 5,654 |
| GF-3 members | 10,000 | 22,761 | 26,734 |
| Maximum neighborhood members | 20 | 20 | 20 |
| SELECT executions | 368 | 3,525 | 14,057 |
| INSERT executions | 1,356 | 6,882 | 25,354 |
| executemany observations | 502 | 1,325 | 5,063 |
| UPDATE executions | 2 | 2 | 2 |
| observed commits | 3 | 3 | 3 |

Cache rows grew 9.97x from 500 to 5k and 4.00x from 5k to 20k. Cache
persistence issued exactly one SELECT and one INSERT per requested row at every
scale: 352/352, 3,509/3,509, and 14,041/14,041. Total SELECTs grew 9.58x then
3.99x. Neighborhoods grew 3.37x then 3.36x; members grew 2.28x then 1.17x.
Profiled wall time grew 2.78x from 500 to 5k. A wall-time growth ratio across
5k and 20k is intentionally not treated as algorithm evidence because only the
former includes cProfile.

The canonical 5k cProfile hot paths by cumulative time were retrieval 69.447,
candidate scoring/evaluation 31.534/31.028/30.981 across 20,500 calls, variant
extraction 30.172 across 176,538 calls, eligibility/allowed-pair evaluation
28.622/27.584 across 68,858 calls, character LSH 25.656, and standard candidate
generation 11.665. Largest self-time entries included character LSH 14.477,
regex compilation 3.735, variant extraction 3.220, and regex search 3.037.
The 20k cProfile-enabled process completed all production discovery buckets;
its raw function table was unavailable because report finalization crossed the
bound. No raw profile dump, SQL parameter, absolute path, hostname, username,
or inventory value was retained.

Proposal and neighborhood fingerprints were identical with profiling enabled
and disabled at the focused semantic gates. The completed 5k fingerprints were
`369fec5ae1653622d9a754ffc0a2191e1188dfa9c2ddd2af22369d5148875e8d`
and `756b2c967ccea72dfa8a06293bbe4d53515dc76185bdba8e7ee806e1a06d50e9`.
The completed 20k observation produced 20,500 proposals and 5,654
neighborhoods/26,734 members with proposal fingerprint
`0d0565f2b4c77a0398ffe36dcb081498fcb4499de0958592d10be0ed76621272`
and neighborhood fingerprint
`60fd2f95b2e44f0e3b7953f306f97f69fac3d851935b3e3f176aa8c57473dc6e`.
Provider requests were zero.

### INFERRED

The earlier claim that approximately 188--200+ seconds occur after hybrid
retrieval is not reproduced by exact call-boundary measurement. Post-retrieval
work was only 7.200, 13.036, and 9.696 seconds. GF-3 is inside DISCOVERY, but
GF-2/GF-3 persistence and all three commits are not dominant. The largest 20k
bucket is retrieval itself, and its largest measured sub-bucket is other
channels/fusion/materialization. cProfile associates that path with repeated
eligibility/allowed-pair checks, variant extraction, and candidate scoring.
The cache-save path is independently query-amplified and approximately linear
in missing vectors, but at 15.133 seconds it is not the largest 20k target.

### NEXT-HYPOTHESIS

The one bounded next GF-11B hardening target is **repeated eligibility and
variant-extraction work in hybrid other-channel fusion/materialization**. Any
optimization requires a separate prompt and must preserve every retrieval,
proposal, neighborhood, identity, and safety fingerprint. GF-11C is not
started.
