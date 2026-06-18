# Redesigned Deterministic Duplicate Engine

## Purpose

The redesigned engine is an ERP Part Master identity-resolution engine for CSV exports that use IFS-compatible field names. It is not a simple text similarity checker. Its job is to produce human-review-ready duplicate candidates, related-but-different decisions, data-conflict warnings, and explanations.

The engine is deterministic and local:

- No LLM or paid AI API is used.
- No real IFS Cloud, Projection, OAuth, or direct table integration is implemented.
- The output is advisory. It does not confirm duplicates and does not merge records.

## Pipeline Flow

1. Data profiling and input preparation

   CSV rows are validated by the existing scan flow before the redesigned engine runs. Required fields remain `PART_NO` and `DESCRIPTION`. Optional ERP fields are carried forward when available. Blank descriptions are excluded from scan comparison by the existing runner.

2. Normalization

   `app.engine.normalizer` converts descriptions and part numbers into stable business tokens. It handles spelling and ERP shorthand such as:

   - `DEC`, `DESICATED`, `DECICATED` -> `desiccated`
   - `COCO`, `CO` -> `coconut`
   - `C01`, `CO1` -> `type 1`
   - `FLT` -> `filter`
   - `GEN` -> `generator`

   Technical differentiators such as `20a`, `30a`, `1l`, `10mm`, colors, and type codes are preserved.

3. Attribute extraction

   `app.engine.attribute_extractor` extracts structured evidence from part number, description, and optional master description:

   - product class
   - application context
   - function/media
   - color
   - rating
   - size
   - volume
   - type code
   - material
   - packaging
   - generic terms

4. Candidate generation

   `app.engine.candidate_generator` creates recall-friendly pairs using selected business fields, normalized description tokens, normalized part-number tokens, and extracted attributes. It avoids self-pairs and reverse duplicate pairs.

5. Similarity scoring

   `app.engine.similarity` calculates deterministic local similarity. It compares normalized descriptions, part numbers, technical tokens, master descriptions when present, and structured attribute overlap. It also exposes mismatch evidence, for example `rating_match = false`.

6. Deterministic guardrails

   `app.engine.guardrails` detects conflicts and warnings before final status assignment:

   - hard conflicts: rating, color, type code, function/media
   - data conflicts: `HSN_SAC_CODE`, `SAFETY_CODE`
   - warnings: generic/sparse descriptions, application-context mismatch
   - scope warnings/conflicts: cross-site `CONTRACT` handling

7. Decision engine

   `app.engine.decision_engine` combines candidate evidence, similarity, and guardrails into one of these statuses:

   - `DUPLICATE_CANDIDATE`
   - `POSSIBLE_DUPLICATE_REVIEW`
   - `RELATED_BUT_NOT_DUPLICATE`
   - `DATA_CONFLICT_REVIEW`
   - `CROSS_SITE_STANDARDIZATION_CANDIDATE`
   - `INSUFFICIENT_DATA`
   - `UNIQUE_NO_MATCH`

8. Explanation generation

   `app.engine.explanations` creates deterministic, business-readable explanations. Examples:

   - `DEC CO1` vs `DEC C01`: descriptions and part numbers match after normalization.
   - `MCB 20A` vs `MCB30A`: both are MCB items, but rating differs.
   - `RED PAINT` vs `BLUE PAINT`: both are paint items, but color differs.

9. Result adapter

   `app.engine.result_adapter` maps redesigned `DecisionResult` objects into the existing scan candidate shape. This preserves current frontend/API compatibility while adding redesigned evidence fields.

10. API persistence and CSV export

   Candidate evidence is persisted through the existing repository and DB model. CSV export includes old fields plus redesigned evidence fields using safe serialization.

## Engine Switch

The redesigned engine is controlled by:

```text
USE_REDESIGNED_ENGINE=false
```

Default is `false`, so the legacy scan path remains active unless explicitly enabled.

To enable the redesigned path:

```powershell
$env:USE_REDESIGNED_ENGINE="true"
uvicorn app.main:app --reload
```

Docker/Kubernetes deployments can set the same environment variable through Compose or ConfigMap values.

## Current API Candidate Fields

The candidate API keeps legacy fields:

- `similarity_score`
- `final_score`
- `score`
- `reason`
- `recommended_action`
- `review_status`
- `matched_fields`
- `mismatched_fields`

It also returns redesigned fields:

- `confidence_score`
- `business_status`
- `matched_evidence`
- `differences`
- `warnings`
- `rule_decision`
- `rejection_reason`
- `normalized_part_no_a`
- `normalized_part_no_b`
- `normalized_description_a`
- `normalized_description_b`
- `extracted_attributes_a`
- `extracted_attributes_b`

For redesigned results, `confidence_score` and `similarity_score` currently use the same numeric value.

## CSV Export Fields

CSV export keeps existing columns and adds:

- `confidence_score`
- `matched_evidence`
- `differences`
- `warnings`
- `extracted_attributes_a`
- `extracted_attributes_b`

Serialization rules:

- Lists export as `; ` joined readable strings.
- Dictionaries export as compact JSON.
- Missing or `None` values export as blank.
- Existing spreadsheet formula sanitization remains active.

## Saved Statuses

The scan path saves candidates that meet the configured threshold. With a low threshold such as `0`, the redesigned path can persist advisory statuses including:

- `DUPLICATE_CANDIDATE`
- `RELATED_BUT_NOT_DUPLICATE`
- `POSSIBLE_DUPLICATE_REVIEW`
- `INSUFFICIENT_DATA`
- `DATA_CONFLICT_REVIEW`
- `CROSS_SITE_STANDARDIZATION_CANDIDATE`

With higher thresholds, low-scoring review candidates may be generated by the isolated pipeline but not persisted by the scan runner.

## Important Safety Boundaries

- The system identifies possible duplicate candidates, not confirmed duplicates.
- Human review remains required.
- Related variants such as red vs blue paint or 20A vs 30A MCBs should not be treated as normal duplicates.
- Real IFS integration is future work only.
- The deterministic engine should be validated on company-specific historical review data before production use.

## Test Coverage

Relevant backend tests:

- `tests/test_normalizer.py`
- `tests/test_attribute_extractor.py`
- `tests/test_candidate_generator.py`
- `tests/test_similarity.py`
- `tests/test_guardrails.py`
- `tests/test_decision_engine.py`
- `tests/test_explanations.py`
- `tests/test_pipeline.py`
- `tests/test_result_adapter.py`
- `tests/test_redesigned_scan_e2e.py`
- `tests/test_export_evidence_fields.py`

Run:

```powershell
cd backend
python -m pytest
```
