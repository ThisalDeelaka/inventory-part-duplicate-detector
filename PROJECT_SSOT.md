# Group-first inventory identity project SSOT

## IQR-0 pre-demo identity-quality recovery

PRM-5 remains historical `WORKFLOW_AND_PRESENTATION_VERIFIED`, but external demo
readiness is now `BLOCKED_BY_IDENTITY_OUTPUT_QUALITY`. The frozen showable-product
baseline is `PRESERVED`; pre-demo identity-quality recovery is `ACTIVE`; the
post-proof roadmap is `DEFERRED`. Read-only Scan-33 tracing proves a multilayer
defect: site is a hard pre-evidence discovery boundary for the Bicycle family,
while Head/Tail functional/location meaning is not extracted into typed identity
evidence. No runtime correction is part of IQR-0. See
`docs/IQR0_PRE_DEMO_IDENTITY_QUALITY_DIAGNOSTIC.md`.

## PRM-5 showable-product freeze

Product Recovery Milestone is `COMPLETE` and the showable human-in-the-loop
product/demo baseline is `FROZEN` at PRM-5. The verified presentation path uses
saved current-product scan 31 (5,327 records, Group-First primary, G2_V2) through
normal Dashboard/history navigation, with a bounded optional 17-row synthetic
live path. System explanations, append-only Human decisions, and separate System
versus Reviewed exports remain truthful; provider calls are 0. Immediate next
action is demo/presentation only. Identity-engine semantics are `PAUSED`, R18
human labels are `DEFERRED`, and deployment is `DEFERRED UNTIL PRODUCT PROOF`.
GF11 remains `IN PROGRESS` under its `ACTIVE` waiver,
`GF11-PERF-100K-COLD-FULL` remains `OPEN`, GF12A2 human-label execution remains
incomplete, and the R12 autonomous-quality freeze failure remains in force. See
`docs/PRODUCT_RECOVERY_PRM5_DEMO_REHEARSAL_AND_FREEZE.md`.

## Status and authority

This document is the authoritative source for product requirements, non-negotiable invariants, and the approved target direction for this repository.

### Immediate priority: Product Recovery Milestone

PRM-4 is VERIFIED: Dashboard exposes authoritative Latest and Recent scan
history, historical results reopen through normal routes, current validation is
required before submission, and synchronous processing shows truthful active and
elapsed guidance with safe recovery. No fake progress, execution-model change,
detector change, or authority change was introduced. PRM-1 through PRM-3 remain
VERIFIED. PRM-5 rehearsal and showable-product freeze are next. See
`docs/PRODUCT_RECOVERY_PRM4_NAVIGATION_PROGRESS_RECOVERY.md`.

PRM-3 is VERIFIED: System Group Export is explicitly presented as analytical
machine-generated suggestions, while Reviewed Identity Export is explicitly
presented as current human-confirmed operational authority. Zero-affirmative,
partial-review, supersession, loading, success, and failure states are truthful;
routes, file shapes, row membership, review authority, and detector semantics
are unchanged. PRM-1 and PRM-2 remain VERIFIED. PRM-4 is next. See
`docs/PRODUCT_RECOVERY_PRM3_EXPORT_AUTHORITY_CLARITY.md`.

PRM-2 is VERIFIED: the unchanged review enums now appear as unmistakable Confirm,
Reject, and Defer decisions with truthful consequences, multi-member guidance,
saved current-state outcomes, append-only Previous decision history, and explicit
409/422/network feedback. PRM-1 remains VERIFIED; System explanation and Human
decision remain separate. PRM-3 export-authority distinction is next. See
`docs/PRODUCT_RECOVERY_PRM2_REVIEW_ACTION_CLARITY.md`.

PRM-1 is VERIFIED: current-product group list/detail, conflict, and deferred read
paths expose bounded plain-language explanations derived only from persisted
authoritative evidence. System explanations remain hypotheses, Human decision is
separate, advanced evidence remains available, and detector/export semantics are
unchanged. PRM-2 is next: make Confirm / Reject / Defer unmistakable and polish
saved-review interaction without authority changes. See
`docs/PRODUCT_RECOVERY_PRM1_GROUP_EXPLANATIONS.md`.

PRM-0 completed the CEO/first-time-user journey audit. The immediate priority is
the finite Product Recovery Milestone defined in
`docs/PRODUCT_RECOVERY_CEO_USER_JOURNEY_AUDIT.md`, beginning with PRM-1's
plain-language presentation of already-persisted group evidence. Detector
semantics are paused for this milestone: no normalization, retrieval, GF2-GF6,
signature, signed-evidence, threshold, status, or membership change is
authorized by PRM-0.

R14-R18 remain valid historical/future identity-engine research. R18 is only
`HUMAN_REVIEW_DATASET_PREPARED` / `HUMAN_LABEL_EXECUTION_PENDING`; label
execution is deferred. The R12 full-real quality failure still leaves the
detector technically unfrozen. GF-11 remains in progress under its active
waiver with the cold-full debt open, and deployment remains deferred until
after product proof.

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

GF-12A2 human-review protocol/tooling is VERIFIED and R18 has prepared an explicitly authorized blinded real candidate-edge package. Its state is `HUMAN_REVIEW_DATASET_PREPARED` / `HUMAN_LABEL_EXECUTION_PENDING`; human labels and metrics remain absent, so no human-quality signoff is claimed.

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
real-target end-to-end demonstration is BLOCKED. GF-12C1-R2 subsequently verifies
the real 5,327-row character channel: three zero vectors now return the legitimate
empty neighbor subset instead of failing an impossible full-K condition, with no
fabricated candidates or large-N exact fallback. The full real scan crossed that
stage but remained nonterminal beyond 900 seconds, so real-target end-to-end
product readiness remains BLOCKED by a separate downstream runtime condition. See
`docs/GF12_REAL_CSV_INGESTION_REGRESSION.md` and
`docs/GF12_REAL_DATA_CHARACTER_RETRIEVAL_CORRECTION.md`. GF-12C1-R3 localizes
that condition to GF5 bounded candidate-group generation for dense eligible
work units: DISCOVERY and GF4 complete, an 18-record/130-edge unit remains in
candidate generation beyond the bounded diagnostic window, and GF6 is not
reached. No production optimization or semantic change was made; the authorized
next category is `NEXT_GF5_REAL_DATA_WORK_UNIT_CORRECTION`. See
`docs/GF12_REAL_DATA_DOWNSTREAM_RUNTIME_LOCALIZATION.md`.

GF-12C1-R4 corrects that proven GF5 blocker without changing any resolver
threshold, evidence rule, cannot-link guarantee, group-size limit, ordering
rule, or safety cap. GF5 now enforces its existing 16,400-attempt exhaustive
generation budget before constructing candidates that the exhausted path must
discard. The unchanged 5,327-row target completes authoritatively through GF6
with `visible_product_ready=true`, 214 review groups, 12 conflicts, 22 deferred
units, 4,879 unassigned records, and zero provider calls. This verifies the
real target's current end-to-end group-first execution path; it does not verify
human accuracy, deployment readiness, GF-11 graduation, or GF-12 completion.
See `docs/GF12_GF5_DENSE_REAL_WORK_UNIT_CORRECTION.md`.

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

## GF-12C1-R9 discriminator coverage status

GF-12C1-R9 is `R9_QUALITY_CORRECTION_PARTIAL_NEW_BLOCKER`. The bounded
`identity-discriminator-v2` corrects all four R8 false groups through reusable
wheel/rim aliasing, explicit physical-component classes, explicit commercial
construct classes, and two-sided part-number contradiction provenance. Fresh
current-product scan 30 completed with G2-v2 authority, 196 groups, 414 grouped
members, 113 likely, 83 review, 30 conflicts, 31 deferred units, 4,913
unassigned records, and zero provider calls. All current protected endpoints
remain outside accepted groups and CSV/XLSX parity is exact.

The repeated 45-group audit found one distinct next blocker: left-side versus
right-side shock abbreviations under a copied description. R9 does not broaden
its ontology to cover that separate variant family. The real output is not
freeze-ready. GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`; GF-11 remains
`IN PROGRESS` under its `ACTIVE` waiver, `GF11-PERF-100K-COLD-FULL` remains
`OPEN`, and the 300-second target remains unmet. Deployment and integration
remain deferred.

## Pair-path migration status

Current: pair machinery remains operational compatibility infrastructure and internal evidence.

Target: pair machinery ceases to be the business-domain center.

The non-destructive migration order is to hide normal pair prominence, introduce independent discovery and evidence, graduate the new resolver through controlled shadow validation, stop new pair feedback and pair LLM writes, stop `DuplicateCandidate` business writes only after consumers migrate, and retain historical read-only diagnostics. Pair tables, APIs, and historical records are not removed in GF-0.

## GF-12C1-R6 current interactive authority and export status

GF-12C1-R6 verifies the ordinary interactive New Scan authority and Excel
compatibility boundary. The browser now selects the allowlisted current product,
which persists policy-v2, group-first-primary, and G2-v2 without changing
explicit legacy compatibility or historical G2-v1 interpretation. The Group
Data Excel Table now owns its single AutoFilter, eliminating the package
conflict that Microsoft Excel repaired. Fresh real scan 27 completes with zero
provider calls and exact G2-v2 API/CSV/XLSX parity. Its read-only quality gate is
`Q2_DEMO_QUALITY_NEEDS_BOUNDED_CORRECTION` for tyre subtype, wheel-versus-tyre,
and dirty carbon-stick-versus-pencil review-group patterns. No detector change
is part of R6; the real output is not frozen as the demo candidate. GF-12A2 and
GF-11 performance debt remain open.

## GF-12C1-R7 deterministic real-identity quality status

GF-12C1-R7 is verified. The GF4 evidence seam now emits protected, auditable
cannot-links for explicit incompatible object classes, mutually exclusive tyre
variants, and the proven dirty-description composite. The existing GF5 resolver
and G2-v2 projection consume those edges without threshold, cap, group-size,
status, review, or export changes. Fresh real scan 29 removes the C5/C6/C7 false
groups, preserves the F30/B38 controls, contains zero surviving groups with the
new contradiction, makes zero provider calls, and has exact API/CSV/XLSX parity.
The result is `Q1_DEMO_QUALITY_PLAUSIBLE`; product-owner workbook inspection and
GF-12A2 human-review validation remain required. GF-11 and its active waiver,
open 100k cold-full debt, and unmet 300-second target remain unchanged.

## GF-12C1-R10 directional-side status

GF-12C1-R10's bounded directional implementation is `VERIFIED`. The bounded
directional qualifier correctly promotes explicit LEFT-versus-RIGHT variants
with a shared side-free component base through GF4. Fresh current-product scan
31 safely separates the R9 shock pair, contains zero protected contradictions
inside accepted groups, preserves all R7/R9 controls, makes zero provider
calls, and has exact 203-group/429-member CSV/XLSX parity.

The required 47-group semantic audit nevertheless finds one new distinct false
group: BUFFER01 versus MIRROR01 under a copied description. It is not a
directional-side family and was not changed in R10. The overall demo-freeze
gate remains closed, while R10A authorizes committing the verified directional
implementation. GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`; GF-11 remains
`IN PROGRESS` under its `ACTIVE` waiver, the cold-full debt remains `OPEN`, the
300-second target remains unmet, and deployment/integration remains deferred.

## GF-12C1-R11 buffer/mirror object-identity status

GF-12C1-R11 is `R11_QUALITY_PASS_READY_FOR_FINAL_FREEZE`. Bounded reusable
`buffer` and `mirror` object classes plus one explicit incompatibility relation
now promote trusted two-sided part-number evidence through GF4. Fresh
current-product scan 2 safely separates the reported LG pair and independently
finds the same CS buffer/mirror family. No accepted group contains a cannot-link
or discriminator contradiction, provider calls remain zero, and exact G2-v2
CSV/XLSX parity holds for 201 groups and 423 members.

The repeated 46-group semantic audit is A=4, B=13, C=28, D=0, E=1. This is a
bounded detector-quality pass, not human accuracy certification. GF-12A2 stays
`HUMAN_REVIEW_DATASET_REQUIRED`; GF-11 stays `IN PROGRESS` under its `ACTIVE`
waiver, `GF11-PERF-100K-COLD-FULL` stays `OPEN`, the 300-second target remains
unmet, and deployment/integration remains deferred.

## GF-12C1-R12 final freeze-only audit status

GF-12C1-R12 is `DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`. The one permitted fresh
browser-equivalent real run completed on the unchanged R11 detector baseline
with current-product G2-v2 authority, visible readiness, exact API/CSV/XLSX
parity, valid XLSX packaging, zero provider calls, and zero internal persisted
cannot-link or bounded discriminator contradictions. Its deterministic
all-group risk screen required inspection of 204 groups.

The offline audit found four likely false groups: brush/paint, Model S/Model X,
wood/steel-frame, and coil-spring/staplers under copied or dirty descriptions.
No detector semantic was changed and the demo candidate is not frozen. This
repeated appearance of obvious unrelated identity nouns outside successive
bounded vocabularies is `ARCHITECTURE_PATCHING_RISK_REMAINS_HIGH`; further
noun-specific expansion is not authorized by this status update. GF-12A2 and
GF-11 performance debt remain open, and deployment/integration remains
deferred.

## GF-12C1-R13 identity-evidence architecture status

GF-12C1-R13 is `ARCHITECTURE_REASSESSMENT_COMPLETE_DETECTOR_UNFROZEN`.
Read-only reconstruction confirms that R12's four D groups are consequences of
broad lexical positive support crossing a narrower, ontology-dependent negative
evidence boundary. The selected target is
`R13-E_COMBINE_SIGNATURE_AND_SUPPORT_GATE`, with ontology
`ONTOLOGY_SUPPORTING`: source-aware per-record identity signatures feed signed
GF4 evidence, while unknown identity remains unknown and cannot-link remains
reserved for protected contradictions. R13 changes no production detector
semantic. The smallest authorized next unit is pure seam/contracts and golden
cases without runtime integration. GF-11 remains `IN PROGRESS`, its waiver is
`ACTIVE`, `GF11-PERF-100K-COLD-FULL` is `OPEN`, the 300-second target remains
unmet, GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`, and deployment and
integration remain deferred.

## GF-12C1-R14 identity-signature contract seam status

GF-12C1-R14 adds only unused, immutable, versioned `IdentitySignature` and
`SignedIdentityEvidence` contracts plus golden representation cases. There is
no extractor, runtime import, GF4 integration, scoring/gate change, persistence,
or detector semantic change. Unknown and unresolved evidence remain distinct
from explicit contradiction; signed evidence channels remain independent. The
detector is still unfrozen and R12 remains `DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`.
GF-11 remains `IN PROGRESS` under its `ACTIVE` waiver,
`GF11-PERF-100K-COLD-FULL` remains `OPEN`, the 300-second target remains unmet,
GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`, and deployment/integration
remain deferred.

## GF-12C1-R15 deterministic signature derivation status

GF-12C1-R15 adds an unused pure `record -> IdentitySignature` deriver and a
read-only audit harness. It reuses existing bounded recognizers and preserves
unknown, unresolved, generic/copied, and multi-source evidence without creating
pair support or contradiction. All 5,327 protected CSV rows derive in memory
with zero failures and zero provider calls. There is no GF4/GF5 integration,
persistence, scan-path import, or detector semantic change. The detector remains
unfrozen and R12 remains `DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`. GF-11 remains
`IN PROGRESS` under its `ACTIVE` waiver, `GF11-PERF-100K-COLD-FULL` remains
`OPEN`, the 300-second target remains unmet, GF-12A2 remains
`HUMAN_REVIEW_DATASET_REQUIRED`, and deployment/integration remain deferred.

## GF-12C1-R16 signed identity evidence shadow status

GF-12C1-R16 is `R16_SIGNED_EVIDENCE_VERIFIED_BUT_GATE_NOT_READY`. Pure,
non-authoritative pairwise signed evidence keeps identity, attribute, lexical,
and contradiction channels distinct. Protected historical families retain
explicit contradictions, while the four R12 false groups remain lexical or
unresolved without misleading identity support. A read-only audit of all 252
complete-pair edges in the 205 accepted R12 groups classified 240 as lexical
only and 12 as trusted identity. Seven named legitimate controls remain
lexical-only risks, so no GF4 gate or runtime integration is authorized. The
detector remains unfrozen and R12 remains `DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`.
GF-11 remains `IN PROGRESS` under its `ACTIVE` waiver,
`GF11-PERF-100K-COLD-FULL` remains `OPEN`, the 300-second target remains unmet,
GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`, and deployment/integration
remain deferred.

## GF-12C1-R17 trusted identity coverage study status

GF-12C1-R17 is `R17-G_NO_SAFE_GENERALIZATION_PROVEN`. Exact reconstruction of
the seven R16 lexical-only controls shows three missing phrase/abbreviation
representations and four existing structured facts without a proven safe trust
composition. Six offline strategies were evaluated against exact controls and
all 252 accepted R12 edges. The only combined strategy covering all seven and
avoiding the four named R12 pairs still produced 12 unsafe numeric-variant
promotions. No production representation, comparator, GF4, or detector change
is authorized. Human-labelled identity evidence is required before semantic
expansion. The detector remains unfrozen, R12 remains
`DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`, and the R16 gate remains not ready.
GF-11 remains `IN PROGRESS` under its `ACTIVE` waiver,
`GF11-PERF-100K-COLD-FULL` remains `OPEN`, the 300-second target remains unmet,
GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`, and deployment/integration
remain deferred.

## GF-12A2-R18 blinded human identity-label dataset status

R18 is `R18_HUMAN_REVIEW_DATASET_PREPARED`. Explicit task authorization and
the persisted scan-31 GF2/GF4 population support a deterministic 20-pair
diagnostic panel and 300-pair evaluation panel without a fresh scan or
accepted-edge-only selection. Separate blinded Reviewer A/B workbooks, a
private mapping, empty adjudication template, and manifest were generated in
an ignored local artifact path. Human labels completed are 0. GF-12A2 is now
`HUMAN_REVIEW_DATASET_PREPARED` / `HUMAN_LABEL_EXECUTION_PENDING`, not VERIFIED,
COMPLETE, or ground truth. No production semantic or authority changed. The
detector, R12, R16, R17, GF-11, performance waiver/debt, and deployment states
remain unchanged.
