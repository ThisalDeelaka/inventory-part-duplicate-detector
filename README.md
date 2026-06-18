# Part Master Duplication Identifier

**AI-Assisted ERP/IFS Part Master Identity Resolution Engine**

This project is a CSV-based demo for identifying possible duplicate ERP/IFS Inventory Part Master records. It is designed around real master-data behavior: part descriptions, part numbers, units of measure, product classifications, compliance fields, and business context all matter.

This is not a simple text similarity tool. The redesigned engine uses deterministic, business-rule-aware matching to produce review-ready duplicate candidates with scores, explanations, evidence, and safety warnings.

The system does **not** auto-merge records. It does **not** directly update IFS. Real IFS Cloud integration is future scope after the detection engine is validated.

## Business Problem

Part Master duplication is risky because text similarity alone creates noisy false positives. Similar descriptions can mean related but different inventory parts.

Examples handled by the redesigned engine:

- `MCB 20A` vs `MCB30A` are related electrical items, but not duplicates because the ampere rating differs.
- `Generator Fuel Filter` vs `Generator Air Filter` are related filters, but not duplicates because the filter function differs.
- `RED PAINT 1L CAN` vs `BLUE PAINT 1L CAN` are different color variants.
- `DEC CO1` vs `DEC C01` can be a likely duplicate after domain normalization maps both toward `desiccated coconut type 1`.
- `Labels` vs `Warning Labels` is too generic or sparse to confirm duplicate identity with high confidence.

The goal is to reduce manual review noise while preserving important uncertainty. Human review remains required.

## Engine Pipeline

```text
CSV Upload
  -> Normalization
  -> Attribute Extraction
  -> Candidate Generation
  -> Similarity Scoring
  -> Guardrails
  -> Decision Engine
  -> Explanation
  -> API Result
  -> Frontend Review
  -> Export
```

The engine combines normalized part numbers/descriptions, extracted attributes, local similarity scoring, deterministic guardrails, and explainable decision statuses. It is intentionally local and repeatable: no paid AI API and no LLM pairwise duplicate decision is used in the current version.

## Business Statuses

The system returns candidate statuses for human review. It never calls a pair a confirmed duplicate before review.

- `DUPLICATE_CANDIDATE`: Strong evidence suggests the records may represent the same part.
- `POSSIBLE_DUPLICATE_REVIEW`: Similar enough for manual review, but evidence is not strong enough for a higher-confidence candidate.
- `RELATED_BUT_NOT_DUPLICATE`: Items are similar or related, but a critical differentiator such as rating, color, type, or function indicates they should not be treated as duplicates.
- `DATA_CONFLICT_REVIEW`: A compliance or strong identity field differs, such as `HSN_SAC_CODE` or `SAFETY_CODE`; review as a data conflict, not as a confirmed duplicate.
- `CROSS_SITE_STANDARDIZATION_CANDIDATE`: Similar item appears across different sites/contracts and may be useful for standardization review.
- `INSUFFICIENT_DATA`: Description or evidence is too generic/sparse to safely classify as a duplicate candidate.
- `UNIQUE_NO_MATCH`: No meaningful duplicate evidence was found.

## Runtime Environment

The legacy scan behavior remains available. The redesigned deterministic engine is controlled by runtime flags.

`USE_REDESIGNED_ENGINE`

- Default: `false`
- Set to `true` to enable the redesigned deterministic engine.

`REDESIGNED_RESULT_MODE`

- Default: `review`
- `review` persists/shows review-ready statuses and hides debug-only related/no-match results.
- `all` persists/shows all statuses, including `RELATED_BUT_NOT_DUPLICATE` and `UNIQUE_NO_MATCH`, for debugging and analysis.

`REDESIGNED_INCLUDE_STATUSES`

- Optional comma-separated override.
- When set, it controls exactly which statuses are persisted/returned.

Demo mode:

```powershell
$env:USE_REDESIGNED_ENGINE="true"
$env:REDESIGNED_RESULT_MODE="review"
$env:REDESIGNED_INCLUDE_STATUSES=""
```

## How To Run

From the project root:

```powershell
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector
```

Backend:

```powershell
cd backend
$env:USE_REDESIGNED_ENGINE="true"
$env:REDESIGNED_RESULT_MODE="review"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8013
```

Frontend:

```powershell
cd frontend
$env:VITE_API_URL="http://127.0.0.1:8013"
npm.cmd run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5173
```

Backend API:

```text
http://127.0.0.1:8013/docs
```

Docker:

```powershell
$env:USE_REDESIGNED_ENGINE="true"
$env:REDESIGNED_RESULT_MODE="review"
$env:REDESIGNED_INCLUDE_STATUSES=""
docker compose up --build
```

## Testing

Backend tests:

```powershell
cd backend
python -m pytest
```

Frontend build:

```powershell
cd frontend
npm.cmd run build
```

Latest known verification:

- Backend tests: `117 passed`
- Frontend build: passed

## Export

Candidate export keeps legacy fields and includes redesigned evidence fields for auditability.

Exported evidence includes:

- `business_status`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`
- normalized descriptions and part numbers
- extracted attributes

This makes the output suitable for business review, data-quality analysis, and later model/policy tuning.

## Safety Boundaries

Current version:

- CSV-based demo only.
- No auto-merge.
- No direct IFS update.
- No direct connection to IFS database tables.
- No real IFS Cloud API/OData integration.
- No LLM pairwise duplicate decision.
- Human review is required before any business action.

The current system identifies possible duplicate candidates. It does not establish final duplicate truth.

## Future Enhancements

Planned or possible future work:

- IFS Cloud API/OData integration.
- Live duplicate warning during inventory part creation.
- Feedback loop from reviewer decisions.
- Optional LLM-assisted attribute extraction, not pairwise automatic duplicate decisions.
- Policy configuration UI for business rules and field importance.
- Golden/survivor record recommendation after human-approved duplicate groups.
- PostgreSQL and background workers for larger production deployments.
- Customer-specific evaluation datasets and threshold/policy tuning.

## Useful Docs

- `backend/docs/redesigned_engine.md`
- `backend/docs/runtime_env.md`
- `backend/docs/smoke_test_results.md`
- `docs/kubernetes_readiness.md`
- `docs/future_ifs_integration.md`
- `docs/data_security_and_privacy.md`
