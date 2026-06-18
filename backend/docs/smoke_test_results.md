# Smoke Test Results

Date: 2026-06-18

## Backend Command

Port `8000` was already in use locally, so the smoke backend was started on port `8011`:

```powershell
$env:USE_REDESIGNED_ENGINE="true"
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Health check:

```text
GET http://127.0.0.1:8011/health -> healthy
```

## CSV Used

```text
F:\part-master-duplication-ai\data set.csv
```

The file contained 99 records. The upload was run with:

```text
selected_fields=CONTRACT,UNIT_MEAS
threshold=0
scan_mode=SAME_SITE_DUPLICATE
USE_REDESIGNED_ENGINE=true
```

## Upload Result

```text
POST /api/scans/upload -> COMPLETED
scan_id: 13
total_records: 99
total_candidates: 807
warnings_count: 1
```

The first manual upload attempt used a JSON-formatted `selected_fields` value that PowerShell/curl quoting mangled. Retrying with the supported comma-separated value `CONTRACT,UNIT_MEAS` succeeded. No backend fix was required.

## Candidate Response Summary

```text
GET /api/scans/13/candidates -> 807 candidates
```

Returned candidate fields included:

- `business_status`
- `similarity_score`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`

Observed pair outcomes:

- `DEC CO1` vs `DEC C01` -> `DUPLICATE_CANDIDATE`
- `MCB 20A` vs `MCB30A` -> `RELATED_BUT_NOT_DUPLICATE`
- `RED PAINT 1L` / `RED PAINT 1L CAN` vs `BLUE PAINT 1L` / `BLUE PAINT 1L CAN` -> `RELATED_BUT_NOT_DUPLICATE`
- `TR LABELS` vs `TR WARNING LABELS` -> `INSUFFICIENT_DATA`

Status counts at threshold `0`:

```text
DUPLICATE_CANDIDATE: 1
POSSIBLE_DUPLICATE_REVIEW: 8
RELATED_BUT_NOT_DUPLICATE: 57
INSUFFICIENT_DATA: 35
UNIQUE_NO_MATCH: 706
```

## Export Result Summary

```text
GET /api/scans/13/export -> 807 CSV rows
```

Legacy export fields were present:

- `similarity_score`
- `final_score`
- `score`
- `recommended_action`
- `review_status`

Redesigned evidence export fields were present:

- `business_status`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`
- `extracted_attributes_a`
- `extracted_attributes_b`

Example serialized values:

```text
matched_evidence: field:CONTRACT; field:UNIT_MEAS; product_class; type_code
extracted_attributes_a: {"product_class":["coconut"],"type_code":["type 1"],...}
```

## Issues Found

No backend startup, scan, candidate API, or export defects were found.

Operational notes:

- Local port `8000` was already occupied, so port `8011` was used for this smoke test.
- Manual curl quoting for `selected_fields` should prefer comma-separated values on Windows PowerShell.

## Fixes Needed

No code fixes were required during this smoke test.

## Review Mode Smoke Test

Date: 2026-06-18

Backend command and environment:

```powershell
$env:USE_REDESIGNED_ENGINE="true"
$env:REDESIGNED_RESULT_MODE="review"
# REDESIGNED_INCLUDE_STATUSES was not set.
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

Port `8012` was used to avoid disturbing existing local services. Health check returned `healthy`.

CSV used:

```text
F:\part-master-duplication-ai\data set.csv
```

Upload settings:

```text
selected_fields=CONTRACT,UNIT_MEAS
threshold=0
scan_mode=SAME_SITE_DUPLICATE
USE_REDESIGNED_ENGINE=true
REDESIGNED_RESULT_MODE=review
```

Upload result:

```text
POST /api/scans/upload -> COMPLETED
scan_id: 14
total_records: 99
persisted/API candidates: 44
warnings_count: 1
```

Comparison with previous all/debug smoke result:

```text
all/debug candidates: 807
review-mode candidates: 44
reduction: 763 fewer UI-facing rows
```

Review mode reduced UI-facing results while preserving review-relevant outcomes.

Observed pair outcomes:

- `DEC CO1` vs `DEC C01` -> returned as `DUPLICATE_CANDIDATE`
- `TR LABELS` vs `TR WARNING LABELS` -> returned as `INSUFFICIENT_DATA`
- `MCB 20A` vs `MCB30A` -> not returned in review mode because it is `RELATED_BUT_NOT_DUPLICATE`
- `RED PAINT 1L CAN` vs `BLUE PAINT 1L CAN` -> not returned in review mode because it is `RELATED_BUT_NOT_DUPLICATE`

Persisted/API status counts:

```text
DUPLICATE_CANDIDATE: 1
POSSIBLE_DUPLICATE_REVIEW: 8
INSUFFICIENT_DATA: 35
```

Returned candidate fields included:

- `business_status`
- `similarity_score`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`

Export result:

```text
GET /api/scans/14/export -> 44 CSV rows
```

Export row count matched the persisted candidate count. Export contained old fields and redesigned evidence fields:

- `similarity_score`
- `final_score`
- `score`
- `recommended_action`
- `review_status`
- `business_status`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`
- `extracted_attributes_a`
- `extracted_attributes_b`

The export did not include `RELATED_BUT_NOT_DUPLICATE` or `UNIQUE_NO_MATCH` rows in review mode.

Issues/fixes:

- No backend startup, upload, candidate API, filtering, or export defects were found.
- No code fixes were required during this review-mode smoke test.

## Docker Compose Review Mode Smoke Test

Date: 2026-06-18

Docker Compose command and environment:

```powershell
$env:USE_REDESIGNED_ENGINE="true"
$env:REDESIGNED_RESULT_MODE="review"
# REDESIGNED_INCLUDE_STATUSES was not set.
docker compose down
docker compose up --build -d
```

The Compose file passes these backend environment variables with safe defaults:

- `USE_REDESIGNED_ENGINE`
- `REDESIGNED_RESULT_MODE`
- `REDESIGNED_INCLUDE_STATUSES`

Container health:

```text
GET http://127.0.0.1:8000/health -> healthy
```

CSV used:

```text
F:\part-master-duplication-ai\data set.csv
```

Upload settings:

```text
selected_fields=CONTRACT,UNIT_MEAS
threshold=0
scan_mode=SAME_SITE_DUPLICATE
USE_REDESIGNED_ENGINE=true
REDESIGNED_RESULT_MODE=review
```

Upload result:

```text
POST /api/scans/upload -> COMPLETED
scan_id: 15
total_records: 99
persisted/API candidates: 44
warnings_count: 1
```

Comparison with previous local review-mode smoke result:

```text
local review-mode candidates: 44
Docker Compose review-mode candidates: 44
```

Comparison with previous all/debug smoke result:

```text
all/debug candidates: 807
Docker Compose review-mode candidates: 44
reduction: 763 fewer UI-facing rows
```

Observed pair outcomes:

- `DEC CO1` vs `DEC C01` -> returned as `DUPLICATE_CANDIDATE`
- `TR LABELS` vs `TR WARNING LABELS` -> returned as `INSUFFICIENT_DATA`
- `MCB 20A` vs `MCB30A` -> not returned in review mode because it is `RELATED_BUT_NOT_DUPLICATE`
- `RED PAINT 1L CAN` vs `BLUE PAINT 1L CAN` -> not returned in review mode because it is `RELATED_BUT_NOT_DUPLICATE`

Persisted/API status counts:

```text
DUPLICATE_CANDIDATE: 1
POSSIBLE_DUPLICATE_REVIEW: 8
INSUFFICIENT_DATA: 35
```

Returned candidate fields included:

- `business_status`
- `similarity_score`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`

Export result:

```text
GET /api/scans/15/export -> 44 CSV rows
```

Export row count matched the persisted candidate count. Export contained old fields and redesigned evidence fields:

- `similarity_score`
- `final_score`
- `score`
- `recommended_action`
- `review_status`
- `business_status`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`
- `extracted_attributes_a`
- `extracted_attributes_b`

The export did not include `RELATED_BUT_NOT_DUPLICATE` or `UNIQUE_NO_MATCH` rows in review mode.

Issues/fixes:

- Docker Compose initially lacked the redesigned engine environment variables, so the Compose backend service was updated to pass them through with safe defaults.
- No engine, scan, API, or export logic changes were required.

## Frontend Review Mode Smoke Test

Date: 2026-06-18

Backend command and environment:

```powershell
$env:USE_REDESIGNED_ENGINE="true"
$env:REDESIGNED_RESULT_MODE="review"
$env:REDESIGNED_INCLUDE_STATUSES=""
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8013
```

Frontend command and environment:

```powershell
$env:VITE_API_URL="http://127.0.0.1:8013"
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\frontend
npm.cmd run dev -- --host 127.0.0.1
```

Runtime checks:

```text
GET http://127.0.0.1:8013/health -> healthy
GET http://127.0.0.1:8013/ready -> ready
GET http://127.0.0.1:5173 -> 200
```

CSV used:

```text
F:\part-master-duplication-ai\data set.csv
```

Upload settings:

```text
selected_fields=CONTRACT,INVENTORY_UOM,PART_TYPE
threshold=60
scan_mode=SAME_SITE_DUPLICATE
USE_REDESIGNED_ENGINE=true
REDESIGNED_RESULT_MODE=review
```

Upload result:

```text
POST /api/scans/upload -> COMPLETED
scan_id: 15
total_records: 99
persisted/API candidates: 10
warnings_count: 3
```

The candidate count was review-mode sized and far below the earlier all/debug count of 807. This run used a stricter selected-field set than the earlier review-mode backend smoke test, so it returned 10 UI-facing candidates instead of 44.

Key UI data checks:

- `DEC CO1` vs `DEC C01` returned as `DUPLICATE_CANDIDATE` with `HIGH` confidence.
- The duplicate candidate explanation mentioned business synonym normalization and `desiccated coconut type 1`.
- `TR LABELS` vs `TR WARNING LABELS` returned as `INSUFFICIENT_DATA`.
- `MCB 20A` vs `MCB30A` was not returned in default review mode because it is a related-but-not-duplicate debug result.
- `RED PAINT 1L CAN` vs `BLUE PAINT 1L CAN` was not returned in default review mode because it is a related-but-not-duplicate debug result.

Returned candidate fields used by the polished results UI included:

- `business_status`
- `similarity_score`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`
- `normalized_part_no_a`
- `normalized_part_no_b`
- `normalized_description_a`
- `normalized_description_b`
- `extracted_attributes_a`
- `extracted_attributes_b`

Export result:

```text
GET /api/scans/15/export -> 10 CSV rows
```

Export row count matched the persisted candidate count. Export contained old fields and redesigned evidence fields:

- `similarity_score`
- `final_score`
- `score`
- `recommended_action`
- `review_status`
- `business_status`
- `confidence_score`
- `confidence_level`
- `explanation`
- `matched_evidence`
- `differences`
- `warnings`
- `extracted_attributes_a`
- `extracted_attributes_b`

Browser/UI note:

- The frontend dev server served the app successfully on `http://127.0.0.1:5173`.
- The scan results API returned the exact fields now rendered by the polished results page.
- A local headless Chrome DOM dump was attempted but produced no DOM output in this shell environment, so this note should be treated as a runtime frontend/API smoke check rather than a full human visual click-through.

Issues/fixes:

- The first background process launch attempted to use unsupported `Start-Process -Environment` on this PowerShell version. The smoke run was restarted using a compatible environment-variable launch style. No application code fix was required.
- No backend engine, scan, export, or frontend rendering code changes were required during this smoke run.
