# Group-first identity domain and persistence contracts

## Purpose

This document defines implementation-neutral contracts for group-first inventory identity discovery. It accompanies `GROUP_FIRST_IDENTITY_ARCHITECTURE_ADR.md` and does not change the current database or runtime.

Contract names may later be adapted to repository naming conventions, but their semantics and invariants require an explicit architecture change to alter.

## Contract conventions

### Identity and ordering

- Every record and relationship is scoped to one scan.
- Every persisted artifact has an opaque database identity and a stable deterministic key.
- Stable keys are SHA-256 fingerprints over canonical, versioned payloads.
- Member collections and edge endpoints have canonical ordering.
- Edge keys always order `left_record_ref_key < right_record_ref_key`.
- Processing iteration order cannot affect discovery, resolution, grouping, partitioning, or export ordering. An original source-row ordinal is part of the declared input identity when the source provides no durable row key, so physically reordering that source creates a new canonical input snapshot rather than silently reidentifying duplicate rows.
- Contract, algorithm, normalization, evidence, and configuration versions are recorded rather than inferred.

### Boundedness

- Strings, arrays, JSON objects, evidence lists, and reason lists have explicit bounds.
- Caps and truncation are persisted and visible.
- A cap never silently converts incomplete work into a likely group.
- Arbitrary complete source rows, complete CSVs, provider payloads, secrets, and headers are excluded.

### Authority

- Discovery provenance is not identity evidence.
- `CANNOT_LINK` is a protected co-membership veto.
- Human `MUST_LINK` cannot override a protected deterministic `CANNOT_LINK`.
- System groups are hypotheses.
- Current human review is final within the scan.
- Optional AI results are advisory only.

## Domain contracts

## InventoryRecord

An immutable canonical representation of one source row within one scan. It has no A/B orientation.

### Required fields

| Field | Semantics |
|---|---|
| `scan_record_id` | Opaque persisted identity |
| `scan_id` | Owning scan |
| `record_ref_key` | Stable scan-local record key |
| `source_row_reference` | Stable source row number/key; never inferred from part number alone |
| `source_record_fingerprint` | Fingerprint of the allowlisted canonical raw evidence |
| `part_no_raw` / `part_no_normalized` | Preserved source value and deterministic normalization |
| `description_raw` / `description_normalized` | Preserved source value and deterministic normalization |
| `site_contract_raw` / normalized context | Scope and display context only |
| `uom_raw` / normalized mapping value | Mapping context, not identity authority |
| category/product/HSN fields | Preserved raw and normalized identity/context values |
| `technical_attributes` | Bounded, versioned extracted attributes with raw evidence spans/tokens where safe |
| `identity_evidence` | Bounded normalized tokens/families used by discovery and resolution |
| `missingness_flags` | Explicit missing/unknown canonical fields |
| `normalization_version` | Version used to create normalized evidence |
| `created_at` | UTC persistence time |

`record_ref_key` includes scan identity and source-row identity. A durable source key is preferred; otherwise the original row ordinal is retained. Two byte-identical rows remain two source records rather than collapsing into an ambiguous identity. Raw-value traceability is limited to approved canonical fields and bounded technical evidence; unknown complete row dictionaries are not persisted by default.

### Invariants

- Unique `(scan_id, source_row_reference)`.
- Unique `(scan_id, record_ref_key)`.
- Raw canonical values are never overwritten by normalization.
- Missing values never become matching evidence.
- Site, contract, UOM, and accounting values are typed separately from physical-identity evidence.

## IdentityDiscoveryRun

One versioned, resumable candidate-discovery execution for a scan.

### Required fields

- `discovery_run_id`, `scan_id`, deterministic `discovery_fingerprint`;
- algorithm and configuration versions;
- normalization/record-snapshot version;
- status: `QUEUED`, `RUNNING`, `COMPLETED`, `COMPLETED_DEGRADED`, `FAILED`;
- start, update, and completion timestamps;
- record counts: total, eligible, covered, reciprocal-covered, no-neighbor;
- proposal counts before/after channel and global caps;
- neighborhood counts, truncated/deferred generic families;
- per-channel success/failure and safe error categories;
- partition/checkpoint progress;
- declared minimum discovery policy and whether it was satisfied;
- provider request count fixed to zero.

### Invariants

- The run does not assign duplicate identity.
- Identical canonical records, versions, and configuration produce the same fingerprint.
- `COMPLETED_DEGRADED` names every degraded channel and affected coverage.
- A failed required channel cannot be represented as ordinary completion.

## NeighborProposal

A bounded discovery-only relationship emitted by one or more channels before evidence evaluation.

### Required fields

- discovery run and ordered record refs;
- contributing channels and per-channel ranks/scores;
- reciprocal channels;
- blocking/scope context;
- discovery priority and deterministic tie-break key;
- generic/family and truncation flags;
- mapping/UOM context;
- proposal version.

The score is retrieval priority only. It is never duplicate confidence or business status.

## IdentityNeighborhood

A bounded, potentially overlapping discovery hypothesis. It carries no duplicate conclusion.

### Required fields

| Field | Semantics |
|---|---|
| `neighborhood_id` / `neighborhood_key` | Opaque and deterministic identities |
| `discovery_run_id` / `scan_id` | Ownership |
| `anchor_record_ref_keys` | One or more canonical anchors |
| `member_record_ref_keys` | Canonically ordered bounded members |
| `retrieval_channels` | Union and per-member channel provenance |
| `coverage` | Anchor/member/channel coverage summary |
| `member_count` | Persisted membership count |
| `proposal_count` | Supporting neighbor proposals |
| `truncated` / `degraded` | Explicit completeness state |
| `cap_reason_codes` | Which bound affected it |
| `discovery_rank_metadata` | Bounded rank/priority summaries |
| `generic_family` | Whether generic suppression/deferral applies |

### Invariants

- Neighborhoods may overlap.
- A member appears at most once in one neighborhood.
- No neighborhood status contains “duplicate,” “likely,” or a business decision.
- Truncated or degraded state is never omitted from downstream fingerprints.

## IdentityEvidenceEdge

A signed internal relationship between two inventory records. It exists independently of a final group.

### Edge classes

- `STRONG_SUPPORT`
- `REVIEW_SUPPORT`
- `CANNOT_LINK`
- `NON_GROUPABLE`

Human constraints are represented as provenance-bearing evidence:

- `HUMAN_MUST_LINK`
- `HUMAN_CANNOT_LINK`

The resolved effective class applies precedence and safety rules. Human must-link is not a fifth way to bypass deterministic conflict.

### Required fields

- `evidence_edge_id`, `scan_id`, optional discovery/resolution run;
- ordered left/right record refs;
- resolved edge class;
- source kind: deterministic scorer, attribute conflict index, human constraint, imported legacy candidate, imported exclusion, or targeted evaluation;
- source artifact ID when available;
- deterministic engine/evaluator version;
- reason codes and critical mismatch evidence;
- component scores and pair status only as internal diagnostics;
- evaluation context, including scan scope and UOM handling mode;
- evaluated/completed state and safe failure category;
- evidence fingerprint and timestamp;
- optional legacy candidate/exclusion reference.

### Invariants

- Self-edges are prohibited.
- Identical evidence identities are idempotent.
- Discovery channel agreement cannot directly create `STRONG_SUPPORT` without evaluation.
- Any protected affirmative identity contradiction produces `CANNOT_LINK`.
- UOM/site/accounting differences alone cannot produce physical-identity `CANNOT_LINK`.
- Raw provider output and advisory results are never edge authority.

## IdentityResolutionRun

One deterministic group-resolution execution over a selected discovery run and evidence manifest.

### Required fields

- `resolution_run_id`, `scan_id`, `discovery_run_id`;
- resolver, edge-evaluator, attribute-rule, and configuration versions;
- evidence fingerprint and resolution fingerprint;
- status: `QUEUED`, `RUNNING`, `COMPLETED`, `COMPLETED_WITH_DEFERRED`, `FAILED`;
- work-unit and checkpoint counters;
- input neighborhood, record, and edge counts;
- evaluated/targeted edge counts;
- likely/review/conflict/deferred/unassigned counts;
- safe errors, timestamps, and runtime/resource metrics;
- shadow/visible purpose flag.

### Invariants

- One visible G2 projection references at most one completed resolution run.
- A shadow run cannot become current through ordinary result selection.
- Provider request count is zero.
- Failure cannot publish a partial accepted G2 projection.

## IdentityGroupHypothesis

A persisted pre-G2 checkpoint of a bounded resolver work item and its lifecycle. Persisting this contract is recommended in the first implementation because the 100k target requires resumability, shadow comparison, and inspectable deferred work.

Only checkpointed hypotheses are persisted; internal partition-search states are not.

### Lifecycle

- `PROPOSED`
- `VALIDATING`
- `LIKELY`
- `REVIEW`
- `CONFLICT`
- `DEFERRED`
- `SPLIT`

`SPLIT` records that the parent hypothesis produced child hypotheses or safe final groups. It is not itself an accepted group.

### Required fields

- hypothesis ID/key, resolution run, parent hypothesis when split;
- canonical member refs;
- lifecycle state and reason codes;
- originating neighborhood keys;
- validation mode and coverage;
- bridge-risk and attribute-consensus summaries;
- selected partition summary and alternative/tie indicator;
- state transition timestamps;
- hypothesis fingerprint.

### Invariants

- State transitions are append-only or auditable.
- A final likely/review hypothesis has complete required safety checks.
- Conflict/deferred hypotheses cannot enter the accepted-group adapter.
- A record can occur in overlapping proposed hypotheses but not in two final accepted hypotheses in one resolution run.

## GroupEvidenceSummary

A typed group-level evidence contract independent of pair-score averaging.

### Required fields

- member count;
- possible, evaluated, strong, review, neutral, and cannot-link relationship counts;
- `COMPLETE_PAIRWISE` or `PROGRESSIVE_TARGETED` validation mode;
- required conflict checks total/completed;
- support and strong-support density as descriptive ratios;
- discovery member/channel coverage;
- attribute consensus rows;
- technical-conflict count;
- description and part-family coherence categories;
- site spread;
- UOM and mapping-quality summaries;
- bridge-risk indicators;
- missing-data burden;
- truncation/degradation flags;
- alternative-partition ambiguity;
- bounded group reason codes.

Ratios describe evidence shape; they are not a calibrated confidence score.

## DuplicateIdentityGroup

A resolved system hypothesis that a disjoint member set represents one physical item.

### Required fields

- stable group/hypothesis key;
- scan, discovery run, resolution run, and G2 projection identities;
- canonical member set;
- status: `LIKELY_DUPLICATE_GROUP` or `POSSIBLE_DUPLICATE_GROUP_REVIEW`;
- `GroupEvidenceSummary`;
- conflict summary with zero protected internal cannot-links;
- evidence and resolution fingerprints;
- algorithm/contract versions;
- immutable creation time.

### Invariants

- Minimum two members.
- Accepted groups are pairwise disjoint within one projection.
- Zero protected cannot-links inside the group.
- All required safety checks are complete.
- A likely group has no unresolved bridge, ownership ambiguity, or disqualifying degradation.
- It remains a system hypothesis until reviewed.

## IdentityConflict

A first-class explanation of why a discovered family cannot safely be accepted as one identity.

### Conflict categories

- `PROTECTED_CANNOT_LINK`
- `TECHNICAL_VARIANT_CONTRADICTION`
- `BRIDGE_CHAINING_CONFLICT`
- `OVERSIZED_UNRESOLVED_NEIGHBORHOOD`
- `AMBIGUOUS_RECORD_OWNERSHIP`
- `INSUFFICIENT_REQUIRED_EVIDENCE`
- `GENERIC_FAMILY_DEFERRED`
- `PARTITION_TIE`
- `DISCOVERY_DEGRADED`

### Required fields

- conflict ID/key and owning resolution/G2 diagnostic run;
- complete affected member refs or a bounded externalized membership page;
- category and reason codes;
- protected conflicting evidence refs;
- originating neighborhoods/hypotheses;
- safe subgroup refs when salvaged;
- coverage, truncation, and bridge summaries;
- algorithm version and fingerprint.

A conflict is not a rejected pair and not an accepted duplicate group.

## GroupReviewDecision

G6 semantics are retained with business labels mapped to current internal values:

| Business meaning | Current contract |
|---|---|
| Confirm complete group | `CONFIRM_ALL_AS_ONE` |
| Confirm selected subset | `CONFIRM_SELECTED` |
| Split into identity sets | `SPLIT_PARTITIONS` |
| Keep every member separate | `KEEP_ALL_SEPARATE` |
| Unsure | `UNSURE` |

Reviews reference the exact immutable G2 group, projection, hypothesis key, and canonical membership. Corrections supersede rather than update prior events.

## ReviewedIdentitySet

A human-authoritative, scan-local identity set derived from the current effective review.

### Required fields

- deterministic reviewed-set key;
- scan, projection, group, and current review identities;
- canonical member refs;
- decision/partition index and member count;
- reviewer and review timestamp;
- derivation fingerprint;
- operational-authority flag;
- future registry-link field reserved but null.

### Invariants

- Every set has a current affirmative human decision.
- A record belongs to at most one reviewed identity set in the scan.
- `UNSURE`, not reviewed, and unselected members do not produce an operational set.
- Singleton partitions from `KEEP_ALL_SEPARATE` record reviewed separation but are not exported as duplicate identity groups; their audit state remains available.
- Sets remain scan-local and do not select a canonical enterprise item.

## Additive pre-G2 persistence model

The names below are conceptual SQLAlchemy table names. Existing tables remain untouched until a later migration phase.

| Table | Purpose | Key constraints/indexes |
|---|---|---|
| `scan_record_snapshot` | Move/create canonical record snapshots before discovery | unique scan/source row and scan/ref key; indexes on scan and normalized blocking fields |
| `identity_discovery_run` | Versioned discovery execution and coverage | unique scan/version/fingerprint; status and scan indexes |
| `identity_neighbor_proposal` | Optional normalized channel proposal audit | unique run/ordered pair; endpoint and channel indexes; may be compacted by retention policy |
| `identity_neighborhood_snapshot` | Bounded overlapping discovery unit | unique run/neighborhood key; status/truncation indexes |
| `identity_neighborhood_member` | Canonical membership/provenance | unique neighborhood/record; record and rank indexes |
| `identity_evidence_edge_snapshot` | Independent signed evidence before G2 | unique evidence identity; scan/ordered endpoints/class indexes; optional legacy FKs |
| `identity_resolution_run` | Resumable resolver execution | unique discovery/version/evidence fingerprint; purpose/status indexes |
| `identity_group_hypothesis_snapshot` | Checkpointed lifecycle and shadow inspection | unique resolution/hypothesis key; parent/state indexes |
| `identity_group_hypothesis_member` | Hypothesis membership | unique hypothesis/record; record index |
| `identity_shadow_comparison_run` | Non-visible old/new comparison metrics | scan and created-at indexes; cannot select current G2 |

For storage control, raw per-channel proposal persistence may be configurable after metrics are aggregated, but the final neighborhood membership and every evidence edge used by a resolution must remain auditable.

## G2 adapter contract

```text
Completed IdentityResolutionRun
  + final likely/review hypotheses
  + conflicts/deferred families
  + canonical records
  + independent evidence edges
      -> versioned G2 projection snapshot
```

### Preserved G2 properties

- Immutable `IdentityGroupProjectionRun`.
- Deterministic evidence fingerprint and idempotency.
- Accepted groups, ordered members, diagnostics, and evidence edges.
- One atomic persistence transaction.
- No recomputation on G3/G5 reads.
- Historical v1 snapshots remain readable.

### Additive extensions

- `snapshot_contract_version` on projection runs, defaulting historical rows to v1.
- Optional discovery and resolution run references.
- Resolver/configuration fingerprints.
- One-to-one typed validation/evidence summary for each accepted group.
- Typed conflict/coverage summary for each diagnostic.
- Optional source independent-evidence-edge reference on copied G2 edges.
- Evidence-source vocabulary extended with resolution/attribute/human-constraint provenance.
- Run-level grouped, unassigned, deferred, truncated, and coverage counts.

### Validation semantics

For v1 `constrained-group-projection-v1`, existing invariants remain unchanged: accepted groups are bounded to 20 and persist every N-choose-2 relationship.

For a future v2 group-first snapshot:

- `possible_relationship_count` is N-choose-2.
- `evaluated_relationship_count` is the number of materialized relationship evaluations.
- `validation_mode` declares complete pairwise or progressive targeted evidence.
- `required_conflict_checks_complete` must be true for every accepted group.
- Every materialized edge is persisted or referenced.
- Progressive groups need not materialize every neutral pair, but must persist the support backbone, all protected conflicts considered, every targeted bridge/outlier check, and the group-level coverage manifest.
- Existing v1 count fields retain their old interpretation for v1 rows. V2 readers use the new validation summary and do not infer completeness from legacy counts.

This is explicit contract versioning, not silent reinterpretation.

## API contracts

### Summary

Extend the existing identity-group summary with:

- records scanned and eligible;
- discovery-covered and no-neighbor records;
- grouped records and accepted groups;
- likely/review/conflict/deferred counts;
- unassigned records by bounded reason;
- truncated/generic-family counts;
- discovery/resolution/G2 versions and degradation state.

### Lists

Group and conflict lists provide stable cursor pagination using deterministic `(status_order, size, stable_key)` ordering. Supported filters include projection/resolution run, status, review state, minimum/maximum size, validation mode, conflict category, and degraded/truncated state. `limit` is bounded to an implementation-defined maximum no greater than the response contract allows.

Offset pagination remains a temporary compatibility option. It is not the 100k target contract.

### Detail and evidence

Group detail returns bounded members, the group evidence summary, review state, and evidence-page metadata. If membership or relationship evidence exceeds the detail bound, members/evidence use cursor-paginated subresources. No endpoint returns an unbounded neighborhood, candidate list, or full scan graph.

### Reviews

Review creation retains immutable context, optimistic concurrency, exact membership validation, and append-only history. The server enforces scan-wide reviewed-set exclusivity before committing the new current review.

## Export contracts

Every CSV applies formula-injection protection, stable ordering, UTC timestamps, explicit contract version, and no provider invocation.

### 1. System Group Export

One row per group member:

```text
export_contract_version
scan_id
projection_run_id
resolution_run_id
group_snapshot_id
group_hypothesis_key
group_status
group_size
member_index
record_ref_key
source_row_reference
part_no
description
site_or_contract
uom
product_category
hsn_sac
validation_mode
possible_relationship_count
evaluated_relationship_count
required_conflict_checks_complete
strong_support_density
support_density
neutral_edge_count
technical_conflict_count
bridge_risk_flags
attribute_consensus_summary
retrieval_coverage
missing_data_burden
discovery_degraded
group_reason_codes
human_review_state
```

### 2. Reviewed Identity Export

Operational mode contains only members of current human-confirmed identity sets:

```text
export_contract_version
scan_id
projection_run_id
group_snapshot_id
review_event_id
reviewed_identity_set_key
reviewed_identity_set_index
reviewed_identity_set_size
member_index
record_ref_key
source_row_reference
part_no
description
site_or_contract
uom
product_category
hsn_sac
review_decision_type
reviewer
reviewed_at
review_comment
operational_authority
```

The current complete-audit reviewed export may remain as a compatibility mode containing `NOT_REVIEWED`, `UNSURE`, and unresolved members. The normal operational UI must request the confirmed-only mode after its versioned introduction.

### 3. Conflict/Deferred Export

One row per affected member:

```text
export_contract_version
scan_id
projection_run_id
resolution_run_id
conflict_id
conflict_key
conflict_category
member_count
member_index
record_ref_key
source_row_reference
part_no
description
site_or_contract
uom
reason_codes
bridge_risk_flags
required_checks_complete
truncated
degraded
safe_subgroup_keys
```

### 4. Advanced Pair Evidence Export

Analyst/audit only:

```text
export_contract_version
scan_id
discovery_run_id
resolution_run_id
evidence_edge_id
left_record_ref_key
right_record_ref_key
edge_class
source_kind
reason_codes
deterministic_engine_version
evaluation_context
component_score_summary
critical_mismatch_summary
legacy_candidate_id
legacy_exclusion_id
evaluated_at
```

The pair evidence export does not contain Part A/Part B business decisions or invite pair-by-pair operational review.

## Compatibility and deprecation flags

During migration, every scan records:

- visible result engine: legacy or group-first;
- whether shadow comparison ran;
- whether legacy candidates were written;
- whether independent evidence was written;
- pair API compatibility version;
- snapshot contract version.

Historical data is never rewritten merely to populate new contracts. Missing new fields on historical scans are returned as explicitly unavailable, not fabricated.

## Security and privacy

- No API key, header, token, prompt, raw provider response, or exception text enters these contracts.
- Canonical raw-value storage is allowlisted and bounded.
- Unknown source columns and complete source rows are not persisted by default.
- Diagnostic reason codes are bounded and safe.
- Cross-client/tenant joins are prohibited by scan and tenant scope.
- Export escaping and authorization are mandatory production concerns.

## Contract-level acceptance tests

- Identical rows at different source positions receive distinct record refs.
- Discovery neighborhoods overlap without creating accepted overlap.
- No-neighbor records are represented successfully.
- Discovery truncation changes the fingerprint and blocks unsupported likely status.
- Cannot-link-aware union never co-locates a protected conflict.
- Bridge fixtures produce conflict/review/deferred outcomes exactly as specified by the ADR.
- Accepted groups are disjoint and deterministic under input permutation.
- Progressive groups persist every required support/conflict/targeted check and coverage summary.
- G2 v1 snapshots retain existing byte/response behavior.
- G2 v2 selection never changes the selected v1 result unless explicitly promoted.
- Current group review cannot create overlapping reviewed sets.
- Operational reviewed export contains confirmed sets only.
- All ordinary contract tests make zero external provider calls.
