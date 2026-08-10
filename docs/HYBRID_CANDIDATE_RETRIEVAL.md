# Hybrid candidate retrieval

## Purpose and architecture

Global all-pairs comparison grows quadratically and is not a viable million-record retrieval design. The application therefore keeps the existing deterministic generator as its protected precision baseline and adds a bounded retrieval layer after it:

1. exact/business blocking;
2. lexical nearest-neighbour retrieval;
3. local vector retrieval;
4. deterministic merge, deduplication, ranking and top-K caps;
5. existing hard rules and deterministic scoring;
6. optional downstream semantic/LLM assistance only for eligible uncertainty;
7. human review.

Retrieval answers only which records deserve detailed comparison. Its score is a ranking signal, **not duplicate confidence**.

## Exact and business blocking

Inverted indexes use normalized description, normalized part-number root and bounded technical-measurement keys. Buckets are capped at 50 records. Self-pairs, identical part numbers, duplicate canonical pairs, scan-mode violations, hard-rule exclusions and critical variant conflicts are removed. Same-site mode requires compatible sites; cross-site standardization requires different sites when both are known. Accounting mappings are not physical-identity exclusions.

## Lexical retrieval

The lexical channel uses the already-pinned scikit-learn TF-IDF stack with character 3–5 grams and bounded nearest-neighbour queries. It reuses the project’s normalized descriptions and returns five neighbours per record by default. It does not introduce a second search dependency.

## Local vector retrieval and runtime decision

The local embedding implementation is `sklearn-hashing-domain-v1`: a fixed 384-feature, CPU-friendly `HashingVectorizer` over normalized text plus retrieval-only inventory abbreviations such as `MTR`, `BRG`, `DE`, `NDE`, `ASSY`, and `VLV`. Fixed hashing requires no corpus fitting, network, API, model download, Torch runtime, or model binary. A fixed model/version/input produces deterministic vectors.

This choice uses the existing pinned `scikit-learn==1.7.0` dependency. Adding sentence-transformers would introduce a large Torch/Transformers runtime and external model acquisition into the small offline MVP. The `LocalEmbedder` interface allows a locally provisioned sentence model or production vector service to replace the current embedder later without changing retrieval contracts.

## Vector cache and future index path

`local_embedding_cache` stores a secret-free normalized-record fingerprint, embedding model/version, bounded vector JSON, state, and generation time. Unchanged records reuse vectors across scans. SQLite is only the bounded MVP cache; it is not presented as a million-row vector database.

The intended production path is durable source datasets in Parquet/object storage, separately built lexical/vector indexes, and top-K query services backed by PostgreSQL metadata and an ANN-capable vector index. The retrieval interfaces avoid coupling downstream scoring to SQLite or to global pair materialization.

## Merge and ranking

Canonical pairs merge evidence from `EXACT_BLOCK`, `LEXICAL`, and `VECTOR`. Multiple channels produce `MULTI_SOURCE`. With the default vector weight of `0.4`, the deterministic score is:

```text
lexical × 0.6 + vector × 0.4
+ 15 for exact blocking
+ 10 for multi-source support
```

Scores below 55 are discarded. Ranking prefers more independent sources, then retrieval score, then canonical record order. Defaults are lexical top-K 5, vector top-K 5, final top-K 10 per record, and 500 pairs per scan. All settings have tight validation bounds. Nearest-neighbour queries run in batches and return bounded outputs; the system does not construct a global pair matrix.

## Integration and provenance

When `HYBRID_RETRIEVAL_ENABLED=false`, the existing generator path is unchanged. When enabled, standard candidates are preserved and excluded from hybrid duplication. Additional pairs pass through existing hard rules and deterministic scoring. Hybrid-only additions that would otherwise be deterministic `LIKELY_DUPLICATE` are constrained to `POSSIBLE_DUPLICATE_REVIEW`, preserving the human boundary.

`candidate_discovery_metadata` records `HYBRID_RETRIEVAL`, retrieval sources/scores/rank, and embedding model version. `hybrid_retrieval_run` stores bounded scan metrics: indexed records, lexical/vector/multi-source candidates, additions, cap skips, per-record averages/maxima, runtime, and a provider-request count fixed at zero.

## LLM relationship and disabled-provider operation

Hybrid retrieval is the normal recall mechanism. When enabled, the older deterministic recall-rescue pool is not scheduled as a parallel LLM-dependent discovery path. Cached semantic profiles and pairwise triage remain optional downstream aids governed by existing eligibility. Retrieval never constructs an LLM provider and works with `LLM_PROVIDER=none`.

No automated path merges, deletes, writes back, or makes a final review decision. Human confirmation remains final.

## API, UI and exports

Scan detail exposes safe retrieval metrics. Candidate responses expose source, retrieval sources, retrieval score, lexical/vector scores, rank, and model version using batch-loaded metadata. The UI includes a Candidate retrieval panel and Standard/Hybrid source filters. Hybrid details label retrieval score as ranking, not confidence.

Legacy exports and their ordering remain unchanged. The enhanced export appends retrieval provenance after the existing assisted columns and reads durable data only, making zero provider calls while retaining CSV formula protection and UTC formatting.

## Configuration

```text
HYBRID_RETRIEVAL_ENABLED=true
HYBRID_RETRIEVAL_LEXICAL_TOP_K=5
LOCAL_EMBEDDING_ENABLED=true
LOCAL_EMBEDDING_MODEL=sklearn-hashing-domain-v1
HYBRID_RETRIEVAL_VECTOR_TOP_K=5
HYBRID_RETRIEVAL_VECTOR_WEIGHT=0.4
HYBRID_RETRIEVAL_FINAL_TOP_K=10
HYBRID_RETRIEVAL_MIN_SCORE=55
HYBRID_RETRIEVAL_MAX_PAIRS_PER_SCAN=500
```

## Current limitations

The hashing embedder provides deterministic local semantic-feature retrieval after domain expansion, not deep pretrained language understanding. The SQLite cache and exact nearest-neighbour implementation are bounded MVP components and have not been benchmarked at one million records. The architecture is million-scale compatible because retrieval/index interfaces replace pair materialization; it makes no unsupported throughput claim.
