# Hybrid candidate retrieval

## Decision boundaries

Hybrid retrieval only decides which missed pairs deserve bounded comparison work. Four boundaries remain separate:

1. **Blocking and eligibility** decide whether a pair may be considered. Scan mode, site/contract scope, existing hard identity rules, and critical variant rules live here. UOM compatibility is deliberately not an identity-eligibility gate.
2. **Retrieval evidence** ranks eligible pairs for candidate budget.
3. **Existing deterministic scoring** decides business status and remains authoritative.
4. **Human review** remains the final decision.

Blocking is not positive identity evidence. In particular, same-site scope, contract compatibility, UOM relationship, and cross-site policy never contribute a retrieval channel or make a pair multi-source. Historical `EXACT_BLOCK` is not a Ranking V2 retrieval channel.

## Physical identity and UOM mapping quality

Physical-item identity and ERP mapping quality are separate questions. A different, missing, wildcard, or malformed Inventory UOM cannot by itself suppress an otherwise eligible same-scope pair from `EXACT_DESCRIPTION`, `PART_NUMBER_FAMILY`, `LEXICAL`, `CHAR_VECTOR`, or `TECHNICAL_IDENTITY` retrieval. This hybrid-only compatibility seam does not change standard deterministic behavior when hybrid retrieval is disabled.

The deterministic pairwise taxonomy is:

- `SAME_UOM`: approved aliases resolve to the same unit, such as `litre` and `l`;
- `CONVERTIBLE_SAME_DIMENSION`: recognized units share a dimension, such as `l` and `liq qt`;
- `DIFFERENT_DIMENSION_OR_BASIS`: recognized units have different dimensions or storage bases, such as `PCS` and `l`;
- `MISSING_OR_WILDCARD`: either value is blank or an explicit bounded wildcard;
- `MALFORMED_OR_UNKNOWN`: a nonblank value is outside the small approved taxonomy.

UOM produces separate bounded provenance: `UOM_MATCH`, `UOM_CONVERTIBLE`, `UOM_DIFFERENT_BASIS`, `UOM_MISSING_OR_WILDCARD`, or `UOM_MALFORMED_OR_UNKNOWN`. Candidate metadata also exposes a 0%, 3%, 20%, 8%, or 12% retrieval-priority reduction respectively and mapping quality `CONSISTENT`, `POSSIBLE_MAPPING_ERROR`, or `UNKNOWN`. Percentage reduction keeps UOM proportional to Ranking V2 priority instead of overwhelming low-valued RRF results. UOM never becomes a retrieval source, never creates multi-source status, and never raises a weak pair into Tier A. A different-basis relationship prevents Tier A but remains eligible for lower-tier review when identity evidence is strong. Missing, wildcard, and malformed UOM remain visible data-quality evidence without blocking recall.

The standard deterministic scorer retains its historical UOM hard rule. Only hybrid candidates use the identity-safe mapping-review seam, remain subject to deterministic similarity and business evidence, and are forced to human review rather than automatic duplicate status. Hard technical conflicts and `critical_mismatches` remain authoritative in both paths. UOM alone never declares records the same item or different items.

## Retrieval channels

Ranking V2 keeps five explicit, independent channels:

- `EXACT_DESCRIPTION`: normalized descriptions are equal. Corpus specificity controls how valuable that equality is.
- `PART_NUMBER_FAMILY`: approved deterministic part-code aliases and complete normalized family signatures agree. A short superficial prefix is insufficient.
- `LEXICAL`: bounded character 3–5 gram TF-IDF nearest neighbours.
- `CHAR_VECTOR`: bounded nearest neighbours from the fixed hashing character-vector runtime.
- `TECHNICAL_IDENTITY`: existing deterministic technical extraction finds shared numbers, measurements, or dimensions.

Reciprocal lexical or character-vector selection is exposed as `LEXICAL_RECIPROCAL` or `CHAR_VECTOR_RECIPROCAL` and receives a small bounded preference. Reciprocity is not mandatory.

`sklearn-hashing-domain-v1` uses a 384-feature `HashingVectorizer(char_wb, 3–5 grams)`. It is a deterministic character-vector representation, **not a semantic embedding model**. It needs no fit, provider, network, model download, Torch, Transformers, or ONNX runtime. The existing cache and replaceable `LocalEmbedder` interface remain unchanged.

## Description specificity and generic suppression

Each scan computes bounded, deterministic corpus statistics:

- normalized-description frequency;
- per-token document frequency and IDF;
- informative-token ratio;
- generic-token ratio;
- description length.

These become `description_specificity_score` and `generic_description_penalty`, both bounded to 0–100. Rare, informative engineering descriptions rank above repeated or generic descriptions. Known phrases such as `PART`, `NORMAL TIME`, `INVENTORY PART`, `BRACKET`, `TEST`, and `CIRCUIT BOARD` receive explicit generic penalties. High-frequency descriptions receive `HIGH_DESCRIPTION_FREQUENCY`. Very short generic exact matches need independent identity evidence and cannot enter Tier A merely because their text is equal.

No unbounded corpus structures are stored on candidate rows.

## Conflicts

Existing hard conflicts remain absolute exclusions and are not changed by retrieval. Ranking V2 also exposes bounded soft ranking reasons:

- `GENERIC_DESCRIPTION`;
- `HIGH_DESCRIPTION_FREQUENCY`;
- `WEAK_SINGLE_CHANNEL`;
- `OPPOSITE_VARIANT_TERM`;
- `TECHNICAL_CONFLICT`.

For example, `SERIAL` versus `NON SERIAL` receives a strong priority reduction and cannot enter Tier A. Existing color, side, electrical-rating, dimension, and other critical mismatches remain excluded before ranking. A conflict is never converted into positive technical evidence.

## Weighted Reciprocal Rank Fusion

Raw channel similarities are not added together. Candidate priority uses channel ranks:

```text
RRF(pair) = Σ channel_weight / (60 + channel_rank)
```

Constants:

```text
RRF_K = 60
EXACT_DESCRIPTION = 2.4
PART_NUMBER_FAMILY = 2.2
TECHNICAL_IDENTITY = 1.8
LEXICAL = 1.0
CHAR_VECTOR = 0.9
```

The RRF value is normalized below 100, then receives at most four points of reciprocal-neighbour preference. Generic, conflict, and bounded UOM penalties are applied after fusion. Missing channels contribute zero. Ties are resolved by tier, priority, specificity, and canonical record order. Blocking and UOM signals contribute zero channels.

The durable and user-visible value is `retrieval_priority`. Historical `retrieval_score` remains readable and is populated as a compatibility alias. Neither value is duplicate confidence.

The V1 `HYBRID_RETRIEVAL_VECTOR_WEIGHT` and `HYBRID_RETRIEVAL_MIN_SCORE` settings remain accepted for environment compatibility but do not participate in Ranking V2 fusion or tier allocation.

## Tiered candidate budget and fairness

Candidates are allocated in deterministic order:

- `TIER_A`: specific exact descriptions or equally strong corroborated part-family/technical evidence without meaningful conflict;
- `TIER_B`: strong multi-channel or reciprocal evidence without conflict;
- `TIER_C`: exploratory, generic, weak single-channel, or conflict-penalized evidence.

Defaults retain the global 500-pair cap:

```text
HYBRID_RETRIEVAL_TIER_A_MAX=250
HYBRID_RETRIEVAL_TIER_B_MAX=200
HYBRID_RETRIEVAL_TIER_C_MAX=50
HYBRID_RETRIEVAL_MAX_PAIRS_PER_SCAN=500
HYBRID_RETRIEVAL_FINAL_TOP_K=10
HYBRID_RETRIEVAL_FAMILY_MAX=25
```

Tier A is allocated first, so strong must-not-miss candidates are not displaced by a generic family encountered earlier. Per-record top-K and per-description-family caps prevent a large repeated family from dominating the global budget. Metrics expose maximum candidates for one record, largest retained description-family count, and candidate-family concentration.

## Persistence, API, UI, and exports

Existing provenance tables are extended rather than duplicated. Candidate metadata stores sources, priority, tier, specificity, generic penalty, bounded conflict reasons, reciprocal evidence, channel scores, rank, model version, separate blocking metadata, UOM relationship/evidence/penalty, and mapping quality. Historical rows return unknown values when UOM fields are absent.

Scan metrics include Tier A/B/C counts, each retrieval channel, reciprocal candidates, generic/conflict penalties, cap skips, family concentration, each UOM relationship considered before budget selection, and added-candidate counts for differing or unknown UOM. Candidate APIs batch-load provenance with existing metadata queries, avoiding per-candidate lookup. Historical scans return `null` for unavailable persisted UOM metrics. The UI calls the hashing channel “Character vector”, describes priority as candidate-budget allocation rather than confidence, and labels differing UOM as a possible mapping/unit inconsistency requiring identity review.

### Pre-scoring and post-scoring metric stages

The observable scan pipeline is:

```text
retrieval selected
→ deterministic rescoring and safety checks
→ post-scoring exclusions
→ hybrid candidates added
```

`hybrid_retrieval_selected_count` is the sum of the selected Tier A, Tier B, and Tier C aliases. These pairs have passed bounded ranking, global/tier budgets, per-record limits, and family limits, but have not yet passed the existing post-retrieval deterministic gate. Historical `tier_a_candidates`, `tier_b_candidates`, and `tier_c_candidates` remain available for compatibility.

`hybrid_post_scoring_excluded_count` records how many selected pairs the unchanged deterministic gate excluded. `hybrid_post_scoring_exclusion_reasons` contains at most 20 deterministically ordered reason-code counts and never contains record descriptions. `hybrid_candidates_added` counts only selected pairs that survive that gate and are added to the scan candidate set. For newly recorded successful scans:

```text
hybrid_candidates_added
= hybrid_retrieval_selected_count - hybrid_post_scoring_excluded_count
```

Historical scans created before these fields return `null` for post-scoring exclusion metrics rather than inferring unavailable facts.

`hybrid_candidates_skipped_by_budget` is a clearer alias of the existing `hybrid_candidates_skipped_by_cap`. Both count pairs omitted during bounded retrieval selection by tier, global, per-record, or description-family controls. They do not include deterministic post-scoring exclusions. The UI labels these stages as “Retrieval selected,” “Excluded after deterministic checks,” “Hybrid candidates added,” and “Skipped by candidate budget.”

Legacy exports and their column ordering remain unchanged. The enhanced export preserves all prior columns and appends:

```text
retrieval_tier
retrieval_priority
description_specificity_score
generic_description_penalty
retrieval_conflict_signals
reciprocal_sources
uom_relationship
uom_evidence
uom_penalty
mapping_quality
```

Enhanced export reads durable rows only, makes zero provider calls, and retains CSV formula-injection and UTC safeguards.

## Offline quality benchmark

`hybrid_retrieval_benchmark.py` provides a deterministic provider-free fixture with silver-positive engineering pairs and challenge-negative/generic pairs. It reports:

- silver recall at the global budget;
- silver recall at top-K;
- Tier-A silver recall;
- generic and conflict candidate rates;
- average candidates per record;
- largest-family share;
- distinct priority count;
- provider request count.

The benchmark measures retrieval quality only. It does not label final duplicates.

## Provider independence and limitations

Retrieval constructs no LLM provider and works with `LLM_PROVIDER=none`. Optional semantic enrichment and Groq triage remain downstream and unchanged. No automatic path merges, deletes, or makes a human decision.

The current lexical and hashing indexes are bounded MVP components, not claimed million-row infrastructure. Character features improve deterministic local recall but do not provide deep language semantics. The UOM taxonomy intentionally covers only a small approved set of aliases and dimensions; it does not calculate quantities, package conversions, or commercial equivalence. Unknown units require data stewardship or human review. A future, separately provisioned true semantic embedding/ANN stage can implement `LocalEmbedder` without changing deterministic scoring, retrieval contracts, or human governance.
