
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
- explicit pristine SQLite Alembic bootstrap service;
- exact current-Alembic no-op and strict pristine-empty preflight;
- programmatic supplied-connection Alembic `upgrade head` with exact postcondition verification;
- explicit bootstrap refusal, configuration, migration and postcondition failure boundaries;
- pinned Psycopg 3 binary dependency `psycopg[binary]==3.3.4`;
- synchronous SQLite/PostgreSQL engine-construction boundary;
- PostgreSQL URL canonicalization to `postgresql+psycopg`;
- explicit unsupported database driver and dialect rejection;
- credential-safe diagnostic database-URL handling;
- lazy PostgreSQL engine construction without a connection attempt;
- preserved SQLite default, application-global engine and session behavior;
- digest-pinned disposable PostgreSQL 18.4 Compose test service;
- explicit `postgres-test` profile with isolated project lifecycle;
- loopback-only PostgreSQL test exposure and tmpfs-only test storage;
- registered `postgres_integration` marker;
- real read-only SQLAlchemy/Psycopg PostgreSQL connectivity verification;
- repeatable PostgreSQL service start, test and teardown with no remaining isolated-project resources;
- real supplied-connection PostgreSQL Alembic `upgrade head` against a fresh disposable database with exact revision `0001_current_schema` verification;
- an independent literal PostgreSQL parity contract for the committed five-table schema, covering exact tables, ordered columns, types, nullability, normalized defaults, keys, constraints, indexes, owned sequences and ownership, triggers, custom types, zero rows and absence of unexpected user objects;
- a second PostgreSQL `upgrade head` no-op proof with an identical deterministic fingerprint and an upgrade-only SQL capture containing two `SELECT` statements;
- preservation of schema-empty `inventory_test`, cleanup of test-owned `inventory_migration_test` and repeatable isolated PostgreSQL migration/parity verification;
- controlled test-only PostgreSQL initial-migration failure, exact transactional rollback, unchanged database identity and real same-database forward recovery to the Phase 3D2B1 fingerprint;
- one active deterministic scoring engine path.

Not implemented:

- workers;
- PostgreSQL production deployment;
- production migration runner;
- Alembic startup integration;
- distributed migration locking or ownership;
- backup and restore tooling;
- existing SQLite database mutation or stamping beyond explicit pristine-empty bootstrap;
- Phase 4 executable work, including the dataset registry and revision `0002_dataset_registry`;
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

- the latest verified executable implementation baseline is commit `10a14b5d4279e294c07b654ba571d68070a22071`;
- the ordinary full backend suite passes with 405 tests, three intentional PostgreSQL skips and one known pytest configuration warning;
- the focused Phase 3D1 engine-configuration suite passes with 39 tests;
- the combined Phase 3 schema, migration, classifier, bootstrap and engine-configuration regression suite passes with 129 tests, three intentional PostgreSQL skips and one known pytest configuration warning;
- live PostgreSQL marker selection passes with three tests and 405 deselected against PostgreSQL 18.4 / `server_version_num` `180004`;
- the Vite 8.0.16 production build passes with 34 modules transformed;
- the Alembic graph is `<base> -> 0001_current_schema (head)`;
- `USE_REDESIGNED_ENGINE` exists and defaults off;
- `REDESIGNED_RESULT_MODE` and `REDESIGNED_INCLUDE_STATUSES` remain absent from runtime configuration;
- the deterministic legacy engine remains the default and fallback;
- the redesigned production engine is not implemented or runnable;
- current startup still uses `Base.metadata.create_all()` and `ensure_sqlite_demo_columns()`;
- the Phase 3C1 read-only SQLite schema classifier is implemented;
- the Phase 3C2 explicit pristine SQLite Alembic bootstrap is implemented;
- Phase 3D1 is implemented and establishes only the Psycopg dependency and lazy synchronous SQLite/PostgreSQL engine-construction foundation;
- Phase 3D2A is implemented at commit `62db2b49196d7cdd70adeb464ce84bcdc822d931` with the exact committed image `postgres:18.4-bookworm@sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296`;
- two complete fresh live PostgreSQL harness cycles passed during Phase 3D2A implementation review and left no isolated-project resources;
- the Phase 3D2A base integration database remains intentionally schema-empty;
- Phase 3D2B1 is implemented at commit `4bda2efecafca819bcdea1af69b58d564f43e04b` with the exact tracked file `backend/tests/test_postgresql_migrations.py`;
- Phase 3D2B1 verifies real PostgreSQL Alembic migration execution, exact independent schema parity, exact revision, second-upgrade no-op behavior, schema-empty base-database preservation and owned temporary-database cleanup;
- Phase 3D2B2 is implemented and verified at commit `10a14b5d4279e294c07b654ba571d68070a22071` in the same focused PostgreSQL migration-test module;
- Phase 3D2B2 proves that a synthetic initial migration attempted transactional probe DDL and raised the exact deterministic test failure; PostgreSQL restored the same database to a pristine user schema with no Alembic revision or synthetic/application object; the database OID remained unchanged through failure, rollback and recovery; and the real committed migration restored revision `0001_current_schema` and the exact Phase 3D2B1 fingerprint;
- Phase 3D2B2 verification removed both test-owned databases and every isolated Docker project resource after each cycle;
- no PostgreSQL production deployment exists;
- no Alembic startup integration exists;
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

This decision approved **Option A — Explicit Empty SQLite Alembic Bootstrap Only**, implemented by the completed Phase 3C2 unit. It supersedes only the earlier classifier decision's initial mutation whitelist. It does not weaken or replace any classifier recognition, conflict, profile, preservation or read-only rule.

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

At Phase 3C2 completion, the only permitted Alembic action for a pristine empty database was:

```text
alembic upgrade head
```

At that completion point, resolved head was exactly `0001_current_schema`. The Phase 4 pinning decision supersedes reliance on moving `head`: Phase 4A1 must change the service to invoke the explicit immutable target `0001_current_schema` before `0002_dataset_registry` exists. The service must continue using the committed Alembic configuration and migration environment and programmatically supply the service-opened connection from the caller-owned `Engine`. It must not use the placeholder URL in `alembic.ini`, construct or infer a repository database URL, run `stamp` or `downgrade`, generate or autogenerate a revision, call `Base.metadata.create_all()` or `ensure_sqlite_demo_columns()`, add seed data, or normalize or repair an existing schema.

Preflight and postcondition behavior is exact:

- exact `CURRENT_ALEMBIC` at `current_alembic_0001` returns an already-current success without invoking a migration command or mutating schema or data;
- exact pristine `EMPTY` runs the explicit `0001_current_schema` upgrade target after Phase 4A1, then classifies again;
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

The completed **Phase 3C2 — Explicit Pristine SQLite Alembic Bootstrap** unit had this implementation scope:

```text
backend/app/db/alembic_bootstrap.py
backend/tests/test_alembic_bootstrap.py
```

No package export or existing production-file modification was required.

Phase 3C2 tests use disposable SQLite databases only and cover pristine bootstrap, already-current no-op, sequential repeat invocation, user-defined tables/views/triggers/indexes, every refused classifier state and profile, malformed and unknown Alembic state, prohibited-command boundaries, caller-owned engine behavior, exact postcondition, migration failure, postcondition failure, no destructive cleanup, no repository database access, no startup integration, and preservation of deterministic legacy behavior.

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

Phase 3C2 established only an explicit pristine-new-database SQLite bootstrap path. It did not complete existing SQLite migration, startup migration integration, PostgreSQL support or deployment, or legacy SQLite retirement.

#### Phase 3 PostgreSQL/Psycopg 3 Engine Foundation Decision

The user approved **Option A — PostgreSQL/Psycopg 3 Foundation**. The completed **Phase 3D1 — PostgreSQL Driver and Engine Configuration Foundation** unit established only the pinned `psycopg[binary]==3.3.4` dependency, explicit supported database-URL parsing and canonicalization, a tested synchronous SQLAlchemy engine-construction boundary for SQLite and PostgreSQL, preservation of the current SQLite default and behavior, and non-network PostgreSQL engine-construction verification. It did not establish a live or deployed PostgreSQL service or prove PostgreSQL connectivity, migration, schema parity, startup integration, operational readiness or production deployment.

Phase 3D1 uses Psycopg 3 through the exact implemented dependency `psycopg[binary]==3.3.4` in `backend/requirements.txt`, verified with Python 3.11 and SQLAlchemy 2.0.41. The unit did not add Psycopg 2, add both binary and source/C variants, add an ORM or asynchronous database dependency, or change the SQLAlchemy or Alembic version. The binary distribution is approved for the Phase 3D1 local, development and verification foundation; production container packaging and whether a later deployment uses a system-linked Psycopg build require a separate deployment decision.

SQLite remains the current default. Phase 3D1 must preserve the existing configured SQLite URL, database location, synchronous SQLAlchemy engine, `check_same_thread=False` connection argument, startup calls, tables, models, persistence, APIs, exports, deterministic scan behavior, compatibility helper and repository SQLite-file handling. It must not silently convert or migrate the current default database.

The engine-construction boundary accepts exactly these PostgreSQL URL schemes:

```text
postgresql://
postgresql+psycopg://
postgres://
```

Both `postgresql://` and `postgres://` must canonicalize to `postgresql+psycopg://`; `postgresql+psycopg://` remains unchanged. Canonicalization must use SQLAlchemy URL parsing rather than ad hoc splitting and must preserve username, password, host, port, database name, percent-encoding and query parameters. The canonical dialect and driver is `postgresql+psycopg`.

The boundary must explicitly reject `postgresql+psycopg2://`, every other PostgreSQL driver, asynchronous PostgreSQL drivers, and unsupported non-SQLite/non-PostgreSQL dialects. There is no silent fallback to SQLite, Psycopg 2 or another driver.

Database URLs may contain credentials. Raw passwords and complete unredacted URLs must not appear in exceptions, logs, test failures, health output, diagnostics or reports. Diagnostics must use SQLAlchemy's redacted URL rendering, while credentials remain available internally for engine construction. Unsupported-URL errors must identify the dialect or driver safely without revealing secrets. Phase 3D1 does not add secret storage, environment-file loading or deployment-secret management.

Phase 3D1 must introduce or extract one focused, testable, synchronous engine-construction function in the existing database module, conceptually:

```python
def create_database_engine(database_url: str) -> Engine:
    ...
```

The exact name may follow an existing module convention if source inspection proves a better seam. For SQLite, it must preserve the currently supported URLs, use the current SQLite connection arguments exactly, retain the current `pool_pre_ping=True`, add no PostgreSQL-only options and leave default engine semantics unchanged. For PostgreSQL, it must use `postgresql+psycopg`, omit SQLite connection arguments, enable `pool_pre_ping=True`, and otherwise retain SQLAlchemy defaults. Constructing either engine must not establish a database connection. Phase 3D1 must not add pool size, overflow, timeout, recycle, isolation level, SSL, application name, retry or failover policy; those require deployment measurements and a separate decision.

The application-global engine may be constructed through this boundary using the existing configured `DATABASE_URL`. Current import and startup behavior must remain functionally unchanged, SQLite must remain the default, and engine construction must add neither a migration command nor an import-time connectivity check. Invalid or unavailable PostgreSQL configuration must not trigger automatic fallback, and invalid supported-URL configuration must fail explicitly. Sessions, ORM metadata, models, repositories, routes and deterministic behavior remain unchanged.

The existing Alembic environment's caller-supplied connection path remains unchanged. Phase 3D1 may verify structurally that a PostgreSQL/Psycopg engine can be constructed, that it exposes the expected PostgreSQL dialect and Psycopg driver, and that the existing Alembic environment has no SQLite-only execution branch for a supplied connection. It must not claim PostgreSQL migration success without a real PostgreSQL server. It must not run PostgreSQL migrations, add a PostgreSQL test container, change `migrations/env.py`, change revision `0001_current_schema`, add startup migration integration, stamp a database or add legacy migration.

Phase 3D1 tests must not require a live PostgreSQL server. They must cover exact dependency and import availability; unchanged SQLite engine behavior; all three accepted URL schemes and canonicalization; preservation of credentials, percent-encoding, host, port, database and query parameters; Psycopg 3 dialect and driver selection; PostgreSQL `pool_pre_ping=True`; absence of SQLite `check_same_thread` on PostgreSQL; no network connection during engine construction; explicit rejection of Psycopg 2, asynchronous drivers, other unsupported PostgreSQL drivers and unsupported dialects; redacted errors without password leakage; the application-global engine continuing to use existing settings and default to SQLite; no startup migration, helper, model, API or frontend change; and no repository database access beyond existing baseline behavior. Mocks or SQLAlchemy engine inspection may be used. Existing database, migration, classifier and bootstrap tests must not be weakened.

The completed Phase 3D1 implementation scope was:

```text
backend/requirements.txt
backend/app/db/database.py
backend/tests/test_database_engine_configuration.py
```

Current source proved that no `backend/app/core/config.py` change was required. One source-proven compatibility update removed the obsolete pre-Psycopg assertion from `backend/tests/test_alembic_migrations.py`; no other production source or test scope was required.

Phase 3D1 has these explicit non-goals:

- no live PostgreSQL server, Docker Compose PostgreSQL or Kubernetes PostgreSQL;
- no PostgreSQL migration execution or schema-parity claim;
- no startup migration integration or startup connectivity check;
- no existing SQLite adoption, stamping or recognized legacy SQLite migration;
- no asynchronous SQLAlchemy or Psycopg;
- no pool sizing, retry, SSL/TLS or broader operational connection policy;
- no credential or secret-management infrastructure;
- no model, schema, index, audit-table or Alembic revision change;
- no unrelated dependency upgrade;
- no API or frontend change;
- no authentication, authorization or tenancy;
- no Phase 4 or later infrastructure.

Phase 3D1 established only a PostgreSQL-capable driver and engine-construction seam. It did not complete a live PostgreSQL server, PostgreSQL connectivity, migration verification, schema parity, startup integration, operational readiness, deployment or production database cutover.

Phase 3D1 was completed at `75271fcd84b177cc7fcb5d471cffac67e228c7f8`. Phase 3D2A then established the separately bounded disposable PostgreSQL Compose connectivity harness defined below. PostgreSQL Alembic migration, exact schema and constraint parity, transaction and forward-recovery behavior, and related failure verification remain separately bounded work under the migration-verification split decision below.

#### Phase 3 Disposable PostgreSQL Compose Test Harness Decision

The user approved **Option A — Docker Compose Test Profile**. **Phase 3D2A — Disposable PostgreSQL Compose Test Harness and Connectivity Baseline** was completed at commit `62db2b49196d7cdd70adeb464ce84bcdc822d931`.

Phase 3D2A establishes only:

- an explicit opt-in PostgreSQL service in the existing Compose file;
- deterministic image and version ownership;
- an isolated disposable test database;
- health-gated startup;
- one real Psycopg/SQLAlchemy connectivity baseline;
- one explicitly registered PostgreSQL integration-test marker;
- repeatable startup and teardown commands;
- preservation of the normal SQLite Compose and runtime path.

It does not run Alembic migrations and does not prove schema parity, operational readiness, production deployment or production cutover.

Use the Docker Official Image tag:

```text
postgres:18.4-bookworm
```

PostgreSQL 18.4 is the approved supported stable baseline, is supported by the pinned Psycopg 3 generation, and the Bookworm variant supplies a conventional glibc-based test environment. `latest`, floating major-only tags, beta tags, Alpine variants and third-party PostgreSQL images are not approved for this unit.

During implementation, resolve the official tag through Docker tooling or the official registry and pin the tracked Compose reference in this form:

```text
postgres:18.4-bookworm@sha256:<verified-manifest-digest>
```

Before editing, report the exact resolved digest, verify that it is the official multi-platform manifest digest rather than an architecture-specific child digest when the manifest is available, confirm it contains the platform required by the current developer environment, and report `linux/amd64` and `linux/arm64` support when present. Stop if the official tag no longer resolves to PostgreSQL 18.4. This SSOT intentionally does not hard-code the digest. A later PostgreSQL major or minor change requires a separately reviewed decision.

Add the service to the existing `docker-compose.yml` with exactly:

```text
profile: postgres-test
service: postgres-test-db
```

The service must declare:

```yaml
profiles:
  - postgres-test
```

Normal `docker compose up` without the profile must not create or start this service. The current backend and frontend remain outside the profile, must not depend on `postgres-test-db`, and must not receive a PostgreSQL URL in this unit. Do not set `container_name` or rename or remove an existing service, port, volume, network or health behavior. Use only the isolated Compose project's default network and no external network.

Every approved lifecycle command must use this explicit isolated Compose project name:

```text
inventory-part-duplicate-postgres-test
```

The test database uses only these public, non-production fixtures:

```text
database: inventory_test
user: inventory_test
password: inventory_test_only
```

They must never be reused for deployment, Kubernetes, staging or production. Password authentication remains enabled; do not use `POSTGRES_HOST_AUTH_METHOD=trust`, add another superuser, use application or IFS credentials, add a secret-bearing `.env` file, or introduce secret-management infrastructure. Failures and reports must not print the password or complete unredacted database URL.

Publish PostgreSQL only on loopback:

```text
127.0.0.1:${POSTGRES_TEST_PORT:-55432}:5432
```

The default host port is `55432` and may be overridden only by `POSTGRES_TEST_PORT`. Never bind to `0.0.0.0` or an unspecified host interface, and do not expose the service through Kubernetes, Ingress or a public network. The host Python environment connects through this loopback mapping.

PostgreSQL test data is disposable. For PostgreSQL 18, mount tmpfs at:

```text
/var/lib/postgresql
```

Do not use a named volume, anonymous persistent volume, bind mount, existing SQLite volume, host database directory, seed or initialization script, customer data or repository data. Use `restart: "no"`. The harness makes no crash-recovery or durable-storage promise.

Use the image-provided `pg_isready` health check with bounded timing:

```yaml
healthcheck:
  test:
    - CMD-SHELL
    - pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"
  interval: 2s
  timeout: 5s
  retries: 30
  start_period: 5s
```

Startup must use Compose `--wait` with a finite initial `--wait-timeout 90`. Running status alone is not readiness; tests start only after Compose reports the service healthy, and timeout or unhealthy status is a hard failure. Do not add an unbounded Python retry loop.

Approved validation commands are:

```powershell
docker compose config --quiet
docker compose --profile postgres-test config
docker compose config --profiles
```

Pull and start only the isolated test service:

```powershell
docker compose `
  -p inventory-part-duplicate-postgres-test `
  --profile postgres-test `
  pull postgres-test-db

docker compose `
  -p inventory-part-duplicate-postgres-test `
  --profile postgres-test `
  up -d --wait --wait-timeout 90 postgres-test-db
```

For the focused integration test, set `POSTGRES_TEST_DATABASE_URL` conceptually to:

```text
postgresql+psycopg://inventory_test:inventory_test_only@127.0.0.1:${POSTGRES_TEST_PORT:-55432}/inventory_test
```

Then run only the registered PostgreSQL integration marker or exact test module. This URL must not become an application setting.

Always tear down after success and failure with:

```powershell
docker compose `
  -p inventory-part-duplicate-postgres-test `
  --profile postgres-test `
  down --volumes --remove-orphans
```

The implementation report must prove that no container, isolated project network, named or anonymous volume, or test database remains. Image removal is not required. Normal development services must not be stopped or removed, and no destructive Docker cleanup outside the isolated project is authorized.

Add one focused integration module:

```text
backend/tests/test_postgresql_connectivity.py
```

Register exactly one marker:

```text
postgres_integration
```

The test must:

- be marked `postgres_integration`;
- require `POSTGRES_TEST_DATABASE_URL`;
- skip with one clear reason when the variable is absent during the ordinary full backend suite;
- fail rather than skip when the supplied value is malformed or unreachable;
- construct the engine through the committed `create_database_engine()` seam;
- require the canonical `postgresql+psycopg` driver;
- open one real connection and execute read-only statements only;
- verify `SELECT 1`, current database `inventory_test`, current user `inventory_test`, and PostgreSQL server major/minor `18.4`;
- close the connection and dispose the engine;
- avoid printing raw credentials;
- not call Alembic, `Base.metadata.create_all()` or `ensure_sqlite_demo_columns()`;
- not import or run FastAPI startup;
- not create application tables or otherwise mutate the database.

A failed connection, wrong driver, database, user or server version is a hard failure whenever the URL is supplied.

The ordinary backend suite must remain runnable without Docker. Register the marker in the existing pytest configuration so no unknown-marker warning is introduced. When `POSTGRES_TEST_DATABASE_URL` is absent, the integration test skips clearly and the full suite may report one additional intentional skip. Ordinary pytest collection or execution must not invoke Docker, start a container or connect to PostgreSQL. Existing unit, SQLite, Alembic, classifier and bootstrap behavior remains unchanged, and the known `asyncio_default_fixture_loop_scope` warning is not addressed in this unit.

Phase 3D2A verification must include:

- current Docker Engine and Docker Compose versions;
- successful Compose schema validation and a profile list containing `postgres-test`;
- unchanged normal profile behavior;
- exact resolved image digest and required platform support;
- healthy service startup within the timeout;
- loopback-only published port;
- tmpfs mounted at `/var/lib/postgresql` with no persistent volume;
- a passing focused integration test;
- a passing ordinary backend suite without the service and proof it did not connect to PostgreSQL;
- service logs containing no application or customer data;
- teardown removing all isolated project resources;
- a second complete start, test and down cycle.

The second cycle proves harness repeatability, not database-data persistence.

Expected Phase 3D2A implementation scope is:

```text
docker-compose.yml
backend/pytest.ini
backend/tests/test_postgresql_connectivity.py
```

The committed Phase 3D2A implementation uses exactly that scope and the exact image reference:

```text
postgres:18.4-bookworm@sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296
```

Two fresh connectivity cycles passed. The ordinary suite behavior is 405 passed, one intentional PostgreSQL skip and one known warning. Phase 3D2A did not run Alembic or establish PostgreSQL schema parity, migration failure recovery, startup integration, operational readiness or deployment.

If pytest configuration resides in another existing file, modify that file instead of creating `backend/pytest.ini`. A small `backend/tests/conftest.py` change is permitted only if source proves module-local environment gating cannot safely satisfy the policy; report that need before editing and stop if it exceeds one small compatibility change. No script, dependency, Dockerfile, application source or migration file is expected.

Phase 3D2A must not add or perform:

- Alembic upgrade, downgrade, stamp or revision generation;
- PostgreSQL schema creation beyond the official image's initial database;
- application tables, indexes, constraints or PostgreSQL schema-parity assertions;
- model or metadata changes;
- `Base.metadata.create_all()` or startup migration integration;
- application startup against PostgreSQL or backend/frontend dependency on PostgreSQL;
- persistent PostgreSQL storage;
- production credentials or secret-management infrastructure;
- Dockerfile, Kubernetes, production-deployment or CI-pipeline changes;
- Testcontainers or another Python dependency;
- transaction-write, rollback, recovery, concurrency or load testing;
- existing SQLite adoption or legacy migration;
- Phase 4 or later infrastructure.

Completing Phase 3D2A establishes only a disposable, opt-in real-PostgreSQL connectivity harness. It does not complete PostgreSQL migration verification, schema parity, operational readiness or production cutover.

After completed Phase 3D2A, PostgreSQL migration verification is governed by the separately approved split decision below.

#### Phase 3 PostgreSQL Migration Verification Split Decision

The user approved **Option A — Split into two bounded units** so basic PostgreSQL migration correctness remains independently reviewable from intentional migration failure injection and recovery behavior.

##### Phase 3D2B1 — PostgreSQL Empty-Database Alembic Upgrade and Independent Schema Parity

Phase 3D2B1 was completed and verified at commit `4bda2efecafca819bcdea1af69b58d564f43e04b`. It establishes only:

- Alembic `upgrade head` against a genuinely empty disposable PostgreSQL database;
- exact resolved and migrated revision `0001_current_schema`;
- a hard-coded, independently reviewed PostgreSQL expectation for the exact committed five-table application schema;
- exact PostgreSQL schemas, tables, columns in ordinal order, types, declared lengths, numeric precision/scale, timestamp/date/time semantics, nullability, normalized server defaults, primary-key defaults, primary keys, foreign keys and `ON DELETE` behavior, unique and check constraints, named indexes including ordered columns, uniqueness, expressions and predicates, owned sequences and ownership relationships, and managed object names;
- absence of unexpected user tables, views, materialized views, foreign tables, sequences, custom types and triggers;
- a second `upgrade head` that leaves the exact deterministic schema fingerprint and revision unchanged and emits no schema-creating, altering or dropping DDL beyond Alembic's required read/version checks;
- repeatability across two fresh disposable PostgreSQL harness cycles;
- preservation of the schema-empty base connectivity database and all SQLite migration and application behavior.

The completed implementation scope is exactly `backend/tests/test_postgresql_migrations.py`. Verification recorded the ordinary suite at 405 passed, two intentional skips and one known warning; the focused Phase 3 regression at 129 passed, two intentional skips and one known warning; the live marker suite at two passed and 405 deselected; PostgreSQL 18.4; revision `0001_current_schema`; two second-upgrade `SELECT` statements only; schema-empty `inventory_test`; and removal of `inventory_migration_test` after every test.

Phase 3D2B1 does not intentionally fail a migration and does not establish failure-recovery policy.

The committed Phase 3D2A base database and role remain exactly:

```text
database: inventory_test
user: inventory_test
```

Phase 3D2B1 must keep `inventory_test` free of non-system relations before and after every test. Its migration test must create and own exactly one separate temporary database:

```text
inventory_migration_test
```

The test must use the existing test-only `inventory_test` role and accept the existing `POSTGRES_TEST_DATABASE_URL` only as its trusted base connection input. It must require that supplied URL to identify the approved PostgreSQL driver, user, server, version and base database. It must derive the migration URL through SQLAlchemy `URL` operations rather than string splitting, preserving host, port, username, password, percent-encoding and query parameters internally while never printing a password, complete URL or query values. The fixed database identifier must not be environment controlled.

Preflight must require that `inventory_migration_test` does not exist and must fail rather than adopt, drop or overwrite a pre-existing database. Creation must use an explicit autocommit administrative connection because PostgreSQL forbids `CREATE DATABASE` inside a transaction. Every connection and engine must be closed or disposed. Only `inventory_migration_test` may be dropped, in a `finally` path after all test-owned connections close. The test must not drop or mutate `inventory_test`, `postgres`, `template0`, `template1` or an unrelated database, terminate unrelated sessions or perform broad cleanup. After cleanup it must prove that `inventory_migration_test` no longer exists and `inventory_test` remains schema-empty. The full isolated Compose project must still be torn down after each verification cycle under the existing Phase 3D2A policy.

Phase 3D2B1 ran Alembic programmatically through the committed `backend/alembic.ini`, migration script location and caller-supplied connection path. The test opened a live SQLAlchemy connection from the derived migration-database engine and supplied it through Alembic configuration. It did not use the placeholder `alembic.ini` URL, mutate settings or `DATABASE_URL`, invoke FastAPI startup, call `Base.metadata.create_all()`, `ensure_sqlite_demo_columns()` or the SQLite bootstrap service, or use an Alembic subprocess. At Phase 3D2B1 completion it ran `alembic upgrade head`, and both resolved head and the database revision were exactly `0001_current_schema`. Under the Phase 4 pinning decision, Phase 4A1 must replace that moving-target invocation with explicit `0001_current_schema`; downgrade, stamp, revision generation and autogeneration remain prohibited.

If the committed migration cannot upgrade a fresh PostgreSQL database, implementation must stop and report the exact credential-safe failure, preserve any uncommitted focused test work already added, and leave the committed migration, models, Alembic environment and production source unchanged. It must not add a fallback schema path or reinterpret failure as parity success. Any required migration or model correction is a separate reviewed decision and bounded correction unit.

The focused module must contain an explicit independent schema contract. It must not generate or import that expectation from `Base.metadata`, ORM models, the Alembic revision implementation, Alembic autogeneration, the SQLite classifier or the observed PostgreSQL schema. Approved PostgreSQL dialect differences must be stated explicitly rather than requiring textual SQLite/PostgreSQL type or default equality. The target remains the exact committed five-table schema; no audit/job-ready tables, redesigned indexes, new constraints or Phase 4 schema are authorized.

The expected Phase 3D2B1 implementation scope is exactly:

```text
backend/tests/test_postgresql_migrations.py
```

That module must contain one focused `postgres_integration` migration/parity test and module-private helpers only. It must require `POSTGRES_TEST_DATABASE_URL`, skip clearly only when it is absent, and fail rather than skip for an empty, malformed, unsupported, unreachable or incorrectly targeted supplied URL. It must use `create_database_engine()`, create, migrate, inspect and drop only `inventory_migration_test`, run no API or startup code, insert no application rows, leave `inventory_test` schema-empty and dispose every engine. No existing production, migration, model, Compose, pytest configuration, dependency or connectivity-test file is expected to change. If source inspection disproves that one-file scope, implementation must stop and report before editing.

After Phase 3D2B1, with no PostgreSQL URL supplied, the ordinary backend suite is expected to report 405 passed, two intentional PostgreSQL skips and one known warning. With the harness and URL supplied, marker selection must run both tests independently: connectivity uses only schema-empty `inventory_test`, while migration/parity uses and cleans only `inventory_migration_test`. Correctness must not depend on pytest file or function order.

Phase 3D2B1 runtime verification must use isolated Compose project `inventory-part-duplicate-postgres-test` for two fresh cycles. Each cycle must prove no prior project resources; start only `postgres-test-db` with `--wait --wait-timeout 90`; verify PostgreSQL 18.4, health, loopback exposure, tmpfs and zero persistent volumes; pass the original connectivity test, the migration/parity test and the complete marker selection; prove the base database remains schema-empty and the temporary database is absent; inspect logs for credentials, customer/application data, unexpected SQL errors and Alembic failure; tear down with `down --volumes --remove-orphans` in a `finally` path; and prove no project container, network or volume remains, port 55432 is released and test environment variables are absent. This proves clean-database sequential repeatability, not concurrent migration ownership or production recovery.

Phase 3D2B1 must not add or perform intentional failure injection; rollback or forward-recovery testing; PostgreSQL downgrade; changes to `0001_current_schema`, Alembic environment, models, naming convention, Compose, pytest configuration, dependencies or production source; new migrations or schemas; PostgreSQL classifier/bootstrap production code; startup migration integration; production database creation, persistence or deployment; or API, frontend, Dockerfile, Kubernetes, CI, authentication, authorization, tenancy, Phase 4 or later work. Success does not authorize PostgreSQL application startup, production deployment, existing-database adoption or production cutover. The implementation must not be committed until reviewed.

##### Phase 3D2B2 — PostgreSQL Initial-Migration Failure, Transaction Rollback and Real Forward Recovery

Phase 3D2B2 was completed and verified at commit `10a14b5d4279e294c07b654ba571d68070a22071`. The user approved **Option A — Failure during initial migration, followed by real forward recovery**. The completed unit followed the accelerated risk-based strategy: migration, rollback and recovery safety received complete verification ceremony, while unrelated policy and infrastructure expansion remained deferred.

Phase 3D2B2 established only:

- a controlled test-only synthetic initial-migration failure;
- evidence of PostgreSQL/Alembic transactional rollback after at least one DDL statement is attempted;
- exact credential-safe failure diagnostics;
- proof that no synthetic or application schema and no Alembic revision remains after rollback;
- real forward recovery on the same database through the committed production migration tree;
- exact recovery to the Phase 3D2B1 fingerprint and revision;
- repeatability through two fresh disposable PostgreSQL Compose cycles;
- unchanged SQLite and deterministic behavior.

It did not add production migration-recovery code or startup migration ownership.

The committed tracked implementation scope is exactly:

```text
backend/tests/test_postgresql_migrations.py
```

The implementation added one additional `postgres_integration` test to that existing module. The module contains exactly two focused PostgreSQL migration tests: the existing empty-database migration/parity test and the synthetic-failure and real-forward-recovery test. Module-private helper refactoring remained in the same file. No production source, migration, Alembic environment, Compose file, pytest configuration, dependency, model, API, frontend, Dockerfile, Kubernetes or CI file changed.

The new test must own exactly one additional fixed database:

```text
inventory_migration_recovery_test
```

The environment must not control that identifier. The test must accept only the existing `POSTGRES_TEST_DATABASE_URL` as trusted base input; require the approved driver, user, server, version and base database `inventory_test`; derive the recovery URL through SQLAlchemy `URL` operations; and require `inventory_migration_recovery_test` to be absent before creation. It must fail rather than adopt, overwrite or drop a pre-existing database. Creation must use an explicit autocommit administrative connection. The test must record internally whether it created this exact database, close all owned connections before cleanup, drop it only when it created it, drop only `inventory_migration_recovery_test` in a `finally` path, prove it absent after cleanup and keep `inventory_test` schema-empty before and after the test.

The test must never drop or mutate `inventory_test`, `inventory_migration_test`, `postgres`, `template0`, `template1` or any unrelated database. It must not terminate unrelated sessions or perform broad cleanup.

The synthetic migration environment must exist only under pytest temporary storage and must be removed automatically with that storage. It must use a temporary Alembic script location, a temporary copy of the committed Alembic environment so the same supplied-connection and transaction configuration is exercised, and exactly one synthetic revision. That isolated revision must use ID `0001_current_schema`; it must not import a production revision or production model metadata and must target only the test-owned recovery database. Reusing the revision ID is approved only inside the separate temporary script location, which must leave no committed revision state after failure. No tracked migration file may be created or modified.

The synthetic revision must create exactly one transactional-DDL probe table:

```text
phase3d2b2_failure_probe
```

It must then raise a deterministic test-only exception before completion, must not catch and suppress its own failure, must not insert application or customer rows and must not invoke production migration code. The stable diagnostic must contain no credential or URL and must identify `phase3d2b2 synthetic migration failure`; a built-in test-only exception class is acceptable when source inspection confirms deterministic assertion.

A SQLAlchemy statement listener must be active only around the synthetic Alembic `upgrade head` call and must be removed in `finally` before catalog, revision or fingerprint verification. The test must prove that at least one statement was captured and that the captured synthetic-upgrade SQL includes `CREATE TABLE phase3d2b2_failure_probe`. Verification queries must not enter the capture window, and raw connection URLs or credentials must never be logged.

After the controlled failure, the failed connection must be closed or safely reset and the same recovery database must be inspected through a fresh connection. Without dropping, recreating, stamping, repairing or deleting objects, the required post-failure state is:

- `phase3d2b2_failure_probe` absent;
- all five application tables absent;
- `alembic_version` absent and no committed Alembic revision;
- no non-system table, partitioned table, view, materialized view, foreign table or sequence;
- no unexpected standalone composite or other custom type;
- no user trigger or application row;
- otherwise pristine empty user schema.

If PostgreSQL or Alembic leaves any different state, the test must fail and report it. It must not silently change this expectation, manually clean residual state, stamp a revision or reinterpret residual state as success.

After proving the exact failed state, and without dropping or recreating the database, the test switched to the real committed `backend/alembic.ini` and production script location, opened a new SQLAlchemy connection to the same `inventory_migration_recovery_test`, and supplied that live connection through the committed Alembic caller-supplied connection path. At Phase 3D2B2 completion, production head resolved exactly to `0001_current_schema`; the test ran only the real committed `alembic upgrade head`; and the resulting database revision and independent schema contract exactly equalled the Phase 3D2B1 revision and fingerprint. No synthetic probe or temporary object remained.

Forward recovery must not use a fallback schema path, stamp, `create_all()`, SQLite helper, bootstrap service, manual DDL repair, drop/recreate, downgrade or application startup. Recovery succeeds only when the same database that experienced the verified rollback reaches the exact committed Phase 3D2B1 schema.

The test must skip clearly only when `POSTGRES_TEST_DATABASE_URL` is absent. Empty, whitespace, malformed, unsupported, unreachable, wrong-user, wrong-server-version or wrong-base-database URLs must fail rather than skip. Pre-existing recovery-database ownership, unexpected synthetic exception type or message, residual post-failure state, real recovery failure, wrong final revision or fingerprint and cleanup failure must all fail explicitly. Diagnostics must not expose raw passwords, complete database URLs, URL query values or production/customer data. This unit adds no production exception or recovery class.

Runtime verification must use the existing isolated Compose project `inventory-part-duplicate-postgres-test` for two fresh complete cycles. Each cycle must prove no prior project resources; start only `postgres-test-db` with `--wait --wait-timeout 90`; verify PostgreSQL 18.4, health, loopback exposure, tmpfs and zero persistent volumes; run the original connectivity test, the Phase 3D2B1 parity test, the new Phase 3D2B2 failure/recovery test and complete marker selection; prove schema-empty `inventory_test`; prove both `inventory_migration_test` and `inventory_migration_recovery_test` absent; inspect sanitized logs; tear down in `finally` with `down --volumes --remove-orphans`; and prove zero project containers, networks and volumes with port 55432 released. The second cycle must use the opposite focused-test order to prove order independence.

The verified ordinary service-down backend suite reported 405 passed, three intentional PostgreSQL skips and one known warning. The focused Phase 3 regression reported 129 passed, three intentional PostgreSQL skips and one known warning. Live marker selection reported three passed and 405 deselected against PostgreSQL 18.4 / `180004`. The known `asyncio_default_fixture_loop_scope` warning remains outside this unit.

Phase 3D2B2 did not add or perform a production migration runner or recovery service; FastAPI startup migration integration; a distributed lock or concurrent migration ownership; changes to `backend/migrations/env.py` or `0001_current_schema`; tracked synthetic revisions or a new production revision; Alembic stamp or downgrade; backup/restore tooling; destructive residual-state cleanup; PostgreSQL classifier/bootstrap production code; application model or schema changes; existing PostgreSQL database adoption; PostgreSQL production service, storage, deployment or cutover; dependency, Compose, Dockerfile, Kubernetes, CI, API, frontend, authentication, authorization, tenancy, Phase 4 executable work or later-phase work.

Completion proves only controlled transactional initial-migration failure behavior and real forward recovery in a disposable test database. Production backup tooling, distributed migration locking, deployment ownership and startup integration remain separately deferred.

### Phase 4 — Durable Dataset Ingestion

- separate upload and scan;
- object storage;
- chunked/streamed CSV;
- profiling;
- Parquet;
- dataset/profile versions;
- first-class MASTER_PART_DESCRIPTION;
- idempotency/retry.

#### Phase 4 Legacy SQLite `0001` Pinning and Dataset Registry Migration Decision

The user approved **Option 1 — Keep legacy deterministic SQLite pinned to `0001_current_schema`**. Durable dataset registry ownership is the selected first Phase 4 capability, but no Phase 4 executable work is implemented by this decision.

Alembic revision ownership is fixed as follows:

- `0001_current_schema` remains the immutable protected five-table deterministic schema;
- the future dataset registry revision is exactly `0002_dataset_registry`;
- `0002_dataset_registry` will declare `down_revision = "0001_current_schema"`;
- once `0002_dataset_registry` is committed, the overall production Alembic head becomes `0002_dataset_registry`;
- moving production head must not reinterpret the legacy SQLite schema as outdated, incomplete or automatically mutable;
- explicitly Alembic-managed production databases may advance from `0001_current_schema` to `0002_dataset_registry`;
- normal deterministic SQLite startup must not advance to `0002_dataset_registry`;
- no existing repository SQLite database may be opened, stamped or upgraded during implementation or tests.

Legacy deterministic SQLite startup retains the existing SQLAlchemy `Base` as the preferred shared model metadata. A separate registry declarative base must not be introduced merely to avoid startup activation. Before registry models enter shared metadata, normal startup must restrict `Base.metadata.create_all()` to actual SQLAlchemy table objects for exactly these original committed tables:

```text
duplicate_scan
duplicate_candidate
duplicate_feedback
scan_warning
rule_exclusion_audit
```

The committed names are singular; older pluralized conceptual spellings do not match current source. The allowlist must use trusted table objects rather than runtime reflection or untrusted strings. Registry tables must not be created by normal legacy startup. `ensure_sqlite_demo_columns()` remains limited to its existing legacy compatibility responsibility. Startup must not call Alembic, connect to PostgreSQL or silently fall back. Deterministic scoring, persistence, API output, exports, warnings, exclusions and existing SQLite behavior remain unchanged.

The Phase 3C2 explicit pristine SQLite bootstrap is permanently pinned to the exact target `0001_current_schema` and must no longer depend on moving `head` semantics once `0002_dataset_registry` exists. An eligible pristine SQLite database bootstrapped through this legacy service receives only the original five-table schema. Success remains exact classifier profile `current_alembic_0001` at revision `0001_current_schema`. The bootstrap must not create registry tables, stamp or advance an existing database, and remains explicit and outside application startup.

The Phase 3C1 classifier remains a classifier for the protected legacy five-table SQLite family. `CURRENT_ALEMBIC` and `current_alembic_0001` continue to mean exact revision `0001_current_schema`. The initial registry foundation does not expand the classifier or authorize `0002_dataset_registry` mutation. Registry services must not treat classifier success as proof that registry tables exist. A future production-startup or managed-database classifier may be designed separately.

Every Phase 3 test whose purpose is the protected five-table baseline must target `0001_current_schema` explicitly rather than moving `head`. This includes PostgreSQL B1 parity/no-op and B2 rollback/recovery verification, plus SQLite migration, classifier and bootstrap paths whose contract is the protected legacy schema. They must continue proving the original five-table fingerprint and must not be weakened to accept registry tables. New Phase 4 migration tests will separately verify `0001_current_schema` to `0002_dataset_registry`, exact `0002` schema parity and repeatability.

#### Phase 4A — Durable Dataset Registry and Versioned Artifact Metadata Foundation

Phase 4A is the selected first durable-ingestion capability. It establishes database ownership and immutable version identity before MinIO/S3 upload APIs or object processing are added.

The schema adds exactly three tables without modifying any original five-table object:

```text
datasets
dataset_versions
dataset_artifacts
```

New registry primary keys are immutable application-generated UUID values. Models must use SQLAlchemy's supported portable UUID type with native PostgreSQL UUID behavior and SQLite test portability. This unit adds no UUID package, database-generated random-UUID extension or public sequential dataset identifier.

`datasets` contains conceptually:

```text
id
name
description
status
created_at
updated_at
```

Its exact policy is:

- `id` is a UUID primary key;
- `name` is required, trimmed, non-empty and at most 255 characters;
- `description` is optional text;
- `status` is required and constrained to exactly `ACTIVE` or `ARCHIVED`;
- a new dataset starts as `ACTIVE`;
- `created_at` and `updated_at` are required application-supplied UTC timestamps, with no server timestamp default or trigger;
- names are not globally unique because tenant ownership is not implemented;
- no delete cascade or automatic deletion is introduced.

`dataset_versions` contains conceptually:

```text
id
dataset_id
version_number
status
source_filename
source_media_type
source_sha256
source_size_bytes
source_record_count
created_at
updated_at
```

Its exact policy is:

- `id` is a UUID primary key;
- `dataset_id` is a required foreign key to `datasets.id`; deletion is restricted and versions are not cascade-deleted;
- `version_number` is a required positive integer, unique with `dataset_id`;
- `status` is constrained to exactly `REGISTERED`, `STAGED`, `PROFILED`, `READY` or `REJECTED`;
- allowed forward transitions are exactly `REGISTERED -> STAGED`, `REGISTERED -> REJECTED`, `STAGED -> PROFILED`, `STAGED -> REJECTED`, `PROFILED -> READY` and `PROFILED -> REJECTED`;
- `READY` and `REJECTED` are terminal in this foundation;
- transient worker failure is not a version status; Phase 5 job-attempt records own retryable operational failure;
- `source_filename` is required display-basename metadata of at most 512 characters and is never trusted as an object key or filesystem path;
- `source_media_type` is required and at most 255 characters;
- `source_sha256` is required lowercase hexadecimal SHA-256 text of exactly 64 characters;
- `source_size_bytes` is a required non-negative big integer;
- `source_record_count` is an optional non-negative big integer;
- `created_at` and `updated_at` are required application-supplied UTC timestamps;
- source identity fields and `version_number` are immutable after creation;
- dataset-scoped idempotency is enforced by uniqueness of `dataset_id + source_sha256 + source_size_bytes`;
- the same dataset and source identity returns the existing version instead of creating another; identical content in different datasets remains permitted; no global checksum uniqueness exists.

`dataset_artifacts` contains conceptually:

```text
id
dataset_version_id
artifact_kind
artifact_ordinal
object_uri
content_sha256
size_bytes
media_type
created_at
```

Its exact policy is:

- `id` is a UUID primary key;
- `dataset_version_id` is a required foreign key to `dataset_versions.id`; deletion is restricted and artifacts are not cascade-deleted;
- `artifact_kind` is constrained initially to exactly `SOURCE_CSV`, `SCHEMA_PROFILE_JSON` or `CANONICAL_PARQUET`;
- `artifact_ordinal` is a required non-negative integer;
- `object_uri` is a required provider-independent opaque URI of at most 2048 characters;
- `content_sha256` is required lowercase hexadecimal SHA-256 text of exactly 64 characters;
- `size_bytes` is a required non-negative big integer;
- `media_type` is required and at most 255 characters;
- `created_at` is a required application-supplied UTC timestamp;
- artifact rows are immutable;
- the unique artifact slot is `dataset_version_id + artifact_kind + artifact_ordinal`;
- `object_uri` is globally unique in the registry so one durable object cannot be silently owned by multiple artifact rows;
- repeated registration of the same slot with identical immutable metadata is idempotent, while conflicting metadata fails explicitly;
- checksum equality alone never collapses artifacts across datasets or versions;
- `CANONICAL_PARQUET` may use multiple ordinals for future shards.

All registry primary keys, foreign keys, unique constraints, checks and indexes use deterministic names under the established naming convention. Required indexes support dataset status, version lookup by dataset, version lifecycle status, artifact lookup by dataset version and artifact-kind lookup within a version. No speculative full-text, vector, tenant, job, scan or profile index is authorized.

The future typed repository/service boundary supports only:

- creating an active dataset and reading it by ID;
- registering a source version and idempotently returning an existing version for the same dataset/source identity;
- deterministically assigning the next positive dataset-local version number;
- recording immutable artifact metadata;
- advancing lifecycle status only through the approved transitions;
- explicit not-found, duplicate/conflict, invalid-transition and invalid-metadata failures.

No HTTP route is introduced. The initial guarantee is deterministic sequential version allocation inside one database transaction, with database uniqueness authoritative. Cross-process concurrent allocation, retry orchestration and distributed ownership remain deferred to Phase 5.

Registry models use the existing shared `Base`, but legacy startup must first be restricted to the original-five-table table-object allowlist. Alembic alone creates registry tables. Registry repositories/services fail explicitly when registry tables are absent and must not call `create_all()`, Alembic, the SQLite helper or SQLite bootstrap. No automatic startup activation is introduced.

The future manually reviewed `0002_dataset_registry` migration must:

- add only the three approved registry tables, constraints and indexes;
- upgrade an exact `0001_current_schema` database to `0002_dataset_registry` on disposable SQLite and real PostgreSQL;
- preserve every original five-table object and row during upgrade;
- downgrade a disposable `0002` database to exact `0001` by dropping only registry-owned objects in dependency-safe order;
- support exact schema-parity verification and a second `upgrade head` no-op proof;
- fail explicitly without fallback or `create_all()`.

Production downgrade remains non-primary recovery; forward migration plus verified backup/restore policy remains the operational direction.

Phase 4A explicitly does not add MinIO or other object storage, an S3 client, multipart/streaming upload, CSV parsing, pandas replacement, schema-profile execution, PyArrow, Polars, Parquet writes, `MASTER_PART_DESCRIPTION` activation, a scan-to-dataset-version foreign key, asynchronous jobs, Redis, Celery, tenancy, authentication, authorization, object deletion/retention, production Alembic startup integration, PostgreSQL deployment/cutover, frontend work or Phase 5 infrastructure. Metadata-only test URIs do not prove object existence.

##### Phase 4A1 — Fixed Legacy Migration Target Compatibility Seam

Phase 4A1 is the sole immediate implementation unit. It must:

- pin the explicit pristine SQLite bootstrap to `0001_current_schema`;
- pin every Phase 3 SQLite baseline path whose contract is the original schema to `0001_current_schema`;
- pin PostgreSQL B1 and B2 migration verification to `0001_current_schema`;
- preserve the exact B1 five-table fingerprint and B2 recovery behavior;
- prove unchanged current behavior while overall `head` is still `0001_current_schema`;
- introduce no `0002` revision, dataset model/table, repository, service, API, dependency or object-storage code;
- change only the smallest source/test set proved necessary;
- preserve normal legacy startup unchanged in this first seam;
- remain uncommitted until reviewed.

Expected files are limited conceptually to the bootstrap target and directly affected migration tests. Any additional focused file must be source-proven and reported before editing.

##### Phase 4A2 — Dataset Registry Schema and Persistence Foundation

Phase 4A2 remains future until Phase 4A1 is committed and verified. It will restrict legacy startup `create_all()` to the original-five-table table-object allowlist, add shared-Base registry models and `0002_dataset_registry`, add typed repository/service contracts and focused tests, add SQLite and live PostgreSQL migration verification, preserve all Phase 3 tests pinned to `0001_current_schema`, and add no object-store or HTTP upload behavior.

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

**Phase 4A1 — Fixed Legacy Migration Target Compatibility Seam**

It must:

- pin the explicit pristine SQLite bootstrap to the immutable `0001_current_schema` target rather than moving `head`;
- pin every directly affected Phase 3 SQLite baseline test to `0001_current_schema` where its contract is the original five-table schema;
- pin PostgreSQL B1 parity/no-op and B2 failure/rollback/recovery verification to `0001_current_schema`;
- preserve the exact B1 fingerprint, B2 recovery behavior, classifier meaning and existing deterministic/SQLite behavior;
- prove behavior is unchanged while the overall Alembic head remains `0001_current_schema`;
- change only the smallest source and test set established by inspection;
- preserve normal legacy startup unchanged in this unit;
- introduce no `0002_dataset_registry`, registry model/table, repository, service, API, dependency, object-storage code, startup Alembic integration, deployment, locking, backup tooling or Phase 5 work;
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

Add entry dated 2026-08-05:

- Phase 3D2B2 completed at `10a14b5d4279e294c07b654ba571d68070a22071`;
- durable dataset registry foundation selected as the first Phase 4 capability;
- legacy deterministic SQLite remains pinned to `0001_current_schema`;
- the future production Alembic head may advance to `0002_dataset_registry`;
- shared SQLAlchemy metadata is retained;
- legacy startup will use an explicit original-five-table table-object allowlist before registry models are activated;
- registry tables are Alembic-owned and are not created by legacy startup;
- Phase 4A1 pins fixed migration targets before Phase 4A2 introduces `0002_dataset_registry`.

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
