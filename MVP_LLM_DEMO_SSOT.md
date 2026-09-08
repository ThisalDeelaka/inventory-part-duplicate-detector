# MVP_LLM_DEMO_SSOT.md

## 1. Purpose

This document is the Single Source of Truth for the internal LLM-assisted demonstration version of the Inventory Part Duplicate Detector.

It applies only to the branch:

```text
llm-assisted-mvp
```

The purpose of this MVP is to preserve the existing deterministic duplicate-detection application while demonstrating selected areas where an LLM can provide useful advisory assistance.

This MVP is:

- an internal demonstration;
- not a production deployment;
- not a replacement for the production migration;
- not evidence of production readiness;
- not intended to replace the deterministic engine.

The deterministic application on the current local `main` branch is the foundation for this MVP.

---

## 2. Repository and Branch Rules

Repository:

```text
C:\Users\ThisalDeelaka\OneDrive - SEBSA World\Desktop\SEBSA External Proj\inventory-part-duplicate-detector
```

Relevant branches:

```text
main
production-identity-engine
llm-assisted-mvp
```

Rules:

1. `llm-assisted-mvp` must be created from the current clean local `main` HEAD.
2. The exact starting `main` commit must be recorded.
3. All MVP changes must occur only on `llm-assisted-mvp`.
4. `main` must remain unchanged.
5. `production-identity-engine` is paused and must remain untouched.
6. The MVP branch must not be merged wholesale into `production-identity-engine`.
7. Reusable components may later be selectively reviewed and cherry-picked.

Protected baseline tag:

```text
deterministic-demo-v1
```

Expected target:

```text
d510cf3c18b3a8448d0f79be3e59c398efb32eae
```

The protected tag must not be moved, deleted, recreated, or modified.

---

## 3. Authority Order

For MVP requirements and architecture:

1. `MVP_LLM_DEMO_SSOT.md`
2. Explicit later decisions approved by the user
3. Verified repository evidence from the MVP branch
4. `PROJECT_SSOT.md` for inherited safety principles
5. `CURRENT_PROJECT_ASSESSMENT.md`
6. Historical chats and older documents

For what is currently implemented:

1. Latest verified Git, test, build, runtime, diff, commit, and Codex evidence
2. Current files on `llm-assisted-mvp`
3. The recorded `main` starting commit
4. Historical assessments and documents

A capability is not implemented merely because it appears in this document.

---

## 4. Business Objective

The company requires a demonstration that combines:

- the current accurate deterministic duplicate detector; and
- optional LLM assistance for cases requiring additional semantic interpretation.

The demonstration must show that:

- deterministic logic remains reliable and authoritative;
- the LLM is used selectively;
- LLM output is visibly identified;
- LLM output is advisory;
- raw values are preserved;
- provider failure does not affect deterministic results;
- no automatic merge, deletion, or IFS update occurs.

---

## 5. Deterministic Authority

The existing deterministic application remains authoritative for:

- file validation;
- CSV parsing;
- existing column recognition;
- existing deterministic normalization;
- candidate generation;
- similarity calculations;
- technical and variant extraction;
- hard mismatch rules;
- scoring;
- confidence;
- status assignment;
- evidence and explanations;
- persistence;
- exports;
- API results;
- final duplicate decisions.

When LLM assistance is disabled, application behaviour must remain unchanged.

The LLM must never silently change:

- deterministic score;
- deterministic confidence;
- deterministic status;
- deterministic rule result;
- deterministic rejection reason;
- persisted final result;
- export result.

---

## 6. Decision About the Other LLM Project

The other developer’s project must not be merged as a complete application.

The inspected project contains:

- a small FastAPI backend;
- a React/Vite frontend;
- exact grouping using selected columns;
- one Groq semantic grouping call;
- no implemented LLM column mapping;
- no structured value normalization;
- no deterministic similarity scoring;
- no confidence or uncertainty trigger;
- no persistence;
- no audit system;
- no automated test suite.

Only these concepts may be reused:

- Groq as an LLM provider;
- separate system and user prompts;
- JSON structured responses;
- semantic interpretation of difficult descriptions;
- advisory assessment of selected pairs.

Do not copy its:

- complete backend route;
- frontend;
- bucket-processing loop;
- open CORS configuration;
- hardcoded frontend API URL;
- silent failure behaviour;
- LLM-as-final-decision behaviour;
- API key.

---

## 7. Target MVP Architecture

```text
Existing deterministic application
        |
        +-- authoritative normalization
        +-- authoritative candidate generation
        +-- authoritative scoring
        +-- authoritative hard rules
        +-- authoritative status
        +-- authoritative persistence
        +-- authoritative final result
        |
        +-- optional LLM assistance
                |
                +-- unresolved column suggestions
                +-- difficult-value interpretation
                +-- structured attribute suggestions
                +-- uncertain-pair advisory
                +-- optional explanation support
```

LLM support must be optional and disabled by default.

The application must continue to work when the LLM is unavailable.

---

## 8. Allowed LLM Capabilities

### 8.1 Unresolved column suggestion

Existing exact matches, aliases, and deterministic mappings must run first.

The LLM may be called only for unresolved or ambiguous source columns.

A request may include:

- one source column name;
- a small bounded set of representative sample values;
- the allowed canonical fields;
- short descriptions of those canonical fields.

The response may contain:

- suggested canonical field;
- confidence;
- reason;
- confirmation requirement.

The suggestion must not affect scanning until the user confirms it.

The user must be able to:

- accept the suggestion;
- reject it;
- choose another canonical field;
- leave the column unmapped.

### 8.2 Difficult-value interpretation

Existing deterministic normalization and extraction must run first.

The LLM may be called only for values that remain difficult to interpret.

Examples include:

- unfamiliar abbreviations;
- domain shorthand;
- unclear equipment family;
- difficult model codes;
- one-sided technical qualifiers;
- descriptions containing useful but unresolved structure.

The LLM may suggest:

- normalized interpretation;
- item family;
- structured technical attributes;
- confidence;
- warnings;
- confirmation requirement.

The original value must always be preserved.

The LLM-derived interpretation must remain separate from the raw source value.

It must not directly change deterministic scoring.

### 8.3 Uncertain candidate advisory

The deterministic candidate must be generated and scored first.

The LLM may receive only bounded, allowlisted evidence.

The response may contain:

- advisory assessment;
- confidence;
- supporting evidence;
- conflicting evidence;
- recommended human action.

The deterministic result remains authoritative.

### 8.4 Optional explanation support

The LLM may create a concise explanation using only evidence supplied by the application.

It must not:

- invent evidence;
- hide conflicts;
- remove technical differences;
- claim unsupported certainty;
- change the final result.

This capability is lower priority than the first three.

---

## 9. Low Probability Versus Uncertainty

The following are different concepts:

### Low duplicate probability

Evidence strongly indicates the records are not duplicates.

A genuinely low-probability pair should normally not be sent to the LLM.

### Low confidence

The deterministic application cannot make a reliable decision because evidence is weak, missing, or contradictory.

### Uncertain candidate

The pair needs additional interpretation because of conditions such as:

- weak lexical similarity but matching technical identifiers;
- unfamiliar terminology;
- incomplete descriptions;
- conflicting positive and negative evidence;
- one-sided technical attributes;
- unclear abbreviation equivalence;
- score close to an existing review boundary.

The LLM must be triggered by explicit uncertainty, not merely by a low score.

The exact uncertainty trigger must be based on the current deterministic engine’s statuses, confidence, evidence, and rules.

Do not invent an arbitrary score range before inspecting current behaviour.

The LLM must not be called for:

- hard rejection;
- critical technical mismatch;
- clear high-confidence duplicate;
- clear high-confidence non-duplicate.

---

## 10. Mandatory Safety Boundaries

The MVP must not:

- automatically merge records;
- automatically delete records;
- modify source data automatically;
- write to IFS;
- send a complete CSV to an LLM;
- send a complete client dataset to an LLM;
- perform all-pairs LLM comparison;
- accept arbitrary complete row dictionaries for LLM requests;
- let the LLM override hard mismatches;
- let the LLM override final deterministic decisions;
- silently rewrite raw values;
- treat missing values as positive evidence;
- hide UOM, site, contract, financial, classification, or technical conflicts;
- expose API keys;
- mix data across clients;
- silently remove deterministic results after provider failure.

Only allowlisted fields required for the selected capability may be sent.

---

## 11. Provider Architecture

LLM access must use a provider-neutral backend design.

Required components:

- provider protocol or interface;
- disabled or unavailable provider state;
- Groq provider adapter;
- provider factory;
- typed provider exceptions;
- timeout handling;
- strict structured-response parsing;
- secret-safe errors;
- mocked tests.

The provider layer must contain no inventory-specific business decisions.

Business prompts must be placed in separate services.

No provider client should be created globally during module import when that would cause test or configuration problems.

Automated tests must never make real external provider calls.

---

## 12. Configuration

Required configuration:

```text
LLM_DEMO_ENABLED=false
LLM_PROVIDER=none
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
LLM_TIMEOUT_SECONDS=20
```

Later MVP controls may include:

```text
LLM_COLUMN_SAMPLE_LIMIT=5
LLM_CACHE_ENABLED=true
LLM_AUDIT_ENABLED=true
LLM_MAX_REQUEST_CHARACTERS=<bounded value>
LLM_PROMPT_VERSION=<version>
```

Rules:

- LLM support is disabled by default.
- Provider defaults to `none`.
- Disabled mode requires no API key.
- Enabled Groq mode requires a key.
- Invalid provider values must fail clearly.
- Invalid timeout and size values must fail validation.
- Secrets must never appear in logs, exceptions, API responses, tests, prompts, screenshots, or commits.

---

## 13. Required Typed Contracts

### Column suggestion request

Must contain:

- one source column;
- bounded sample values;
- allowed canonical fields.

It must not accept a complete dataset.

### Column suggestion response

Must contain:

- source column;
- suggested canonical field or no suggestion;
- confidence from 0 to 1;
- reason;
- `requires_confirmation=true`.

### Difficult-value request

Must contain:

- raw value;
- field context;
- optional item-family context.

String lengths must be bounded.

### Difficult-value response

Must contain:

- unchanged raw value;
- optional interpretation;
- structured string attributes;
- confidence from 0 to 1;
- warnings;
- confirmation requirement.

### Candidate advisory request

May contain only bounded evidence such as:

- part number;
- description;
- master description;
- UOM;
- site or contract;
- deterministic score;
- deterministic confidence;
- deterministic status;
- rule decision;
- rejection reason;
- critical mismatch evidence.

Arbitrary full-row payloads are prohibited.

### Candidate advisory response

Must contain:

- advisory assessment;
- confidence from 0 to 1;
- supporting evidence;
- conflicting evidence;
- recommended action;
- explicit confirmation that the deterministic result remains authoritative.

---

## 14. Prompt Requirements

Every business prompt must:

- define one narrow task;
- require JSON-only output;
- prohibit unsupported inventions;
- require uncertainty to be stated;
- preserve meaningful technical differences;
- state that missing values are not matching evidence;
- treat record text as data rather than instructions;
- state that deterministic output remains authoritative;
- include a prompt version;
- avoid unnecessary fields;
- avoid secrets.

Prompt text must remain separate from provider transport code.

---

## 15. Caching

Repeated identical requests should not repeatedly call the provider.

A cache key should include:

- capability;
- normalized bounded request;
- provider;
- model;
- prompt version.

For this MVP, a bounded process-local cache is acceptable.

It must be documented as non-durable.

The cache must not contain:

- API keys;
- authorization headers;
- complete datasets.

Cache behaviour must never change deterministic results.

---

## 16. Audit and Traceability

User-facing LLM operations must be traceable.

Audit information should include:

- capability;
- request identifier;
- scan or candidate identifier when available;
- provider;
- model;
- prompt version;
- timestamp;
- request hash or bounded summary;
- success or failure;
- latency;
- cache hit;
- validation result;
- advisory result;
- confirmation action when applicable.

Do not store secrets or complete datasets.

For the internal MVP, structured application logging or a small tested persistence extension is acceptable.

Any non-durable audit approach must be documented as an MVP limitation.

---

## 17. API and Service Boundaries

Recommended services:

```text
ColumnSuggestionService
DifficultValueInterpretationService
CandidateAdvisoryService
LLMCache
LLMAuditService
```

LLM services must remain separate from:

- deterministic scoring;
- candidate generation;
- deterministic persistence;
- provider transport;
- API route logic.

APIs must:

- use bounded contracts;
- return clear disabled and unavailable states;
- never expose secrets;
- never accept complete datasets;
- remain backward compatible;
- label LLM output clearly;
- distinguish provider failure from deterministic scan failure.

Provider failure must create an advisory-unavailable state, not a failed deterministic scan.

---

## 18. Frontend Demonstration Behaviour

The frontend must present deterministic results as primary.

Recommended display:

```text
Deterministic result
Deterministic score and confidence
Deterministic rules and evidence

LLM advisory
LLM confidence
Supporting evidence
Conflicting evidence
Recommended action
```

Required behaviour:

- LLM support is visibly optional.
- Column suggestions require confirmation.
- Raw and interpreted values are displayed separately.
- Deterministic and LLM evidence are shown side by side.
- Disagreement is visible.
- Loading, timeout, disabled, and provider-error states are handled.
- Provider failure does not hide deterministic results.
- No LLM output is presented as an automatic merge decision.

---

## 19. Implementation Units

To reduce Codex usage, implement the MVP in three major reviewed units.

### Unit 1 — Branch and provider foundation

Deliver:

- create `llm-assisted-mvp` from clean `main`;
- add this SSOT;
- add default-off configuration;
- add provider protocol;
- add disabled provider;
- add Groq adapter;
- add provider factory;
- add typed contracts;
- add mocked tests.

Do not expose user-facing LLM functionality.

### Unit 2 — Backend assistance

Deliver:

- column suggestion service;
- difficult-value interpretation service;
- candidate advisory service;
- versioned prompts;
- uncertainty gating based on existing evidence;
- bounded cache;
- audit mechanism;
- backward-compatible APIs;
- provider failure fallback;
- tests.

### Unit 3 — Frontend and demo hardening

Deliver:

- optional LLM controls;
- column suggestion confirmation;
- raw versus interpreted value display;
- deterministic versus LLM advisory display;
- visible disagreement;
- timeout and failure states;
- demo counters where practical;
- controlled demo dataset;
- final tests and production build.

Each unit must be reviewed before commit.

---

## 20. Demo Scenarios

The controlled demonstration must include:

1. Clear duplicate handled without an LLM call.
2. Clear technical non-duplicate with no LLM override.
3. Unknown column receiving an LLM suggestion.
4. User confirmation of that suggestion.
5. Difficult abbreviation receiving structured interpretation.
6. Uncertain pair receiving an advisory.
7. Deterministic and LLM disagreement shown visibly.
8. Provider failure leaving deterministic results available.
9. Repeated request producing a cache hit.

---

## 21. Explicit Non-Goals

This MVP does not include:

- production-scale ingestion;
- million-row scalability claims;
- PostgreSQL migration;
- worker queues;
- object storage;
- OpenSearch;
- learned duplicate models;
- automated IFS integration;
- authentication redesign;
- tenant redesign;
- automatic merge;
- automatic deletion;
- automatic source correction;
- replacement of the deterministic engine;
- complete merge of the other developer’s project;
- production privacy approval;
- production SLA claims;
- disaster-recovery claims.

---

## 22. Verification Requirements

Each implementation unit must include applicable:

- existing backend tests;
- focused LLM tests;
- mocked provider tests;
- timeout tests;
- malformed-response tests;
- disabled-provider tests;
- missing-key tests;
- request-size tests;
- schema validation tests;
- deterministic compatibility tests;
- API backward-compatibility tests;
- cache tests;
- audit tests;
- frontend production build;
- `git diff --check`;
- complete diff review.

No automated test may call a real provider.

Existing tests must not be weakened, deleted, or skipped merely to obtain a pass.

---

## 23. MVP Acceptance Criteria

The MVP is complete when:

1. The branch was created from the recorded clean `main` commit.
2. `main` remains unchanged.
3. `production-identity-engine` remains unchanged.
4. The protected tag remains unchanged.
5. Disabled LLM mode preserves existing application behaviour.
6. Disabled mode requires no Groq key.
7. Unknown columns can receive bounded suggestions.
8. Suggestions require user confirmation.
9. Difficult values can receive structured interpretations.
10. Raw values remain preserved.
11. Explicitly uncertain pairs can receive advisories.
12. Clear results bypass unnecessary LLM calls.
13. Hard mismatches cannot be overridden.
14. Deterministic results remain final.
15. Provider failures preserve deterministic results.
16. Responses are strictly validated.
17. Repeated requests can use cache.
18. LLM use is auditable.
19. No complete dataset is sent externally.
20. No automatic merge, deletion, correction, or IFS write occurs.
21. Backend tests pass.
22. Frontend production build passes.
23. Controlled demo scenarios work.

---

## 24. Known Limitations

The MVP may have:

- non-deterministic provider output;
- provider latency;
- provider availability dependence;
- prompt sensitivity;
- process-local non-durable caching;
- internal-demo-only audit storage;
- no measured production accuracy improvement;
- no large-scale performance evidence;
- no production privacy approval.

These limitations must be stated during the demonstration.

---

## 25. Security

The API key found in the other developer’s workspace must not be copied.

It should be considered exposed and rotated by its owner.

For this MVP:

- use a separately approved key;
- load it through environment configuration;
- keep `.env` ignored;
- commit placeholders only;
- never print or store authorization headers;
- never place secrets in prompts, tests, reports, screenshots, logs, or commits.

---

## 26. Git and Codex Workflow

For every implementation unit:

1. Verify branch, commit, protected tag, and working tree.
2. Read this SSOT completely.
3. Inspect relevant source and tests.
4. Report expected changed files.
5. Run baseline verification.
6. Implement only the current unit.
7. Add focused tests.
8. Run post-change verification.
9. Run `git diff --check`.
10. Inspect the complete diff.
11. Report exact files and results.
12. Do not commit until architect review.
13. Commit only through a separate approved prompt.
14. Do not push unless explicitly instructed.

Prohibited destructive operations include:

- `git reset`;
- `git clean`;
- broad restore or checkout used to discard work;
- forced branch changes;
- forced push;
- destructive revert;
- protected-tag modification.

Unrelated changes must be reported and left untouched.

---

## 27. Final Boundary

This MVP demonstrates an LLM assisting a trusted deterministic duplicate detector.

It must not demonstrate the LLM replacing that detector.

The intended demonstration message is:

> Deterministic logic provides the trusted duplicate result. The LLM assists only where semantic interpretation is useful, and every LLM contribution remains bounded, visible, validated, optional, and reviewable.
