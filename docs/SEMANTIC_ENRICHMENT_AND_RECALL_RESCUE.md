# Semantic enrichment and recall rescue

## Architecture

The standard deterministic engine remains the precision authority. After its scan transaction commits, a separate deterministic recall-expansion pass builds a bounded pool below the normal review threshold. Unique records from standard review candidates and that pool are enriched as independent records. Durable semantic profiles are compared locally; only unresolved pairs use `candidate-triage-v3`. Every persisted result remains advisory and requires the existing human review controls.

The method is **Deterministic recall expansion + semantic adjudication**. The LLM does not discover pairs, group candidates, cluster records, or infer transitive relationships.

## Enrichment contract and batching

`INVENTORY_RECORD_ENRICHMENT` uses prompt version `inventory-record-enrichment-v1`. One request contains at most 12 independent records by default and returns one bounded typed profile per `record_id`. Approved inputs are part number, description, UOM, site/contract, product category, and HSN/SAC code. The contract requires null or `UNKNOWN` for insufficient evidence, separates administrative tokens from physical identity, and prohibits comparisons and duplicate decisions.

The defaults are:

- enrichment enabled: `true`
- batch size: `12` (maximum 20)
- records per scan: `200` (maximum 500)
- concurrency: `1` (maximum 2)

Valid partial results are saved immediately. Unknown IDs are ignored. Missing or invalid IDs are retried in smaller batches, then individually. Successful profiles are never resent. Existing pacing, bounded retries, exponential backoff, `Retry-After`, safe failure categories, pause/resume, and circuit-breaker behavior apply.

## Durable cache and fingerprint

`llm_semantic_profile` is a cross-scan cache keyed uniquely by evidence fingerprint, model, and prompt version. The SHA-256 fingerprint covers only normalized bounded evidence plus `semantic-evidence-v1`, the model, prompt version, and `domain-dictionary-v1`. It excludes `record_id`, scan identity, secrets, prompts, provider responses, headers, and raw exceptions. Field ordering and whitespace/case changes do not change identity.

Only typed profile JSON and safe state/error metadata are stored. Complete rows and source files are never stored in the semantic cache.

## Deterministic profile comparison

The pure comparator makes no provider call. Explicit product, purpose, model, material, size/rating, side/placement, application, or technical-role conflicts support non-duplicate review. Specific canonical equivalence without such conflict supports duplicate prioritization. Part-number, prefix, punctuation, spelling, and formatting differences are neutral. Generic descriptions and matching site/UOM/administrative evidence alone remain inconclusive.

The outcomes are `SUPPORTS_DUPLICATE`, `SUPPORTS_NON_DUPLICATE`, and `INCONCLUSIVE`, with bounded reason codes. They map to `LLM_LIKELY_DUPLICATE`, `LLM_DOWNGRADED`, and `HUMAN_REVIEW`; none is a final business decision.

## Recall expansion

Recall expansion runs after the standard scan commit and does not modify the standard candidate generator. It reuses normalized descriptions/part numbers, character TF-IDF, fuzzy similarity, technical tokens, and existing hard rules. Its conservative score floor is **62**, below the normal 75 review threshold. Defaults are top-K **3** per record, pool cap **50**, and pairwise fallback cap **10**.

Self-pairs, identical part numbers, standard candidates, terminal exclusions, hard conflicts, critical mismatches, and generic-only pairs are excluded. Canonical pairs are deduplicated, reciprocal top-K is preferred, and deterministic rank/caps apply before provider work. Non-duplicate semantic results are discarded. Duplicate results are persisted; inconclusive results use the bounded pairwise fallback. Rescue candidates always remain `POSSIBLE_DUPLICATE_REVIEW / UNREVIEWED` and never become deterministic `LIKELY_DUPLICATE`.

## Provenance and human boundary

`candidate_discovery_metadata` separates candidate source (`DETERMINISTIC_STANDARD` or `DETERMINISTIC_RECALL_EXPANSION`) from resolution source (`SEMANTIC_PROFILE_COMPARISON` or `PAIRWISE_LLM_FALLBACK`). Historical rows without metadata derive standard provenance. The API and UI separately expose deterministic status, semantic result, pairwise result, effective assisted status, and human review decision.

No automated path marks duplicate/not-duplicate, merges, deletes, changes source data, or writes to IFS. Human confirmation remains mandatory.

## API, UI, exports, and request reduction

The triage status includes safe cache, generation, failure, local-resolution, fallback, recall, cap, and provider-request counters. Candidate provenance is batch-loaded to avoid N+1 queries. The UI provides an AI-enhancement metrics panel and filters for standard, recall, semantic, and pairwise paths.

Legacy exports and their column ordering are unchanged. The enhanced candidate export appends candidate source, rescue score/signals, resolution source, and semantic prompt version. Export reads durable state only, performs zero provider calls, retains formula-injection protection and UTC handling, and exposes no raw provider material.

Batching reduces requests from one per candidate pair to roughly one per 12 unique cache misses, plus pairwise calls only for residual ambiguity. Repeated evidence becomes a zero-request cache hit.

## Failure handling and limitations

Provider failures use safe categories only. Successful batch members remain durable when siblings fail. Repeated retryable failures pause work, preserve pending records, and can be resumed. The recall pool is intentionally bounded and can miss distant semantic relationships; profile quality depends on supplied evidence; and all assisted outcomes remain review aids rather than authoritative decisions.
