# ADR: Group-first inventory identity discovery

## Status

Approved target architecture for implementation planning. No production behavior is changed by this document.

## Decision

The previous pair-first MVP architecture is retained as internal evidence/compatibility infrastructure during migration, but duplicate identity groups are now the primary business/domain result.

The target product answers one question: which sets of inventory-master records may represent the same physical inventory item? A pair is an internal relationship used for discovery, evidence, safety, and diagnostics. It is not the normal business result, review unit, export unit, or AI reasoning unit.

This ADR supersedes the pair-centered target architecture in `MVP_LLM_DEMO_SSOT.md` for new group-first design work. That file remains historical MVP context and is not modified here. `docs/IDENTITY_GROUP_SNAPSHOTS.md` remains authoritative for the behavior of the currently implemented G0-G7 layers until a later implementation phase changes and versions those contracts.

`PROJECT_SSOT.md` is the product-requirements authority. This ADR is the architecture authority, `GROUP_FIRST_DOMAIN_CONTRACTS.md` defines target domain contracts, and `GROUP_FIRST_MIGRATION_ROADMAP.md` defines phase order. `CURRENT_PROJECT_ASSESSMENT.md` and `CHATGPT_ARCHITECT_WORKFLOW.md` are descriptive and procedural respectively and cannot override those authorities.

## Context

The implemented system is transitional:

```text
current computation
    pair discovery -> pair scoring/rules -> pair persistence -> edge projection

current product surface
    group summary -> 2..N groups -> group review -> member-shaped exports
```

G0-G2 added safe group projection over pair evidence. G3-G6 made groups real API, UI, export, and review objects. G7 added a provider-neutral whole-group advisory boundary. The remaining architectural problem is that normal discovery and identity decision are still organized around `DuplicateCandidate`.

## Product decisions

1. Physical identity may cross site or contract. Site/contract is scope and business context, never proof of same or different physical identity.
2. A user may explicitly restrict the records in scope to selected sites/contracts.
3. Discovery neighborhoods may overlap.
4. Accepted system groups in one projection are disjoint.
5. A source record belongs to at most one reviewed identity set in one scan.
6. System groups are hypotheses. The system group export is analytical.
7. Only human-confirmed reviewed identity sets are operationally authoritative.
8. Reviewed identity remains scan-local. A cross-scan enterprise identity registry is deferred.
9. The first serious production target is 100,000 records per scan. The design must have a credible extension seam for 1,000,000 or more.
10. There is no automatic merge, delete, source rewrite, IFS writeback, or provider authority.

## Goals

- Make 2..N identity groups the primary domain output.
- Separate high-recall discovery from safety-oriented identity resolution.
- Preserve signed evidence, cannot-link protection, auditability, and human authority.
- Salvage safe subgroups when a larger candidate family contains a bridge or conflict.
- Avoid global all-pairs work and full in-memory quadratic matrices.
- Keep G2-G7 usable through additive, versioned adapters.
- Migrate without deleting historical pair data or presenting two user-visible truths.

## Non-goals

- Selecting or benchmarking an AI provider.
- Creating a cross-scan identity registry.
- Automatically choosing a canonical master record.
- Merging inventory, deleting records, or writing to IFS.
- Treating a vector cluster or connected component as identity truth.
- Defining an uncalibrated numeric group-confidence score.

## Target system view

```text
CSV / future source adapter
          |
          v
Canonical immutable InventoryRecord snapshots
          |
          v
Identity discovery run
  exact-description / part-family / lexical / vector / technical channels
          |
          v
Bounded neighbor proposals and overlapping IdentityNeighborhoods
          |
          v
Evidence acquisition
  deterministic edge evaluator / attribute-conflict index / human constraints
          |
          v
Independent signed IdentityEvidenceEdges
          |
          v
Constrained group resolution
  consensus / bridge analysis / bounded partitioning / progressive validation
          |
          +--> disjoint likely groups
          +--> disjoint review groups
          +--> conflicts and deferred families
          +--> unassigned records
          |
          v
G2 immutable projection snapshot
          |
          +--> G3 typed group APIs
          +--> G4 group-first UI
          +--> G5 member-shaped exports
          +--> G6 append-only human review and reviewed sets
          +--> G7 optional one-group advisory
```

## Authority boundaries

| Layer | May do | Must not do |
|---|---|---|
| Canonicalization | Preserve raw canonical values and produce normalized evidence | Infer duplicate identity |
| Discovery | Propose bounded neighbors and neighborhoods with provenance | Assign duplicate status |
| Edge evaluation | Classify one relationship and expose deterministic evidence | Become the business result |
| Group resolver | Produce safe, disjoint system hypotheses and diagnostics | Override cannot-link or human authority |
| G2 snapshot | Persist an immutable scan-time result | Become permanent enterprise identity |
| Human review | Confirm, select, split, separate, or abstain | Override terminal deterministic conflicts |
| Optional AI | Advise on one eligible unresolved group | Discover candidates, merge records, or make final decisions |

## Discovery architecture

Discovery consumes canonical `InventoryRecord` snapshots and produces only neighbor proposals and overlapping neighborhoods. It optimizes recall subject to explicit budgets.

### Reused channels

- Exact normalized description.
- Part-number family.
- Lexical similarity.
- Character/vector similarity through an ANN-ready interface.
- Technical-identity keys.
- Explicit business-scope filtering.

Site, contract, UOM, accounting group, and other administrative values may filter an explicitly scoped run or supply context. They do not become positive physical-identity evidence merely because they match.

### Required budgets

Every discovery configuration is versioned and records:

- maximum neighbors per record per channel;
- maximum final neighbors per record;
- maximum proposals per channel partition;
- maximum members per persisted neighborhood;
- maximum neighborhoods or evidence proposals per scan partition;
- maximum expansion for one exact/generic family;
- reciprocal-neighbor policy;
- minimum channel-specific retrieval threshold;
- degradation behavior when a budget is exhausted.

Initial numeric values must be selected by offline benchmark rather than copied blindly from current pair caps.

### Reciprocal-neighbor policy

Reciprocal neighbors receive stronger discovery priority and provenance, but reciprocity is not identity evidence. Non-reciprocal proposals may be retained when a high-value deterministic channel or coverage rule justifies them.

### Coverage and degradation

The discovery run reports:

- records eligible for discovery;
- records with at least one proposal;
- records with reciprocal proposals;
- records with no neighbors;
- proposals before and after each cap;
- neighborhoods truncated or deferred;
- generic families suppressed or deferred;
- per-channel contribution and failure;
- partitions processed and remaining.

A record with no neighbors is a normal, successful discovery outcome. A channel failure can produce a degraded-but-usable discovery run only when required safety channels and the declared minimum discovery policy remain satisfied. Degradation is visible and fingerprinted.

### Generic and oversized families

Discovery must not expand a large generic family into all pairs. It records a deferred generic-family diagnostic and may retain a bounded, diversity-aware sample for investigation. A generic hub cannot join otherwise separate neighborhoods solely through common generic text.

## Evidence acquisition and pair compatibility seam

The compatibility seam is an internal `IdentityEdgeEvaluator`:

```text
InventoryRecord left + InventoryRecord right + evaluation context
    -> IdentityEvidenceEdge
```

The first implementation may adapt the current pair scorer, business rules, variant extractor, and `IdentityEdgeClass`. The adapter must not create a `DuplicateCandidate` merely to evaluate an edge.

Current pair fields move as follows:

| Current field group | Target role |
|---|---|
| Retrieval channels, rank, priority, reciprocal signals | Discovery metadata |
| Component scores, rule result, critical mismatches, normalized evidence | Internal edge evidence |
| `STRONG_SUPPORT`, `REVIEW_SUPPORT`, `CANNOT_LINK`, `NON_GROUPABLE` | Signed edge class |
| Pair confidence, pair business status, recommended action | Legacy compatibility/advanced diagnostics |
| Pair review state | Historical compatibility; G6 supersedes it for new review |
| Pair advisory snapshot | Historical compatibility; group advisory is the target AI path |

Human `MUST_LINK` is strong evidence only when compatible with every protected deterministic cannot-link. Human `CANNOT_LINK` is authoritative within its scan.

## Constrained group resolver

### Inputs

- One resolution run over one discovery run.
- Overlapping neighborhoods.
- Signed evidence edges.
- Group-wide technical attributes and missingness.
- Current effective G6 constraints when explicitly requested.
- Versioned resolution configuration and bounds.

### Outputs

- Disjoint `LIKELY_DUPLICATE_GROUP` hypotheses.
- Disjoint `POSSIBLE_DUPLICATE_GROUP_REVIEW` hypotheses.
- Conflict and deferred families.
- Unassigned records with reason categories.
- A complete evidence/coverage manifest and deterministic fingerprint.

### Practical incremental algorithm

1. **Normalize work units.** Combine overlapping neighborhoods only while a configured work-unit bound is respected. An over-bound union becomes an oversized/deferred work unit; it is never silently truncated into an accepted group.
2. **Build signed graphs.** Maintain separate support, cannot-link, and neutral graphs. Neutral/non-groupable edges never create connectivity.
3. **Index attribute conflicts.** Build per-work-unit indexes for explicit identity-defining values so contradictory values produce cannot-links without scanning unrelated global pairs.
4. **Create safe base cells.** Process human must-links and strong-support edges in canonical order with a cannot-link-aware union operation. A merge is allowed only when no known cannot-link crosses the two cells.
5. **Attach review evidence.** Review-support edges propose cell merges but do not force them. Competing attachments or overlapping ownership are marked ambiguous.
6. **Detect bridge risk.** Identify articulation records, bridge edges, low-redundancy branches, generic hubs, and support paths whose endpoints lack compatible evidence.
7. **Acquire targeted evidence.** Evaluate missing cross-branch pairs, attribute outliers, alternative attachment endpoints, and any pair needed to settle a protected constraint. Do not evaluate unrelated global pairs.
8. **Run bounded partition search.** For a small or still-ambiguous work unit, explore a capped set of partitions. Constraints are lexicographic: zero cannot-links inside a block; satisfy effective human constraints; maximize retained strong support; then review support; minimize neutral internal relationships and ambiguous ownership. A tie at the configured resolution margin is deferred rather than broken arbitrarily.
9. **Salvage stable subgroups.** Emit a subgroup only if its membership is stable across admissible best partitions, it is disjoint from already emitted groups, and its required checks are complete. Conflicting or ambiguous members remain diagnostic/unassigned.
10. **Classify.** Apply categorical group-state rules and persist the resolution manifest for the G2 adapter.

The resolver is deterministic for identical inputs, configuration, and versions. Ordering keys and tie behavior are part of the versioned contract.

### Validation modes

`COMPLETE_PAIRWISE` is used when the work unit is within the configured complete-validation bound. Every possible internal pair is classified.

`PROGRESSIVE_TARGETED` is used for larger work units. It requires:

- a connected support backbone for every proposed group;
- complete protected-attribute conflict checks;
- checks across each support-graph cut and bridge branch;
- checks for every attribute outlier;
- checks for competing neighborhood ownership;
- explicit coverage and truncation metadata;
- no unresolved required check for a likely classification.

Selected support edges establish a hypothesis, not proof. Targeted cross-branch checks protect against chaining. Attribute conflict indexes replace unnecessary repeated comparisons for explicit contradictory values. Bounded partition search is used only inside capped work units.

## Bridge and chaining safety

The resolver records these deterministic bridge-risk signals:

- `SUPPORT_ARTICULATION_RECORD`;
- `SINGLE_EDGE_BRANCH`;
- `GENERIC_HUB`;
- `CROSS_BRANCH_CANNOT_LINK`;
- `CROSS_BRANCH_NEUTRAL_ONLY`;
- `COMPETING_NEIGHBORHOOD_OWNERSHIP`;
- `LOW_SUPPORT_REDUNDANCY`;
- `TARGETED_CHECK_INCOMPLETE`.

For `A-B` support, `B-C` support, and `A-C` cannot-link, `{A,B,C}` is always prohibited. The resolver attempts `{A,B}` and `{B,C}` as alternative partitions. It emits only a stable, non-overlapping safe subgroup; otherwise the family is `CONFLICT` or `DEFERRED`.

For `A-B` support, `B-C` support, and `A-C` neutral, the family cannot be `LIKELY`. It may become a review group only when targeted checks are complete, no alternative partition is equally supported, and the group has sufficient non-bridge evidence. Otherwise it is split, conflict-diagnostic, or deferred.

Classification effects:

| Signal | Likely | Review | Conflict | Deferred |
|---|---:|---:|---:|---:|
| Protected cannot-link inside proposed block | prohibited | prohibited | required unless safe split removes it | possible if bounds prevent resolution |
| Unresolved articulation/generic hub | prohibited | possible only with completed targeted checks | possible | required when checks are incomplete |
| Neutral cross-branch relation | prohibited | possible | no, unless another conflict exists | possible on tied partitions |
| Incomplete required conflict check | prohibited | prohibited | not inferred | required |

## Group-level evidence model

Group classification uses an interpretable evidence summary, not an average pair score:

- member count;
- possible relationship count;
- evaluated relationship count and validation mode;
- required-check completion;
- support-edge and strong-support densities;
- neutral and cannot-link counts;
- attribute consensus by identity field;
- technical-conflict count;
- description coherence category;
- part-number-family coherence category;
- site spread;
- UOM relationship and mapping-quality summaries;
- discovery-channel and member-coverage summaries;
- bridge-risk indicators;
- missing-data burden;
- truncation/degradation flags;
- alternative-partition ambiguity.

Initial status remains categorical:

- `LIKELY_DUPLICATE_GROUP`: zero cannot-links, complete required checks, connected strong-support backbone, no unresolved bridge or ownership ambiguity, no material identity contradiction, and no disqualifying truncation.
- `POSSIBLE_DUPLICATE_GROUP_REVIEW`: zero cannot-links inside the proposed block, complete minimum safety checks, but review support, neutral gaps, missing data, or non-terminal ambiguity prevents likely status.
- `CONFLICT`: the original hypothesis contains protected incompatibility or mutually incompatible ownership; safe subgroups may be emitted separately.
- `DEFERRED`: bounds, missing required evidence, tied partitions, oversized work units, or degraded discovery prevent a safe decision.

No numeric group confidence is approved. A future calibrated score requires representative human-reviewed data, calibration analysis, and a separate ADR.

## Attribute consensus

Technical attributes are normalized into domain/versioned attribute observations. Each field declares one of four semantics:

- `IDENTITY_DEFINING`: incompatible affirmative values can create a cannot-link.
- `MAPPING_CONTEXT`: inconsistency is visible but cannot determine physical identity.
- `MISSING`: absence reduces coverage and never counts as agreement.
- `NON_AUTHORITATIVE`: a difference is explanatory only.

Initial identity-defining candidates include explicit incompatible voltage, power, capacity, diameter/size, side, grade/material, filter function, sensor type, connectivity, product category, HSN/SAC, and protected technical roles where the current deterministic rules already support the interpretation. Every attribute rule remains versioned and domain-tested; this list does not make every textual difference terminal.

UOM is always summarized separately as mapping context. Site/contract and accounting context never create identity support or cannot-link by themselves.

## Scan lifecycle

```text
UPLOAD / RECEIVED
  -> VALIDATING
  -> SNAPSHOTTING_RECORDS
  -> DISCOVERING
  -> ACQUIRING_EVIDENCE
  -> RESOLVING_GROUPS
  -> PERSISTING_G2
  -> COMPLETED | COMPLETED_WITH_DEFERRED
```

Required-stage failure states retain the failed stage and a safe category:

- Validation failure: no canonical record snapshot is declared complete.
- Record-snapshot failure: the discovery run does not start.
- Discovery failure: no resolution run starts; a resumable checkpoint may remain.
- Degraded optional channel: continue only when the versioned minimum discovery policy is satisfied and record degradation explicitly.
- Evidence/resolution failure: no G2 snapshot is published.
- G2 persistence failure: the complete G2 transaction rolls back and the scan is not group-ready.
- Optional AI failure: never changes scan or group readiness.

`COMPLETED` means a required G2 result exists, including a valid zero-group result. Deferred families produce `COMPLETED_WITH_DEFERRED`, not a false fully-resolved state. Stage progress records bounded counters, timestamps, retry/resume checkpoints, versions, and safe errors.

## Scalability boundaries

### 100,000-record target

- Persist canonical records in chunks; do not require the complete scan as one pandas object.
- Use bounded field blocks and lexical inverted retrieval.
- Provide an `IdentityVectorIndex` interface supporting build/upsert/query; the initial adapter may be local, but the contract must not require brute-force matrices.
- Bound neighbor proposals by record, channel, block, and scan partition.
- Defer generic families before pair expansion.
- Make evidence volume proportional to `records * configured_neighbors`, not global N-choose-2.
- Use attribute indexes to find contradictions.
- Resolve bounded work units with progressive validation.
- Execute stages through a resumable background-job seam.
- Use cursor-based server pagination and bounded detail/evidence pages.

### 1,000,000-plus extension seam

- Partition discovery by tenant/domain/site scope without making site identity authority.
- Use an external/distributed ANN implementation behind the same vector-index interface.
- Use durable work queues, sharded evidence partitions, and idempotent stage checkpoints.
- Store large analytical manifests in suitable object/columnar storage while retaining transactional result metadata.
- Support incremental index maintenance and changed-record resolution.
- Keep the G2 result adapter and human-review authority unchanged.

## G2-G7 compatibility decisions

| Layer | Decision | Target change |
|---|---|---|
| G2 | Keep with small, versioned extension | Resolver adapter, discovery/resolution provenance, progressive-validation summary |
| G3 | Keep with small extension | Group evidence/coverage fields, cursor pagination, unassigned/deferred counts |
| G4 | Keep with small extension | Group summary first; move relationship evidence and pair tools under Advanced |
| G5 | Keep with small extension | Add group coverage/consensus fields; keep member-shaped rows |
| G6 | Keep with small extension | Enforce scan-wide reviewed-set exclusivity and produce confirmed-only operational view |
| G7 | Keep with small extension | One eligible unresolved group remains one inference; progressive/oversized groups fail eligibility unless the bounded contract is satisfied |

The G2 adapter and persistence details are defined in `GROUP_FIRST_DOMAIN_CONTRACTS.md`.

## Primary API design

Existing group routes are retained instead of renamed for aesthetics:

- `GET /api/scans/{scan_id}/identity-groups/summary`
- `GET /api/scans/{scan_id}/identity-groups`
- `GET /api/scans/{scan_id}/identity-groups/{group_snapshot_id}`
- `GET /api/scans/{scan_id}/identity-group-diagnostics`
- `POST /api/scans/{scan_id}/identity-groups/{group_snapshot_id}/reviews`
- `GET /api/scans/{scan_id}/identity-groups/export.csv`
- `GET /api/scans/{scan_id}/identity-groups/reviewed-export.csv`

The summary response is extended to cover records scanned, discovered, grouped, unassigned, deferred, and truncated. Group/conflict lists accept status, review state, size, evidence mode, projection, and stable cursor filters. `limit` is bounded; offset remains compatibility-only. Large edge lists use a separate bounded evidence page or cursor rather than an unbounded group detail.

Discovery runs, neighborhoods, and pair evidence are advanced diagnostic resources. Existing pair routes remain available during compatibility and are later documented under an advanced/legacy namespace without breaking historical clients.

## UI design

The normal Scan Results workflow shows:

- records scanned;
- potential duplicate identity groups;
- likely and review-required groups;
- conflicts/deferred families;
- grouped and unassigned record counts;
- discovery degradation or truncation warnings;
- human review status.

Each group presents all members, shared identity signals, important differences, technical checks, site/UOM context, review rationale, and human review state. Pair relations appear only inside **Advanced relationship evidence**. The normal workflow does not use Part A/Part B language or pair review controls.

## Export classes

1. **System Group Export**: analytical G2 hypotheses, one row per member.
2. **Reviewed Identity Export**: human-confirmed, disjoint, scan-local identity sets for operational use.
3. **Conflict/Deferred Export**: unresolved families, reason categories, coverage, and members.
4. **Advanced Pair Evidence Export**: evaluated relationship evidence for analyst/audit use only.

Stable implementation-neutral columns are defined in `GROUP_FIRST_DOMAIN_CONTRACTS.md`.

## Pair-path deprecation

The migration is non-destructive:

1. Stop presenting pair counts/status as the scan headline.
2. Hide pair review and pair LLM controls from the normal workflow.
3. Write new independent evidence edges in parallel while legacy `DuplicateCandidate` writes continue for compatibility.
4. Make G2 output from the new resolver the visible result after shadow graduation.
5. Stop new pair feedback and pair LLM triage writes; keep reads and historical exports.
6. Stop `DuplicateCandidate` writes after all supported consumers read independent evidence.
7. Keep historical pair tables and APIs read-only for a declared compatibility period.
8. Retire legacy connected-component grouping first, then pair business APIs/UI, and only later evaluate archival migration.

No historical pair row is deleted by this program.

## Shadow comparison

Controlled shadow mode runs:

```text
visible path: old pair-first -> G1/G2
shadow path: neighborhood-first -> new resolver -> G2-compatible manifest
```

Only the old path is user-visible until graduation. Shadow results use separate comparison persistence or an explicitly non-visible namespace. They never create reviews, change current G2 selection, call an external provider, or modify source records.

Comparison includes:

- exact and Jaccard group membership overlap;
- record-level co-membership agreement;
- likely/review/conflict/deferred counts;
- records covered, unassigned, and missed;
- old-group splits and new-group merges;
- protected cannot-link violations;
- bridge-risk and salvage differences;
- runtime, peak memory, proposals, evaluated edges, and persisted evidence volume;
- per-case differences on labeled fixtures and human-reviewed samples.

Aggregate count similarity is never a graduation criterion by itself. Every cannot-link violation is a release blocker. Material split/merge differences require case-level adjudication.

## Acceptance gates

### Safety

- Zero accepted groups containing a protected cannot-link.
- Zero records in more than one accepted group per projection.
- Zero records in more than one current reviewed identity set per scan.
- Zero automatic source mutation, merge, deletion, or writeback.
- Human review remains final.

### Functional

- 2..N groups are the primary API, UI, review, and export outputs.
- A normal scan no longer requires `DuplicateCandidate` as its business-domain center.
- Pair UI is absent from the normal workflow.
- Group export remains member-shaped.
- Operational reviewed export contains only human-confirmed identity sets.
- Conflict and deferred outcomes are explicit and never shown as accepted groups.

### Discovery

- Record coverage, no-neighbor outcomes, caps, truncation, and generic-family deferral are measurable.
- Discovery scores are never exposed as duplicate confidence.
- Repeating identical input/configuration produces identical neighborhoods and fingerprints.

### Regression

- Historical scans and pair diagnostics remain readable during compatibility.
- G2-G7 behavior is preserved or explicitly selected by contract version.
- Existing cannot-link, UOM, human-review, and provider-neutral safety tests remain authoritative.
- Ordinary tests make zero provider requests.

### Performance

Benchmark suites are required at 5,000, 20,000, and 100,000 records. Before implementation graduation, benchmark owners establish hardware, representative data shapes, baseline runtime/memory/storage, and explicit pass thresholds. No timing threshold is approved by this ADR without those measurements.

## Consequences

### Positive

- Product and domain semantics become aligned.
- Pair logic is reused without remaining the architecture center.
- Group safety, human review, and exports survive.
- The pipeline becomes resumable and scale-oriented.
- Discovery quality and resolution quality can be measured separately.

### Costs and risks

- New additive persistence and migration code are required.
- During compatibility, pair and group evidence representations coexist.
- Resolver versioning and deterministic partition behavior require extensive tests.
- Progressive validation requires richer coverage semantics than current all-pair G1.
- Production readiness depends on representative labeled data and measured scale benchmarks.

## Implementation sequencing

Implementation is governed by `GROUP_FIRST_MIGRATION_ROADMAP.md`. GF-0 is the prerequisite governance and contract-freeze phase. GF-1 is the first production implementation phase; no production implementation or resolver code should begin before GF-0 acceptance checks pass.
