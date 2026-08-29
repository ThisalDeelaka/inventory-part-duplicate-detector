# Group-first inventory identity project SSOT

## Status and authority

This document is the authoritative source for product requirements, non-negotiable invariants, and the approved target direction for this repository.

The repository authority order is:

1. `PROJECT_SSOT.md` — authoritative product requirements, invariants, and target direction.
2. `docs/GROUP_FIRST_IDENTITY_ARCHITECTURE_ADR.md` — authoritative architecture decision and system boundaries.
3. `docs/GROUP_FIRST_DOMAIN_CONTRACTS.md` — authoritative target domain semantics and contracts.
4. `docs/GROUP_FIRST_MIGRATION_ROADMAP.md` — authoritative implementation sequence and phase boundaries.
5. `docs/CURRENT_PROJECT_ASSESSMENT.md` — descriptive current repository state only; it never overrides requirements or architecture.
6. `docs/CHATGPT_ARCHITECT_WORKFLOW.md` — implementation and governance procedure only; it never overrides requirements.
7. `MVP_LLM_DEMO_SSOT.md` and older pair-first documents — historical compatibility and regression context only where they conflict with the approved group-first architecture.

Older pair-first MVP requirements remain useful for historical compatibility and regression context, but they do not override the approved group-first product architecture.

## Primary business requirement

Given an inventory master, identify all sets of records that may represent the same underlying physical inventory item.

The primary business output is a `DuplicateIdentityGroup` or reviewed identity set containing 2..N records. A Part A versus Part B result is not the primary product output. Pair relationships may exist internally for discovery, evidence, safety, compatibility, and diagnostics only.

## Group semantics

- Every group contains 2..N records.
- Discovery neighborhoods may overlap.
- Accepted system groups within one projection are disjoint.
- Reviewed identity sets within one scan are disjoint.
- One record cannot belong to two accepted groups in one projection.
- One record cannot belong to two reviewed identity sets in one scan.
- System groups are scan-time hypotheses; reviewed identity sets are scan-local human decisions.

## Discovery and decision boundary

`DISCOVERY` performs high-recall, bounded candidate and neighborhood discovery. It is never authoritative identity and produces no duplicate decision.

`DECISION` applies deterministic signed evidence and a constrained resolver to produce likely, review, conflict, or deferred outcomes.

A retrieval score is not identity confidence. A discovered neighbor relationship is not a duplicate decision. No centroid, spanning tree, average score, or connected path can independently authorize group membership.

Small bounded groups may use complete pairwise validation. Larger work units use progressive targeted validation. The operational cutoff is benchmarked and tuned in later implementation phases; it is not permanent product truth.

## Physical identity rules

- Site and contract are context and optional scan scope, not physical identity authority.
- UOM is mapping and context evidence, not physical identity authority.
- Accounting group is context, not physical identity authority.
- Generic description alone is insufficient to establish physical identity.
- A protected technical identity contradiction may prove difference.
- A protected `CANNOT_LINK` always prevents co-membership.
- Cross-site identity is allowed when multiple sites are within scan scope.

## Group outcome semantics

### `LIKELY_DUPLICATE_GROUP`

May be emitted only when there is no protected conflict, validation is sufficiently complete, group cohesion is sufficient, and there is no unresolved bridge risk or ownership ambiguity. It remains a system hypothesis until human review.

### `POSSIBLE_DUPLICATE_GROUP_REVIEW`

Represents a plausible identity set with no protected cannot-link inside the proposed accepted membership, but unresolved, neutral, missing, or ambiguous evidence requires human review. It does not mean that every member is already proven to be a duplicate.

### `CONFLICT`

At least one protected contradiction or incompatible partition condition blocks acceptance of the affected hypothesis as one identity. Safe, disjoint subgroups may be emitted separately when the resolver can prove them.

### `DEFERRED`

The system cannot safely complete resolution within the current evidence, bounds, or resources. `DEFERRED` is not `CONFLICT`, and the two states must not be collapsed.

## Human authority

System groups are hypotheses. Human review is final operational authority within deterministic safety boundaries.

Supported review intent is:

- `CONFIRM_ALL`
- `CONFIRM_SELECTED`
- `SPLIT`
- `KEEP_SEPARATE`
- `UNSURE`

Implementations may map these business intents to versioned internal enum names without changing their meaning.

Human final authority means that a human chooses among constitutionally and safety-valid identity outcomes. It does not mean a reviewer can force a protected technical contradiction or cannot-link into one identity set. Terminal protected conflicts cannot be overridden into unsafe co-membership.

## Export authority

The System Group Export is an analytical system-hypothesis output and may contain unreviewed likely or review groups.

The Reviewed Identity Export is the operational human-authoritative output. Only confirmed reviewed identity sets are operationally authoritative. Unreviewed, unsure, conflict, and deferred outcomes must not be represented as confirmed operational identity.

## Optional AI boundary

- AI is optional.
- Provider choice is not approved or final.
- Claude adapter code exists, but Claude live testing and provider progression are paused pending CEO direction.
- Groq is reference-only.
- `GROUP_LLM_PROVIDER` defaults to `none`.
- One unresolved eligible group produces at most one advisory request.
- AI never discovers candidates.
- AI never changes deterministic evidence.
- AI never merges, deletes, mutates source data, or performs writeback.
- AI never becomes final identity authority.
- Provider calls are absent from the deterministic pipeline.

No provider-specific implementation is part of the product architecture.

## Cross-scan scope

Reviewed identity sets are scan-local. There is no durable enterprise cross-scan identity registry in the current roadmap. Contracts may preserve a future extension seam, but must not imply that such a registry currently exists.

## Scale direction

The first serious production design target is 100,000 records per scan. The future architecture evolution target is 1,000,000 or more records. The current implementation is not claimed to meet either target.

Global all-pairs computation and a full dense N-by-N matrix are prohibited as production architecture.

## GF-11 bounded cold-full performance waiver

The canonical 100,000-record `COLD_FULL` DISCOVERY target remains `<=300.000000 s` and remains unmet. The current three-run fresh/disposable-state sample is 304.764270 seconds minimum, 323.791250 seconds median, 324.468367 seconds maximum, 317.674629 seconds mean, and 2.8750% coefficient of variation.

By explicit supervising architect / product-owner decision, the bounded `GF11-PERF-100K-COLD-FULL` performance waiver is ACTIVE solely to permit independent GF-12 production-validation work to begin. GF-11 remains IN PROGRESS, the performance debt remains OPEN, and this waiver is not GF-11 performance graduation, a claim that the 300-second target was met, or final production graduation. GF-12 start was authorized under this bounded waiver and GF-12A1 has now begun that independent validation work.

The waiver does not relax correctness, determinism, cannot-link enforcement, membership uniqueness, provider isolation, GF-4 through GF-6 integrity, source immutability, deprecated-write prohibitions, security, or privacy. The detailed scope, expiry conditions, authorized GF-12 categories, blocked claims, and regression guard are authoritative in `docs/GF11_100K_COLD_FULL_PERFORMANCE_WAIVER.md`.

## GF-12 production-validation status

GF-12 is STARTED. GF-12A1 is VERIFIED: the group-first production-validation contract and corrected canonical offline quality baseline are established using `group-first-scale-corpus-v1`, `group-first-scale-truth-v2`, and evaluation contract `gf12-group-quality-v1`.

GF-12A2 human-review protocol/tooling is VERIFIED. No explicitly authorized representative non-synthetic validation dataset exists in the repository, so the blinded pilot is NOT EXECUTED, human labels and metrics are absent, and the state is `HUMAN_REVIEW_DATASET_REQUIRED`.

GF-12B1 is VERIFIED as a bounded privacy/security/data-boundary baseline. Provider-none isolation, synthetic-secret non-disclosure, offline truth/human-label separation, export/review allowlists, controlled input failure, and record-independent artifact paths pass PS1-PS24 with zero provider calls. Current retention/deletion policy gaps remain explicitly `UNSPECIFIED`.

GF-12B2 is VERIFIED: `RECOVERY/FAILURE-MODE/TRANSACTIONAL-INTEGRITY BASELINE VERIFIED`. Failed scans remain non-authoritative, caller-owned rollback and cache rollback preserve consistency, fresh retry equals a clean identity-aligned control, cross-scan isolation passes, and provider calls remain zero. Production cancellation and production scan timeout are `UNSUPPORTED / NOT IMPLEMENTED`; durable same-scan resume status is `NOT_IMPLEMENTED`, so the safe current action is a new scan by retry or restart rather than a claimed stage resume.

GF-12B3 is VERIFIED: `OBSERVABILITY/RUNBOOK/OPERATIONAL-READINESS BASELINE VERIFIED`. The synchronous lifecycle, stable scan/result ownership, authoritative read boundary, safe provider-none evidence, health/readiness surfaces, recovery actions, waiver debt, and human-validation dependency are documented and pass OR1-OR24 with zero provider calls. Public stage/failure-history telemetry, structured scan logging, and public group-provider status remain open; resume, production cancellation, and production scan timeout remain `NOT_IMPLEMENTED`.

The product owner has selected `SHOWABLE WORKING PRODUCT / DEMO READINESS` as the current milestone before deployment/integration architecture. GF-12C1 is VERIFIED for that bounded milestone: the explicitly synthetic 17-record local demo completes end to end through group-first scan, identity-read UI, 2..N group detail, conflict visibility, append-only review, and authority-selected System/Reviewed exports. DEMO1-DEMO24 and three fresh semantic-equivalence runs pass with provider calls zero. `SHOWABLE WORKING PRODUCT = VERIFIED` and `DEMO-READY = YES`; production deployment readiness and final human-quality signoff remain unclaimed.

GF-12C1-R1 restores deterministic real/legacy CSV intake compatibility and closes
the synthetic demo-harness/browser mapping gap. The unchanged historical 5,327-row
target CSV validates through the actual New Scan multipart contract, and the
synthetic fixture now does so without a hidden explicit mapping. The complete real
scan is not product-ready: character retrieval fails safely with
`PRIMARY_IDENTITY_FAILED` because the LSH candidate pool has too few
positive-cosine candidates. Therefore `SHOWABLE WORKING PRODUCT = VERIFIED`
remains qualified to the synthetic demo; real-target intake is VERIFIED but
real-target end-to-end demonstration is BLOCKED. See
`docs/GF12_REAL_CSV_INGESTION_REGRESSION.md`.

Until after this milestone, deployment architecture, tenancy, an application IAM/authorization platform, managed production storage, cloud/platform deployment, external integrations, production network/retention policy, and reference production hardware are deferred, not completed. Post-demo work remains separated into authorized human-reviewed quality validation; deployment/IAM/tenancy/storage/network/retention architecture; authorized integrations/provider strategy; and remaining production performance/scale debt.

These are validation-infrastructure results, not final human-reviewed production-quality signoff or GF-12 completion. No numeric quality or reviewer-agreement threshold is authorized. GF-11 remains IN PROGRESS, its performance waiver remains ACTIVE, `GF11-PERF-100K-COLD-FULL` remains OPEN, and the unchanged 300-second target remains unmet.

## Non-negotiable safety invariants

- Naive connected-component acceptance is prohibited.
- An accepted group containing a protected cannot-link is impossible.
- A record appearing in multiple accepted groups in one projection is impossible.
- A record appearing in multiple reviewed identity sets in one scan is impossible.
- There is no automatic source mutation, merge, delete, or writeback.
- Deterministic evidence is versioned and auditable.
- Historical snapshots are immutable.
- Provider calls are absent from the deterministic pipeline.
- Missing, truncated, degraded, or unevaluated evidence cannot silently become positive proof.
- Historical pair data is not destructively rewritten or deleted by the group-first migration.

## G2 snapshot versioning

G2 v1 retains its historical complete N-choose-2 snapshot semantics unchanged.

G2 v2 may support `COMPLETE_PAIRWISE` or `PROGRESSIVE_TARGETED` validation. Every v2 group explicitly declares its validation mode and persists enough evidence and coverage to audit its classification. A v2 reader must never silently reinterpret a v1 snapshot.

## Migration freeze

GF-0 is the governance and contract-freeze phase. GF-1 is the first production implementation phase. No implementation may skip prerequisite contracts and persistence to begin GF-3 neighborhoods, GF-5 resolver work, GF-8 orchestration, or GF-9 UI inversion.

The approved sequence is:

1. GF-0 Governance and contract freeze.
2. GF-1 Canonical scan-record catalog.
3. GF-2 Discovery-run and neighbor-proposal contracts.
4. GF-3 Overlapping identity neighborhoods.
5. GF-4 Independent signed evidence.
6. GF-5 Constrained resolver v1.
7. GF-6 Versioned G2 adapter.
8. GF-7 Controlled shadow comparison.
9. GF-8 Group-first scan orchestration.
10. GF-9 API/UI/export inversion.
11. GF-10 Pair-path write deprecation.
12. GF-11 100k scale hardening.
13. GF-12 Production validation and graduation.

The phase order may change only through an explicit architecture decision.

## Pair-path migration status

Current: pair machinery remains operational compatibility infrastructure and internal evidence.

Target: pair machinery ceases to be the business-domain center.

The non-destructive migration order is to hide normal pair prominence, introduce independent discovery and evidence, graduate the new resolver through controlled shadow validation, stop new pair feedback and pair LLM writes, stop `DuplicateCandidate` business writes only after consumers migrate, and retain historical read-only diagnostics. Pair tables, APIs, and historical records are not removed in GF-0.
