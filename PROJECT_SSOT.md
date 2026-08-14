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
