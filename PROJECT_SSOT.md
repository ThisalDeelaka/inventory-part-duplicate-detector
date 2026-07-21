
# PROJECT_SSOT.md

## 1. Purpose and Authority

State that:

- this is the authoritative SSOT for evolving the current Inventory Part Duplicate Detector into a production identity-resolution platform;
- repository is `inventory-part-duplicate-detector`;
- development branch is `production-identity-engine`;
- protected baseline tag is `deterministic-demo-v1`;
- baseline commit is `d510cf3c18b3a8448d0f79be3e59c398efb32eae`;
- this file takes precedence over older architecture documents, prompts, README claims and unimplemented proposals when they conflict;
- Codex and humans must read it fully before application changes;
- capabilities cannot be claimed as implemented without source and verification.

## 2. Current Verified Baseline

Document the current application accurately:

Implemented:

- FastAPI backend;
- React/Vite frontend;
- SQLAlchemy;
- SQLite demo database;
- whole-file `UploadFile.read()` plus pandas ingestion;
- synchronous scan execution inside upload request;
- deterministic normalization and dictionaries;
- technical and variant extraction;
- TF-IDF;
- RapidFuzz;
- deterministic guardrails;
- business statuses;
- deterministic explanations;
- feedback;
- grouping;
- CSV export;
- global 20,000 generated-pair cap;
- one active deterministic engine path.

Not implemented:

- workers;
- PostgreSQL production deployment;
- Alembic;
- object storage;
- Parquet;
- scalable lexical/vector retrieval;
- CatBoost/LightGBM identity model;
- LLM gateway;
- IFS integration;
- authentication;
- authorization;
- tenant isolation;
- frontend tests.

Verified baseline:

- 48 backend tests passed with repository Python 3.11;
- Vite production build passed;
- sample smoke had 20 rows, 48 pairs, 10 candidates, 38 rule exclusions and completed;
- `USE_REDESIGNED_ENGINE`, `REDESIGNED_RESULT_MODE`, and `REDESIGNED_INCLUDE_STATUSES` are currently absent;
- deterministic engine must remain runnable throughout migration.

## 3. Product Problem

Explain that clients may have millions of IFS Inventory Part records with:

- different part numbers for the same item;
- abbreviations;
- spelling, punctuation and spacing differences;
- inconsistent descriptions;
- multiple sites;
- missing or incorrect classifications;
- different financial mappings;
- client custom fields and column names;
- meaningful technical differences.

State that the system answers two independent questions:

1. Whether two records represent the same physical/business item.
2. Whether the ERP financial, governance and classification mappings are consistent.

State explicitly:

A financial mapping difference is a conflict to investigate and is not automatic proof of different physical identity.

## 4. Mandatory Safety Boundaries

Include:

- never auto-merge;
- never auto-delete;
- never modify IFS without separately approved governed workflow;
- never hide mapping conflicts;
- missing values are not positive matching evidence;
- LLM is not final authority;
- never send complete CSV to external LLM;
- never silently activate production engine;
- never change legacy output silently;
- no tenant data, label, profile, index, model or prompt mixing.

Require reproducibility from:

- dataset;
- source record;
- semantic profile;
- normalizer;
- dictionary;
- feature;
- model;
- threshold/policy;
- optional LLM provider/model/prompt;
- reviewer and timestamp versions.

## 5. Target Business Semantics

### 5.1 Physical Identity Evidence

Include:

- PART_NO;
- DESCRIPTION;
- MASTER_PART_DESCRIPTION;
- INVENTORY_UOM;
- manufacturer;
- manufacturer part number;
- GTIN;
- model;
- version;
- type designation;
- size;
- capacity;
- dimensions;
- material;
- colour;
- voltage;
- amperage;
- pressure;
- weight;
- pack quantity;
- client-approved technical fields.

State:

- PART_NO importance is client configurable;
- system-generated part numbers may have low semantic value;
- user-defined part numbers may be important;
- MASTER_PART_DESCRIPTION becomes first-class in production;
- UOM mismatch is strong evidence but not a universal hard rejection;
- pack size, conversions, missing data, client policy and data-entry errors must be considered.

### 5.2 Site and Scope

State:

- CONTRACT is site/scope;
- same item + same contract may be a duplicate;
- same item + different contract is normally cross-site standardization;
- same part number across sites may be normal IFS behaviour;
- same-part-number site consistency is separate from different-part-number duplicate detection.

### 5.3 Governance and Financial Evidence

Include:

- COMMODITY_GROUP_1;
- COMMODITY_GROUP_2;
- ACCOUNTING_GROUP;
- PART_PRODUCT_CODE;
- PART_PRODUCT_FAMILY;
- PRODUCT_CATEGORY_ID;
- HSN_SAC_CODE.

State these:

- are not mandatory candidate blockers;
- do not automatically prove different identity;
- do not suppress strong identity candidates;
- produce conflict/anomaly evidence;
- support cluster and site-aware analysis;
- may be intentional or incorrect.

### 5.4 Display/Context Fields

State that, under current client policy:

- PART_TYPE;
- SAFETY_CODE;

do not determine physical identity, but may be preserved, displayed, exported and audited.

## 6. Description and Attribute Policy

May normalize:

- case;
- spacing;
- punctuation;
- singular/plural;
- extra whitespace;
- approved abbreviations;
- equivalent unit formatting;
- accents;
- harmless stop words.

Must preserve:

- size;
- capacity;
- model;
- version;
- material;
- environment/instance;
- identity-relevant location;
- serial/unique identifiers;
- pack quantity;
- voltage;
- amperage;
- pressure;
- weight;
- dimensions;
- numeric specifications;
- identity-relevant owner/department;
- colour.

State that safety-critical specifications must never be normalized away.

## 7. Target Business Statuses

Define:

- DUPLICATE_CANDIDATE
- POSSIBLE_DUPLICATE_REVIEW
- RELATED_BUT_NOT_DUPLICATE
- DATA_CONFLICT_REVIEW
- CROSS_SITE_STANDARDIZATION_CANDIDATE
- INSUFFICIENT_DATA
- UNIQUE_NO_MATCH

State that legacy statuses remain available through a compatibility adapter.

## 8. Human Review and Training Labels

Physical identity labels:

- SAME_ITEM
- DIFFERENT_ITEM
- UNSURE

Mapping labels:

- RECORD_A_MAPPING_ERROR
- RECORD_B_MAPPING_ERROR
- BOTH_MAPPINGS_VALID
- BOTH_MAPPINGS_INCORRECT
- UNSURE

Every review event preserves:

- candidate and record IDs;
- reviewer;
- timestamp;
- note;
- evidence snapshot;
- engine/model/profile versions;
- prior decision.

State the practical initial target:

- about 2,000 reviewed pairs;
- first 200–300 double-reviewed;
- separate held-out evaluation set;
- active learning for uncertain pairs.

## 9. Target Production Architecture

Include this exact conceptual flow:

CSV or future IFS adapter
→ staged object storage
→ streaming validation and schema profiling
→ client semantic profile
→ canonical records with raw attributes
→ Parquet
→ lexical/vector index
→ top-K candidate retrieval
→ pair features
→ physical identity model
→ financial mapping conflict/anomaly analysis
→ deterministic safety policy
→ business decision composer
→ optional LLM assistance
→ human review
→ governed training feedback.

Also show PostgreSQL storing jobs, audits, profiles, reviews and metadata.

## 10. Target Technology Stack

Use:

- React/Vite;
- FastAPI;
- PostgreSQL;
- Alembic;
- S3-compatible storage;
- MinIO locally;
- Parquet;
- PyArrow;
- Polars;
- Redis;
- Celery;
- OpenSearch;
- local sentence-transformer embeddings by default;
- CatBoost initially;
- optional provider-independent LLM gateway;
- Docker;
- Kubernetes;
- structured logs, correlation IDs, Prometheus/Grafana-compatible metrics.

State not to add Spark unless measurements prove it necessary.

## 11. LLM Responsibilities and Boundaries

Core must work with:

`LLM_PROVIDER=none`

Approved optional uses:

- unfamiliar-column interpretation;
- column-role suggestions;
- difficult structured attribute extraction;
- difficult-case advisory;
- evidence-grounded business explanations.

Prohibited:

- million-row candidate generation;
- whole-dataset transmission;
- authoritative final decisions;
- safety-policy bypass;
- IFS writes;
- invented evidence;
- silent profile changes.

Providers may include:

- none;
- azure_openai;
- openai;
- anthropic;
- xai;
- local.

Controls:

- strict schemas;
- prompt/model versions;
- field allowlists;
- redaction;
- tenant settings;
- retries;
- timeouts;
- caching;
- cost/token budgets;
- audits;
- deterministic fallback.

## 12. Migration Strategy

State:

- evolve the existing repository;
- do not create a replacement repository;
- use a strangler pattern with:
  - Deterministic Legacy Engine;
  - Production Identity Engine;
- legacy remains default until production gates pass.

## 13. Implementation Phases

Define these phases with objectives and exit gates.

### Phase 1 — Compatibility Seam

- default-off `USE_REDESIGNED_ENGINE`;
- typed engine protocol;
- default path unchanged;
- parity/characterization tests;
- no redesigned behaviour.

### Phase 2 — Typed Contracts and Result Policy

- canonical record, candidate, evidence and result contracts;
- preserve raw attributes;
- legacy adapters;
- version metadata.

### Phase 3 — PostgreSQL and Real Migrations

- PostgreSQL;
- Alembic;
- indexes;
- audit/job-ready schema;
- SQLite only where explicitly supported.

### Phase 4 — Durable Dataset Ingestion

- separate upload and scan;
- object storage;
- chunked/streamed CSV;
- profiling;
- Parquet;
- dataset/profile versions;
- first-class MASTER_PART_DESCRIPTION;
- idempotency/retry.

### Phase 5 — Asynchronous Jobs and Progress

- Redis/Celery;
- job, attempt, stage and checkpoint models;
- retry, cancellation, progress APIs;
- production scans outside HTTP request;
- legacy synchronous mode retained.

### Phase 6 — Client Semantic Profiles

Roles:

- IDENTITY
- IDENTITY_ATTRIBUTE
- GOVERNANCE
- SCOPE
- OPERATIONAL
- DISPLAY_ONLY
- IGNORE

Include arbitrary client schemas, dictionaries, part-number policy, product-family policy, profile UI/API and profile versioning.

### Phase 7 — Scalable Candidate Retrieval

- exact identifiers;
- lexical;
- vector;
- attribute blocking;
- same-site/cross-site;
- merge and deduplicate;
- top-K;
- candidate recall;
- no all-pairs at million-row scale.

### Phase 8 — Generic Pair Features and Training Data

- versioned feature contract;
- current similarity reuse;
- equality, text, numeric, missingness, rarity and conflict features;
- two-label reviews;
- governed export;
- leakage-safe splits.

### Phase 9 — Learned Physical Identity Model

- CatBoost;
- training;
- calibration;
- model registry;
- inference;
- shadow mode;
- deterministic safety remains authoritative;
- report precision, recall, F1, false-negative rate and calibration;
- rollback and explicit promotion.

### Phase 10 — Mapping Analysis and Active Learning

Mapping outputs:

- CONSISTENT
- POSSIBLE_MAPPING_ERROR
- POSSIBLY_INTENTIONAL_DIFFERENCE
- UNKNOWN

Include cluster/site-aware anomaly analysis, active-learning queues, assignment, filtering, history and safe bulk review.

### Phase 11 — Optional LLM Gateway

- provider abstraction;
- column interpretation;
- difficult extraction;
- difficult-case advisory;
- grounded explanations;
- no-provider fallback;
- malformed output, privacy, prompt injection, timeout and cost tests.

### Phase 12 — Production Hardening and IFS Adapter

- authentication;
- authorization;
- tenancy;
- retention;
- observability;
- autoscaling;
- backups;
- disaster recovery;
- approved IFS integration;
- CSV retained;
- IFS remains advisory until separately approved write-back.

## 14. Global Quality Gates

Backend:

- full repository test suite;
- focused unit/integration/regression tests;
- never weaken tests just to pass.

Frontend:

- production build when affected;
- loading/error/empty/large-result states;
- tests after framework introduction.

Database:

- Alembic migration;
- clean and previous-version upgrade;
- indexes and constraints;
- rollback or forward recovery.

API:

- typed schemas;
- compatibility or versioning;
- pagination for unbounded results;
- error and authorization tests.

Performance:

- dataset size;
- runtime;
- memory characteristics;
- candidate recall;
- candidates per record;
- output cap is not proof of scale.

Security:

- tenant isolation;
- secrets;
- minimization;
- redaction;
- audit;
- external-provider field controls.

## 15. Codex Working Protocol

For every future prompt, Codex must:

1. Read PROJECT_SSOT.md completely.
2. Inspect branch, commit and Git status.
3. Stop for unrelated changes.
4. Inspect relevant source/tests.
5. State expected files.
6. Run baseline before changes.
7. Implement only requested scope.
8. Add focused tests.
9. Run verification.
10. Report files, tests/builds/results, limitations and diff summary.
11. Never modify SSOT without explicit instruction.
12. Never commit without explicit instruction.
13. Never use destructive Git commands.
14. Never reset, clean, revert, discard or overwrite unrelated work.
15. Never introduce later-phase infrastructure early.
16. Never claim production readiness before gates pass.
17. Stop and report conflicts with SSOT.

## 16. Prompt and Review Workflow

Document:

1. Implementation prompt without commit.
2. Architect reviews response and diff.
3. Correction prompt if required.
4. Separate atomic commit prompt after approval.

State that unrelated implementation units must not share a commit.

## 17. Immediate Next Step

Define:

**Phase 1A — Compatibility-seam foundation**

It must:

- add `USE_REDESIGNED_ENGINE=false`;
- add minimal engine-selection interface;
- false/default path delegates unchanged to `score_candidate`;
- add parity tests;
- not implement production engine;
- not change candidate generation, scoring, statuses, thresholds, persistence, API or frontend;
- not commit until reviewed.

## 18. Decision Log

Add entry dated 2026-07-20:

- existing repository retained;
- development branch `production-identity-engine`;
- baseline tag preserved;
- deterministic engine retained as baseline/fallback;
- production engine built incrementally;
- physical identity separated from mapping;
- governed reviews supply training data;
- LLM optional only;
- production target is million-row staged, asynchronous, indexed, model-backed and tenant-isolated operation.

## 19. Definition of Final Production Success

Require:

- client-scale non-blocking ingestion;
- million-row retrieval without all-pairs;
- measured recall;
- calibrated predictions;
- separate mapping analysis;
- auditable reviews/training;
- reproducible profile/model/prompt versions;
- no-LLM operation;
- PostgreSQL;
- resumable jobs;
- pagination;
- background exports;
- tenant isolation;
- authentication/authorization;
- monitoring/alerts;
- backup/recovery;
- rollback;
- controlled CSV and approved IFS workflows;
- no automatic merging;
- no uncontrolled source-system writes.

Formatting requirements:

- valid Markdown;
- no placeholder text;
- no claim that future capabilities are implemented;
- all 19 sections must be complete;
- the file must end with:
  `- no uncontrolled source-system writes.`

After creating the file:

1. Confirm it contains all section headings from 1 through 19.
2. Confirm the final line exactly matches the required final line.
3. Report line count and byte count.
4. Show `git diff -- PROJECT_SSOT.md`.
5. Report Git status.
6. Do not stage or commit.