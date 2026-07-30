
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
- default-off redesigned-engine compatibility seam;
- deterministic legacy engine adapter and typed engine-selection boundary;
- Phase 2 canonical-record, candidate-pair, scoring-evidence, scoring-result, target-status, result-policy, legacy-status compatibility, and engine-version metadata contracts;
- target result-policy and legacy-status compatibility contracts without activation of redesigned runtime filtering;
- current five-table SQLite schema characterization tests;
- Alembic 1.18.5 migration-authority foundation;
- deterministic SQLAlchemy and Alembic constraint-naming convention;
- initial Alembic revision `0001_current_schema`;
- disposable SQLite upgrade, downgrade, repeatability, and schema-parity tests;
- read-only SQLite schema fingerprint classifier;
- exact current and approved historical SQLite profile recognition;
- structured deterministic SQLite managed-schema conflicts;
- read-only caller-supplied SQLAlchemy `Engine` and `Connection` classification;
- one active deterministic scoring engine path.

Not implemented:

- workers;
- PostgreSQL production deployment;
- Alembic startup integration;
- existing SQLite database mutation or stamping;
- explicit empty-database Alembic bootstrap;
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

- the latest verified executable implementation baseline is commit `bc1f6a9dec4c9f8954af1e6d1ae19cd3afe97beb`;
- the full backend suite passes with 339 tests and one known pytest configuration warning;
- the focused SQLite schema classifier suite passes with 45 tests;
- the combined schema, migration and classifier regression suite passes with 63 tests;
- the Vite 8.0.16 production build passes with 34 modules transformed;
- the Alembic graph is `<base> -> 0001_current_schema (head)`;
- `USE_REDESIGNED_ENGINE` exists and defaults off;
- `REDESIGNED_RESULT_MODE` and `REDESIGNED_INCLUDE_STATUSES` remain absent from runtime configuration;
- the deterministic legacy engine remains the default and fallback;
- the redesigned production engine is not implemented or runnable;
- current startup still uses `Base.metadata.create_all()` and `ensure_sqlite_demo_columns()`;
- the Phase 3C1 read-only SQLite schema classifier is implemented;
- no explicit Alembic bootstrap service or Alembic startup integration exists;
- as protected-baseline historical evidence, the sample smoke completed with 20 rows, 48 pairs, 10 candidates, and 38 rule exclusions.

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

### Target Result Policy

Define exactly two target result modes:

- `review`
- `all`

The default redesigned result mode is `review`.

`review` includes exactly:

- DUPLICATE_CANDIDATE
- POSSIBLE_DUPLICATE_REVIEW
- DATA_CONFLICT_REVIEW
- CROSS_SITE_STANDARDIZATION_CANDIDATE
- INSUFFICIENT_DATA

`review` excludes exactly:

- RELATED_BUT_NOT_DUPLICATE
- UNIQUE_NO_MATCH

`all` includes all seven target business statuses in the order defined above.

State that this policy applies only to target business statuses. Legacy deterministic statuses must be translated through a separately reviewed compatibility adapter before this policy can be applied.

State that this decision does not activate target-status filtering in the current deterministic path and does not change current scoring, thresholds, candidate or exclusion routing, persistence, APIs, exports, frontend behavior, or legacy statuses.

State that runtime parsing for `REDESIGNED_RESULT_MODE` and override behavior for `REDESIGNED_INCLUDE_STATUSES` remain separate implementation decisions.

### Legacy-to-Target Status Compatibility Mapping

Translate current legacy deterministic business statuses to target business statuses exactly as follows:

- `LIKELY_DUPLICATE` → `DUPLICATE_CANDIDATE`
- `POSSIBLE_DUPLICATE_REVIEW` → `POSSIBLE_DUPLICATE_REVIEW`
- `RELATED_BUT_NOT_DUPLICATE` → `RELATED_BUT_NOT_DUPLICATE`
- `REJECTED_BY_BUSINESS_RULE` → `DATA_CONFLICT_REVIEW`
- `DATA_CONFLICT_REVIEW` → `DATA_CONFLICT_REVIEW`
- `CROSS_SITE_STANDARDIZATION_CANDIDATE` → `CROSS_SITE_STANDARDIZATION_CANDIDATE`
- `INSUFFICIENT_DATA` → `INSUFFICIENT_DATA`

Map `REJECTED_BY_BUSINESS_RULE` conservatively to `DATA_CONFLICT_REVIEW` regardless of the current legacy rejection reason. Preserve the original legacy `business_status`, `rule_decision`, and `rejection_reason` for compatibility and auditability.

`UNIQUE_NO_MATCH` has no legacy deterministic source mapping. It may be produced only by a future redesigned engine through a separately reviewed implementation.

Unknown, missing, malformed, or unsupported legacy statuses must not silently fall back to a target status. The compatibility adapter must fail explicitly for unsupported legacy statuses and must not mutate the original legacy result.

State that this mapping does not activate target-status filtering or the target result policy in the current deterministic path and does not change current scores, thresholds, decisions, exclusions, warnings, counts, persistence, APIs, exports, frontend behavior, or legacy output.

Reason-aware refinement of `REJECTED_BY_BUSINESS_RULE` remains deferred and requires a separate approved SSOT decision.

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

#### Phase 2 Engine Version Metadata Decision

During Phase 2, version metadata is engine-owned.

Define an immutable engine metadata contract containing exactly:

- `engine_id`
- `engine_version`

For the current deterministic engine:

- `engine_id` is `legacy-deterministic`;
- `engine_version` is sourced from the existing `app.core.constants.MODEL_VERSION` production constant;
- the currently verified `engine_version` value is `hybrid-nlp-v1`.

Do not introduce another engine-version literal, environment variable, or application-level version source in this unit.

Expose the metadata through the typed candidate-scoring engine seam and `LegacyDeterministicScoringEngine`.

Do not insert engine metadata into `CandidateScoringResult`, `ScoringEvidence`, the 26-key legacy result dictionary, candidate rows, rejection rows, feedback rows, APIs, exports, or frontend output.

State that this decision does not change `settings.model_version`, health output, diagnostics output, `DuplicateScan.model_version`, scan persistence, scan API payloads, deployment defaults, current API labels, exports, frontend display, scoring, thresholds, routing, warnings, counts, default engine selection, or redesigned-engine failure behavior.

State that the current split between environment-backed health metadata and constant-backed persisted and diagnostic metadata remains an accepted current limitation for a later separately reviewed integration decision.

Do not represent dataset, source-record, semantic-profile, normalizer, dictionary, feature-contract, learned-model artifact, threshold/policy, LLM provider/model/prompt, or reviewer/timestamp version linkage until an authoritative versioned artifact or later-phase contract exists.

Completing this minimal engine metadata contract satisfies the Phase 2 contract-level version metadata requirement. It does not satisfy or claim completion of the full-system reproducibility requirements or review-event version snapshots.

### Phase 3 — PostgreSQL and Real Migrations

- PostgreSQL;
- Alembic;
- indexes;
- audit/job-ready schema;
- SQLite only where explicitly supported.

#### Phase 3 Controlled Alembic Transition Decision

Alembic will become the sole long-term schema authority for managed production databases. The transition is incremental: current startup schema creation and SQLite compatibility behavior remain temporarily unchanged until separately reviewed Alembic startup and legacy-bootstrap units are implemented and verified.

The first Alembic revision will create the exact currently committed five-table schema for an empty database. The characterized fresh SQLAlchemy `create_all()` behavior is the canonical initial schema:

- no new server defaults;
- no silent schema corrections;
- no change to SQLite foreign-key enforcement;
- no unapproved column, constraint, index, or semantic change.

The initial revision must be reviewed against the independent schema-characterization tests. Autogeneration output is not accepted without complete review.

Existing SQLite databases must never be blindly stamped as current. A later, separately reviewed fingerprint/bootstrap unit must:

- recognize explicitly supported legacy five-table variants;
- preserve unknown extra tables and columns;
- fail explicitly for incompatible managed columns or unsupported schemas;
- avoid destructive deletion or silent repair;
- avoid certifying an unknown schema as current;
- provide a controlled upgrade or review path before stamping.

Unknown schemas must be preserved and reported for review.

`Base.metadata.create_all()` and `ensure_sqlite_demo_columns()` remain temporarily unchanged while the Alembic foundation and empty-database migration path are introduced and tested. They must not be removed from normal startup in the first Alembic-foundation unit. Their retirement or restriction requires a separate reviewed unit after:

- Alembic upgrade behavior is verified;
- recognized legacy SQLite bootstrap is verified;
- startup failure behavior is defined;
- compatibility with current deterministic operation is demonstrated.

Before generating the first revision, SQLAlchemy and Alembic must use these deterministic constraint-naming conventions:

```text
pk_<table>
fk_<table>_<column>_<referred_table>
ix_<table>_<column>
uq_<table>_<column>
ck_<table>_<name>
```

Composite or multiple-column constraints must include the participating columns in a deterministic, unambiguous order. Introducing the naming convention must not silently alter current application behavior.

Alembic downgrade must be tested on disposable test databases. For databases containing real production data, operational recovery is forward migration plus verified backup and restoration procedures; destructive production downgrade is not the primary recovery mechanism.

PostgreSQL driver selection, engine configuration, service and deployment wiring, and PostgreSQL integration testing remain a separate Phase 3 unit after the Alembic empty-database baseline is established. The approved driver direction is Psycopg 3, with its pinned dependency selected in a separately reviewed unit. The first Alembic-foundation unit must not add Psycopg or PostgreSQL deployment.

The completed **Phase 3B — Alembic Migration Authority Foundation** unit had these boundaries:

- add a pinned Alembic dependency;
- add Alembic configuration and environment;
- add deterministic constraint naming;
- add an initial revision for the exact characterized empty five-table schema;
- add migration upgrade, downgrade, and schema-parity tests using disposable SQLite databases;
- keep `Base.metadata.create_all()` and `ensure_sqlite_demo_columns()` unchanged;
- do not integrate Alembic into application startup yet;
- do not add PostgreSQL driver, configuration, or deployment;
- do not stamp or upgrade existing repository SQLite files;
- do not introduce Phase 4 or later infrastructure.

Phase 3B established the migration-authority foundation only. It did not complete PostgreSQL deployment, legacy SQLite bootstrap, startup migration integration, index redesign, or the audit/job-ready target schema.

#### Phase 3 Read-Only SQLite Schema Classifier Decision

Before any legacy SQLite bootstrap or startup-migration policy is considered, Phase 3 must establish a completely read-only schema fingerprint classifier. The classifier may inspect and report schema state only. It must not:

- create any table, including `alembic_version`;
- alter any table or create or drop any index or constraint;
- insert, update, or delete data;
- stamp an Alembic revision or run an Alembic upgrade or downgrade;
- repair, normalize, or reinterpret schema;
- integrate with application startup;
- open either ignored repository SQLite database during implementation or tests.

Classification and profile recognition never authorize mutation or stamping.

The classifier uses exactly these broad classifications:

```text
EMPTY
CURRENT_ALEMBIC
CURRENT_UNVERSIONED
RECOGNIZED_LEGACY
INCOMPLETE
INCOMPATIBLE
UNKNOWN
```

Their meanings are:

- `EMPTY` — no managed application tables and no Alembic revision; the database is not corrupt, but it is not initialized.
- `CURRENT_ALEMBIC` — the exact current managed schema at the approved Alembic head.
- `CURRENT_UNVERSIONED` — an exact approved current-compatible managed schema without Alembic history.
- `RECOGNIZED_LEGACY` — an exact approved historical five-table profile recognized for reporting only.
- `INCOMPLETE` — one or more required managed tables or columns are missing.
- `INCOMPATIBLE` — a managed table or column exists with an incompatible type, length, nullability, default, key, constraint, index, or meaning.
- `UNKNOWN` — the schema or Alembic revision does not match an approved profile and is not safely classified as empty, incomplete, or incompatible.

The initial exact profile whitelist is:

```text
current_alembic_0001
current_named_unversioned
protected_baseline_unnamed
helper_from_07c9a6e
helper_from_00204e1
helper_from_fee3f3d_or_42fa7ba
```

These profiles mean:

- `current_alembic_0001` is the exact application schema at Alembic revision `0001_current_schema` and has broad classification `CURRENT_ALEMBIC`.
- `current_named_unversioned` is the exact current named five-table schema created from current SQLAlchemy metadata without `alembic_version` and has broad classification `CURRENT_UNVERSIONED`.
- `protected_baseline_unnamed` is the exact protected-baseline five-table schema with equivalent managed semantics, historical unnamed primary-key and foreign-key constraints, and no Alembic history; it has broad classification `CURRENT_UNVERSIONED`.
- `helper_from_07c9a6e` is the exact five-table schema produced from the known historical `07c9a6e` origin after the committed SQLite helper additions and has broad classification `RECOGNIZED_LEGACY`.
- `helper_from_00204e1` is the exact five-table schema produced from the known historical `00204e1` origin after later helper additions and has broad classification `RECOGNIZED_LEGACY`.
- `helper_from_fee3f3d_or_42fa7ba` is the exact five-table schema produced from the known `fee3f3d` or reverted `42fa7ba` origin after later helper additions and has broad classification `RECOGNIZED_LEGACY`.

Recognition of any profile is read-only and does not establish that the database is safe to stamp, upgrade, or mutate. Profiles derived only from ignored local databases, unrelated branches, manual edits, transient or reverted extra tables, or unsupported incomplete historical schemas must not be added to the automatic whitelist without a separate approved SSOT decision.

For managed application schema, classification must compare all of:

- managed table presence;
- column names and strict column order;
- SQLite type affinity, with normalization permitted only while declared string lengths and other relevant type semantics remain strict;
- nullability and server defaults;
- primary-key membership and structure;
- foreign-key columns, targets, and `ON DELETE` behavior;
- index names, columns, order, and uniqueness;
- unique constraints and check constraints;
- Alembic revision state.

Server defaults and index names are strict. Named and unnamed constraint profiles are recognized separately and are not universally interchangeable. An unknown Alembic revision is `UNKNOWN`. The classifier must not silently ignore any mismatch category.

An empty database is `EMPTY`, not corrupt or incompatible. Whether it may later run `alembic upgrade head` is a separate bootstrap and startup decision. A database missing any required managed table or managed column is `INCOMPLETE`; Phase 3C1 must not add or repair the missing schema.

Extra unknown tables must be preserved and reported separately. They do not change an otherwise exact recognized managed-schema profile, but they block any future automatic mutation or stamping until separately approved. Extra columns on managed tables are not allowed in a recognized current or legacy profile; they make the schema `UNKNOWN` or `INCOMPATIBLE` according to the observed conflict and block mutation and stamping. Classifier results must expose both extra tables and managed-schema conflicts rather than hide them behind a successful profile match.

A managed schema is `INCOMPATIBLE` whenever a required managed element exists but conflicts with the approved meaning, including a wrong type affinity or declared length, nullability, server default, primary or foreign key, index or constraint definition, `ON DELETE` behavior, or semantic use of a managed column. The classifier must not repair, reinterpret, or normalize an incompatible managed schema.

The initial automatic mutation whitelist contains only:

```text
CURRENT_ALEMBIC
```

That classification requires no mutation because it is already managed. No `CURRENT_UNVERSIONED` or `RECOGNIZED_LEGACY` profile is authorized for Alembic stamping, additive upgrade, schema normalization, startup migration, or automatic repair. Any later mutation policy requires a separate SSOT decision and bounded implementation unit.

The completed **Phase 3C1 — Read-Only SQLite Schema Fingerprint Classifier** unit had this implementation scope:

```text
backend/app/db/schema_fingerprint.py
backend/tests/test_schema_fingerprint.py
```

No package export or existing production file was required.

Phase 3C1 covered:

- `EMPTY`;
- `current_alembic_0001`;
- `current_named_unversioned`;
- `protected_baseline_unnamed`;
- all three approved helper-derived profiles;
- missing tables and columns;
- incompatible type, length, nullability, defaults, keys, indexes, and constraints;
- extra unknown tables and extra managed-table columns;
- unknown Alembic revisions;
- deterministic repeatability;
- complete read-only behavior;
- absence of repository-database access.

Phase 3C1 has these explicit non-goals:

- no Alembic stamp, upgrade, or downgrade;
- no schema repair or mutation policy;
- no startup integration;
- no compatibility-helper change;
- no PostgreSQL or Psycopg work;
- no repository SQLite access;
- no Phase 4 or later infrastructure.

Phase 3C1 established read-only recognition only. It did not authorize database mutation or complete legacy bootstrap.

#### Phase 3 Explicit Pristine SQLite Alembic Bootstrap Decision

This decision approves **Option A — Explicit Empty SQLite Alembic Bootstrap Only** for the next bounded unit. It supersedes only the earlier classifier decision's initial mutation whitelist. It does not weaken or replace any classifier recognition, conflict, profile, preservation or read-only rule.

Mutation authorization is deliberately narrow:

- exact `CURRENT_ALEMBIC` at profile `current_alembic_0001` is already managed, so no migration command or schema or data mutation is required or performed;
- exact `EMPTY` may run Alembic `upgrade head` only when the stricter pristine-empty precondition below is also satisfied;
- `CURRENT_UNVERSIONED`, `RECOGNIZED_LEGACY`, `INCOMPLETE`, `INCOMPATIBLE` and `UNKNOWN` are always refused before mutation;
- `EMPTY` with any extra or user-defined schema object is refused before mutation.

Recognition remains separate from mutation authorization. No current-unversioned or recognized-legacy profile is authorized for stamping, additive upgrade, normalization, repair or any other mutation.

A SQLite database is pristine empty only when all of these conditions hold immediately before migration:

- classifier result is exactly `EMPTY`;
- `profile_id` is `None`;
- `alembic_revision` is `None`;
- `extra_tables` and `conflicts` are empty;
- no `alembic_version` table or managed application table exists;
- no unknown user-defined table, view, trigger or index exists;
- no other unsupported user-defined schema object exists.

SQLite internal objects whose names begin with `sqlite_` are not user-defined objects. A database containing an unknown table, view, trigger, index, malformed Alembic table or other user-defined schema object is not pristine and must be refused without mutation. An empty database is not corrupt; refusal means only that this initial mutation policy is intentionally conservative.

The bootstrap service must be separately and explicitly invoked. It must not run during FastAPI startup, module import, `Base.metadata.create_all()`, `ensure_sqlite_demo_columns()`, or application connection opening. It must not infer a database path or URL from application settings and must not inspect or modify either ignored repository SQLite database. Startup integration requires a later separately approved SSOT decision and implementation unit.

The initial service accepts only a caller-supplied SQLite SQLAlchemy `Engine`. It opens and owns the connection used for classification and migration, closes that connection when finished, and does not dispose the caller-owned engine. Caller-supplied `Connection` support is deferred because transaction ownership and rollback semantics require a separate decision.

For a pristine empty database, the only permitted Alembic action is:

```text
alembic upgrade head
```

The resolved target head must be exactly `0001_current_schema`. The service must use the committed Alembic configuration and migration environment and programmatically supply the service-opened connection from the caller-owned `Engine`. It must not use the placeholder URL in `alembic.ini`, construct or infer a repository database URL, run `stamp` or `downgrade`, generate or autogenerate a revision, call `Base.metadata.create_all()` or `ensure_sqlite_demo_columns()`, add seed data, or normalize or repair an existing schema.

Preflight and postcondition behavior is exact:

- exact `CURRENT_ALEMBIC` at `current_alembic_0001` returns an already-current success without invoking a migration command or mutating schema or data;
- exact pristine `EMPTY` runs `upgrade head`, then classifies again;
- bootstrap success requires the post-migration result to be exactly `CURRENT_ALEMBIC`, profile `current_alembic_0001`, revision `0001_current_schema`, with no managed-schema conflicts or unexpected extra tables;
- every other state is refused explicitly before mutation.

Alembic command completion alone is not proof of successful bootstrap. Exact post-migration classification is the success condition.

The service returns an immutable typed result with exactly two successful outcomes:

```text
ALREADY_CURRENT
BOOTSTRAPPED
```

The result preserves the outcome, pre-bootstrap classifier result and post-bootstrap classifier result. For `ALREADY_CURRENT`, the immutable pre- and post-results may be the same object. The result does not authorize future schema mutation.

Unsupported preflight state, migration execution failure and postcondition failure must be distinguishable. A preflight refusal must expose the classifier result and diagnostic reason for ineligibility. The service must not silently fall back, stamp after failure, invoke the compatibility helper or `create_all()`, suppress Alembic or SQLAlchemy errors, retry through another schema path, reinterpret an unversioned or legacy schema as empty, restore from backup automatically, or delete partially created objects.

SQLite DDL rollback is not assumed to provide complete recovery in every failure mode. If migration starts and fails, the service must surface the failure and the observable post-failure classifier state when that state can be obtained safely. It must perform no destructive cleanup.

Phase 3C2 promises sequential repeatability, not safe concurrent bootstrap by multiple processes. The explicit caller must serialize attempts for a database. The first invocation against a pristine empty database returns `BOOTSTRAPPED`; a later sequential invocation returns `ALREADY_CURRENT`. Cross-process locking and distributed migration ownership are not claimed. A later startup or deployment decision must define single-owner execution and concurrency controls.

Every refused or already-current database must preserve schema, data, Alembic revision, tables, views, triggers and indexes exactly and must prove that neither the compatibility helper nor a repository database was accessed. For pristine empty bootstrap, the only permitted persistent change is the exact committed Alembic upgrade to `0001_current_schema`. No customer data transformation occurs because an eligible database contains no managed or user-defined schema objects.

The next bounded unit is **Phase 3C2 — Explicit Pristine SQLite Alembic Bootstrap** with expected scope:

```text
backend/app/db/alembic_bootstrap.py
backend/tests/test_alembic_bootstrap.py
```

No package export or existing production-file modification is expected. A third existing file may be modified only if current source proves it is strictly required; otherwise implementation must stop and report the conflict before scope expands.

Phase 3C2 tests must use disposable SQLite databases only and cover pristine bootstrap, already-current no-op, sequential repeat invocation, user-defined tables/views/triggers/indexes, every refused classifier state and profile, malformed and unknown Alembic state, prohibited-command boundaries, caller-owned engine behavior, exact postcondition, migration failure, postcondition failure, no destructive cleanup, no repository database access, no startup integration, and preservation of deterministic legacy behavior.

Phase 3C2 has these explicit non-goals:

- no startup integration;
- no stamping of current-unversioned schemas;
- no legacy additive upgrade, schema normalization or repair;
- no caller-supplied `Connection` support;
- no concurrent multi-process guarantee;
- no PostgreSQL or Psycopg;
- no migration revision, dependency or compatibility-helper change;
- no repository database access;
- no Phase 4 or later infrastructure.

Completing Phase 3C2 will establish only an explicit new-database bootstrap path. It will not complete existing-database migration, startup migration integration, PostgreSQL deployment or legacy SQLite retirement.

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

**Phase 3C2 — Explicit Pristine SQLite Alembic Bootstrap**

It must:

- follow the complete Phase 3 explicit pristine SQLite Alembic bootstrap decision above;
- create `backend/app/db/alembic_bootstrap.py`;
- create `backend/tests/test_alembic_bootstrap.py`;
- accept an explicitly supplied SQLite `Engine`;
- return `ALREADY_CURRENT` for exact current Alembic state without mutation;
- bootstrap only an exact pristine `EMPTY` database through Alembic `upgrade head`;
- reclassify and require exact `current_alembic_0001`;
- refuse every other classifier state and any user-defined schema object;
- never stamp, downgrade, call `Base.metadata.create_all()`, call `ensure_sqlite_demo_columns()`, or integrate with startup;
- not access ignored repository SQLite files;
- not add PostgreSQL, Psycopg, or later-phase infrastructure;
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
