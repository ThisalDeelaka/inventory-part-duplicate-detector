# Claude Prompt: Generate Company Technical Documentation

Use this prompt in Claude to generate a polished company-facing technical document for the project.

---

## Prompt

You are acting as a senior software architect, chief technology lead, full-stack engineer, and AI/NLP engineer.

Write a professional technical architecture and design document for the project below. The audience is company leadership, ERP stakeholders, software architects, security reviewers, data owners, and engineering teams evaluating whether this system is suitable for a real enterprise IFS ERP environment.

The document should be detailed, clear, and suitable for export to Word or PDF.

Use a professional architecture-document style inspired by:

- arc42 software architecture documentation
- C4 model architecture communication
- Microsoft Azure Well-Architected Framework principles
- OWASP file-upload security guidance

Do not write a marketing brochure. Write a technical document with honest limits, risks, and production-readiness recommendations.

---

## Project Identity

Project repository name:

```text
inventory-part-duplicate-detector
```

Business title:

```text
Part Master Duplication Identifier
```

Purpose:

This system identifies possible duplicate inventory part master records from ERP CSV exports. It is inspired by IFS Inventory Part Master data, but the current version does not integrate with IFS Cloud directly.

The system accepts CSV files using IFS-compatible field names, detects possible duplicate part candidates, produces confidence scores, explains why candidates were matched, shows data-quality warnings, and allows human review feedback.

Important positioning:

```text
This is AI-assisted duplicate candidate detection, not automatic merging.
The system does not claim that two parts are definitely duplicates.
Human review is required.
```

---

## Mandatory Scope Rules

Clearly state that the current version:

- Uses CSV uploads only.
- Uses IFS-compatible field names.
- Treats IFS only as source/domain context.
- Does not integrate with IFS Cloud directly.
- Does not use IFS Projections.
- Does not use OAuth.
- Does not connect directly to `inventory_part_tab`.
- Does not create IFS Lobby pages.
- Does not create IFS Event Actions.
- Does not use paid AI APIs.
- Does not use ChatGPT, Gemini, OpenAI APIs, or other external LLM APIs.
- Does not use deep learning.
- Does not automatically merge or modify ERP master data.

Future IFS integration should be described only as future work.

---

## Technology Stack

Backend:

- Python 3.11+
- FastAPI
- Pandas
- scikit-learn
- RapidFuzz
- SQLAlchemy
- SQLite for demo
- Pytest

Frontend:

- React
- Vite
- Plain CSS / lightweight styling

AI/NLP:

- TF-IDF character n-gram similarity
- Cosine similarity
- RapidFuzz fuzzy matching
- Part number similarity
- Technical token matching
- Business rule scoring

Deployment:

- Docker Compose
- Kubernetes-ready manifests

---

## Current Architecture

Describe the architecture as:

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
  +-- Services
  +-- AI/NLP Engine
  +-- Repositories
  v
SQLite Demo Database
```

Main backend layers:

- API routes
- Services
- Repositories
- Engine
- Database models

Main backend services/modules:

- `ValidationService`
- `ScanRunner`
- `FeedbackService`
- `ExportService`
- `LoadTestService`
- `PrivacyService`

Main AI/NLP engine modules:

- `normalizer.py`
- `candidate_generator.py`
- `similarity_model.py`
- `scoring.py`
- `explanation.py`

Repository layer:

- `ScanRepository`
- `CandidateRepository`
- `WarningRepository`

Frontend pages:

- Dashboard
- New Scan
- Scan Results
- Warnings
- Load Test
- Data Security
- Future IFS Integration

---

## Required CSV Fields

Required:

| Field | Meaning |
|---|---|
| `PART_NO` | Part No |
| `DESCRIPTION` | Item Description |

Optional:

| Field | Meaning |
|---|---|
| `CONTRACT` | Site |
| `TYPE_CODE` | Purchase Type / Part Type |
| `UNIT_MEAS` | Inventory UOM |
| `PRIME_COMMODITY` | Com Group 01 |
| `SECOND_COMMODITY` | Com Group 02 |
| `HAZARD_CODE` | Safety Code |
| `ACCOUNTING_GROUP` | Accounting Group |
| `PART_PRODUCT_CODE` | Product Code |
| `PART_PRODUCT_FAMILY` | Product Family |
| `PRODUCT_CATEGORY_ID` | Product Category |
| `HSN_SAC_CODE` | HSN/SAC Code |

Supported aliases for realistic ERP exports:

| Uploaded Column | Canonical Field |
|---|---|
| `PART_TYPE` | `TYPE_CODE` |
| `INVENTORY_UOM` | `UNIT_MEAS` |
| `COMMODITY_GROUP_1` | `PRIME_COMMODITY` |
| `COMMODITY_GROUP_2` | `SECOND_COMMODITY` |
| `SAFETY_CODE` | `HAZARD_CODE` |

---

## End-to-End Flow To Explain

Explain this flow from CSV upload to final review result:

1. User uploads CSV.
2. Backend checks file size and parseability.
3. Backend normalizes column names and applies field aliases.
4. Backend validates required fields.
5. Backend checks data quality:
   - missing required columns
   - empty descriptions
   - duplicate part numbers
   - missing selected optional fields
   - high-null selected fields
   - sensitive-looking values
6. Backend creates a scan record.
7. Descriptions are normalized.
8. Technical tokens are extracted.
9. Candidate pairs are generated using selected business fields.
10. Each pair is scored using the hybrid AI/NLP model.
11. Final score is classified into confidence bands.
12. Explanation is generated.
13. Candidates above threshold are saved.
14. Warnings are saved.
15. User reviews candidates.
16. User marks each candidate as Duplicate, Not Duplicate, or Unsure.
17. User comments are saved as feedback.
18. User exports results as CSV.

---

## AI/NLP Model Details

The selected model is:

```text
TF-IDF Character N-Gram + RapidFuzz Fuzzy Matching + Business Rule Scoring
```

Explain why this model was selected:

- Runs locally.
- No external API dependency.
- Cost-effective.
- Repeatable.
- Explainable.
- Good for spelling mistakes and abbreviations.
- Good for ERP part master text.
- Suitable for Kubernetes deployment.

Explain what the system does during normalization:

- Handles null safely.
- Lowercases text.
- Trims spaces.
- Removes unnecessary punctuation.
- Replaces multiple spaces with one.
- Splits alphanumeric values:
  - `MCB30A` becomes close to `mcb 30 a`
  - `20MM` becomes `20 mm`
  - `3PH` becomes `3 ph`
- Expands known abbreviations:
  - `mcb` becomes `miniature circuit breaker`
  - `ss` becomes `stainless steel`
- Corrects known spelling variations:
  - `decicated` becomes `desiccated`
  - `decicatted` becomes `desiccated`
- Preserves critical technical words:
  - oil
  - air
  - hydraulic
  - stainless
  - carbon
  - rubber
  - copper
  - pvc
  - left
  - right

Explain technical token extraction:

- numbers
- dimensions
- amp values
- mm values
- kg/g/l/ml values
- voltage values
- critical modifiers

Important examples:

- `MCB30A` and `MCB 30 Amp` should score high.
- `Generator Oil Filter` and `Generator Air Filter` should not score high because oil and air differ.
- `Decicated Coconut type 1` and `Desiccated Coconut type 1` should score high.
- `20A` and `30A` should not be treated as the same value.
- `10MM` and `12MM` should not be treated as the same value.

---

## Scoring Formula

Explain the scoring formula exactly.

Description Similarity:

```text
Description Similarity = 60% TF-IDF score + 40% RapidFuzz score
```

Final Score:

```text
Final Score =
  60% Description Similarity
+ 20% Selected Business Field Match Score
+ 10% Part Number Similarity
+ 10% Technical Token Score
```

Mention that critical mismatches apply penalties:

- oil vs air
- left vs right
- 20A vs 30A
- 10MM vs 12MM

Confidence bands:

| Score | Confidence | Recommended Action |
|---|---|---|
| 90 to 100 | HIGH | Review as likely duplicate |
| 75 to 89 | MEDIUM | Manual review recommended |
| 60 to 74 | LOW | Weak match; review only in discovery mode |
| Below 60 | IGNORE | Not likely duplicate |

---

## Explanation Generation

Explain that explanations are deterministic and rule-based, not LLM-generated.

Example explanations:

- Descriptions are highly similar and selected business fields match.
- Descriptions are similar, but critical modifier differs: oil vs air.
- Same site and UOM, but product classification differs.
- Different site detected. Treat as cross-site possible duplicate.
- Classification fields are missing, so the result is based mainly on description similarity.

---

## Feedback Loop

Explain clearly:

- User review feedback is stored.
- The reviewer can mark Duplicate, Not Duplicate, or Unsure.
- Reviewer comments are saved.
- In the current version, feedback does not automatically retrain the model.
- Feedback can be used in a future supervised-learning or threshold-calibration phase.

Make clear that this is intentional because automatic learning from unvalidated feedback can introduce quality and compliance risk.

---

## Sensitive Data / Security Section

Write a strong section about sensitive ERP data.

Explain that uploaded CSV files may contain commercially sensitive data from large IFS ERP customers.

Current controls:

- Local-only processing.
- No external AI API.
- Raw uploaded CSV is not persisted.
- SHA-256 file fingerprint can be calculated.
- Only scan summaries, candidates, warnings, scores, explanations, and feedback are persisted.
- Sensitive-pattern warnings can detect email-like values, phone-like values, project/work-order references, and supplier/manufacturer references.
- Upload-size and row-count limits exist.

Be honest:

- This does not replace enterprise data governance.
- For real production, deploy inside the customer-controlled Kubernetes/network environment.

Production security recommendations:

- Authentication.
- Authorization / RBAC.
- TLS.
- Network policies.
- Private container registry.
- Secrets manager.
- Audit logging.
- Retention policy.
- Encryption at rest.
- Malware scanning for uploads if needed.
- CSV formula injection protection for exports.
- Data classification and DLP review.

---

## Reliability Section

Explain reliability features:

- `/health`
- `/ready`
- database readiness check
- validation-only endpoint
- bad CSV handling
- empty file handling
- missing column handling
- empty description warnings
- duplicate part number warnings
- missing selected field warnings
- high-null field warnings
- scan status tracking
- failed scan status
- export support
- tests

---

## Scalability and Load Test Section

Explain current scalability strategy:

- Candidate grouping by selected fields.
- Avoid full O(n²) comparisons when business fields are selected.
- Loose blocking when no fields are selected.
- No self-pairs.
- No reverse duplicate pairs.
- Candidate pair safety cap of 20,000 for synchronous demo scans.
- Synthetic load-test simulation.

Use this latest readiness evidence:

| Record Count | Candidate Pairs | Processing Time | Candidates Found | Warnings |
|---|---:|---:|---:|---:|
| 500 | 14,680 | 6.488 seconds | 8,915 | 0 |
| 2,000 | 20,000 | 8.520 seconds | 14,972 | 1 |
| 5,000 | 20,000 | 10.553 seconds | 20,000 | 1 |

Be honest:

- This proves demo/pilot readiness.
- It does not prove multi-million-record production readiness.

For large production IFS environments, recommend:

- PostgreSQL instead of SQLite.
- Background scan workers.
- Job queue.
- Object storage for controlled file retention if required.
- Horizontal scaling.
- Observability.
- Metrics.
- Approximate nearest-neighbor or stronger blocking strategy for very large catalogs.
- Incremental scans.

---

## Kubernetes and Load Balancing Section

Explain:

- The app includes Kubernetes manifests.
- Backend has liveness probe using `/health`.
- Backend has readiness probe using `/ready`.
- ConfigMap stores runtime configuration.
- Secret example has placeholders only for future IFS integration.
- Current demo should not horizontally scale backend writes with SQLite.

Production load-balanced architecture:

```text
                +----------------+
                |  User Browser  |
                +-------+--------+
                        |
                        v
                +----------------+
                | Ingress / WAF  |
                +-------+--------+
                        |
          +-------------+-------------+
          |                           |
          v                           v
  +---------------+           +---------------+
  | Frontend Pod  |           | Frontend Pod  |
  +---------------+           +---------------+
                        |
                        v
              +-------------------+
              | Backend Service   |
              +---------+---------+
                        |
          +-------------+-------------+
          |                           |
          v                           v
  +---------------+           +---------------+
  | Backend Pod   |           | Backend Pod   |
  +-------+-------+           +-------+-------+
          |                           |
          +-------------+-------------+
                        |
                        v
              +-------------------+
              | Background Worker |
              +---------+---------+
                        |
                        v
              +-------------------+
              | PostgreSQL        |
              +-------------------+
```

Explain:

- No sticky sessions are needed once state is externalized.
- API pods can scale horizontally after replacing SQLite.
- Workers can scale separately for scan workloads.
- HPA can scale on CPU, latency, or queue depth.

---

## Required Diagrams and Visualizations

Include these diagrams using Mermaid where possible.

### 1. System Context Diagram

Show:

- Business user
- React frontend
- FastAPI backend
- SQLite demo database
- CSV export
- Future IFS Cloud APIs as future-only external system

### 2. Container Diagram

Show:

- Frontend container
- Backend container
- NLP/scoring engine inside backend
- SQLite database
- Docker Compose
- Kubernetes deployment boundary

### 3. CSV-to-Result Sequence Diagram

Show:

- User uploads CSV
- Frontend sends upload
- Backend validates
- Backend normalizes
- Candidate generator creates pairs
- Similarity model scores
- Explanation engine explains
- Database stores results
- Frontend shows results
- User submits feedback

### 4. AI Scoring Pipeline Diagram

Show:

- Raw description
- Normalizer
- Technical token extractor
- TF-IDF similarity
- RapidFuzz similarity
- Part number similarity
- Business field scorer
- Weighted final score
- Confidence classifier
- Explanation generator

### 5. Deployment Diagram

Show:

- Local dev
- Docker Compose
- Kubernetes-ready production target
- Future PostgreSQL
- Future worker queue

### 6. Score Band Visualization

Use a table or simple visual showing:

```text
0-59 IGNORE | 60-74 LOW | 75-89 MEDIUM | 90-100 HIGH
```

---

## Database Tables

Document these tables:

### duplicate_scan

- id
- scan_name
- source_type
- selected_fields
- threshold
- status
- total_records
- total_candidates
- warnings_count
- started_at
- completed_at
- model_version

### duplicate_candidate

- id
- scan_id
- contract_a
- part_no_a
- description_a
- contract_b
- part_no_b
- description_b
- similarity_score
- confidence_level
- description_similarity
- tfidf_score
- fuzzy_score
- part_no_similarity
- technical_token_score
- matched_fields
- mismatched_fields
- explanation
- recommended_action
- review_status
- reviewed_by
- reviewed_at

### duplicate_feedback

- id
- candidate_id
- user_decision
- user_comment
- created_by
- created_at

### scan_warning

- id
- scan_id
- warning_type
- message
- record_reference
- created_at

---

## API Endpoints

Document:

- `GET /health`
- `GET /ready`
- `GET /api/config/fields`
- `GET /api/scans`
- `GET /api/scans/{scan_id}`
- `GET /api/scans/{scan_id}/candidates`
- `GET /api/scans/{scan_id}/warnings`
- `POST /api/scans/upload`
- `POST /api/scans/validate-only`
- `GET /api/scans/{scan_id}/export`
- `POST /api/candidates/{candidate_id}/feedback`
- `GET /api/diagnostics/summary`
- `POST /api/load-test/generate`
- `POST /api/load-test/run`

---

## Testing and Production Readiness Evidence

Mention that tests cover:

- normalizer
- technical token extraction
- TF-IDF similarity
- fuzzy similarity
- part number similarity
- technical token score
- candidate generation
- scoring
- CSV validation
- API health endpoint
- feedback endpoint

Mention readiness checks:

- Backend tests passed.
- Frontend build passed.
- Docker Compose smoke test passed.
- Bandit security scan passed.
- pip-audit passed.
- npm audit passed.
- Production readiness script passed.

Use careful wording:

```text
These checks support demo and pilot readiness. They do not replace formal enterprise security, performance, compliance, and disaster-recovery testing.
```

---

## Document Structure To Produce

Generate the final document with these sections:

1. Title Page
2. Executive Summary
3. Business Problem and Purpose
4. Scope and Non-Scope
5. Stakeholders and Usage Context
6. Architecture Overview
7. End-to-End CSV Processing Flow
8. AI/NLP Model and Reasoning Layer
9. Scoring and Confidence Classification
10. Explanation Generation
11. Human Review and Feedback
12. Data Model
13. API Design
14. Frontend Design
15. Security and Sensitive Data Handling
16. Reliability and Failure Handling
17. Scalability and Load Testing
18. Kubernetes and Load Balancing Readiness
19. Testing and Model Evaluation
20. Current Production Readiness Verdict
21. Limitations and Risks
22. Future IFS Integration Path
23. Production Hardening Roadmap
24. Demo Script
25. Glossary
26. References

---

## Writing Rules

Follow these rules:

- Be technically precise.
- Do not claim perfect duplicate detection.
- Do not imply current IFS integration exists.
- Do not say the system is fully enterprise-production-ready today.
- Say it is a production-oriented demo and pilot-ready engine.
- Explain uncertainty clearly.
- Explain why human review is required.
- Explain that feedback is currently stored but does not retrain the model.
- Use tables where helpful.
- Include Mermaid diagrams.
- Include command examples where useful.
- Keep the tone professional and clear.

---

## Final Positioning Statement To Include

Include this statement near the end:

```text
This demo is a production-oriented duplicate intelligence engine for Inventory Part master data. It uses configurable business conditions, local hybrid NLP similarity, confidence scoring, explanation generation, data-quality warnings, and human feedback to identify possible duplicate parts safely and cost-effectively. The current version works with CSV exports using IFS-compatible field names. Real-time IFS Cloud integration is kept as future work after the detection engine is validated.
```

