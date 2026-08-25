# Group-first identity migration roadmap

## Purpose and constraints

This roadmap turns the approved group-first ADR and domain contracts into bounded implementation phases. It is planning documentation only.

Every phase must preserve:

- protected cannot-link safety;
- disjoint accepted groups;
- append-only human review;
- immutable G2 snapshots;
- historical pair and group readability;
- zero automatic inventory mutation or writeback;
- optional, advisory-only AI with ordinary tests making zero provider calls;
- a documented rollback point before the next phase begins.

No phase may silently change the current selected projection, group status semantics, or export authority.

## Program-wide delivery rules

1. Each phase has its own reviewed prompt/change set and explicit file allowlist.
2. Additive schema changes precede new writes. Readers tolerate absent historical data.
3. Old and new paths never both appear as current user-visible truth.
4. Shadow mode is provider-free and review-free.
5. Safety gates are release blockers, not weighted quality metrics.
6. Performance thresholds are established from measured baselines on declared hardware and data shapes.
7. Pair tables are not deleted during this roadmap.

## GF-0 — Governance and contract freeze

### Goal

Approve the ADR, domain contracts, terminology, product authority, G2 versioning strategy, and phase boundaries before production code begins.

### Likely files/modules

- `docs/GROUP_FIRST_IDENTITY_ARCHITECTURE_ADR.md`
- `docs/GROUP_FIRST_DOMAIN_CONTRACTS.md`
- `docs/GROUP_FIRST_MIGRATION_ROADMAP.md`
- `PROJECT_SSOT.md`, the repository product-requirements authority

### Invariants

- Group is the business result; pair is internal evidence.
- Site/contract and UOM semantics are approved.
- Discovery overlap and final disjointness are approved.
- Reviewed identity remains scan-local.
- No numeric group confidence is approved.

### Tests/review

- Cross-document vocabulary and route comparison.
- Source trace verifying every reuse/deprecation decision has an implemented origin.
- Architecture review of bridge fixtures and progressive-validation semantics.
- Product-owner sign-off on export authority and the 100k target.

### Migration risk

Low technical risk; high risk of later churn if skipped.

### Rollback point

Documentation commit can be reverted without runtime effect.

### Explicitly out of scope

Production code, database changes, APIs, UI, providers, and benchmarks.

## GF-1 — Canonical scan-record catalog

### Goal

Create immutable, source-row-distinct `InventoryRecord` snapshots before discovery while preserving current raw-data privacy boundaries.

### Likely files/modules

- `backend/app/db/models.py`
- `backend/app/db/migrations.py`
- `backend/app/services/validation_service.py`
- `backend/app/services/scan_runner.py`
- New canonical-record repository/service and schemas
- Record/migration/privacy tests

### Invariants

- Distinct source rows never collapse because their canonical values match.
- Raw canonical values and normalized evidence remain separate.
- Existing G2 record references remain readable.
- No complete CSV or arbitrary full row is persisted.
- Current scan results remain unchanged.

### Tests

- Idempotent snapshot creation and source-row uniqueness.
- Duplicate-identical-row fixtures.
- Header mapping, missing data, raw/normalized traceability.
- Transaction rollback and historical database migration.
- Privacy allowlist and no-secret/no-provider tests.
- Existing backend regression suite.

### Migration risk

Medium: record-reference changes can affect G2 fingerprints if introduced prematurely.

### Rollback point

New tables/columns remain unused; current transient rows and G2 path continue.

### Explicitly out of scope

New retrieval, evidence evaluation, resolver behavior, visible API changes.

## GF-2 — Discovery run and neighbor-proposal contracts

### Goal

Separate retrieval proposals from duplicate decisions and add versioned discovery-run observability.

### Likely files/modules

- New discovery contracts, repositories, and run service
- `backend/app/services/hybrid_retrieval.py`
- `backend/app/core/config.py`
- `backend/app/db/models.py` and additive migrations
- Discovery metrics and tests

### Invariants

- Retrieval priority is never identity confidence.
- Discovery produces no business status.
- Per-record/channel/global caps and degradation are explicit.
- No-neighbor records are successful outcomes.
- Current `DuplicateCandidate` writes and visible results remain unchanged.

### Tests

- Stable proposal ordering and fingerprints under input permutation.
- Cap, reciprocal, no-neighbor, generic-family, and degraded-channel cases.
- Coverage equations and bounded persistence.
- Provider request count remains zero.
- Compatibility comparison with current hybrid retrieval fixtures.

### Migration risk

Medium: duplicated computation or metadata drift during adaptation.

### Rollback point

Disable discovery-contract writes; legacy hybrid retrieval remains authoritative.

### Explicitly out of scope

Neighborhood grouping, independent identity edges, new G2 output.

## GF-3 — Overlapping identity neighborhoods

### Goal

Build and persist bounded, overlapping discovery neighborhoods from neighbor proposals.

### Likely files/modules

- New neighborhood builder/service and schemas
- New neighborhood tables/repositories
- Discovery metrics and advanced diagnostic tests
- No normal UI changes

### Invariants

- Neighborhood overlap is allowed and deterministic.
- A neighborhood never declares duplicate identity.
- Generic/oversized families are deferred before unbounded expansion.
- Every truncation changes provenance and downstream fingerprint.
- Current visible pair-first G2 remains unchanged.

### Tests

- Overlapping anchors and canonical membership.
- Generic hub suppression and family deferral.
- Neighborhood/member cap behavior.
- Coverage/no-neighbor accounting.
- Persistence idempotency, pagination, and rollback.

### Migration risk

Medium: poorly chosen neighborhood rules can reduce recall or create oversized unions.

### Rollback point

Retain proposal rows/metrics but disable neighborhood creation.

### Explicitly out of scope

Identity resolution and user-visible group selection.

## GF-4 — Independent signed evidence

### Goal

Introduce `IdentityEvidenceEdge` independently of `DuplicateCandidate` and adapt the current deterministic scorer/rules behind `IdentityEdgeEvaluator`.

### Likely files/modules

- `backend/app/engine/identity_edge.py`
- `backend/app/engine/decision_engine.py`
- New edge evaluator/service/contracts/repository
- `backend/app/db/models.py` and additive migrations
- Attribute-conflict index foundation
- Pair compatibility adapters and tests

### Invariants

- Existing deterministic scores/rules do not change in this phase.
- Protected conflicts always resolve to cannot-link.
- Human must-link cannot override deterministic cannot-link.
- UOM/site/accounting alone cannot become identity authority.
- Edge evaluation does not require or create `DuplicateCandidate`.
- Visible G2 remains legacy-generated.

### Tests

- Parity between evaluator output and current pair classifier fixtures.
- Legacy candidate/exclusion import provenance.
- Edge idempotency, ordering, precedence, and safe failure.
- Attribute conflict index equivalence for protected rules.
- Zero-provider test.

### Migration risk

High: safety drift between the legacy scorer path and the adapter is unacceptable.

### Rollback point

Stop independent edge writes and retain legacy candidate-based G0.

### Explicitly out of scope

New partitioning, group status changes, pair deprecation.

## GF-5 — Constrained resolver v1

Implementation status: verified through GF-5A contracts and golden cases,
GF-5B pure constrained resolution, and GF-5C immutable lifecycle/persistence
with non-visible normal-scan integration. It still publishes no G2 result.

### Goal

Implement the deterministic group-first resolver over neighborhoods and independent signed evidence, initially without publishing G2 results.

### Likely files/modules

- New resolution contracts/service
- Refactored/reused logic from `identity_group_projection.py`
- Attribute consensus and bridge-analysis modules
- Bounded partition-search module
- Resolution/hypothesis persistence tables
- Extensive resolver fixtures

### Invariants

- Neutral edges never seed support.
- No accepted hypothesis contains cannot-link.
- Final likely/review hypotheses are disjoint.
- Bridge conflicts cannot become one group.
- Safe subgroup salvage cannot create overlapping accepted membership.
- Bounds cause deferred results, never optimistic acceptance.
- Resolver is deterministic and provider-free.

### Tests

- A-B/B-C/A-C cannot-link and neutral bridge fixtures.
- Rotor/stator, DE/NDE, inlet/outlet, side, component, generic hub fixtures.
- Competing neighborhoods and ambiguous ownership.
- Stable safe-subgroup salvage and partition ties.
- Complete-pair small groups and progressive large neighborhoods.
- Input-order/property tests and invariant fuzzing.
- Persistence checkpoint/resume and rollback.

### Migration risk

High: this is the new decision core.

### Rollback point

Resolver runs remain non-visible; legacy G1/G2 is untouched.

### Explicitly out of scope

G2 publication, normal APIs/UI, pair-write shutdown, AI.

## GF-6 — Versioned G2 adapter

Implementation status: verified through GF-6A pure adapter contracts and GF-6B
immutable, non-current persistence with current-reader compatibility isolation.

### Goal

Adapt completed resolver output to immutable, idempotent G2 snapshots with explicit v1/v2 validation semantics.

### Likely files/modules

- `backend/app/services/identity_group_snapshot_service.py`
- `backend/app/db/models.py`
- `backend/app/db/migrations.py`
- `backend/app/services/identity_group_query_service.py`
- Group schemas and G2 snapshot tests

### Invariants

- Historical v1 snapshots are byte/semantically compatible.
- V2 snapshots record discovery/resolution provenance and validation mode.
- Required checks are complete for every accepted group.
- G2 write remains one atomic transaction.
- Creating a v2 shadow snapshot does not make it current/visible.
- Conflicts/deferred families remain separate from accepted groups.

### Tests

- V1 fixture replay and historical empty-state behavior.
- V2 complete and progressive snapshots.
- Evidence copying/reference integrity.
- Fingerprint idempotency and version isolation.
- Transaction fault injection.
- Wrong-scan/run selection rejection.

### Migration risk

High: accidental selection of a shadow or partial projection would create two truths.

### Rollback point

Keep v2 adapter disabled; v1 G2 remains selected.

### Explicitly out of scope

Normal UI promotion, pair deprecation, provider work.

## GF-7 — Controlled shadow comparison

Implementation status: verified through GF-7A pure comparison contracts and
metrics plus GF-7B immutable, explicitly controlled, non-visible persistence.
G2-v1 remains current; GF-8 promotion/orchestration has not started.

### Goal

Run old and new pipelines on controlled scans, keeping the old G2 result visible and recording non-visible comparison metrics.

### Likely files/modules

- New shadow orchestration/comparison service and tables
- Scan/admin diagnostic route or offline CLI
- Benchmark corpora and comparison reports
- No business UI result selector

### Invariants

- Old path remains the only visible current result.
- Shadow output cannot receive human review.
- Shadow execution makes zero external provider calls.
- No source data or existing snapshot is modified.
- Full case-level differences remain inspectable without exposing secrets.

### Tests

- Comparison metric correctness on exact/split/merge/overlap fixtures.
- Cannot-link and duplicate-membership blocker detection.
- Old/new failure isolation.
- No-visible-selection and no-review enforcement.
- Runtime/evidence-volume measurement integrity.

### Migration risk

Medium: operational cost and confusion if shadow artifacts leak into normal APIs.

### Rollback point

Disable shadow scheduling and retain collected read-only comparison records.

### Explicitly out of scope

Graduation, business UI changes, provider benchmarking.

## GF-8 — Group-first scan orchestration

Implementation status: verified through GF-8A frozen orchestration contracts
and GF-8B controlled legacy-primary/group-first-primary runtime integration.
G2-v1 remains the visible compatibility projection until GF-9.

### Goal

Make canonical snapshot, discovery, evidence acquisition, resolver, and G2 v2 the required normal scan stages after graduation gates pass.

### Likely files/modules

- `backend/app/services/scan_runner.py`
- `backend/app/services/scan_service.py`
- `backend/app/api/routes_scans.py`
- Scan status/stage models and migrations
- Background/resume scheduler seam
- End-to-end scan tests

### Invariants

- A scan is not group-ready completed without a valid selected G2 snapshot.
- Stage failures are safe, observable, and resumable where declared.
- Optional channel degradation is explicit.
- Automatic LLM work is not a required stage.
- Legacy mode remains a feature-flagged rollback during compatibility.

### Tests

- Stage success, degradation, failure, retry, restart, and atomic G2 publication.
- Valid zero-group scan.
- Completed-with-deferred behavior.
- Concurrent scan isolation.
- Old/new mode selection and rollback.
- Zero-provider execution with AI disabled.

### Migration risk

High: changes the normal execution path.

### Rollback point

Switch the visible engine flag back to legacy pair-first orchestration; v2 records remain non-destructive.

### Explicitly out of scope

Removing pair tables or changing provider defaults.

## GF-9 — Group-first API, UI, and export inversion

Implementation status: verified and complete through GF-9A read-authority
contracts, GF-9B backend inversion, and GF-9C frontend/export end-to-end
graduation. GF-10 pair-path write deprecation is verified and complete.

### Goal

Make group counts, groups, conflicts, and human review the complete normal business workflow while keeping advanced pair diagnostics available.

### Likely files/modules

- `backend/app/api/routes_identity_groups.py`
- Group query/export/review services and schemas
- `frontend/src/pages/ScanResults.jsx`
- Group/review UI utilities and components
- Frontend/backend API and export tests

### Invariants

- Groups remain the default view.
- Pair counts/status are not the scan headline.
- Pair review and pair AI controls are absent from the normal workflow.
- Group evidence is bounded and paginated.
- System and reviewed exports clearly differ in authority.
- Existing compatibility routes continue to read historical scans.

### Tests

- Summary counters and cursor pagination at large fixture sizes.
- Group detail/evidence pagination.
- Group review and scan-wide reviewed-set exclusivity.
- Confirmed-only operational export.
- UI accessibility and group-first wording tests.
- Historical scan and compatibility behavior.

### Migration risk

Medium: user confusion or accidental change to export authority.

### Rollback point

Re-enable the prior UI composition while retaining v2 API fields and snapshots.

### Explicitly out of scope

Deleting legacy endpoints/data or adding AI UI.

## GF-10 — Pair-path write deprecation

Implementation status: VERIFIED AND COMPLETE. GF-10A verified the residual
dependency inventory and froze the post-GF-9 policy-v2 contracts. GF-10B-PRE
verified truthful G2-v2 audit persistence, and GF-10B runtime deprecation now
suppresses pair/G1/G2-v1/shadow writes for explicit group-first scans while
preserving policy-v2 legacy behavior and historical policy-v1 reads.

GF-10 remains one roadmap phase with two bounded delivery units:

- GF-10A — residual pair-path dependency inventory and post-GF-9
  orchestration/deprecation contracts;
- GF-10B — runtime write deprecation for group-first-primary scans plus
  compatibility/shadow cleanup.

### Goal

Stop creating new pair business decisions after every supported consumer uses independent evidence and group results.

### Likely files/modules

- Candidate repository and scan orchestration
- Pair feedback routes/services
- Pair LLM triage scheduling/services
- Pair export/API compatibility layer
- Deprecation telemetry and documentation

### Deprecation order

1. Hide pair review and pair LLM controls from normal UI.
2. Mark pair feedback and pair LLM APIs deprecated; reject new writes only after client telemetry confirms no supported dependency.
3. Stop automatic pair LLM scheduling.
4. Stop `DuplicateCandidate` writes in group-first scans.
5. Keep pair APIs/exports read-only for historical and legacy-mode scans.
6. Remove the legacy conflict-unaware grouping route after its compatibility window.
7. Consider archival strategy only in a later separately approved program.

### Invariants

- Historical pair data stays readable.
- No G2/G6 evidence loses provenance.
- New group-first scans remain fully explainable without `DuplicateCandidate`.
- Pair deprecation cannot change group membership.

### Tests

- Read-only historical API/export fixtures.
- Explicit write rejection and version headers.
- No hidden pair scheduler/background writes.
- New group-first scan contains complete independent evidence.
- Legacy-mode rollback continues during the declared period.

### Migration risk

Medium/high: undocumented consumers may depend on pair endpoints.

### Rollback point

Temporarily re-enable pair writes behind the compatibility flag without changing G2 selection.

### Explicitly out of scope

Dropping tables, deleting rows, or migrating historical pair feedback into invented group reviews.

## GF-11 — 100k scale hardening

Implementation status: IN PROGRESS. GF-11A, GF-11B, GF-11C-PRE, and GF-11C
are verified bounded units. GF-11D is measured but insufficient/not graduated.
Production policy-v2 discovery uses exact indexed
v4 lexical retrieval below 25,000 eligible records and bounded rarity-aware
retrieval with one fixed fail-closed second pass at 25,000 and above. The 50k
production run recovered all 6,250 primary-insufficient anchors, left zero
remaining, and matched the exact reference for final proposals, neighborhoods,
and coverage. Deterministic 900-key cache-load chunks resolve the SQLite
variable-limit failure without changing transactions or hit/miss behavior.

The 100k production lexical-only check completed bounded retrieval in 98.300
seconds and recovered all 12,500 primary-insufficient anchors, but it is not a
full-pipeline graduation. CHAR_VECTOR, cache save, and fusion/materialization
remain measured bottlenecks. The canonical GF-11D 100k run timed out at the
300-second gate. Its sole 900-second diagnostic completed 721.191-second
DISCOVERY and GF4, then timed out in GF5 before GF6. CHAR_VECTOR was the
largest measured production stage at 336.432 seconds and is the single next
hardening target. GF-12 remains not started. These units do not alter the
GF-0 through GF-12 order.

### Goal

Meet measured 100k-record performance and reliability gates without changing identity semantics.

### Likely files/modules

- Chunked ingestion/canonical snapshot services
- Discovery indexes and `IdentityVectorIndex` adapters
- Background/resumable stage execution
- Database indexes/query pagination
- Load/benchmark tooling and observability
- Frontend virtualization where measured necessary

### Invariants

- No global all-pairs operation.
- No full dense N-by-N matrix.
- Evidence and neighborhood volume obey configured bounds.
- Generic families defer safely.
- Performance optimization cannot weaken cannot-link or required checks.
- Repeated/resumed stages remain idempotent.

### Tests/benchmarks

- 5k, 20k, and 100k representative scans on declared hardware.
- Sparse, generic-heavy, technical-family, and cross-site distributions.
- Runtime, peak memory, database growth, evidence volume, and pagination latency.
- Kill/restart/resume and concurrent-job isolation.
- Quality/coverage comparisons at each cap.
- Thresholds set from baseline before graduation; no invented timings.

### Migration risk

High: index/storage changes can alter recall if contracts are not fixed.

### Rollback point

Select the previous discovery adapter/configuration version; keep resolver/G2 contracts stable.

### Explicitly out of scope

One-million-record distributed execution and external provider optimization.

## GF-12 — Production validation and graduation

### Goal

Validate correctness, safety, usability, and operating characteristics on representative human-reviewed data before declaring the new architecture production-ready.

### Likely files/modules

- Offline evaluation/benchmark services
- Curated and organization-approved labeled datasets
- Security/privacy/operations documentation
- Release and rollback runbooks
- No provider selection requirement

### Invariants

- Safety gates remain absolute.
- Aggregate shadow similarity cannot substitute for case review.
- Operational accuracy claims use human-reviewed real-client data.
- Provider performance is not part of deterministic engine graduation.

### Tests/review

- Per-group precision/recall-style evaluation against approved reviewed sets.
- Split/merge and missed-record adjudication.
- Cannot-link, exclusivity, and writeback-zero audits.
- 100k benchmark thresholds and recovery exercises.
- Security, privacy, tenancy, authorization, and export review.
- User acceptance of group review and operational export.

### Migration risk

High organizational risk if representative labels or owner decisions are absent.

### Rollback point

Keep group-first disabled for production tenants or revert the visible-engine flag while preserving validation artifacts.

### Explicitly out of scope

Cross-scan identity registry, automatic merge/writeback, and provider selection.

## Shadow-comparison specification

### Execution isolation

- Enabled only by explicit controlled configuration/CLI/admin action.
- Never scheduled merely because a normal scan exists.
- Reads the same canonical record snapshot and approved scope.
- Writes to shadow-purpose discovery/resolution/comparison records.
- Does not become the selected G2 projection.
- Cannot create or consume G6 review as current state unless a read-only labeled-evaluation copy is explicitly supplied.
- Makes zero provider calls.

### Metrics

| Category | Metrics |
|---|---|
| Membership | exact-group matches, group Jaccard, record co-membership agreement |
| Coverage | records with neighbors, grouped, unassigned, missed by either path |
| Shape | group counts/sizes, likely/review/conflict/deferred counts |
| Difference | old groups split by new, old groups merged by new, moved records, unmatched groups |
| Safety | protected cannot-link violations, duplicate accepted membership, unresolved bridge risks |
| Evidence | proposals, independent edges, targeted evaluations, complete/progressive checks |
| Resource | runtime by stage, peak memory, DB bytes/rows, resume count |
| Quality | case-level labeled outcome, safe abstention, false merge, false split, missed identity |

Comparison group matching uses deterministic maximum-overlap matching only for reporting. It does not resolve identity.

### Graduation rules

- Every safety metric is zero on all required suites.
- Every material merge/split difference is reviewed at case level.
- Discovery coverage and cap losses meet thresholds established by the evaluation owner.
- Human-reviewed quality meets approved thresholds on representative data.
- 5k/20k/100k performance meets measured budgets.
- Historical APIs/exports and rollback have been exercised.
- Architecture owner, product owner, and data steward approve promotion.

## Program acceptance matrix

### Safety gates

- `accepted_group_cannot_link_count == 0`
- `accepted_record_multi_membership_count == 0`
- `reviewed_set_multi_membership_count == 0`
- `automatic_source_mutation_count == 0`
- `external_provider_calls_in_deterministic_pipeline == 0`

### Functional gates

- Normal result, review, and export operate on 2..N groups.
- Group resolution does not require a persisted `DuplicateCandidate`.
- Conflict/deferred/unassigned outcomes are explicit.
- Group status derives from the group evidence contract, never average pair score.
- Advanced pair evidence remains available without being the business workflow.

### Discovery gates

- Coverage denominator and numerator are reproducible.
- No-neighbor records are counted.
- Every cap and truncation has a bounded reason.
- Generic-family deferral is visible.
- Identical inputs/configuration produce identical proposal and neighborhood fingerprints.

### Regression gates

- Historical G2 v1 scans remain readable.
- Current G3-G7 behavior is unchanged for v1 or explicitly versioned for v2.
- Pair diagnostics remain readable through the compatibility period.
- Existing human review history remains append-only.
- Ordinary automated tests make zero real provider requests.

### Performance benchmark requirements

For 5k, 20k, and 100k datasets, record:

- hardware/OS/runtime/database and configuration versions;
- data-shape distribution, block sizes, missingness, and generic-family prevalence;
- stage runtime and retry/resume behavior;
- peak process memory and persisted storage growth;
- proposal, neighborhood, evidence, group, conflict, deferred, and unassigned counts;
- API list/detail/export latency under bounded pagination;
- discovery coverage and labeled quality effects of caps.

Baseline results are collected before setting pass thresholds. A phase cannot claim 100k readiness merely because it completes a synthetic uniform dataset.

## Compatibility-period exit criteria

Pair compatibility may end only after:

- no supported normal UI uses pair APIs;
- no current export consumer requires pair business columns;
- new scans have complete independent evidence provenance;
- historical pair reads have an archival/access plan;
- pair feedback and pair LLM write endpoints have been deprecated for a declared period;
- rollback no longer depends on creating new pair rows;
- the user explicitly approves retirement.

Table deletion is not part of this roadmap and requires a separate destructive-migration decision.

## Recommended first implementation phase

GF-0 is the prerequisite governance and contract-freeze phase. Once its documentation commit is reviewed and accepted, **GF-1 — Canonical scan-record catalog** is the first production implementation phase. No later phase may start by skipping its prerequisites.
