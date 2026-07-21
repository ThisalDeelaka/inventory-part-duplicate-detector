# Current Project Assessment

Assessment date: 2026-07-20 (Asia/Colombo). This document describes commit `d510cf3c18b3a8448d0f79be3e59c398efb32eae` as inspected. “Current” means behavior supported by source code in this repository; proposals in older documents are not treated as implemented.

# 1. Repository Status

- Current branch: `main`.
- Current commit: `d510cf3c18b3a8448d0f79be3e59c398efb32eae` (`Add structural role and rule exclusion audit`, committed 2026-07-13 12:33:58 +0530).
- Initial Git status: clean, tracking `origin/main` (`## main...origin/main`).
- Status after this assessment: only `docs/CURRENT_PROJECT_ASSESSMENT.md` is newly created; no application, configuration, test, schema, or dependency file was changed.
- Main folders:
  - `backend/`: FastAPI application, matching engine, SQLAlchemy persistence, services, repositories, and pytest suite.
  - `frontend/`: React single-page application built by Vite.
  - `data/`: sample inventory CSV and labeled evaluation pairs.
  - `docs/`: architecture, readiness, security, evaluation, demonstration, and integration-boundary documentation.
  - `k8s/`: example Kubernetes Deployments, Services, ConfigMap, Ingress, and placeholder Secret.
  - `scripts/`: readiness runner and technical-document generator.
- Main projects: one Python backend and one JavaScript frontend. There are no additional packages, workers, model services, or infrastructure modules.

Important pinned backend dependencies from `backend/requirements.txt` are FastAPI 0.137.1, Starlette 1.3.1, Uvicorn 0.34.3, pandas 2.3.0, scikit-learn 1.7.0, RapidFuzz 3.13.0, SQLAlchemy 2.0.41, python-multipart 0.0.32, Pydantic 2.11.7, pytest 9.1.0, and HTTPX 0.28.1. Installed frontend versions reported by `npm.cmd list --depth=0` are React 19.2.7, React DOM 19.2.7, React Router DOM 7.17.0, Vite 8.0.16, and `@vitejs/plugin-react` 6.0.2. `frontend/package.json` requests `"latest"` for all frontend dependencies, while `frontend/package-lock.json` resolves the concrete versions; future clean installs can therefore change versions if the lockfile is regenerated.

# 2. Current Architecture

## Frontend

`frontend/src/main.jsx` mounts `App` in React strict mode. `frontend/src/App.jsx` defines a client-side `BrowserRouter` with a shared `Layout` and pages for dashboard, new scan, scan results, warnings, synthetic load test, data security, and the future IFS boundary. There is no global state framework: pages use local React state and `useEffect`. `frontend/src/api/client.js` is a small `fetch` wrapper for JSON, multipart forms, and browser Blob downloads.

The frontend is a build-time static SPA. Vite builds it, and the production Dockerfile serves it from nginx with an SPA fallback. There is no server-side rendering, frontend authentication, frontend test framework, or generated API client.

## Backend

`backend/app/main.py` constructs a synchronous FastAPI application. Startup creates SQLAlchemy tables and applies a narrow SQLite-only additive migration. Route modules call service functions; `ScanRunner` orchestrates validation, candidate generation, scoring, and persistence; repositories isolate SQLAlchemy queries and writes. Matching is deterministic and local: normalization, dictionaries, TF-IDF, RapidFuzz, technical-token features, hard rules, and decision logic. No external model endpoint or LLM is called.

FastAPI path functions are ordinary `def` for reads and load tests; upload handlers are `async def`, but the scan itself runs directly inside the upload request after `await file.read()`. There is no worker process, queue, scheduler, or job broker.

## Database and storage

`backend/app/db/database.py` uses `DATABASE_URL`; the default is a file-backed SQLite database at repository root. SQLAlchemy creates five entities: scans, candidates, feedback, warnings, and rule-exclusion audits. The uploaded CSV is not written to disk. Candidate evidence is stored partly as scalar columns and partly as JSON strings in `Text` columns.

Docker Compose mounts a named volume at `/data` for SQLite. The Kubernetes backend instead mounts `emptyDir` at `/data`, so its database is pod-local and ephemeral. No PostgreSQL-specific schema, object storage, Parquet storage, Redis, or migration framework such as Alembic exists.

## Scan execution

`POST /api/scans/upload` reads and parses the complete upload, validates required fields, then calls `run_scan`/`ScanRunner.run`. A scan row is committed as `RUNNING`; warnings are staged; non-empty-description records are blocked into at most 20,000 pairs; every pair is scored sequentially. Results at or above the requested threshold become `DuplicateCandidate` rows. Below-threshold results with a non-`ALLOW` rule decision become `RuleExclusionAudit` rows. Other below-threshold pairs are discarded. A single commit persists staged candidates, exclusions, and warnings, then the scan is updated to `COMPLETED`. Exceptions roll back staged work and update the already-created scan to `FAILED`.

## Docker and Kubernetes

- `docker-compose.yml` builds a Python 3.11 backend and Node 22/nginx frontend, exposes 8000 and 5173, waits for backend health, and persists SQLite in a named volume.
- `backend/Dockerfile` installs pinned requirements and starts one Uvicorn process.
- `frontend/Dockerfile` runs `npm install`, builds with `VITE_API_URL`, and serves static files through nginx 1.27.
- `k8s/backend-deployment.yaml` uses one replica, health/readiness probes, resource requests/limits, ConfigMap environment, inline SQLite URL, and `emptyDir`.
- `k8s/frontend-deployment.yaml` uses one nginx-backed replica with resource requests/limits.
- Services are ClusterIP by default. `k8s/ingress.example.yaml` routes `/api`, `/health`, and `/ready` to the backend and `/` to the frontend.
- `k8s/secret.example.yaml` contains placeholders for a future IFS integration; no running code consumes them.

## Runtime feature flags

There is no feature-flag subsystem. `USE_REDESIGNED_ENGINE`, `REDESIGNED_RESULT_MODE`, and `REDESIGNED_INCLUDE_STATUSES` do not occur anywhere in tracked source or configuration. The current `decision_engine.evaluate_candidate` path is always used through `scoring.score_candidate`. Scan mode and sensitive-data mode are request parameters, not deployment feature flags.

## Text architecture diagram

```text
Browser
  |
  | React pages -> frontend/src/api/client.js
  v
FastAPI routes
  |
  +--> validation_service (whole-file CSV parse + mapping + warnings)
  |
  +--> ScanRunner
         |
         +--> candidate_generator (blocking, maximum 20,000 pairs)
         +--> decision_engine
         |      +--> normalizer/domain dictionary/attribute extractors
         |      +--> TF-IDF + RapidFuzz + technical/business features
         |      +--> hard rules + guardrails + explanation
         |
         +--> SQLAlchemy repositories
                    |
                    v
             SQLite by default
  |
  +--> unpaginated JSON / in-memory CSV export
  v
React result/group/warning/review views
```

# 3. Current End-to-End Data Flow

| Stage | Current behavior | Responsible files and main symbols |
|---|---|---|
| CSV upload | Browser creates `FormData`; API reads the entire `UploadFile` into `bytes`. Size and row caps are applied. | `frontend/src/pages/NewScan.jsx`: `form`, `validate`, `run`; `frontend/src/api/client.js`: `postForm`; `backend/app/api/routes_scans.py`: `validate_only`, `upload`; `backend/app/services/validation_service.py`: `read_csv_upload_with_metadata` |
| Parsing and field mapping | `pandas.read_csv(..., dtype=str)` creates a complete DataFrame. Headers are NFKC/uppercase/underscore normalized. Explicit canonical-to-source mappings win; known aliases map automatically; collisions are changed to `UNMAPPED_*`. | `validation_service.py`: `normalize_column_name`, `parse_column_mapping`, `apply_column_mapping`, `read_csv_upload_with_metadata`; `core/constants.py`: `FIELD_DEFINITIONS`, `FIELD_ALIASES` |
| Normalization | Description text is lowercased, spelling-corrected, split at alpha/numeric boundaries, punctuation-cleaned, abbreviation-expanded, and domain-dictionary-expanded. Part numbers receive domain token expansion. Normalization is cached. | `engine/normalizer.py`: `normalize_description`, `extract_technical_tokens`; `engine/domain_dictionary.py`: `expand_domain_tokens`, `normalize_part_no_with_dictionary` |
| Attribute extraction | Technical tokens, variant attributes, application contexts, item families, generic-description signals, and structural roles are extracted from descriptions/part numbers. | `normalizer.py`: `extract_technical_tokens`; `variant_extractor.py`: `extract_variant_attributes`; `application_context.py`: `extract_application_context`; `item_family_classifier.py`: `classify_item_family`; `generic_description_guard.py`: `is_generic_description` |
| Candidate generation | Available selected fields block by exact group equality. Selected fields with at least 50% blanks are ignored for blocking. If no usable field remains, the first normalized description/part-number token is used as a block. Same part numbers are skipped. Pair generation stops at 20,000. | `services/scan_runner.py`: `ScanRunner.run`; `engine/candidate_generator.py`: `generate_candidate_pairs`, `_pair`, `_same_part_number`, `MAX_CANDIDATE_PAIRS` |
| Similarity calculation | Per pair: character 3–5 gram TF-IDF cosine, fuzzy token-set/partial scores, normalized part-number ratio, technical-token overlap, and selected-field match percentage. Description is 60% TF-IDF/40% fuzzy. Final score is 60% description, 20% selected-field evidence, 10% part number, 10% technical tokens. | `engine/similarity_model.py`: `calculate_tfidf_similarity`, `calculate_fuzzy_similarity`, `calculate_part_no_similarity`, `calculate_technical_token_score`; `engine/decision_engine.py`: `_field_matches`, `evaluate_candidate` |
| Guardrails | Hard rules handle same part number, HSN/SAC, UOM, product category, and cross-site comparison in same-site mode. Variant, one-sided qualifier, generic text, application-context, and structural-role checks reject, cap, or downgrade results. | `engine/business_rules.py`: `evaluate_hard_business_rules`; `variant_extractor.py`: `find_critical_mismatches`, `find_one_sided_qualifier`, `find_structural_role_mismatch`; `generic_description_guard.py`: `has_generic_description`; `application_context.py`: `find_application_context_mismatch` |
| Decision engine | Applies hard rules before similarity. Otherwise computes score, caps/downgrades for guardrails, assigns confidence, business status, rule decision, reason, recommendation, and evidence. | `engine/scoring.py`: `score_candidate`; `engine/decision_engine.py`: `evaluate_candidate`, `confidence_for`, `business_status_for`, `_blocked_result` |
| Explanation | Produces fixed, deterministic prose based on the first applicable mismatch/context or the available matching evidence. No generative model is used. | `engine/explanation.py`: `build_explanation`; `decision_engine.py`: `_critical_mismatch_explanation`, `evaluate_candidate`; `core/constants.py`: `CONFIDENCE_ACTIONS` |
| Persistence | Scan metadata is committed first. Above-threshold candidates and below-threshold rule exclusions are staged and committed together; warnings and feedback use their repositories/services. JSON-shaped evidence is serialized into text. | `services/scan_runner.py`: `ScanRunner.run`; `repositories/candidate_repository.py`: `CandidateRepository.save`; `repositories/rejection_repository.py`: `RejectionRepository.save`; `repositories/scan_repository.py`; `repositories/warning_repository.py`; `services/feedback_service.py`: `save_feedback`; `db/models.py` |
| API response | Upload returns scan metadata and privacy metadata. Separate endpoints return complete arrays of candidates, connected groups, warnings, and exclusions. `candidate_json` deserializes legacy text evidence and supplies defaults for newer fields. | `api/routes_scans.py`: `scan_json`, `candidate_json`, `candidates`, `duplicate_groups`, `warnings`, `rejections` |
| Frontend display | Results default to connected group view; pair view shows status, rule, explanation, mismatch warnings, component scores, normalized values, and review controls. | `frontend/src/pages/ScanResults.jsx`: `ScanResults`, `GroupView`, `PairTable`; `components/Score.jsx` |
| Export | API queries all rows for a scan, creates the complete CSV in `io.StringIO`, sanitizes formula-leading cells, and returns one `Response`. Browser then materializes the response as a Blob and triggers a download. | `services/export_service.py`: `candidates_to_csv`, `rejections_to_csv`, `sanitize_csv_cell`; `api/routes_scans.py`: `export`, `export_rejections`; `frontend/src/api/client.js`: `download` |

# 4. Current Data Model

## Accepted CSV columns

Canonical fields are defined in `backend/app/core/constants.py`. Required: `PART_NO`, `DESCRIPTION`. Optional/selectable: `CONTRACT`, `TYPE_CODE`, `UNIT_MEAS`, `PRIME_COMMODITY`, `SECOND_COMMODITY`, `HAZARD_CODE`, `ACCOUNTING_GROUP`, `PART_PRODUCT_CODE`, `PART_PRODUCT_FAMILY`, `PRODUCT_CATEGORY_ID`, `HSN_SAC_CODE`.

Automatic aliases include `PART_NUMBER`, `ITEM_NO`, `ITEM_NUMBER`; `PART_DESCRIPTION`, `ITEM_DESCRIPTION`; site aliases; `PART_TYPE`; `INVENTORY_UOM`; commodity group aliases; `SAFETY_CODE`; and shorter product/HSN aliases. Human-readable headers work because punctuation and spaces normalize first. Arbitrary source headers work only with an explicit `column_mapping`. Other columns remain in the DataFrame under normalized/unmapped names and are considered by sensitive-pattern scanning, but matching does not consume them.

There is no typed internal record class. Records are pandas rows converted to dictionaries. Candidate scoring results are dictionaries. Persisted result and API models are separate:

- Internal pair shape from `_pair`: `record_a`, `record_b`, `matched_fields`, `mismatched_fields`, `warnings`.
- Decision result from `evaluate_candidate`: final/component scores, confidence, matched/mismatched fields, explanation/action, business/rule status, rejection reason, scan mode, critical/variant/context/generic/normalized evidence.
- Database entities in `backend/app/db/models.py`: `DuplicateScan`, `DuplicateCandidate`, `DuplicateFeedback`, `ScanWarning`, `RuleExclusionAudit`.
- Pydantic schemas in `backend/app/schemas/schemas.py`: `FeedbackCreate`, `FeedbackResponse`, `LoadTestRequest`, and `CandidateResponse`. `CandidateResponse` is not attached to the candidate route and omits several newer evidence fields, so the effective candidate API schema is the hand-built dictionary in `routes_scans.candidate_json`.

## Field treatment

| Requested field | Current treatment |
|---|---|
| `CONTRACT` | Canonical optional field and default UI selection. Can block candidate generation by exact site. In `SAME_SITE_DUPLICATE`, a compared cross-site pair is capped at 55 and classified `CROSS_SITE_STANDARDIZATION_CANDIDATE`; this rule is not applied in the other two scan modes. |
| `PART_NO` | Required. Used for same-number exclusion, blocking fallback, part-number similarity, application context, normalized evidence, persistence, and display. Exact same part numbers never become generated pairs. |
| `DESCRIPTION` | Required. Empty values are warned and skipped from scanning. Primary normalization, blocking fallback, attributes, similarities, explanations, and display derive from it. |
| `MASTER_PART_DESCRIPTION` | Not canonical and not an automatic alias. It can explicitly map to `DESCRIPTION`; this override is tested in `test_explicit_mapping_can_override_an_automatic_description_column`. Otherwise it remains an unused extra column. |
| `PART_TYPE` | Automatic alias for canonical `TYPE_CODE`. It can be selected for exact blocking/match evidence. Although `TYPE_CODE` is listed as a hard identity field in `column_semantics.py`, no hard rule directly checks it. |
| `INVENTORY_UOM` | Automatic alias for `UNIT_MEAS`. Optional/selectable for blocking and evidence, but any two non-empty different values trigger a hard rejection capped at 45 whether or not it was selected. |
| `COMMODITY_GROUP_1` | Automatic alias for `PRIME_COMMODITY`; optional selected-field blocking/match evidence and explanation classification context. |
| `COMMODITY_GROUP_2` | Automatic alias for `SECOND_COMMODITY`; optional selected-field blocking/match evidence and explanation classification context. |
| `SAFETY_CODE` | Automatic alias for `HAZARD_CODE`; optional selected-field blocking/match evidence. It is listed as hard identity/strict mismatch metadata, but `evaluate_hard_business_rules` does not implement a hazard-code rule. |
| `ACCOUNTING_GROUP` | Canonical optional field used only when selected for blocking and field match percentage/evidence. |
| `PART_PRODUCT_CODE` | Canonical optional field used for selected blocking/evidence and classification-related explanations. |
| `PART_PRODUCT_FAMILY` | Canonical optional field used for selected blocking/evidence and classification-related explanations. |
| `PRODUCT_CATEGORY_ID` | Canonical optional field used for blocking/evidence. Any two non-empty different values trigger a hard rejection capped at 50 even if not selected. |
| `HSN_SAC_CODE` | Canonical optional field. Aliases include HSN and SAC forms. Any two non-empty different values trigger `DATA_CONFLICT_REVIEW`, capped at 45, even if not selected. |

“Redesigned evidence fields” are not an alternate schema or flag-controlled mode. They are always generated by the current engine and stored on `DuplicateCandidate`: `business_status`, `rule_decision`, `rejection_reason`, `scan_mode`, `critical_mismatches`, `variant_attributes_a/b`, `generic_description_warning`, `application_context_a/b`, `application_context_warning`, `normalized_description_a/b`, and `normalized_part_no_a/b`. `db/migrations.py:ensure_sqlite_demo_columns` adds these fields to older SQLite candidate tables and adds scan mode/rejection count to older scan tables. `RuleExclusionAudit` stores a smaller subset.

Fixed-column assumptions remain substantial: the matching engine reads exact canonical keys from dictionaries, required fields are fixed, hard rules are coded against named fields, and persistence stores only a fixed subset of record attributes. Header mapping makes source labels flexible, but there is no per-client semantic schema or arbitrary feature definition.

# 5. Current Matching Behaviour

## Normalization and abbreviations

`normalize_description` lowercases, recognizes `M.C.B`, separates letters/numbers, removes most punctuation while retaining decimal points, fixes two desiccated-coconut misspellings, expands `piece/pieces/pcs`, `ss`, `mcb`, `cu`, filtration forms, ampere forms, and then applies `DOMAIN_TOKEN_MAP`. The domain map expands tokens such as `dec`, `coco`, `c01/co1`, `flt/filt`, `gen`, `stl`, `bat`, `temp`, and `press`. Part numbers use only domain-token expansion, not the full description normalizer.

Technical extraction returns unique numbers, number/unit measurements, dimensions, critical modifiers, and units. Variant extraction returns filter function, color, size, type/grade, electrical rating, millimeter dimension, sensor type, side, connectivity, environment, operation mode, placement, hierarchy, signal type, structural role, and trailing ordinal/numeric variant evidence.

## Candidate generation and site behavior

With usable selected fields, pandas groups on all of them and enumerates combinations inside each exact group. With no usable fields, rows are blocked on the first normalized description/part-number token. Thus worst-case work is quadratic within a large block, although enumeration stops once 20,000 unique pairs have been appended. The function holds the resulting pair dictionaries in memory. Repeated exact `PART_NO` pairs are skipped.

Candidate generation itself does not inspect scan mode. Same-site isolation occurs only when `CONTRACT` is a usable selected blocking field (it is selected by default in the UI). If it is not selected, cross-site rows may be paired. The decision engine then rejects/caps such a pair only in `SAME_SITE_DUPLICATE`. `CROSS_SITE_STANDARDIZATION` and `DISCOVERY` currently differ from same-site mode only by avoiding that contract hard rule; there is no separate cross-site ranking algorithm.

## Similarity, guardrails, and decisions

- TF-IDF: per-pair character `char_wb` n-grams 3–5 and cosine similarity.
- Fuzzy: 60% RapidFuzz token-set ratio plus 40% partial ratio.
- Description score: 60% TF-IDF plus 40% fuzzy.
- Selected-field score: exact non-empty matches divided by comparable selected fields; defaults to 50 when none are comparable.
- Final score: 60% description + 20% selected fields + 10% part number + 10% technical tokens.
- Hard rules run before similarity and return zero component scores.
- Critical two-sided variant mismatches return score 55 and `RELATED_BUT_NOT_DUPLICATE`.
- A defining qualifier present on only one side returns score 65 and `INSUFFICIENT_DATA`.
- Generic descriptions cap at 65; application-context mismatch caps at 78; structural-role mismatch caps at 85.

Confidence statuses from `confidence_for`:

- `HIGH`: score >= 90.
- `MEDIUM`: 75 <= score < 90.
- `LOW`: 60 <= score < 75.
- `IGNORE`: score < 60.

Business statuses and conditions:

- `LIKELY_DUPLICATE`: unblocked final score >= 90, unless a later guardrail changes the status.
- `POSSIBLE_DUPLICATE_REVIEW`: unblocked final score 60–89.99; also assigned for application-context and structural-role downgrades (unless a generic warning retains `INSUFFICIENT_DATA`).
- `INSUFFICIENT_DATA`: unblocked score below 60, one-sided defining qualifier, or generic-description guardrail.
- `RELATED_BUT_NOT_DUPLICATE`: critical variant mismatch.
- `REJECTED_BY_BUSINESS_RULE`: same `PART_NO`, UOM mismatch, or product-category mismatch.
- `DATA_CONFLICT_REVIEW`: HSN/SAC mismatch.
- `CROSS_SITE_STANDARDIZATION_CANDIDATE`: different non-empty contracts compared in `SAME_SITE_DUPLICATE`.

Rule decisions actually assigned are `ALLOW`, `DOWNGRADE`, `REJECT`, `DATA_CONFLICT`, and `CROSS_SITE`. `INSUFFICIENT_DATA` is declared in `RULE_DECISIONS` but is not assigned by the current decision engine. Rejection reasons are rule-specific strings such as `SAME_PART_NO`, `UNIT_MEAS_MISMATCH`, `PRODUCT_CATEGORY_ID_MISMATCH`, `HSN_SAC_CODE_MISMATCH`, `CONTRACT_MISMATCH_IN_SAME_SITE_MODE`, `<VARIANT>_MISMATCH`, `<QUALIFIER>_UNSPECIFIED`, `GENERIC_DESCRIPTION`, `APPLICATION_CONTEXT_MISMATCH`, and `STRUCTURAL_ROLE_MISMATCH`.

Persistence is threshold-driven, not status-driven. Any result with `final_score >= threshold` is a normal candidate, including a downgraded result if the user chooses a sufficiently low threshold. A below-threshold result is retained only when `rule_decision != "ALLOW"`, in the separate exclusion audit. There is no `review` versus `all` result mode, no `REDESIGNED_INCLUDE_STATUSES`, and no API/frontend status filter. Candidate and group endpoints operate on all persisted above-threshold candidates.

Scan lifecycle statuses are `RUNNING`, `COMPLETED`, and `FAILED`. Candidate human-review statuses are initially `UNREVIEWED` and become `DUPLICATE`, `NOT_DUPLICATE`, or `UNSURE` on feedback; later feedback can overwrite the candidate’s current review status while every feedback row remains stored.

# 6. Current API and Frontend

## Endpoints

| Method and path | Request | Response |
|---|---|---|
| `GET /health` | None | Health, service name, configured model version |
| `GET /ready` | None | Database connectivity and fixed `"model": "loaded"` |
| `GET /api/config/fields` | None | `FIELD_DEFINITIONS` array |
| `GET /api/diagnostics/summary` | None | Service/model/database status, aggregate counts, latest scan |
| `GET /api/scans` | None | Complete scan list |
| `GET /api/scans/{scan_id}` | Path ID | Scan metadata |
| `POST /api/scans/validate-only` | Multipart `file`, `selected_fields`, `column_mapping`, `sensitive_mode` | Validation counts/warnings, mapping metadata, privacy metadata |
| `POST /api/scans/upload` | Multipart fields above plus `threshold`, `scan_name`, `scan_mode` | Completed/failed-via-error scan metadata and privacy metadata; execution is synchronous |
| `GET /api/scans/{scan_id}/candidates` | Path ID | Complete candidate array |
| `GET /api/scans/{scan_id}/groups` | Path ID | Connected components of persisted candidates with score >= 75 and confidence medium/high |
| `GET /api/scans/{scan_id}/warnings` | Path ID | Complete warning array |
| `GET /api/scans/{scan_id}/rejections` | Path ID | Complete rule-exclusion array |
| `GET /api/scans/{scan_id}/export` | Path ID | Candidate CSV |
| `GET /api/scans/{scan_id}/rejections/export` | Path ID | Exclusion CSV |
| `POST /api/candidates/{candidate_id}/feedback` | JSON `user_decision`, optional `user_comment`, optional `created_by` | Stored feedback row |
| `POST /api/load-test/generate` | `LoadTestRequest` JSON | Generated CSV |
| `POST /api/load-test/run` | `LoadTestRequest` JSON | Scan ID, record/pair/candidate counts, elapsed time, warning count |

There is no authentication, authorization, tenant parameter, pagination, cancellation, retry, resume, deletion, or generic match-only API.

The scan response contains IDs/name/source, selected fields, threshold, status/counts, timestamps, model version, scan mode, and optional privacy summary. Candidate response fields are the persisted pair identity/text, final and component scores, confidence, matched/mismatched fields, explanation/action, review metadata, business/rule/reason/scan-mode evidence, critical and variant evidence, generic/context flags and contexts, and normalized descriptions/part numbers.

The pair table displays Part A, Part B, score, business/confidence status, rule/reason, explanation/mismatch warnings, and review controls. Expansion displays TF-IDF, fuzzy, part-number, technical score, matched/mismatched fields, scan mode, normalized descriptions and part numbers, and recommended action. Variant attribute dictionaries are returned by the API and exported, but are not displayed in the expansion. Contracts are present in the API but not in pair-table cells; group parts display site.

Candidate export fields are defined by `candidates_to_csv` and include pair identity/site, final status/rule evidence, context/normalization/variant evidence, component scores, matched/mismatched fields, explanation/action, and review status. It does not export scan ID, candidate ID, reviewed-by/time, or feedback history. Exclusion export contains pair identity/site, score/confidence/status/rule/reason, critical mismatches, and explanation.

Legacy compatibility consists of SQLite additive columns in `ensure_sqlite_demo_columns`, `getattr` defaults for new scan/candidate attributes, tolerant JSON decoding helpers in `routes_scans.py`, the field alias map, and explicit source-column overrides. There is no versioned API. `CandidateResponse` represents an older subset and is currently unused by the candidate route.

# 7. Configuration

| Setting | Default/current source | Location and behavior |
|---|---|---|
| `USE_REDESIGNED_ENGINE` | Not implemented | No occurrence in tracked repository |
| `REDESIGNED_RESULT_MODE` | Not implemented | No occurrence in tracked repository |
| `REDESIGNED_INCLUDE_STATUSES` | Not implemented | No occurrence in tracked repository |
| `MODEL_VERSION` | `hybrid-nlp-v1` | `core/config.py`; Docker/Kubernetes set same value. Persistence and diagnostics instead import the separate constant in `core/constants.py`, also currently `hybrid-nlp-v1`. |
| `DEFAULT_THRESHOLD` | `75` | Parsed in `core/config.py`, set by Docker/Kubernetes, but upload route and UI each independently default to literal 75; the settings value is not consumed by them. |
| `ENVIRONMENT` | `development` | Parsed but otherwise unused. Kubernetes sets `kubernetes`. |
| `MAX_UPLOAD_BYTES` | 52,428,800 (50 MiB) | Enforced after the entire upload has already been read into bytes. Same value in Compose/ConfigMap. |
| `MAX_CSV_RECORDS` | 100,000 | Enforced after full pandas parsing. Same value in Compose/ConfigMap. |
| `DATABASE_URL` | Root `inventory_detector.db` SQLite file | `core/config.py`/`db/database.py`; Compose uses persistent `/data`; Kubernetes uses `/data` on `emptyDir`. |
| `CORS_ORIGINS` | localhost/127.0.0.1 ports 5173 and 3000 | Comma-split in `core/config.py`; Compose adds ports 5174; Kubernetes uses the example HTTPS host. |
| `CORS_ORIGIN_REGEX` | local loopback, any port | `core/config.py`; Compose sets the same pattern; Kubernetes does not override it, so the development regex remains active there. |
| `MAX_CANDIDATE_PAIRS` | 20,000 | Hard-coded in `engine/candidate_generator.py`, not environment-configurable. |
| Score weights | TF-IDF/fuzzy description 60/40; final description/business/part/technical 60/20/10/10 | Hard-coded in `decision_engine.py`. |
| Confidence thresholds | 90/75/60 | Hard-coded in `confidence_for`. |
| Guardrail caps | 0, 45, 50, 55, 65, 78, 85 depending on rule | Hard-coded in `business_rules.py` and `decision_engine.py`. |
| Upload threshold | API 75; UI 75; UI range 60–95; API accepts 0–100 | `routes_scans.upload`, `NewScan.jsx` |
| `VITE_API_URL` | Browser fallback `http://127.0.0.1:8000`; Dockerfile build arg default `http://localhost:8000` | Compile-time value in `frontend/src/api/client.js` and `frontend/Dockerfile`; Compose supplies `http://127.0.0.1:8000`. Kubernetes does not show how the frontend image is built, so its effective API URL is **Unknown**. |

Docker passes environment directly in Compose. Kubernetes backend consumes the ConfigMap with `envFrom` and overrides `DATABASE_URL` inline. The example Secret is not referenced by a Deployment. There are no `.env.example`, Helm, Kustomize, Terraform, sealed-secret, or runtime frontend configuration files.

# 8. Tests and Verification

Backend test files grouped by responsibility:

- Candidate blocking: `backend/tests/test_candidate_generator.py` (6 tests).
- Duplicate grouping: `backend/tests/test_grouping_service.py` (2 tests).
- Normalization/technical extraction: `backend/tests/test_normalizer.py` (3 tests).
- Decision logic, rules, false positives, true positives, and evidence: `backend/tests/test_scoring.py` (20 tests).
- Similarity components: `backend/tests/test_similarity.py` (4 tests).
- Validation/API/upload/feedback/load/export/mapping/audit behavior: `backend/tests/test_validation_api.py` (13 tests).
- Fixtures and in-memory SQLite isolation: `backend/tests/conftest.py`.

Current backend test count: 48.

Requested backend command result:

- Literal `cd backend; python -m pytest` used system Python 3.14 and failed before collection: `No module named pytest`.
- The repository test environment was then used without changing dependencies: `backend/.venv/Scripts/python.exe -m pytest`.
- Actual project result: **48 passed, 1 warning in 2.26s** on Python 3.11.9 and pytest 9.1.0.
- Warning: `backend/pytest.ini` contains unknown option `asyncio_default_fixture_loop_scope`; no asyncio pytest plugin is installed/listed.

Frontend test availability: no frontend unit, component, or end-to-end tests and no `test` script exist. The required build command is `cd frontend; npm.cmd run build`.

Frontend build result:

- The first sandboxed attempt failed with `spawn EPERM` while Vite loaded its config.
- Retrying the identical command with child-process execution allowed passed: **Vite 8.0.16, 34 modules transformed, built in 706 ms**.
- Output: `dist/index.html` 0.16 kB, CSS 6.42 kB (2.16 kB gzip), JS 256.42 kB (80.59 kB gzip).

Docker smoke tests: `docs/production_readiness_testing.md` says the readiness check covers Docker Compose build/runtime smoke tests, but `scripts/production_readiness_check.py` contains no Docker calls and `docs/production_readiness_results.json` contains no Docker result. No Docker smoke test was requested or performed in this assessment. Therefore the current reproducible Docker smoke result is **Unknown**.

Kubernetes validation: manifests and a narrative readiness review exist, but no manifest test, schema validation, `kubectl --dry-run`, or recorded command result exists. None was requested or performed in this assessment. Current executable Kubernetes validation result: **Unknown**.

Sample-data smoke run performed during this assessment, using `data/sample_inventory_parts.csv`, in-memory SQLite, selected fields `CONTRACT` and `UNIT_MEAS`, and threshold 75:

- 20 input rows.
- 48 candidate pairs generated.
- 10 candidates persisted.
- 38 below-threshold rule exclusions persisted.
- 1 warning.
- Scan status `COMPLETED`.

Historical `docs/production_readiness_results.json` (generated 2026-06-16) reports a separate parent-directory 99-row ERP export passed with 25 candidates and 9 warnings, plus 500/2,000/5,000-row synthetic runs. That external 99-row input is not tracked here, the script rewrites the results file, and the result predates the assessed commit; it is historical evidence, not a current rerun.

# 9. Production Scalability Assessment

| Concern | Current finding and evidence |
|---|---|
| CSV memory | `read_csv_upload_with_metadata` first awaits `file.read()` into one bytes object, then `pd.read_csv` creates a complete DataFrame. Size/row validation happens after those allocations. |
| Candidate complexity | `generate_candidate_pairs` uses `itertools.combinations` within exact blocks: theoretical time is `O(sum(block_size²))` until the global cap; output memory is up to 20,000 pair dictionaries. |
| All-pairs risk | If all records share selected values, a block is all-pairs. If no selected field is usable, first-token blocking reduces many cases but a common first token can still make a large all-pairs block. The cap truncates rather than ranks the pair space. |
| Execution | `routes_scans.upload` calls `run_scan` inline. Pair scoring and repository additions are sequential. There is no asynchronous job despite the async upload handler. |
| SQLite | One file, no production migration system, limited write concurrency, and one Kubernetes replica with ephemeral `emptyDir`. `check_same_thread=False` allows FastAPI thread use but does not remove SQLite locking/scale constraints. |
| Persistence volume | Up to 20,000 generated pairs can become candidate or exclusion rows per scan; each candidate repeats descriptions and stores several JSON text fields. Ordinary below-threshold `ALLOW` pairs are dropped. No retention/deletion or partitioning exists. |
| API pagination | None. Scan, candidate, group, warning, and exclusion endpoints call `.all()` and return complete arrays. Group building also holds nodes/edges/groups in memory. |
| Export memory | Repository `.all()` + server `StringIO` + complete HTTP body; browser then creates a complete Blob. There is no streaming response. |
| Workers/jobs | None. One Uvicorn process in Docker, no queue/broker/worker manifests, no job polling/cancellation. |
| Retry/resume | None. A failed scan can be recorded, but there is no checkpoint, retry endpoint, idempotency key, or resume cursor. |
| Tenant isolation | None: no identity, tenant key, row-level scope, authorization, or per-tenant storage. |
| Observability | `/health`, `/ready`, and aggregate diagnostics only. No structured logging setup, metrics, tracing, correlation/job IDs, dashboards, or alerts. |
| Model/LLM | Local deterministic feature logic only. No trained identity model, vector index, embedding model, LLM, provider gateway, prompt/model registry, or model artifact loading. `/ready` returns fixed `"model": "loaded"`. |

Scale verdicts:

- **10,000 rows:** Accepted under default row/byte limits, but not production-safe as a complete scan. A favorable set of selective blocks may run; a broad block reaches the 20,000 cap and silently returns only the earliest enumerated pairs plus a warning. Full file/DataFrame/pair/result handling is synchronous and in memory. The current historical load evidence reaches the cap by 2,000 rows.
- **100,000 rows:** Nominally accepted at the default row cap if under 50 MiB, but not practically supported for exhaustive or reliable matching. Full parsing, pandas grouping, request occupancy, capped/non-ranked pair enumeration, SQLite writes, and unpaginated retrieval remain bottlenecks.
- **1,000,000 rows:** Rejected by default after full parsing because `MAX_CSV_RECORDS` is 100,000. Raising the limit would not supply streaming, distributed retrieval, workers, scalable persistence, pagination, or resumability. The current architecture does not support this size.

# 10. Reuse, Modify, or Replace

“Keep” means retain as a foundation; “Modify” means evolve in place; “Replace” means the current implementation is unsuitable for the target responsibility.

| Component | Keep | Modify | Replace | Reason | Relevant files |
|---|:---:|:---:|:---:|---|---|
| React shell | ✓ | ✓ |  | Small, understandable SPA; add auth, job state, pagination, and tests. | `frontend/src/App.jsx`, `components/Layout.jsx` |
| FastAPI shell | ✓ | ✓ |  | Routes/services are a useful API boundary; add versioning, auth, jobs, and typed responses. | `backend/app/main.py`, `app/api/*` |
| CSV ingestion |  | ✓ |  | Mapping/validation is reusable, but whole-file reading must become staged/streamed ingestion. | `services/validation_service.py` |
| Record model |  | ✓ |  | Dict rows work for demo only; introduce canonical typed records plus raw/client metadata. | `core/constants.py`, `engine/column_semantics.py` |
| Normalizer | ✓ | ✓ |  | Useful deterministic baseline; make profiles/versioning configurable and batch-friendly. | `engine/normalizer.py`, `engine/domain_dictionary.py` |
| Attribute extractor | ✓ | ✓ |  | Good evidence baseline, but hard-coded vocabulary needs profile/plugin and version support. | `engine/variant_extractor.py`, `engine/application_context.py` |
| Candidate generator |  |  | ✓ | Exact blocking plus first-token fallback and truncation cannot provide scalable recall. | `engine/candidate_generator.py` |
| Similarity engine | ✓ | ✓ |  | Preserve baseline features, then batch/vectorize and add generic features/model inputs. | `engine/similarity_model.py` |
| Guardrails | ✓ | ✓ |  | Deterministic safety rules are valuable; externalize/version by client and resolve declared-vs-implemented mismatches. | `engine/business_rules.py`, `engine/generic_description_guard.py` |
| Decision engine | ✓ | ✓ |  | Preserve as flagged demo/baseline; add versioned model-backed path and calibrated decisions. | `engine/decision_engine.py`, `engine/scoring.py` |
| Explanations | ✓ | ✓ |  | Deterministic explanations are auditable; expand structured reason codes before optional LLM prose. | `engine/explanation.py` |
| Persistence |  | ✓ |  | Repository pattern is reusable; schema, migrations, batching, retention, tenant/audit fields need redesign. | `app/repositories/*`, `db/models.py` |
| SQLite |  |  | ✓ | Demo-only concurrency/durability/scaling characteristics. | `db/database.py`, Compose/Kubernetes DB settings |
| APIs | ✓ | ✓ |  | Preserve route concepts; add jobs, pagination, schemas, versioning, auth, and streaming exports. | `app/api/*`, `app/schemas/schemas.py` |
| Frontend review page | ✓ | ✓ |  | Existing evidence/review UI is useful; add server filtering/pagination, audit history, bulk/assignment flows. | `frontend/src/pages/ScanResults.jsx` |
| Exports | ✓ | ✓ |  | Fields and formula sanitization are useful; implement streamed/background exports. | `services/export_service.py` |
| Docker | ✓ | ✓ |  | Useful local packaging; pin frontend install behavior and add worker/production process configuration. | `docker-compose.yml`, both Dockerfiles |
| Kubernetes | ✓ | ✓ |  | Useful skeleton; replace ephemeral SQLite and add worker, security, autoscaling, policies, secrets, and observability. | `k8s/*` |
| Tests | ✓ | ✓ |  | Strong rule regression baseline; add frontend, job, database, migration, scale, security, and manifest tests. | `backend/tests/*` |

# 11. Gap Against the Target Production Solution

| Target capability | Status | Evidence/gap |
|---|---|---|
| Millions of records | Not Implemented | 100,000-row default cap, 20,000-pair cap, synchronous in-memory path |
| Streaming ingestion | Not Implemented | Complete `file.read()` and pandas DataFrame |
| Parquet/object storage | Not Implemented | CSV input and SQLite only |
| PostgreSQL | Partially Implemented | SQLAlchemy can accept another URL and migration helper skips non-SQLite, but no PostgreSQL deployment, tested migration, schema tuning, or driver is present |
| Asynchronous jobs | Not Implemented | Inline request execution |
| Flexible client schemas | Partially Implemented | Header aliases and explicit mappings exist; canonical fields/features remain fixed |
| Client semantic profiles | Not Implemented | Global hard-coded dictionaries/rules |
| Scalable lexical/vector retrieval | Not Implemented | Exact pandas blocking/first-token fallback; no index/vector store |
| Generic pair-feature generation | Partially Implemented | Several reusable pair scores exist, but the feature contract is fixed and computed pair-by-pair |
| Training-data collection | Partially Implemented | Human feedback is persisted; no dataset extraction, labeling governance, sampling, or feature/model version linkage |
| CatBoost/LightGBM identity model | Not Implemented | No such dependency/model/artifact |
| Financial-mapping anomaly analysis | Not Implemented | Accounting group can be exact match evidence only |
| Active learning | Not Implemented | No uncertainty sampling or review prioritization loop |
| Optional LLM column interpretation | Not Implemented | Deterministic aliases/explicit UI mapping only |
| Optional LLM attribute extraction | Not Implemented | Regex/dictionaries only |
| Optional LLM difficult-case advice | Not Implemented | No LLM integration |
| Optional LLM explanation generation | Not Implemented | Fixed deterministic templates only |
| Provider-independent LLM gateway | Not Implemented | No provider client/interface |
| Model/prompt versioning | Partially Implemented | A static model-version string is stored; no artifact, feature, dictionary, threshold, or prompt registry |
| Human review audit | Partially Implemented | Immutable feedback rows and current candidate status exist; no auth identity, assignment, history API/UI, tenant, or general audit log |
| IFS Cloud integration | Not Implemented | Explicitly documented future boundary; placeholder Secret only |

# 12. Recommended Migration Order

All phases should keep the current synchronous demo available behind a new `USE_REDESIGNED_ENGINE=false` default until parity and operational gates are met.

## Phase 1 — Establish a compatibility seam

- Objective: add settings for `USE_REDESIGNED_ENGINE`, result mode/status inclusion, an engine interface, and characterization tests while preserving identical default behavior.
- Reuse: `ScanRunner`, current `score_candidate`, API payloads, current tests.
- New: configuration validation, baseline/redesigned engine protocol, result-policy object, version metadata.
- Likely files: `core/config.py`, new engine interface module, `services/scan_runner.py`, `api/routes_scans.py`, tests; Compose/ConfigMap only after defaults are proven.
- Tests: existing 48 unchanged; parity snapshots for candidate/exclusion/API/export behavior; invalid-config tests.
- Risks: accidental status/filter drift and split model-version sources.

## Phase 2 — Canonical ingestion and durable job contract

- Objective: separate upload/staging from scanning and define typed canonical records plus scan-job states.
- Reuse: column normalization/mapping, validation warnings, privacy metadata, FastAPI routes.
- New: chunked CSV reader, object-storage abstraction, canonical schema/profile version, job/status APIs, idempotency.
- Likely files: `validation_service.py`, schemas, DB models/migrations, routes, new ingestion/job services, frontend new-scan/results pages.
- Tests: chunk boundaries, malformed/oversized uploads, idempotency, job state transitions, compatibility-mode synchronous scan.
- Risks: changed validation timing, partial uploads, cleanup/retention, duplicate submissions.

## Phase 3 — PostgreSQL and production migrations

- Objective: move metadata/results/audit to PostgreSQL with real migrations and batched writes.
- Reuse: repository boundaries and entity concepts.
- New: PostgreSQL driver/config, Alembic migrations, indexes, tenant/job keys, bulk persistence, retention.
- Likely files: requirements, `db/*`, repositories, Compose/Kubernetes, tests.
- Tests: migration up/down/upgrade from representative SQLite-exported data, concurrency, transaction failure, query plans.
- Risks: JSON/text compatibility, timestamp behavior, long migration locks, dual-run data consistency.

## Phase 4 — Background workers and scalable retrieval

- Objective: execute resumable scans asynchronously and replace truncating blocking with lexical/vector top-K retrieval.
- Reuse: normalizer, attributes, guardrails, baseline scoring, explanations.
- New: queue/broker, worker deployment, checkpoints, cancellation/retry, lexical/vector index, deterministic candidate deduplication.
- Likely files: scan services, candidate generator replacement, new worker/retrieval modules, API/job schemas, Docker/Kubernetes, frontend polling.
- Tests: recall fixtures, deterministic top-K, retry/resume, worker crashes, load/backpressure, millions-scale benchmarks.
- Risks: recall regression, duplicate work, index/profile drift, operational complexity.

## Phase 5 — Generic features, training loop, and identity model

- Objective: version pair features and train/calibrate CatBoost or LightGBM from governed review labels.
- Reuse: existing similarity features, structured guardrails, feedback table concept, evaluation pairs.
- New: feature schema/store, training export, label/audit governance, experiment/model registry, calibration and shadow evaluation.
- Likely files: engine modules, feedback/persistence schemas, evaluation service, new training package, result evidence/API.
- Tests: offline precision/recall by client/profile, leakage checks, model serialization, baseline fallback, calibration and drift.
- Risks: biased labels, client leakage, uncalibrated confidence, loss of explainability.

## Phase 6 — Review operations and anomaly analysis

- Objective: production human-review audit, assignment/bulk workflows, active learning, and separate financial-mapping anomaly signals.
- Reuse: review page, feedback endpoint, accounting/product fields.
- New: identity/tenant/RBAC, review queues/history, active-learning sampler, anomaly feature/model, audit event log.
- Likely files: DB/API/frontend broadly plus new security/review/anomaly modules.
- Tests: authorization/tenant isolation, audit immutability, workflow concurrency, anomaly evaluation.
- Risks: privacy/access errors, reviewer disagreement, confusing identity and financial anomaly conclusions.

## Phase 7 — Optional provider-independent LLM services

- Objective: add opt-in, policy-controlled LLM assistance for column interpretation, attributes, difficult cases, and prose explanations.
- Reuse: deterministic output as source of truth/fallback, sensitive-mode transparency.
- New: provider gateway, allowlists/redaction, prompt/model registry, caching, budgets/timeouts, structured outputs.
- Likely files: new LLM package, config, schemas, privacy service, evidence UI, deployment secrets.
- Tests: provider contract, no-provider fallback, prompt injection/data leakage, deterministic schema validation, cost/latency limits.
- Risks: confidential-data transfer, hallucination, vendor behavior, nondeterminism, cost.

## Phase 8 — IFS Cloud adapter and controlled rollout

- Objective: integrate through an approved IFS API/Projection workflow while keeping recommendations advisory.
- Reuse: canonical ingestion/match API, review evidence, job/auth/audit infrastructure.
- New: OAuth/client management, IFS adapter, mapping/profile, rate limits, reconciliation, customer deployment runbooks.
- Likely files: new integration service/package, gateway routes, secrets/config, Kubernetes, documentation.
- Tests: contract sandbox, token rotation, retries/idempotency, rate limits, reconciliation, end-to-end user acceptance.
- Risks: IFS customization differences, permissions, stale master data, operational ownership.

# 13. Immediate Next Step

Implement only the compatibility seam from Phase 1: add a default-off `USE_REDESIGNED_ENGINE` setting and an engine-selection interface whose default path delegates unchanged to the current `score_candidate`, plus one parity test proving the existing sample/API result is identical when the flag is off. Do not add the redesigned engine yet. This is the smallest step that makes every later migration reversible and preserves the working demo.

# 14. Exact File Inventory

## Root, data, and scripts

- `.gitignore` — excludes environments, databases, frontend build output, secrets, logs, and local scan artifacts.
- `README.md` — project positioning, local/Compose run instructions, features, limitations, and troubleshooting.
- `docker-compose.yml` — local backend/frontend builds, ports, backend health check, environment, and persistent SQLite volume.
- `data/sample_inventory_parts.csv` — tracked 20-row canonical sample used for the current smoke run.
- `data/evaluation_pairs.csv` — labeled description pairs consumed by the offline evaluation service.
- `scripts/production_readiness_check.py` — TestClient-based health, external-export, failure, model-case, and synthetic-load runner that rewrites the readiness JSON.
- `scripts/generate_company_technical_document.py` — generates the long technical architecture document.

## Backend source and configuration

- `backend/.dockerignore` — backend container build exclusions.
- `backend/Dockerfile` — Python 3.11/Uvicorn backend image.
- `backend/requirements.txt` — pinned runtime and test Python dependencies.
- `backend/pytest.ini` — pytest cache/warning settings and one currently unrecognized asyncio option.
- `backend/app/main.py` — FastAPI application, lifespan table setup/migration, CORS, routers, health and readiness.
- `backend/app/api/routes_config.py` — canonical field-definition endpoint.
- `backend/app/api/routes_diagnostics.py` — database and aggregate diagnostic summary.
- `backend/app/api/routes_feedback.py` — candidate feedback endpoint.
- `backend/app/api/routes_load_test.py` — synthetic CSV generation and load-test execution endpoints.
- `backend/app/api/routes_scans.py` — scan validation/upload/read/group/warning/exclusion/export endpoints and response serialization.
- `backend/app/core/config.py` — environment-backed settings.
- `backend/app/core/constants.py` — canonical fields/aliases, confidence actions, critical modifiers, and strict mismatch metadata.
- `backend/app/db/database.py` — engine, session factory, declarative base, and request session dependency.
- `backend/app/db/migrations.py` — SQLite-only additive compatibility migration.
- `backend/app/db/models.py` — scan, candidate, feedback, warning, and exclusion SQLAlchemy entities.
- `backend/app/engine/application_context.py` — part/description application-context extraction and mismatch detection.
- `backend/app/engine/business_rules.py` — deterministic hard business rules and score caps.
- `backend/app/engine/candidate_generator.py` — exact/fallback blocking, pair enumeration, same-part exclusion, and 20,000 cap.
- `backend/app/engine/column_semantics.py` — canonical semantic sets, scan modes/status constants, and field cleaning.
- `backend/app/engine/decision_engine.py` — full pair evaluation, score/status assignment, guardrails, and evidence payload.
- `backend/app/engine/domain_dictionary.py` — cached domain token and part-number expansion.
- `backend/app/engine/explanation.py` — deterministic evidence-to-text explanation rules.
- `backend/app/engine/generic_description_guard.py` — generic short-description detection.
- `backend/app/engine/item_family_classifier.py` — small deterministic item-family classifier used in mismatch explanations.
- `backend/app/engine/normalizer.py` — description normalization, abbreviation handling, and technical-token extraction.
- `backend/app/engine/scoring.py` — compatibility wrapper exposing `score_candidate` and `confidence_for`.
- `backend/app/engine/similarity_model.py` — TF-IDF, fuzzy, part-number, and technical-token similarity functions.
- `backend/app/engine/variant_extractor.py` — variant/qualifier/structural attribute extraction and mismatch checks.
- `backend/app/repositories/candidate_repository.py` — candidate serialization, insert staging, and ordered scan query.
- `backend/app/repositories/rejection_repository.py` — exclusion-audit insert staging and ordered scan query.
- `backend/app/repositories/scan_repository.py` — scan lifecycle creation, status/count updates, and reads.
- `backend/app/repositories/warning_repository.py` — warning insert/query/count operations.
- `backend/app/schemas/schemas.py` — feedback/load-test Pydantic schemas and currently unused partial candidate response schema.
- `backend/app/services/evaluate_model.py` — offline precision/recall/F1 evaluation over `evaluation_pairs.csv`.
- `backend/app/services/export_service.py` — in-memory candidate/exclusion CSV construction and spreadsheet-formula sanitization.
- `backend/app/services/feedback_service.py` — feedback append and candidate review-state update.
- `backend/app/services/grouping_service.py` — union-find connected duplicate groups from medium/high persisted pairs.
- `backend/app/services/load_test_service.py` — synthetic dataset generation and timed synchronous scans.
- `backend/app/services/privacy_service.py` — upload hash, data-handling disclosure, and sensitive-pattern warnings.
- `backend/app/services/scan_runner.py` — synchronous scan orchestration and transaction handling.
- `backend/app/services/scan_service.py` — service façade around runner and repositories.
- `backend/app/services/validation_service.py` — selected-field/mapping parsing, whole-file CSV ingestion, validation, and metadata.
- `backend/app/utils/file_utils.py` — standalone filename sanitizer; currently not referenced elsewhere.
- Package `__init__.py` files — Python package markers with no project logic.

## Backend tests

- `backend/tests/conftest.py` — in-memory SQLite and FastAPI TestClient fixtures.
- `backend/tests/test_candidate_generator.py` — blocking, warning, uniqueness, same-part, and synonym-pair tests.
- `backend/tests/test_grouping_service.py` — connected-group inclusion/exclusion tests.
- `backend/tests/test_normalizer.py` — abbreviation, spelling, and technical-token tests.
- `backend/tests/test_scoring.py` — score, business-rule, guardrail, false-positive, true-positive, and evidence regression tests.
- `backend/tests/test_similarity.py` — component similarity behavior tests.
- `backend/tests/test_validation_api.py` — validation, upload, feedback, load, error, export, privacy, mapping, exclusion, and evidence API tests.

## Frontend

- `frontend/.dockerignore` — frontend container build exclusions.
- `frontend/Dockerfile` — Node 22 build and nginx 1.27 runtime image.
- `frontend/index.html` — SPA HTML mount point.
- `frontend/package.json` — frontend metadata, Vite scripts, and broad `"latest"` dependency declarations.
- `frontend/package-lock.json` — concrete npm dependency graph.
- `frontend/vite.config.js` — React plugin configuration.
- `frontend/src/main.jsx` — React application bootstrap.
- `frontend/src/App.jsx` — browser routes and page composition.
- `frontend/src/api/client.js` — build-time API base and fetch/download wrapper.
- `frontend/src/components/Layout.jsx` — navigation shell and human-review notice.
- `frontend/src/components/Score.jsx` — numeric score and bar display.
- `frontend/src/pages/Dashboard.jsx` — health/readiness/diagnostic summary and latest scan.
- `frontend/src/pages/DataSecurity.jsx` — current data-handling and production-control disclosure.
- `frontend/src/pages/FutureIFSIntegration.jsx` — explicit non-implemented IFS boundary and potential flow.
- `frontend/src/pages/LoadTest.jsx` — synthetic generation/load-test controls and metrics.
- `frontend/src/pages/NewScan.jsx` — upload, validation, field mapping, scan options, and execution UI.
- `frontend/src/pages/ScanResults.jsx` — group/pair evidence, review feedback, warnings links, and exports.
- `frontend/src/pages/Warnings.jsx` — scan warning list.
- `frontend/src/styles.css` — all SPA styling.

## Kubernetes

- `k8s/configmap.yaml` — backend model, threshold, environment, CORS, and upload/row settings.
- `k8s/backend-deployment.yaml` — one-replica backend, probes/resources, ConfigMap, SQLite URL, and ephemeral volume.
- `k8s/backend-service.yaml` — backend Service on port 8000.
- `k8s/frontend-deployment.yaml` — one-replica frontend with resource settings.
- `k8s/frontend-service.yaml` — frontend Service on port 80.
- `k8s/ingress.example.yaml` — example host/path routing.
- `k8s/secret.example.yaml` — unused placeholder IFS credentials, not real secrets.

## Documentation and recorded artifacts

- `docs/architecture.md` — concise current architecture narrative.
- `docs/data_security_and_privacy.md` — privacy/security behavior and production gaps.
- `docs/demo_script.md` — demonstration walkthrough.
- `docs/future_ifs_integration.md` — future IFS adapter boundary.
- `docs/kubernetes_readiness.md` — Kubernetes suitability and SQLite/worker caveats.
- `docs/model_evaluation.md` — model evaluation approach/results narrative.
- `docs/model_selection.md` — rationale for the local hybrid matching approach.
- `docs/reliability_and_scalability.md` — reliability/scale claims and limitations.
- `docs/production_readiness_testing.md` — intended readiness-check scope and execution guidance.
- `docs/production_readiness_results.json` — historical 2026-06-16 readiness and synthetic-load results.
- `docs/Part_Master_Duplication_Identifier_Technical_Architecture.md` — long-form generated technical architecture.
- `docs/Part_Master_Duplication_Identifier_Technical_Architecture.docx` — Word rendering of the technical architecture.
- `docs/claude_technical_document_prompt.md` — prompt/source material used for long-form documentation, not executable behavior.
- `docs/CURRENT_PROJECT_ASSESSMENT.md` — this source-backed current-state assessment.
