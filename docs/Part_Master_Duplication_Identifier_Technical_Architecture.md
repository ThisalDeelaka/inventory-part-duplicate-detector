# Part Master Duplication Identifier

Technical Architecture and Design Document

Version: 1.0
Date: 2026-06-16
System name: inventory-part-duplicate-detector
Business title: Part Master Duplication Identifier
Prepared for: Company technical and business review
Current status: Production-oriented demo / pilot-ready detection engine

## 1. Executive Summary

Part Master Duplication Identifier is a production-oriented demo system for detecting possible duplicate Inventory Part master-data records from ERP CSV exports. The system is inspired by IFS Inventory Part Master data, but the current implementation does not integrate with IFS Cloud, does not call IFS Projections, does not connect to inventory_part_tab, and does not use OAuth or paid AI APIs.

The system accepts CSV exports with IFS-compatible field names, validates the file, normalizes item descriptions, generates scalable candidate pairs, scores similarity using a local hybrid NLP engine, explains each result, and allows human reviewers to mark candidates as Duplicate, Not Duplicate, or Unsure.

The system does not claim that a part is definitely duplicated. It returns possible duplicate candidates with confidence scores, matched and mismatched business fields, data-quality warnings, and recommended review actions.

## 2. Business Purpose

Large ERP environments often accumulate duplicate or near-duplicate part master records because users create new parts using slightly different descriptions, abbreviations, units, product classifications, or site-specific naming conventions. Duplicate part masters can increase inventory carrying cost, procurement fragmentation, reporting noise, and maintenance complexity.

This system provides a safe assisted-review workflow:

- Upload an ERP part master CSV export.
- Select business conditions that should narrow comparisons.
- Run local duplicate candidate detection.
- Review scored and explained candidate pairs.
- Capture human feedback for governance and future model improvement.
- Export review results.

## 3. Current Scope

In scope:

- CSV upload using IFS-compatible field names.
- Field alias mapping for realistic ERP exports such as PART_TYPE, INVENTORY_UOM, COMMODITY_GROUP_1, COMMODITY_GROUP_2, and SAFETY_CODE.
- Required-field validation for PART_NO and DESCRIPTION.
- Optional business-condition fields such as CONTRACT, TYPE_CODE, UNIT_MEAS, commodity groups, accounting group, product code, product family, product category, HSN/SAC code, and hazard code.
- Local hybrid NLP similarity using TF-IDF character n-grams, RapidFuzz, part-number similarity, technical-token matching, and business rule scoring.
- Human review feedback.
- CSV export of results.
- Health and readiness endpoints.
- Data-quality warnings.
- Sensitive Data Mode transparency.
- Synthetic load-test simulation.
- Docker Compose support.
- Kubernetes-ready manifests.

Out of scope for the current version:

- Real IFS Cloud API integration.
- IFS Projection integration.
- OAuth or identity integration.
- Direct database connection to inventory_part_tab.
- IFS Lobby pages or event actions.
- Automatic part merging.
- Paid AI APIs.
- Deep learning models.
- Claims of perfect duplicate detection.

## 4. Architecture Overview

The system follows a simple single-application architecture with a React frontend, a FastAPI backend, a local NLP/scoring engine, SQLAlchemy persistence, and SQLite for the demo database.

Text architecture diagram:

```text
User Browser
  |
  | CSV upload, validation request, scan request, feedback
  v
React + Vite Frontend
  |
  | REST API over HTTP
  v
FastAPI Backend
  |
  +-- API Routes
  |     /health
  |     /ready
  |     /api/config/fields
  |     /api/scans/upload
  |     /api/scans/validate-only
  |     /api/scans/{id}/candidates
  |     /api/scans/{id}/warnings
  |     /api/candidates/{id}/feedback
  |     /api/load-test/run
  |
  +-- Services
  |     ValidationService
  |     ScanRunner
  |     FeedbackService
  |     ExportService
  |     LoadTestService
  |     PrivacyService
  |
  +-- AI/NLP Engine
  |     Normalizer
  |     CandidateGenerator
  |     SimilarityModel
  |     Scoring
  |     Explanation
  |
  +-- Repositories
  |     ScanRepository
  |     CandidateRepository
  |     WarningRepository
  |
  v
SQLite Demo Database
```

## 5. End-to-End Processing Flow

### Step 1: CSV Upload

The user uploads a CSV file from the frontend New Scan page. The backend accepts a multipart request containing the file, scan name, selected business fields, and similarity threshold.

The backend reads the file in memory, checks that it is not empty, checks the configured upload-size limit, parses it using Pandas, normalizes column names to uppercase, and applies known field aliases.

Example alias mapping:

- PART_TYPE maps to TYPE_CODE.
- INVENTORY_UOM maps to UNIT_MEAS.
- COMMODITY_GROUP_1 maps to PRIME_COMMODITY.
- COMMODITY_GROUP_2 maps to SECOND_COMMODITY.
- SAFETY_CODE maps to HAZARD_CODE.

### Step 2: Validation and Data-Quality Warnings

The backend validates required fields:

- PART_NO
- DESCRIPTION

It also checks for:

- Empty descriptions.
- Duplicate part numbers.
- Selected fields that are missing from the CSV.
- Selected fields with high null percentages.
- Sensitive-looking values such as emails, phone numbers, project/work-order references, and supplier/vendor references.

Missing optional fields do not stop the scan. The system continues safely and records warnings so the reviewer understands the quality of the input data.

### Step 3: Sensitive Data Mode

The current implementation assumes ERP part master data may contain sensitive business information. Sensitive Data Mode is enabled by default.

Current controls:

- The raw uploaded CSV is not persisted.
- Processing is local inside the backend.
- No external AI API is called.
- A SHA-256 file fingerprint can be calculated for traceability.
- Only scan summaries, candidate pairs above threshold, scores, explanations, warnings, and review feedback are persisted.
- Sensitive-pattern warnings are produced for values that look like emails, phone numbers, project/work-order references, or supplier/manufacturer references.

This does not replace enterprise data governance. For real ERP deployment, the application should run inside the customer's controlled network or Kubernetes cluster with approved storage, logging, retention, access control, and audit policies.

### Step 4: Description Normalization

The AI layer first normalizes descriptions so that small spelling and formatting variations do not dominate the result.

Normalization performs:

- Null-safe handling.
- Lowercasing.
- Space trimming.
- Punctuation cleanup.
- Multiple-space compression.
- Alphanumeric splitting such as MCB30A to mcb 30 a, 20MM to 20 mm, and 3PH to 3 ph.
- Known abbreviation expansion such as mcb to miniature circuit breaker and ss to stainless steel.
- Known spelling correction such as decicated or decicatted to desiccated.
- Preservation of critical technical modifiers such as oil, air, hydraulic, stainless, carbon, rubber, copper, pvc, left, and right.

This step is important because ERP descriptions are often written by different users over many years.

### Step 5: Technical Token Extraction

The engine extracts structured technical signals from descriptions:

- Numbers.
- Dimensions.
- Amp values.
- Millimeter values.
- Weight and volume values such as kg, g, l, and ml.
- Voltage values.
- Critical modifiers such as oil vs air or left vs right.

These tokens prevent unsafe overmatching. For example, Generator Oil Filter and Generator Air Filter may look similar as text, but oil and air are critical modifiers and should reduce confidence. Bolt 10MM and Bolt 12MM should not be treated as the same technical item.

### Step 6: Candidate Generation

The system avoids comparing every row with every other row when business fields are available.

If selected fields exist in the CSV, records are grouped by those fields and only compared inside matching groups. For example, if the user selects CONTRACT and UNIT_MEAS, the system compares records within the same site and unit-of-measure group.

If a selected field is missing, the scan continues and a warning is generated. If a selected field has too many empty values, it is treated as unreliable and a warning is generated.

If no useful selected fields are available, the system falls back to loose blocking based on normalized description tokens.

Candidate generation rules:

- Always use DESCRIPTION for similarity.
- Do not compare a record with itself.
- Do not create reverse duplicates.
- A-B is allowed; B-A is not repeated.
- A safety cap of 20,000 candidate pairs is enforced for synchronous scans.

### Step 7: Similarity Scoring

Each candidate pair is scored using a hybrid local NLP model.

Model components:

- TF-IDF character n-gram similarity with n-grams from 3 to 5 characters.
- Cosine similarity over TF-IDF vectors.
- RapidFuzz fuzzy string similarity using token-set and partial matching.
- Part-number similarity.
- Technical-token similarity.
- Business-field match scoring.

Description Similarity formula:

```text
Description Similarity = 60% TF-IDF score + 40% RapidFuzz score
```

Final Score formula:

```text
Final Score =
  60% Description Similarity
+ 20% Selected Business Field Match Score
+ 10% Part Number Similarity
+ 10% Technical Token Score
```

Additional penalties are applied for critical technical mismatches:

- Different critical modifiers reduce score, for example oil vs air.
- Different important numbers reduce score, for example 20A vs 30A or 10MM vs 12MM.

### Step 8: Confidence Classification

The final score is converted into a confidence level:

| Score Range | Confidence | Recommended Action |
| --- | --- | --- |
| 90 to 100 | HIGH | Review as likely duplicate |
| 75 to 89 | MEDIUM | Manual review recommended |
| 60 to 74 | LOW | Weak match; review only in discovery mode |
| Below 60 | IGNORE | Not likely duplicate |

Candidates below the user-selected threshold are not stored as scan results.

### Step 9: Explanation Generation

Explanations are deterministic and rule-based. They are not generated by an LLM.

Example explanations:

- Descriptions are highly similar and selected business fields match.
- Descriptions are similar, but critical modifier differs: oil vs air.
- Same site and UOM, but product classification differs.
- Different site detected. Treat as cross-site possible duplicate.
- Classification fields are missing, so the result is based mainly on description similarity.

This makes the reasoning repeatable, auditable, and easier for master-data teams to challenge.

### Step 10: Human Review and Feedback

The user can mark each candidate as:

- Duplicate.
- Not Duplicate.
- Unsure.

The reviewer can also add comments. Feedback is stored in the duplicate_feedback table and the candidate review status is updated.

In the current version, feedback does not retrain or change the model automatically. It is stored for audit, governance, and future supervised calibration. This is intentional for the demo because uncontrolled automatic learning from reviewer input can introduce quality and compliance risks.

### Step 11: Export

Scan candidates can be exported to CSV. The export contains the candidate pair details, confidence scores, matched and mismatched fields, explanations, recommended actions, and review status.

## 6. AI/NLP Layer Explained

The system uses a local hybrid NLP similarity engine:

```text
TF-IDF Character N-Gram + RapidFuzz Fuzzy Matching + Business Rule Scoring
```

Why this model is suitable:

- It runs locally with no external API dependency.
- It is cost-effective.
- It is stable and repeatable.
- It handles spelling mistakes, abbreviations, and formatting variations.
- It is explainable enough for ERP master-data review.
- It is lightweight enough for container and Kubernetes deployment.

Why paid LLMs are not used:

- ERP exports may contain sensitive business data.
- External API calls would create data-sharing and compliance concerns.
- LLM reasoning may be less deterministic.
- The business task needs repeatable similarity scoring, not natural-language generation.

Why deep learning is not used yet:

- A strong labeled training dataset is not yet available.
- The demo needs transparent reasoning.
- Traditional similarity methods are easier to validate with business users.
- Feedback should be collected first before supervised training is considered.

## 7. Data Model

The backend uses SQLAlchemy and SQLite in the demo.

Main tables:

- duplicate_scan: scan metadata, status, selected fields, threshold, totals, timestamps, and model version.
- duplicate_candidate: pair-level result, descriptions, scores, matched fields, mismatched fields, explanation, recommended action, and review status.
- duplicate_feedback: reviewer decision and comment.
- scan_warning: validation, data-quality, privacy, and scan warnings.

SQLite is acceptable for the local demo. For production-scale ERP deployment, PostgreSQL or another enterprise database should replace SQLite.

## 8. Frontend Application

The frontend is a React + Vite application with plain CSS.

Main pages:

- Dashboard: health, readiness, model version, total scans, total candidates, and total feedback records.
- New Scan: CSV upload, scan name, condition checkboxes, threshold slider, validation button, and run-scan button.
- Scan Results: candidate table, scores, confidence badges, explanations, detailed component scores, and review actions.
- Warnings: missing fields, empty descriptions, duplicate part numbers, high-null fields, and sensitive-pattern warnings.
- Load Test: synthetic data generation and load-test execution.
- Data Security: explains local processing and sensitive-data handling.
- Future IFS Integration: explains the future IFS Cloud integration path without implementing it.

The UI clearly communicates that this is AI-assisted candidate detection, not automatic merging.

## 9. API Summary

Key endpoints:

- GET /health
- GET /ready
- GET /api/config/fields
- GET /api/scans
- GET /api/scans/{scan_id}
- GET /api/scans/{scan_id}/candidates
- GET /api/scans/{scan_id}/warnings
- POST /api/scans/upload
- POST /api/scans/validate-only
- GET /api/scans/{scan_id}/export
- POST /api/candidates/{candidate_id}/feedback
- GET /api/diagnostics/summary
- POST /api/load-test/generate
- POST /api/load-test/run

## 10. Reliability and Failure Handling

Reliability features implemented:

- Health endpoint for liveness checks.
- Readiness endpoint that checks database connectivity.
- Required-column validation.
- Empty-file handling.
- Bad-CSV handling.
- Upload-size limit.
- Synchronous record-count limit.
- Empty-description skipping with warning.
- Missing selected-field warning.
- High-null selected-field warning.
- Duplicate part-number warning.
- Pair-generation safety cap.
- Explicit FAILED scan status if scan execution raises an error.

The latest readiness test recorded:

- Health endpoint passed.
- Readiness endpoint passed.
- ERP-format CSV upload passed with 99 records, 25 candidates, and 9 warnings.
- Empty-file handling returned HTTP 400.
- Missing required DESCRIPTION validation returned invalid validation result.
- Model-failure cases for oil vs air, numeric mismatch, and left vs right were correctly reduced below duplicate confidence.

## 11. Scalability and Load Handling

Current scalability strategy:

- Candidate blocking by selected business fields.
- Loose description blocking only when business fields are unavailable.
- No self-pairs and no reverse duplicate pairs.
- 20,000 candidate-pair cap for synchronous demo scans.
- Synthetic load-test endpoint for repeatable demo benchmarking.
- Docker and Kubernetes-ready packaging.

Latest local synthetic load-test evidence:

| Record Count | Candidate Pairs | Processing Time | Candidates Found | Warnings |
| --- | --- | --- | --- | --- |
| 500 | 14,680 | 6.488 seconds | 8,915 | 0 |
| 2,000 | 20,000 | 8.520 seconds | 14,972 | 1 |
| 5,000 | 20,000 | 10.553 seconds | 20,000 | 1 |

These results show that the demo can handle realistic pilot-scale files and safely cap expensive comparisons. For multi-million-record ERP scale, the architecture should be extended before production rollout.

Recommended production-scale changes:

- Replace SQLite with PostgreSQL.
- Store uploads in controlled object storage only when required by governance.
- Move scan execution to a background worker.
- Add job status polling and cancellation.
- Use database indexes for scan, candidate, and feedback queries.
- Add distributed tracing and metrics.
- Add horizontal pod autoscaling for API and worker components.
- Consider approximate nearest-neighbor search or precomputed blocking keys for very large catalogs.

## 12. Load Balancing and Kubernetes Readiness

The application includes Kubernetes manifests for backend and frontend deployment.

Current Kubernetes demo posture:

- Backend exposes /health for liveness.
- Backend exposes /ready for readiness.
- ConfigMap stores environment-level settings.
- Secret example contains placeholder future IFS values only.
- Frontend runs as a separate deployment.
- Backend deployment is configured conservatively because SQLite is not suitable for multiple writing replicas.

For true load-balanced production:

- The API should become stateless.
- SQLite must be replaced by PostgreSQL or another external database.
- Backend replicas can then scale horizontally behind a Kubernetes Service or Ingress.
- Long-running scans should be handled by background workers.
- The frontend can be served by Nginx or a static hosting layer.
- Health and readiness probes should be used by Kubernetes for traffic routing.
- Horizontal Pod Autoscaler can scale API pods based on CPU, request latency, or custom queue depth.

No sticky sessions are required once state is externalized to the database and object storage.

## 13. Security and Privacy Assessment

The most important security concern is that uploaded CSV files may contain sensitive commercial data from a large ERP system.

Current demo controls:

- Local-only processing.
- No paid AI or external LLM API.
- Raw CSV not persisted.
- Sensitive-pattern warnings.
- Size and row limits.
- CORS limited for local/demo frontend origins.
- Dependency audit previously passed with no known npm or Python vulnerabilities in the readiness run.
- Bandit static security scan previously reported no issues in the readiness run.

Additional controls required before enterprise production:

- Authentication and authorization.
- Role-based access control for upload, review, export, and admin actions.
- TLS-only access.
- Network policies in Kubernetes.
- Private container registry.
- Centralized audit logging.
- Data retention policy.
- Encryption at rest for persisted database data.
- Malware scanning for uploads if files are accepted from untrusted workstations.
- Strict file-type and content validation.
- Secrets managed by a platform secret store.
- Security review for CSV formula injection in exported files.
- Production observability and incident response processes.

## 14. Testing and Validation

Automated tests cover:

- Normalization.
- Technical token extraction.
- TF-IDF similarity.
- Fuzzy similarity.
- Part number similarity.
- Technical token score.
- Candidate generation.
- Scoring.
- CSV validation.
- API health endpoint.
- Feedback endpoint.

Model evaluation support:

- data/evaluation_pairs.csv contains duplicate, non-duplicate, spelling variation, critical modifier, and numeric mismatch examples.
- backend/app/services/evaluate_model.py calculates precision, recall, F1-score, false positives, and false negatives.

The model should be evaluated with customer-specific historical examples before production use. Threshold tuning affects precision and recall.

## 15. Operations

Recommended operational metrics:

- Upload count.
- Scan count.
- Scan duration.
- Candidate-pair count.
- Candidate count above threshold.
- Warning count.
- Feedback distribution.
- Error rate.
- API latency.
- Worker queue depth, once background processing is introduced.

Recommended alerts:

- Readiness failures.
- Repeated scan failures.
- High processing time.
- Pair-limit reached frequently.
- High warning rates for missing or null fields.
- Storage growth.
- Dependency vulnerability alerts.

## 16. Future IFS Integration Path

The current system intentionally uses CSV only.

Future IFS integration could be added after the detection engine is validated:

- Read Inventory Part data through approved IFS Cloud APIs or Projections.
- Add an authenticated service-to-service integration.
- Run a preventive duplicate check when a user creates or changes a part.
- Return top possible duplicate candidates to the ERP workflow.
- Show a warning to the user before saving a potentially duplicated part.
- Keep human review and business ownership in the loop.

Future integration must be designed with IFS security, customer identity provider, network boundaries, audit requirements, and API rate limits.

## 17. Production Readiness Verdict

Current verdict: strong production-oriented demo and pilot candidate.

It is suitable for:

- Demonstrating business value.
- Running local or controlled pilot scans on CSV exports.
- Testing duplicate-detection logic with business users.
- Collecting human feedback.
- Validating threshold behavior and explanations.
- Showing future Kubernetes readiness.

It is not yet sufficient for direct enterprise production against a large live IFS ERP estate without additional hardening.

Required before large-scale production:

- Enterprise authentication and authorization.
- PostgreSQL or enterprise database replacement for SQLite.
- Background scan processing.
- Production observability.
- Security governance for uploads and exports.
- Formal performance testing with customer-scale data.
- Disaster recovery and backup design.
- Data-retention and audit policies.

## 18. Supported CSV Fields

Required:

| Field | Business Meaning |
| --- | --- |
| PART_NO | Part No |
| DESCRIPTION | Item Description |

Optional:

| Field | Business Meaning |
| --- | --- |
| CONTRACT | Site |
| TYPE_CODE | Purchase Type / Part Type |
| UNIT_MEAS | Inventory UOM |
| PRIME_COMMODITY | Com Group 01 |
| SECOND_COMMODITY | Com Group 02 |
| HAZARD_CODE | Safety Code |
| ACCOUNTING_GROUP | Accounting Group |
| PART_PRODUCT_CODE | Product Code |
| PART_PRODUCT_FAMILY | Product Family |
| PRODUCT_CATEGORY_ID | Product Category |
| HSN_SAC_CODE | HSN/SAC Code |

## 19. Demo Script

1. Start the backend.
2. Start the frontend.
3. Open the dashboard and confirm health/readiness.
4. Open New Scan.
5. Upload data set.csv or sample_inventory_parts.csv.
6. Select fields such as Site, Inventory UOM, Product Code, and Product Family.
7. Set threshold to 60 for discovery or 75+ for stricter review.
8. Click Validate Only and review warnings.
9. Click Run Scan.
10. Open results and inspect candidate scores, matched fields, mismatched fields, and explanations.
11. Expand a result to show TF-IDF, fuzzy, part-number, and technical-token scores.
12. Mark selected candidates as Duplicate, Not Duplicate, or Unsure.
13. Add reviewer comments.
14. Export results as CSV.
15. Open Load Test and run synthetic load simulation.
16. Open Data Security and Future IFS Integration pages.

## 20. Local Run Commands

Backend:

```powershell
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Docker Compose:

```powershell
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector
docker compose up --build
```

Tests:

```powershell
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\backend
pytest
```

Model evaluation:

```powershell
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector\backend
python -m app.services.evaluate_model
```

## 21. References Used for Document Structure

- arc42 documentation template: https://docs.arc42.org/
- C4 model for architecture communication: https://c4model.com/
- Microsoft Azure Well-Architected Framework: https://learn.microsoft.com/azure/well-architected/
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

## 22. Final Positioning Statement

This demo is a production-oriented duplicate intelligence engine for Inventory Part master data. It uses configurable business conditions, local hybrid NLP similarity, confidence scoring, explanation generation, data-quality warnings, and human feedback to identify possible duplicate parts safely and cost-effectively. The current version works with CSV exports using IFS-compatible field names. Real-time IFS Cloud integration is kept as future work after the detection engine is validated.
