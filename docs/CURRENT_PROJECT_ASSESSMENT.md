# Current project assessment

## Document role

This document describes the observed repository state. It is not a requirements or architecture authority and never overrides `PROJECT_SSOT.md` or the approved group-first architecture package.

## Assessed baseline

- Baseline HEAD before the GF-12C1 demo-readiness commit: `a836585a6b7634e03f716cb470843f58f6b8fb8f`.
- Baseline HEAD before the GF-12B3 validation commit: `1c4e7d9876719e194bad252f0f23e5a44202bd3a`.
- Baseline HEAD before the GF-12B2 validation commit: `4b644b08dac59dddba2893556c356d71f4b55a8f`.
- Baseline HEAD before the GF-11A implementation commit: `2dcc948c46675b57ff521a824c186bcad35758bb`.
- Baseline HEAD before the GF-10B prerequisite schema-migration commit: `bb5f5775e0e93a8ec80d9e8411840c9ca5d0b72a`.
- Baseline HEAD before the GF-10A implementation commit: `53aa554095f1e4b476102d9e25d8fbd841493836`.
- Baseline HEAD before the GF-9C implementation commit: `e8dcd5795b7e522129827e85316739ab64fed661`.
- Branch: `llm-assisted-mvp`.
- Baseline HEAD before the GF-9B implementation commit: `4470249ff8ce1988e253df5556e7e6a3c46f7af5`.
- Baseline HEAD before the GF-9A implementation commit: `ab0e8b152d306807a69f6ba58d41346b14252c51`.
- Baseline HEAD before the GF-8B implementation commit: `be357ff397c921f2248a879570dfb47f541706ea`.
- Baseline HEAD before the GF-8A implementation commit: `004093209c04ad5cc27f0222c3293d0cd7292d37`.
- Baseline HEAD before the GF-7A implementation commit: `9b6b058530c9ee15e7cf223427a0a97d8131086c`.
- Baseline HEAD before the GF-6B implementation commit: `ae87011c91ee678607784713e0717347935f8ba8`.
- Baseline HEAD before the GF-6A implementation commit: `88863868b0e8c58b311007c921fe8c114165e715`.
- Baseline HEAD before the GF-5C implementation commit: `abda90ace57187292cd28f428fa57028d496dacc`.
- Baseline HEAD before the GF-5B implementation commit: `d31a5bb9d5c8ef5b55a4a6db5d305e8b7a886269`.
- Baseline HEAD before the GF-5A implementation commit: `be05baace42540de6983bfdc70fe483d0b852467`.
- Baseline HEAD before the GF-4 implementation commit: `64d98fb13363953016a42669a934b756776eacd0`.
- Baseline HEAD before the GF-4-PRE safety correction: `d294b6ca5b77a9d8a6b185b514484b75fa20424a`.
- Baseline HEAD before the GF-3 implementation commit: `b5ca5be28475c9e7205c7cc4544d685d2c749578`.
- Baseline HEAD before the GF-2 implementation commit: `7614a1ea84eef0649caecbd11a011b041d3a9ba7`.
- Baseline HEAD before the GF-1 implementation commit: `bdefe9dad25b112c92f7f40af358e361d37e59f0`.
- Baseline HEAD before the GF-0 governance commit: `f58b3f881a70a2c0d704092c929df55cd878dc90`.
- Architecture package commit: `f58b3f881a70a2c0d704092c929df55cd878dc90` (`Define group-first identity architecture`).
- Protected tag `deterministic-demo-v1`: `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Previously observed legacy `MVP_LLM_DEMO_SSOT.md` blob: `4538df1668cf189394bc3eb728fee946c6e490ee`.

The current system classification is hybrid/transitional. The STAGE-1B deterministic/group product smoke test passed, and a normal scan currently generates G2 groups. The discovery and decision core remains pair-first, while group APIs, UI, exports, review, and advisory boundaries project or consume group results.

The group-first architecture is approved and its product-read graduation is complete. GF-0 through GF-10 are verified and complete: GF-10A froze policy/dependency contracts, GF-10B-PRE enabled truthful G2-v2 audit persistence, and GF-10B deprecates pair-path writes for explicit group-first scans. Legacy numeric group routes remain v1-only compatibility endpoints while normal frontend, review, advisory eligibility, and authoritative exports use persisted per-scan authority and projection-safe keys. GF-11 is IN PROGRESS: GF-11A, GF-11B, GF-11C-PRE, and GF-11C are verified. GF-11D remains insufficient/not graduated after GF-11D-RERUN3: the official post-CACHE1 100k run timed out during retrieval fusion/materialization at 300.009 seconds, while the single extended run completed the full pipeline with 324.468-second DISCOVERY, corrected/persisted GF5, and GF6. GF-11D-CHAR-PRE, GF-11D-CHAR1, GF-11D-GF5-PRE, GF-11D-GF5-FIX, and GF-11D-CACHE1 are verified. CACHE1 replaced per-row cache-save round trips with deterministic bounded prefetch and executemany persistence while preserving exact cache/transaction semantics; the RERUN3 fresh 100k cache save used 79 lookup SELECTs and 71 batched inserts in 7.137 seconds. CHAR_VECTOR is now the largest measured DISCOVERY stage at 128.777 seconds. The `<=300.000000 s` target remains unmet and bounded debt `GF11-PERF-100K-COLD-FULL` is OPEN under an ACTIVE supervising architect / product-owner waiver. GF-12 is STARTED; GF-12A1 is VERIFIED, GF-12A2 human-review protocol/tooling is VERIFIED with `HUMAN_REVIEW_DATASET_REQUIRED`, GF-12B1 and GF-12B2 are VERIFIED, and GF-12B3 is VERIFIED with evidence-based operational gaps retained. No human pilot, labels, human-quality metrics, final production-quality signoff, or GF-12 graduation exists.

## GF-1 canonical scan-record catalog

Normal scans now create the canonical `ScanRecordSnapshot` catalog immediately after validation and row filtering, before candidate generation, hybrid retrieval, pair scoring, and G2 projection.

- Every currently valid source row (a row with the required mapped columns and a nonblank description under existing validation behavior) produces one immutable catalog row.
- Identity uses the database primary key plus unique `(scan_id, source_row_index)` and a deterministic scan-local `record_ref_key`; identical business rows remain distinct.
- The source row index is the original zero-based input ordinal and is carried through persisted candidate/exclusion evidence for G1/G2 reference reuse.
- The catalog stores only allowlisted canonical fields. It does not store arbitrary source columns or a complete raw row payload.
- Canonical business values remain separate from the existing deterministic normalized part-number and description fields, with an explicit normalization version.
- Catalog creation uses one scan-level read and one batched flush, is uniqueness-protected and idempotent, and rolls back as one transaction on failure.
- ORM update/delete guards enforce immutability after creation.
- G2 no longer creates `ScanRecordSnapshot` rows. It requires and reuses the early catalog and fails safely if a projection record is missing.
- Existing pair retrieval, scoring, rule, status, exclusion, export, G2 v1, review, API, and UI semantics remain unchanged.
- Historical G2 rows with legacy null source-row fields remain readable; the SQLite compatibility migration is additive and does not backfill or reinterpret them.

## GF-2 discovery runs and neighbor proposals

Every normal scan now starts one versioned, provider-independent `IdentityDiscoveryRun` after the GF-1 catalog commit and before candidate discovery. The run fingerprints the canonical record evidence and the stable subset of standard/hybrid discovery configuration that materially affects proposal generation.

- Standard candidate-generator output and selected hybrid retrieval output are adapted in parallel into neutral `NeighborProposal` rows; the legacy candidate/scoring path remains unchanged and authoritative for current visible behavior.
- Proposal endpoints are ordered canonical GF-1 record IDs. One run can persist only one row for a logical record pair, while deterministic JSON preserves all contributing channels, available channel ranks/scores, reciprocal provenance, retrieval context, and mapping/UOM context.
- Retrieval priority and proposal order are explicitly discovery-only values, never identity confidence, duplicate probability, business status, human review, or LLM output.
- Completion records exact catalog-record coverage and proposal counts. No-neighbor records are successful outcomes. Current cap metrics expose conservative degradation warnings; exact affected-record truncation and generic-family deferral remain nullable because current retrieval does not identify those sets precisely.
- The RUNNING/COMPLETED/FAILED lifecycle is auditable. A proposal-stage failure rolls back partial proposals and legacy evidence in that transaction, marks the discovery run failed, marks the scan failed, and preserves the already committed immutable GF-1 catalog.
- Persistence resolves endpoints from the catalog in bulk and uses bounded batched proposal insertion. Additive tables require no historical backfill, so scans without GF-2 data and all current G2-G7 reads remain compatible.
- Discovery calls no provider and records a provider request count of zero.

## GF-3 overlapping identity neighborhoods

New GF-3-version discovery runs now remain `RUNNING` after GF-2 proposal persistence and become `COMPLETED` only after required neighborhood snapshots and members have been persisted successfully.

- The authoritative neighborhood builder consumes only persisted GF-2 proposals and the GF-1 canonical catalog. It does not query pair scores, pair business status, feedback, LLM snapshots, rule exclusions, G0/G1 classifications, or G2 results.
- Every canonical record participating in at least one proposal receives one anchor neighborhood containing the anchor and its bounded direct neighbors only. Neighbors-of-neighbors are not expanded transitively.
- Neighborhoods deliberately overlap. A canonical record may be the anchor of one neighborhood and a direct member of any number of other neighborhoods.
- The configurable `IDENTITY_NEIGHBORHOOD_MAX_MEMBERS` cap includes the anchor and defaults to the current 20-member compatibility bound. The default is operational rather than permanent product truth and remains subject to GF-11 benchmarking.
- High-degree anchors preserve their exact candidate-neighbor count, bounded included count, persisted source proposals, `MEMBER_CAP_REACHED` warning, degradation state, and deterministic fingerprint. Omitted proposals are not treated as rejections.
- Every non-anchor member references the exact persisted proposal connecting it directly to the anchor. Snapshot and member readers validate same-run, same-scan, same-catalog, and direct-link integrity.
- Neighborhood and membership rows are immutable and idempotent. Persistence uses bulk catalog/proposal reads and batched writes without per-anchor or per-member lookup queries.
- A neighborhood-stage failure rolls back proposals, neighborhoods, members, and uncommitted legacy evidence together; the run and scan become failed while the committed GF-1 catalog remains intact.
- Historical GF-2 completed runs without neighborhoods remain readable, receive no automatic backfill, and are not reinterpreted as failed.
- Visible product behavior remains the legacy pair path through G1 and G2 v1. GF-3 neighborhoods are internal, non-authoritative discovery work units and do not affect APIs, UI, exports, review, or provider behavior.

## GF-4 prerequisite generic-description safety correction

Before GF-4 implementation, its initial review correctly identified that an identical one-token category description could bypass the existing generic-description lexicon and become strong identity support from text and matching context alone.

- The deterministic genericity guard now treats a single alphabetic token as insufficiently specific while preserving alphanumeric model-like tokens on the normal scoring path.
- Generic text without independent strong identity evidence cannot produce `LIKELY_DUPLICATE` or `STRONG_SUPPORT`. Identical generic text remains review evidence rather than proof of difference.
- The only current rescue is the scorer's existing strong part-number relationship at its established threshold; site, UOM, accounting, category, or fuzzy/TF-IDF agreement does not rescue generic text.
- Protected technical contradictions remain `CANNOT_LINK`, context differences alone remain non-terminal, and specific clear matches retain their existing results.
- Focused scoring and G0/G1/G2 safety regressions plus the complete backend, frontend, and build gates verified the correction and cleared the GF-4 implementation blocker.

## GF-4 independent signed identity evidence

Every new scan now completes one provider-neutral `IdentityEvidenceRun` after GF-2/GF-3 discovery and before legacy pair business writes and the visible G1/G2-v1 projection.

- Normal acquisition evaluates every unique persisted GF-2 proposal exactly once from its GF-1 canonical endpoints. GF-3 overlap never duplicates an edge and does not cause transitive non-proposal evaluation.
- The pure canonical relationship evaluator is independently callable for a future GF-5 targeted check, but normal GF-4 orchestration persists proposal relationships only.
- The evaluator reuses the current deterministic scorer, generic-description guard, technical extraction, protected mismatch rules, UOM decoupling, and authoritative signed edge classifier. It does not read `DuplicateCandidate`, exclusions, feedback, pair advisory data, G1/G2 results, or G6 review as machine-evidence authority.
- Immutable evidence edges use canonical endpoints and preserve exact source-proposal provenance, signed class/reasons, score components, protected conflicts, generic and technical summaries, UOM mapping context, evaluator version, and a deterministic non-secret fingerprint. An edge score is neither group confidence nor duplicate probability.
- Completed runs prove exact proposal coverage and class-count reconciliation. Repeating a compatible completed acquisition is idempotent; changed relevant context creates a separate versioned run rather than mutating completed evidence.
- A GF-4 failure rolls back partial edges, records a safe failed run, fails the scan, preserves the completed GF-1/GF-2/GF-3 state, and prevents legacy candidate/G1/G2 completion.
- The GF-4-PRE generic safety correction is inherited: generic text and matching context alone cannot produce strong support. Site, UOM, and accounting differences alone remain non-terminal, while protected technical contradictions remain cannot-links.
- Historical scans require no GF-4 backfill. Current visible pair results, G1/G2-v1 snapshots, G3 APIs, G4 UI, G5 exports, G6 reviews, and G7 advisory behavior remain legacy-compatible and unchanged.

## GF-5A constrained resolver contracts and golden safety cases

GF-5A establishes an isolated, provider-free boundary for the future GF-5
decision core without implementing a production resolver or changing normal
scan execution.

- Immutable input contracts consume GF-1 canonical records, normalized GF-3
  overlapping neighborhoods, normalized GF-4 signed evidence, optional narrow
  G6 effective human constraints, and versioned deterministic bounds.
- Human `CANNOT_LINK` and protected machine `CANNOT_LINK` prohibit accepted
  co-membership. A human `MUST_LINK` against a protected machine cannot-link is
  an explicit authority conflict, never an override.
- Typed targeted requests are limited to bridge, partition, likely-completeness,
  and ownership checks. The pure GF-4 evaluator result can be adapted in memory
  without changing GF-4 persistence.
- Accepted hypothesis contracts distinguish `COMPLETE_PAIRWISE` from
  `PROGRESSIVE_TARGETED`. GF-5A's conservative likely validator requires every
  internal pair to be strong support and authorizes no permissive progressive
  likely rule.
- Group evidence is categorical and auditable rather than an average pair
  score. Bridge, generic-hub, missing-evidence, truncation, and ownership risks
  are explicit typed summaries.
- Conflicts remain deterministic contradictions or incompatible authority;
  bounds, missing evidence, truncation, and unresolved ambiguity are deferred.
  Unassigned records are not classified as non-duplicates.
- Pure validators reject cross-scan references, noncanonical/self pairs,
  duplicate members, false complete-pairwise claims, cannot-link membership,
  duplicate accepted membership, unresolved likely risks, and unsupported
  generic/neutral support chains.
- Fifteen executable golden cases freeze GF-5B acceptance expectations for
  strong triangles, contradictions, bridge checks, generic hubs, human
  constraints, ownership overlap, safe disjoint groups, site/UOM context,
  technical variants, truncation, unassigned records, and duplicate-valued
  distinct source rows.
- Deterministic fingerprints use canonical versioned payloads and exclude
  timestamps, secrets, randomness, provider data, and LLM content.
- There are no schema or persistence changes. No scan runner, G2 publication,
  API, UI, export, pair-path, review persistence, or provider behavior changed.

GF-5 is intentionally subdivided internally into GF-5A contracts/safety cases,
GF-5B pure constrained resolution, and GF-5C lifecycle/persistence plus
non-visible integration. This does not alter the frozen GF-0 through GF-12
roadmap order. GF-5 remains in progress until its later units are complete.

## GF-5B pure constrained resolver algorithm

The production library now includes a pure, deterministic
`resolve_identity_groups(...)` implementation over the immutable GF-5A
boundary. It is not wired into normal scans and persists nothing.

- Overlapping GF-3 neighborhoods and in-scope GF-4 evidence form bounded work
  units only; connectivity is never accepted as identity.
- Machine/human cannot-links remain protected vetoes. Compatible must-links
  contribute positive authority, while direct and transitive must-link
  contradictions remain explicit conflicts.
- Missing small-work-unit relationships are scheduled through a narrow typed
  targeted-evidence protocol in bridge, ownership, likely-completeness, then
  partition-refinement priority. Requests are canonical, deduplicated, cached,
  bounded, and may use the existing pure GF-4 evaluator adapter.
- Bridge articulation, single-edge branches, generic hubs, neutral gaps, and
  missing cross-branch evidence are analyzed before group acceptance.
- Complete-pairwise likely remains all-strong only. Review hypotheses must pass
  the frozen GF-5A cohesion and ambiguity validators. Progressive likely is not
  emitted in v1.
- Candidate generation and disjoint partition selection are bounded and
  lexicographic: safety, compatible constraints, coverage, strong cohesion,
  bridge/generic stability, then deterministic identity. Equal materially
  different ownership remains deferred.
- Safe subgroups common to the selected stable partition are retained without
  hiding the broader conflict. Accepted membership remains globally disjoint.
- Member caps, targeted-budget exhaustion, evaluator failure, truncation, and
  bounded-search exhaustion produce typed deferred work rather than optimistic
  acceptance.
- All 15 frozen golden cases now execute against the real resolver. Additional
  tests cover shuffled determinism, bounds, disjoint cliques, must-link closure,
  neutral evidence, duplicate-valued rows, evaluator failure, targeted
  ordering/deduplication, GF-4 evaluator inheritance, legacy-path isolation,
  and bounded-search metrics.
- There are no database, migration, repository, scan-runner, G2, API, UI,
  export, pair-path, provider, or secret changes.

## GF-5C durable resolver lifecycle and non-visible integration

Every new successful scan now invokes the GF-5B resolver after its completed
GF-4 evidence transaction and before legacy pair writes and the visible
G1/G2-v1 projection.

- A versioned immutable `IdentityResolutionRun` fingerprints the exact GF-1
  catalog, GF-3 neighborhoods, GF-4 signed evidence, normalized effective G6
  constraints, resolver algorithm, and bounded configuration.
- Accepted hypotheses and ordered members, conflicts and involved records,
  deferred work and records, explicit unassigned records, effective constraint
  provenance, and resolver-only targeted requests/results are persisted as
  queryable immutable rows. Targeted checks do not alter GF-4 evidence.
- Child result persistence is atomic. A failure rolls back every partial result
  row and terminally records a bounded safe failure category.
- A completed run is reloaded into the typed GF-5 result, revalidated, and
  compared with the pure resolver output before commit. Identical input reuses
  the terminal run without duplicate children.
- Changed G6 constraints create a distinct resolver run and never auto-run or
  mutate a G2 projection.
- GF-5C failure is deliberately non-visible: the legacy pair path and G1/G2-v1
  projection continue unchanged.
- Resolution is deterministic and provider-free; provider requests remain zero.
  No API, UI, export, LLM, dependency, deployment, or pair behavior changed.

## GF-6A pure G2-v2 adapter contracts

The production library now contains a pure, immutable, database-independent
adapter from a completed GF-5C typed resolution result and authoritative
GF-1/GF-4/GF-5C evidence to a typed G2-v2 snapshot manifest.

- G2-v1 remains the current visible and persisted contract. Its complete
  N-choose-2 evidence semantics, schema, persistence, selection, readers, APIs,
  exports, reviews, and advisory targets are unchanged.
- Every v2 group maps one accepted GF-5 hypothesis without changing status or
  membership. It carries ordered GF-1 members, GF-5 summaries, validation mode,
  exact coverage, effective internal evidence, and stable provenance.
- `COMPLETE_PAIRWISE` requires exactly N-choose-2 deterministic evidence items.
  `PROGRESSIVE_TARGETED` explicitly preserves evaluated and missing-nonrequired
  pair counts and never fabricates unevaluated neutral edges.
- GF-4 proposal evidence and GF-5C targeted evidence are normalized separately.
  Equivalent overlap uses deterministic proposal precedence with supplemental
  targeted provenance; incompatible overlap is rejected.
- Conflicts, deferred work, and exact unassigned identities remain distinct
  first-class manifest outcomes. Deferred and unassigned never mean unique or
  non-duplicate.
- Canonical fingerprints cover stable record references, source GF-5
  fingerprints, validation coverage, effective evidence, and adapter versions.
  Input order, timestamps, provider data, secrets, and avoidable database IDs do
  not affect semantic fingerprints.
- The validator rejects cross-scan/source-run drift, overlapping or invalid
  membership, cannot-links, false complete coverage, missing required targeted
  evidence, duplicate/out-of-group evidence, status drift, and fingerprint drift.
- GF-5B-v1 currently emits complete-pairwise accepted groups and no progressive
  likely groups. GF-6A nevertheless freezes a validator-approved progressive
  review mapping seam for future resolver versions.
- GF-6A creates no database model, migration, repository loader, persistence
  path, scan integration, public route, UI, export, review, advisory, or provider
  behavior. GF-6B remains responsible for non-current v2 persistence.

## GF-6B non-current G2-v2 persistence

Every successful new GF-5C resolution now feeds the pure GF-6A adapter and is
persisted in structurally separate `g2_v2_*` tables before legacy pair writes.

- One immutable `G2V2ProjectionRun` owns structured group, ordered member,
  internal evidence, conflict, deferred, and explicit unassigned rows. The
  persisted manifest reconstructs exactly and revalidates against GF-1,
  GF-4, and GF-5C before completion.
- Complete-pairwise and progressive-targeted coverage retain their distinct
  semantics. Missing progressive pairs are never synthesized, and proposal
  versus targeted evidence origin/provenance remains explicit.
- Stable source, adapter/configuration, and manifest fingerprints make repeats
  idempotent. Terminal runs and every child row are immutable.
- Child persistence and completion are atomic. A failed v2 write rolls back its
  child graph, records a bounded FAILED run, and cannot change completed GF-5C
  history or the legacy visible G2-v1 result.
- The v2 schema has no current flag and no relationship to current v1 selection.
  Existing G3 APIs, G5 exports, G6 reviews, G7 advisory eligibility, and
  `snapshot_available` continue querying only `identity_group_*` v1 tables.
- Historical scans are not backfilled, and reads never create v2 data. GF-6B
  itself creates no comparison metric, and no GF-8 promotion/orchestration
  switch exists.

## GF-7A pure controlled shadow-comparison contracts and metrics

The production library now contains a database-independent deterministic
comparison between a neutral completed G2-v1 DTO and a completed GF-6 v2
manifest.

- Neither version is treated as ground truth. Outputs describe exact agreement,
  status changes, splits, merges, partial reassignment, version-only groups,
  complex overlap, safety deltas, and categorical adjudication priority.
- Positive co-membership work enumerates pairs only inside accepted groups and
  never constructs the global negative inventory-pair universe.
- A membership-indexed bipartite graph scopes structural cases without using
  connectivity as an identity decision. Every accepted group belongs to one
  primary case.
- Protected-conflict deltas require direct protected evidence provenance;
  ordinary splits, genericity, neutral evidence, and targeted evaluation are
  not mislabeled as correctness or safety proof.
- Stable semantic fingerprints exclude run/group database IDs, input order,
  timestamps, providers, secrets, and randomness.
- Twelve golden cases and five edge cases freeze exact/status/split/merge/
  reassignment/conflict/deferred/targeted/identity-order behavior.
- GF-7A adds no schema, persistence, scan integration, current selection, API,
  UI, export, review, advisory, pair-deprecation, or provider behavior. GF-7B
  remains responsible for persisted explicitly controlled shadow runs.

## GF-7B persisted controlled shadow runs

GF-7B now persists the exact pure GF-7A result for eligible scans only when
`GROUP_FIRST_SHADOW_COMPARISON_ENABLED=true`; the setting defaults to false.

- The enabled normal-scan hook runs after completed non-current G2-v2 and after
  the ordinary current G2-v1 selector resolves the just-persisted v1 run, but
  before visible scan completion.
- Separate additive comparison tables store immutable run provenance and
  summary metrics plus normalized cases, source group/member relations,
  involved records, safety deltas, and case/delta associations.
- Semantic input identity covers stable GF-1 evidence, v1 memberships/statuses,
  the v2 manifest and non-accepted context, and comparison algorithm/config;
  timestamps, providers, secrets, randomness, and avoidable database IDs are
  excluded.
- Repeated identical work reuses one completed graph. Changed configuration or
  semantic input creates a distinct historical run. Terminal rows are
  immutable.
- Child persistence is atomic and must reconstruct and exactly equal the pure
  typed result before completion. Failures retain a bounded FAILED run with no
  partial children and do not fail or reinterpret the visible scan.
- Bulk reconstruction uses six SELECTs independent of case/record/delta count
  in the controlled multi-case fixture. This is a query-shape observation, not
  a 100k-readiness claim.
- The gate-disabled path creates no run. Historical reads create no backfill.
  Current/latest selection, `snapshot_available`, G3 APIs, G5 exports, G6
  review targets, and G7 advisory eligibility remain v1-only.
- No winner, correctness, quality, error-rate, or promotion semantics were
  introduced. No public API, frontend, provider, or secret behavior changed.

## GF-8A group-first orchestration contracts and authority gates

GF-8A defines a pure, immutable planning boundary without changing execution.

- `LEGACY_PRIMARY` preserves the current legacy pair/G1 authority and current
  G2-v1 projection. GF-5C/GF-6B remain failure-isolated internal stages.
- `GROUP_FIRST_PRIMARY` is a future GF-8B mode in which GF-1 through GF-6 are
  primary-required. Before GF-9, legacy pair/G1/G2-v1 output remains
  compatibility-required because all current product readers still consume
  G2-v1.
- Primary identity authority and visible compatibility projection are separate
  concepts. In group-first-primary mode, visible readiness requires both
  primary readiness and compatibility-projection readiness.
- The stage taxonomy distinguishes primary-required, compatibility-required,
  optional-diagnostic, and not-applicable work. Primary, compatibility,
  optional, configuration, and multiple-required-stage failure categories are
  explicit.
- `IDENTITY_ORCHESTRATION_MODE` is allowlisted to `legacy_primary` and
  `group_first_primary`, defaults to `legacy_primary`, and rejects invalid
  values. It is not wired into the scan runner in GF-8A.
- GF-7 agreement metrics, cases, deltas, and fingerprints are excluded from
  policy and plan identity. No comparison threshold or scalar score can select
  an orchestration mode.
- The pure planner/evaluator has no SQLAlchemy, repository, scan mutation,
  current-selector, API, frontend, export, review, advisory, or provider
  dependency. GF-8A adds no schema or migration.
- The visible projection contract remains `G2_V1` in both modes throughout
  GF-8. GF-8B now consumes these contracts; GF-9 product-reader inversion
  remains unstarted.

## GF-8B controlled group-first-primary runtime

Normal scans now resolve the explicit `IDENTITY_ORCHESTRATION_MODE`, consume
the frozen GF-8A policy/plan, record categorical stage results, and use the
GF-8A outcome evaluator as the readiness classification boundary.

- `legacy_primary` remains the default and preserves the verified pre-GF-8
  ordering and failure isolation: GF-5C, GF-6B, and GF-7B failures remain
  non-visible while legacy pair/G1/G2-v1 stays authoritative.
- `group_first_primary` makes GF-1 through GF-6 primary-required. A failed
  GF-5C or GF-6B stage fails the scan before compatibility work and cannot be
  rescued by legacy output.
- After primary success, legacy pair persistence, G1, and G2-v1 execute as one
  compatibility boundary. A compatibility failure leaves completed GF-5/GF-6
  history intact but makes compatibility and visible readiness false.
- G2-v2 remains structurally non-current. G2-v1 remains the selected visible
  projection for `snapshot_available`, G3, G5, G6, and G7 readers in both modes.
- GF-7 shadow comparison remains optional diagnostic work. Failure is audited
  without failing a scan whose primary and compatibility stages succeeded.
- Additive `scan_orchestration_run` and `scan_orchestration_stage_result`
  tables preserve the exact mode, policy/plan fingerprints, stage authority,
  execution order, categorical status, bounded safe failure, and same-scan
  source-run references. Historical scans are not backfilled and reads create
  no audit row.
- One scan has at most one immutable orchestration run and one row per planned
  stage/order. Stage writes are bounded by the nine-stage plan, never by record
  or candidate volume. Process-crash resume is not introduced; GF-11 retains
  resumability and scale hardening.
- Mode selection comes only from configuration. GF-7 metrics cannot promote or
  demote a mode, and deterministic execution makes zero provider calls.

## GF-9A group-first read authority and projection contracts

GF-9 is IN PROGRESS. GF-9A is verified; GF-9B and GF-9C have not started.

- A pure immutable read boundary represents G2-v1 and G2-v2 through one
  projection-tagged snapshot while preserving their distinct validation
  semantics.
- Future authority is selected from the persisted orchestration mode that
  actually ran for the scan. Historical scans without a GF-8 audit and
  completed legacy-primary scans select G2-v1; completed group-first-primary
  scans require G2-v2.
- Missing, failed, cross-scan, provenance-incompatible, or invalid required v2
  data fails closed. Compatibility v1 is never a silent fallback for a
  group-first-primary scan.
- Versioned group keys include scan, projection contract, and group reference,
  preventing future G6 reviews or G7 advisories for a v1 group from being
  silently applied to a v2 group with the same textual reference.
- The v1 adapter preserves legacy complete N-choose-2 semantics without
  inventing v2 conflicts, deferred work, progressive coverage, targeted
  evidence, or resolution provenance. The v2 adapter preserves complete or
  progressive validation, exact coverage, summaries, evidence, conflicts,
  deferred work, unassigned records, and source-resolution provenance.
- Canonical semantic SHA-256 fingerprints exclude current configuration,
  providers, secrets, timestamps, randomness, and source run database IDs.
- The package has no database, repository, selector, scan mutation, route,
  frontend, export, review, advisory, or provider dependency. No current reader
  is switched in GF-9A.

## GF-9B backend read, review, and advisory inversion

GF-9B is verified. At its delivery boundary, GF-9 remained in progress pending
the GF-9C frontend and final System Group Export inversion now documented below.

- `IdentityReadService` is now the canonical backend product-reader boundary.
  It loads the persisted GF-8 audit and exact stage source-run references,
  delegates selection to GF-9A, loads only the required v1 or v2 source, and
  never reads current mode configuration.
- New `/api/scans/{scan_id}/identity-read/*` routes expose authority-selected
  summary, groups, detail, v2 outcomes, projection-safe review, and advisory
  eligibility. Existing numeric group routes remain v1-only compatibility
  routes because their database IDs cannot safely represent v2 identity.
- Missing/failed required v2 returns HTTP 409. Invalid, cross-scan,
  provenance-incompatible, or projection-mismatched authority returns HTTP 422.
  Compatibility v1 is never served as group-first truth.
- G6 v2 reviews use additive append-only versioned review, partition, member,
  and constraint tables. V1 targets delegate to unchanged historical G6 rows.
  V2 chain heads and constraints are scoped by scan, projection, source run,
  group reference, opaque key, and source group fingerprint. Review does not
  auto-run GF-5/GF-6.
- G7 request identity now includes projection contract, source projection run,
  opaque group key, and source group fingerprint. Existing G7 has no durable
  group-advisory result table, so no historical advisory rows required schema
  migration. Progressive groups fail closed; likely groups remain ineligible.
- At the GF-9B boundary, System Group Export remained byte-compatible for
  historical/legacy scans and was temporarily blocked for group-first-primary
  scans with a typed GF-9C migration-pending conflict. Reviewed export was
  unchanged until GF-9C.
- Controlled reads observed five SELECTs for historical v1 and fourteen for
  v2, independent of member/evidence cardinality. No scale-readiness claim is
  made.

## GF-9C frontend and authoritative export graduation

GF-9C is verified and completes GF-9.

- Normal scan results now load summary, paged group list, lazy group detail,
  typed outcomes, review history, and advisory eligibility only through the
  authority-selected `/identity-read` API family. The frontend contains no
  orchestration-mode or current-configuration authority logic and performs no
  legacy fallback after a 409 or 422 authority failure.
- Opaque `igk1` keys are treated as strings and are used for detail, G6 review,
  and G7 eligibility targets. Numeric v1 group IDs remain compatibility-only.
- The primary summary counts records and 2..N identity groups, likely groups,
  review groups, conflicts, deferred work, and not-safely-assigned records.
  Pair counts and A/B language are absent from the business headline.
- Group cards provide bounded member previews, validation mode, exact coverage,
  and projection-scoped review state. Detail shows every member, exact opaque
  identity, actual evaluated evidence, review, and backend-owned advisory
  eligibility. Progressive 2-of-3 evidence stays 2-of-3; no third pair is
  synthesized.
- Conflict, deferred, and unassigned outcomes stay distinct. Unassigned is
  described only as not safely assigned and never as confirmed unique.
- Pair data remains available under Advanced legacy diagnostics without pair
  review, pair LLM action, headline, or primary export prominence. Pair writes
  and compatibility machinery remain unchanged for GF-10.
- Canonical System Group, Reviewed Identity, Identity Conflict, and Deferred
  Identity Work CSV routes consume `IdentityReadSnapshot`. System rows are
  member-shaped and include stable projection/coverage provenance. Reviewed
  output contains current human-confirmed sets from only the exact selected
  projection review chain. Historical G5/G6 routes remain unchanged.
- A controlled disagreement fixture preserves compatibility v1 `{A,B,C}` but
  presents and exports only authoritative v2 `{A,B}` with `C` deferred. Missing
  required v2 fails closed; a ready zero-group snapshot remains a valid empty
  product/export result.
- Verification completed with 878 backend tests, 94 frontend tests, and the
  production build. Ordinary verification made zero provider calls. Controlled
  group-first System Group and Reviewed Identity exports used 16 and 17 SELECTs
  respectively, independent of member count; this is not a GF-11 scale claim.

## GF-10A pair-path write deprecation policy and dependency freeze

GF-10A is verified as a pure governance/contract unit. It activates no runtime
behavior.

- A code-backed typed manifest classifies every direct runtime module that
  reads or writes legacy candidates, G1, or G2-v1. The
  authoritative-required group-first residual count is zero.
- Post-GF-9 orchestration policy v2 makes GF-1 through GF-6 primary-required
  and G2-v2 visible for `group_first_primary`. Pair, G1, G2-v1, and GF-7 shadow
  stages are not applicable, so visible readiness has no compatibility-v1 gate.
- Policy-v2 `legacy_primary` retains pair/G1/G2-v1 authority and the existing
  optional shadow gate. Historical policy-v1 audit reconstruction and
  readiness evaluation continue to use the persisted policy generation.
- The immutable pair-write policy disables legacy pair, G1, and G2-v1 writes,
  shadow comparison, new-scan pair diagnostics, and numeric-route authority
  only for future policy-v2 group-first scans. It retains them for legacy mode.
- Future group-first pair diagnostics are explicitly
  `NOT_GENERATED_NOT_APPLICABLE`, distinct from a generated zero-pair result.
- Static dependency tests prove GF-9 authority-selected reads, versioned G6
  review, and versioned G7 advisory eligibility use G2-v2 for persisted
  group-first scans without `DuplicateCandidate`, G1, or v1 current selection.
- `scan_runner.py`, schema, migrations, APIs, frontend, exports, G6/G7 runtime,
  configuration defaults, and provider behavior are unchanged. GF-10B owns
  runtime activation and write shutdown.

## GF-10B prerequisite orchestration-audit schema migration

The prerequisite orchestration-audit migration was verified before GF-10B
runtime activation.

- The previous non-null `visible_projection_contract = 'G2_V1'` check could not
  truthfully persist the frozen policy-v2 group-first plan.
- Fresh and migrated databases now allow exactly `G2_V1 | G2_V2`; unsupported
  values such as `G2_V3` and `AUTO` remain rejected.
- The SQLite migration is idempotent and rebuilds only the orchestration-run
  table. Historical policy-v1 rows remain byte-for-value `G2_V1`, with row
  count, IDs, scan references, timestamps, readiness/failure data, keys,
  indexes, triggers, and unrelated checks preserved.
- A valid policy-v2 `group_first_primary` audit with visible `G2_V2` and
  `compatibility_projection_required=false` now persists and reads back.
- At this prerequisite boundary, runtime behavior remained unchanged; the
  subsequent verified activation is recorded below.

## GF-10B runtime pair-path write deprecation

GF-10B is verified and completes GF-10.

- New scans persist policy v2. Explicit group-first execution completes GF-1
  through GF-6, exposes G2-v2, and records pair/G1/G2-v1/shadow stages as
  `NOT_APPLICABLE` without invoking their writers.
- Independent proposals, signed and targeted evidence, resolver results, and
  G2-v2 evidence/provenance remain present. GF-5/GF-6 failure has no v1 rescue.
- Pair diagnostics and pair CSVs are explicitly not applicable rather than
  generated empty output. Advanced diagnostics presents that distinction.
- Canonical reads/exports, versioned G6 review/constraints, and G7 eligibility
  work against v2 without pair, G1, v1, or shadow rows.
- Policy-v2 legacy mode retains candidates, G1/G2-v1 authority, legacy routes,
  diagnostics/exports, review/advisory behavior, and the existing shadow gate.
- Historical policy-v1 audit rows remain immutable and version-interpreted.
  Default orchestration remains `legacy_primary`; provider calls remain zero.
- No schema/migration change was required beyond GF-10B-PRE, and no GF-11
  scale-readiness claim is made.

## GF-11A scale baseline and benchmark harness

GF-11A is verified as the measurement and observability unit of GF-11.

- Immutable benchmark contracts, safe environment metadata, deterministic
  semantic fingerprints, stable JSON, and optional Markdown output are present.
- The fixed-seed S1-S8 generator supports 500, 5k, 20k, and 100k without a
  global negative-pair matrix; synthetic truth never enters product inputs.
- The command runs policy-v2 group-first semantics against a disposable SQLite
  database with provider none and records stage, persistence, query, resource,
  safety, complexity, and synthetic-quality observations.
- B1-B16 verify determinism, source-row distinctness, truth isolation, bounded
  100k generation, schema stability, persistence reconciliation, safety
  detection, deprecated-write absence, database isolation, timeout truthfulness,
  fingerprint stability, and environment privacy.
- Measured 5k fails safely in group resolution with
  `IDENTITYRESOLUTIONVALIDATIONERROR`; 20k times out with GF5 running; 100k
  times out in discovery. These results establish a baseline, not readiness.
- Discovery retrieval/fanout is the single measured GF-11B recommendation.
  GF-11B-PRE/PRE2 and the GF-11B-ANN architecture decision are complete;
  production GF-11B hardening, GF-11C, GF-11D, and GF-12 remain unverified.

## GF-11B-ANN approximate character-retrieval architecture decision

The decision-only benchmark authorizes one future production target: fixed-seed
random-hyperplane LSH candidate generation over the current normalized 384-bin
character vectors, followed by bounded exact cosine reranking and the verified
canonical GF1 tie contract. The measured minimum safety-passing pool is 320 for
current top-k 5. Exact, part-family, technical, standard-blocking, and lexical
channels remain exact.

Canonical 500 and 5k character coverage did not regress, 5k final hybrid output
was identical, and repeat/reverse/shuffle semantic fingerprints were stable.
The benchmark-only selector completed 20k in 31.987 seconds and 100k in 308.493
seconds; the latter is plausible but 8.493 seconds above the preferred evidence
target. The observed exact/LSH crossover is approximately 2,000 records.

No production retrieval path, threshold, dependency, schema, migration, API,
frontend, resolver, provider, or secret behavior changed. GF-11B remains
blocked and unverified until the separately reviewed production adapter,
fingerprinting, explicit failures, and full scale regression are implemented.

## GF-11B production fixed-seed LSH hardening

The production adapter and its prerequisites are implemented, but GF-11B is
**INSUFFICIENT / NOT VERIFIED** against the frozen scale gate.

- `N < 2,000` retains exact deterministic character retrieval; `N >= 2,000`
  selects fixed-seed LSH pool 320 plus exact cosine/canonical rerank.
- P1-P20, 500 exact reference, 5k character coverage, 5k 500/500 final-hybrid
  overlap, and 5k repeat/reverse/shuffle determinism pass with zero providers.
- The 5k normal pipeline improves discovery from 73.99 to 57.731 seconds and
  reaches the same GF-5 `IDENTITYRESOLUTIONVALIDATIONERROR`.
- The normal 20k pipeline times out in discovery at 300.036 seconds rather than
  improving on the 219.86-second GF-11A discovery baseline. The bounded 100k
  run also times out in discovery at 300.030 seconds.
- At 20k, combined in-memory hybrid retrieval is 99.804 seconds, of which
  character LSH is 34.639 seconds; the greater-than-188-second residual before
  durable discovery completion is outside the combined hybrid retriever.
- No schema, migration, dependency, frontend, provider, resolver, identity
  rule, pair/G1/G2-v1/shadow write, or historical-run interpretation changed.

GF-11A and the GF-11B-PRE/PRE2/ANN prerequisites remain verified. GF-11B is
insufficient; GF-11C and GF-11D are not started; GF-11 remains IN PROGRESS.

## GF-11B residual discovery profiling

GF-11B-RESIDUAL is **VERIFIED** as a measurement-only prerequisite. The
production LSH adapter remains committed, but GF-11B remains **INSUFFICIENT /
NOT VERIFIED** and GF-11C is not started.

Exact production-path measurements attribute 99.08% of 5k discovery and
99.14% of completed 20k discovery; post-retrieval attribution is 99.74% and
99.70%, respectively. The completed no-cProfile 20k observation measured
146.811 seconds total, 121.674 seconds in retrieval, and only 9.696 seconds
after retrieval. The earlier inferred 188--200+ second post-retrieval residual
was not reproduced. GF-2/GF-3 persistence, reconstruction, and commits are not
the dominant residual.

The next bounded GF-11B hardening target is exactly **repeated eligibility and
variant-extraction work in hybrid other-channel fusion/materialization**, the
largest measured 20k retrieval sub-bucket at 43.169 seconds. The separately
measured per-vector cache-save SELECT/INSERT pattern is query-amplified but is
not the largest target. No production optimization is included in the
profiling prerequisite; GF-11D, GF-12, provider work, and readiness graduation
remain outside this change.

## GF-11B repeated eligibility and variant-extraction hardening

GF-11B is **VERIFIED** as a bounded scale-hardening unit; GF-11 as a whole
remains IN PROGRESS and no 100k or production-readiness graduation is claimed.

The production discovery path now creates one immutable, scan-local
`CandidateEvaluationFeatures` bundle per GF-1 `record_ref_key` and reuses it
across eligibility, allowed-pair evaluation, standard/hybrid scoring, technical
grouping, and fusion conflict checks. Pair-local decisions still execute for
every pair. Raw helper APIs remain equivalent and no discovery fingerprint or
version changed.

At 5k, variant extraction fell from 176,538 to 5,000 calls while eligibility,
allowed-pair, and scoring remained 68,858/68,858/20,500. Canonical proposal and
neighborhood fingerprints remained exact. The authoritative 20k repeat reduced
DISCOVERY from 146.811 to 111.927 seconds and retrieval from 121.674 to 86.370
seconds; feature construction cost 1.902 seconds. Full 5k execution retained
the same GF-5 `IDENTITYRESOLUTIONVALIDATIONERROR` and zero safety/provider/
deprecated-write violations.

The bounded 100k run completed 100,000 feature bundles and standard blocking
but timed out during the pre-cache retrieval path. Checkpoint order identifies
exact lexical nearest-neighbor construction/query as the next measured target.
GF-11C is not started; GF-11D, GF-12, provider work, and graduation remain out
of scope.

## GF-11C-PRE deterministic lexical reference correction

The brute-force lexical selector now excludes self before top-k, orders by
full-precision cosine descending, and resolves exact ties with immutable GF-1
`record_ref_key` ascending. TF-IDF, cosine, top-k, two-decimal output, zero
filtering, reciprocity, provenance, fusion, and caps remain unchanged.

Canonical 500/5k measurements found 625/8,607 directed tie substitutions and
zero unequal-score substitutions. Reverse and shuffles 7/19/1101 had zero
semantic differences. Lexical-only truth/protected/cross-site/bridge coverage
was unchanged. At 500 final hybrid coverage was unchanged. At 5k, 26 final
pair memberships changed and synthetic truth/bridge coverage moved from
231/113 to 226/108 while retaining 500 proposals. A bounded 64-record
GF1-through-GF6 comparison remained identical and every safety/provider/
deprecated-write count was zero.

New discovery runs use the v4 lexical-canonical-tie contract; historical runs
remain immutable. Brute-force quadratic lexical work remains. GF-11C indexed
lexical retrieval is still not started and is the next bounded task.

## Reusable current capabilities

- deterministic normalization;
- bounded hybrid retrieval;
- deterministic pair evidence;
- G0 signed-edge safety;
- G1 constrained group projection;
- G2 immutable identity-group snapshots;
- G3 typed identity-group APIs;
- G4 group-centric scan-results UI;
- G5 group and reviewed-identity exports;
- G6 append-only group review;
- G7 provider-neutral group advisory boundary.

These are reusable transitional capabilities. Their presence does not mean that the target GF-1 through GF-12 pipeline has been implemented.

## AI/provider state

- A Claude group-advisory adapter exists in the repository.
- Claude live testing and provider progression are paused pending CEO direction.
- Groq remains reference-only.
- No provider is selected as final.
- `GROUP_LLM_PROVIDER` defaults to `none`.
- Provider work is outside GF-0 and outside the deterministic pipeline.

## Current and target pair-path status

Pair machinery remains operational for historical and policy-v2 legacy
compatibility. Explicit policy-v2 group-first scans no longer write the legacy
pair/G1/G2-v1 path or run GF-7 shadow comparison.

The approved target makes groups the business-domain center. Pair machinery will be reduced non-destructively after independent discovery, evidence, resolver, G2 adapter, and shadow-graduation prerequisites exist. Historical pair data remains readable.

## Next phase boundary

GF-0 through GF-10 are verified and complete. GF-11 is IN PROGRESS; GF-11A,
GF-11B, GF-11C-PRE, and GF-11C are verified bounded units. GF-11D remains
insufficient after the post-CACHE1 100k graduation rerun. No 100k performance
graduation or production-graduation claim exists. The bounded
`GF11-PERF-100K-COLD-FULL` waiver is ACTIVE and authorized independent GF-12
production-validation work to start. GF-12 is now STARTED, GF-12A1 is
VERIFIED, and GF-12A2 protocol/tooling is VERIFIED with
`HUMAN_REVIEW_DATASET_REQUIRED`; final human-reviewed production quality and
GF-12 graduation remain pending. The waiver does not revise the failed
300-second gate or complete GF-11.

## GF-11C production lexical strategy

Policy-v2 discovery now records the v5 bounded-lexical strategy contract. The
eligible-record count entering lexical discovery selects unchanged exact
indexed v4 below 25,000 and bounded rarity-aware retrieval at 25,000 and above.
The bounded primary pass is P1/R2 with 32 features, 4,096 visits, an 80-item
pool, and batches of 64. Exactly one fixed 16,384-visit second pass runs only
for primary-insufficient anchors; remaining insufficiency fails closed.

At 50k, production bounded discovery completed in 322.704 seconds, recovered
all 6,250 insufficient anchors, left zero remaining, and matched the v5 exact
reference for 500 final hybrid candidates, 20,500 persisted proposals, 13,194
neighborhoods, proposal/neighborhood fingerprints, and product coverage.
Provider calls and policy-v2 pair/G1/G2-v1/shadow writes remained zero.

The cache-load SQL-variable defect is corrected with deterministic 900-key
chunks (maximum 902 SQL parameters) without added commits or changed hit/miss
semantics. A production lexical-only 100k check completed in 98.300 seconds,
selected the bounded strategy, recovered all 12,500 insufficient anchors, and
left zero remaining. This is not 100k production graduation. CHAR_VECTOR,
cache-save, and fusion/materialization remain the measured full-pipeline
bottlenecks for subsequent GF-11 work.

## GF-11D 100k production graduation result

GF-11D is **INSUFFICIENT / NOT GRADUATED**. The pinned 100k/seed-1101,
provider-none, policy-v2 run timed out at 300.008 seconds during cache save,
before CHAR_VECTOR or GF2-GF6. One evidence-justified 900-second diagnostic
completed CATALOG (40.505 seconds), DISCOVERY (721.191 seconds), and GF4
(36.575 seconds), then timed out in GF5; GF6 was not reached.

Within completed DISCOVERY, CHAR_VECTOR was the largest production stage at
336.432 seconds, followed by cache save at 142.257 seconds and lexical retrieval
at 93.349 seconds. The run persisted 20,500 proposals, 20,687 neighborhoods,
41,706 neighborhood members, and 20,500 evidence edges. The maximum resolution
work unit was 20,113 records. Provider and deprecated pair/G1/G2-v1/shadow
writes were zero for reached stages. Accepted-group safety outcomes are
`NOT_REACHED` because GF5 did not complete.

GF-11 remains IN PROGRESS. The only next recommendation is bounded hardening of
the measured CHAR_VECTOR retrieval stage before GF-11D is rerun. GF-12 remains
not started.

## GF-11D-CHAR-PRE character bottleneck attribution

GF-11D-CHAR-PRE is verified as a benchmark-only measurement prerequisite. The
frozen production character contract was mirrored without changing production
code or parameters. Canonical isolated runs completed at 20k, 50k, and 100k.
The 100k run finished within the 450-second diagnostic bound at 277.062
instrumented seconds and reproduced 320,810,636 bucket visits, 32,000,000
exact reranks, 500,000 directed neighbors, and zero provider calls.

`CANDIDATE_POOL_SELECTION` dominated at 194.797 seconds (70.31%), versus
23.141 seconds for exact rerank, 17.515 seconds for candidate dedupulation, and
16.040 seconds for directed top-k finalization. Every anchor hit the 1,280
gather bound and retained a 320-item pool. The 20k instrumented/uninstrumented
fingerprints were identical, although instrumentation overhead was 57.75% and
is not treated as a production timing claim.

GF-11D remains insufficient and GF-11 remains IN PROGRESS. The single next
hardening target is candidate-pool selection under the unchanged frozen
character contract. GF-12 remains not started.

## GF-11D-CHAR1 exact candidate-pool selection hardening

GF-11D-CHAR1 is **VERIFIED** as a bounded, semantics-preserving optimization.
The selector now traverses finite bit-agreement priorities and only orders the
canonical-reference ties needed to fill the unchanged 320-item pool. E1-E10,
500 randomized differential cases, old/new production comparisons at 500 and
5,000 records, and isolated 20k/50k/100k fingerprints establish exact ranking
and output equivalence.

Uninstrumented isolated character time changed from 30.823 to 18.673 seconds at
20k, 205.231 to 53.507 seconds at 50k, and 264.302 to 145.483 seconds at 100k.
The instrumented candidate-pool stage improved 77.36% at 100k. A single 50k
full DISCOVERY regression completed in 187.530 seconds and reproduced exactly
20,500 proposals, 13,194 neighborhoods, and both frozen semantic fingerprints,
with zero provider requests and unchanged group-first write-deprecation policy.

GF-11D remains INSUFFICIENT / NOT GRADUATED and GF-11 remains IN PROGRESS. The
next bounded action is the frozen GF-11D 100k graduation rerun. GF-12 remains
not started.

## GF-11D post-CHAR1 100k graduation rerun

The official canonical 300-second run still timed out during cache save at
300.011 seconds, before CHAR_VECTOR and GF2-GF6. The one permitted extended
diagnostic completed DISCOVERY in 571.720 seconds, improved full-pipeline
CHAR_VECTOR from 336.432 to 144.876 seconds with unchanged fingerprint and
32,000,000 reranks, and completed GF4 in 24.708 seconds.

The diagnostic then failed GF5 after 201.772 seconds with the typed
`IDENTITYRESOLUTIONVALIDATIONERROR`; the maximum connected work unit was
20,113 records. GF6 was skipped and no partial accepted result or G2-v2
projection was published. Reached work persisted 20,500 proposals, 20,687
neighborhoods/41,706 members, and 20,500 signed evidence edges. Provider and
pair/G1/G2-v1/shadow rows remained zero.

GF-11D remains INSUFFICIENT / NOT GRADUATED, GF-11 remains IN PROGRESS, and
GF-12 is not started. The single measured blocker is the GF5 typed resolution-
validation failure; this verification task changed no production behavior.

## GF-11D post-CACHE1 100k graduation rerun

GF-11D-RERUN3 is **INSUFFICIENT / NOT GRADUATED**. The official frozen run
timed out truthfully at 300.009 seconds during retrieval fusion/materialization.
Its last checkpoint had completed CATALOG, cache load/save, lexical retrieval,
and CHAR_VECTOR, but GF2 through GF6 were not reached.

The one permitted 900-second diagnostic completed the full pipeline safely.
DISCOVERY took 324.468 seconds, GF4 23.106, corrected GF5 292.625, and GF6
32.338. GF5/GF6 retained 247 groups/494 members, 13 conflicts, five deferred
units, and 99,506 unassigned records. Provider, pair, G1, G2-v1, shadow,
accepted-cannot-link, duplicate-membership, singleton, and cross-scan counters
were zero.

CACHE1 behaved as designed on the fresh 100k database: 70,235 requested rows,
79 bounded lookup SELECTs, 71 executemany INSERTs, zero updates, zero local
commits, and 7.137 seconds. The prior 89.274-second cache-save bottleneck is no
longer the largest stage. Lexical retrieval retained the bounded fixed-second-
pass contract and recovered all 12,500 insufficient anchors. Character
retrieval retained its pool-320 contract, 32,000,000 exact reranks,
320,810,636 bucket enumerations, and stable contract fingerprint.

The official <=300-second DISCOVERY gate still fails. `CHAR_VECTOR` is the
largest newly measured DISCOVERY stage at 128.777 seconds and is the single
next hardening target. GF-11 remains IN PROGRESS and GF-12 is not started.

## GF-11 100k cold-full performance waiver

The frozen COLD_FULL 100k DISCOVERY target remains `<=300.000000 s` and is
`TARGET NOT MET`. The current fresh/disposable-state sample is 304.764270
seconds minimum, 323.791250 seconds median, 324.468367 seconds maximum,
317.674629 seconds mean, and 2.8750% coefficient of variation.

By explicit supervising architect / product-owner decision, a bounded waiver
is ACTIVE solely for roadmap progression. GF-11 remains IN PROGRESS, debt
`GF11-PERF-100K-COLD-FULL` remains OPEN, and GF-12 is NOT STARTED; START
AUTHORIZED for independent validation categories. The waiver grants neither
GF-11 performance graduation nor final production graduation and does not
weaken correctness, determinism, safety, data integrity, provider isolation,
security, or privacy. Its complete scope, expiry conditions, allowed GF-12
work, blocked claims, and regression guard are recorded in
`GF11_100K_COLD_FULL_PERFORMANCE_WAIVER.md`.

## GF-12A1 corrected canonical quality baseline

GF-12A1 is VERIFIED as validation infrastructure. The offline evaluator consumes
the authority-selected persisted/reconstructed identity-read snapshot after
production execution and compares it only then with validated
`group-first-scale-truth-v2`. Production modules do not import evaluator or
truth code.

Fresh 500, 5k, 20k, and 50k corpus-v1 runs completed with provider none. Safety
counters were zero at every scale, and three fresh 5k runs produced byte-
identical result JSON and fingerprints. The baseline reports GQ1–GQ8, secondary
pair diagnostics, status-aware outcomes, group-size buckets, and authoritative
S1–S8 scenario breakdowns. Exact recall and member coverage are weak at larger
scales and remain explicit evidence; no numeric quality threshold is authorized.

This establishes the evaluation contract and synthetic/canonical baseline, not
final human-reviewed production-quality signoff. GF-12 is STARTED, not complete.
GF-11 remains IN PROGRESS, its waiver remains ACTIVE, its cold-full debt remains
OPEN, and the 300-second target remains unchanged and unmet.

## GF-12A2 human-review protocol and blinded-pilot gate

GF-12A2 human-review protocol/tooling is VERIFIED. Pure offline contracts now
provide group-first partitions, deterministic blinded/private artifact
separation, fixed-seed stratified sampling, fail-closed human-label ingestion,
independent-reviewer agreement diagnostics, an adjudication seam, and
stratum-specific human-outcome metrics. Production modules do not import the
tooling, and synthetic smoke fixtures are explicitly ineligible as human
evidence.

The repository dataset audit found no explicitly authorized representative
non-synthetic validation dataset. The LLM demo and scale corpus are synthetic;
the sample inventory and illustrative evaluation pairs are not authorized for
human quality validation. No ordinary/customer upload was used. Therefore the
blinded pilot is NOT EXECUTED, no human labels or human-quality metrics exist,
and the state is `HUMAN_REVIEW_DATASET_REQUIRED`.

GF-12 remains STARTED, not complete. No quality/agreement threshold or final
signoff is claimed. GF-11 remains IN PROGRESS, its waiver remains ACTIVE,
`GF11-PERF-100K-COLD-FULL` remains OPEN, and the unchanged 300-second target
remains unmet.

## GF-12B1 privacy, security, and data-boundary baseline

GF-12B1 is **VERIFIED** as a bounded validation unit. PS1-PS24 passed against
the current B1-B6 boundaries with provider calls zero. The default group
provider remains `none`; offline benchmark and human-review modules cannot
dispatch providers and have no production reverse-import path. A synthetic
secret sentinel was absent from API/result serialization, business-export
allowlists, human-review artifacts, evaluation JSON, captured logs, and fixed
typed errors. Blinded/private field separation, business export exclusions,
controlled CSV failure, safe artifact identifiers, traversal rejection, and
source immutability were revalidated without production semantic, schema,
migration, dependency, provider, or frontend changes.

No blocking security finding was evidenced. Retention/deletion policy, a
repository-wide operator benchmark-output root, and deployment tenancy/
authorization policy remain documented observations or `UNSPECIFIED` policy
areas; no policy was invented. No `.env`, real secret, live provider, or
non-synthetic customer inventory was accessed. GF-12 remains STARTED, not
complete; GF-12A2 still requires an authorized human-review dataset. GF-11
remains IN PROGRESS, the waiver remains ACTIVE, debt
`GF11-PERF-100K-COLD-FULL` remains OPEN, and the 300-second target remains unmet.

## GF-12B2 recovery, failure-mode, and transactional-integrity baseline

GF-12B2 is **VERIFIED** as a bounded validation unit. RF1-RF26 passed with
provider calls zero. Test-only fault injection covered validation, GF1,
DISCOVERY, GF2/GF3's shared transaction, GF4, GF5 validation/persistence/reload,
GF6 persistence, and embedding-cache rollback. Failed scans remain terminal
non-successes and cannot pass the persisted GF9 authority boundary; final reads,
versioned review creation, and authoritative exports fail closed.

A one-time GF2 persistence failure followed by a fresh scan produced the same
proposal fingerprints, neighborhood fingerprints, GF5 resolution fingerprint,
GF6 product manifest fingerprint, and result counts as an independent identity-
aligned clean full-run control. A-fails/B-succeeds ownership isolation passed.
Narrow disposable GF6 child corruption failed closed during reconstruction.
The provider-free 500-record production-path integration completed with all
persisted safety invariants and one GF6 projection.

Production cancellation and production scan timeout are `UNSUPPORTED / NOT
IMPLEMENTED`; CPU-bound helpers have a `CANCELLATION GRANULARITY GAP`. The
existing isolated benchmark timeout remains typed, terminates and joins its
worker, and cannot report completion. Durable same-scan resume status is
`NOT_IMPLEMENTED`; committed stage rows and reconstruction/idempotency helpers
are not a production resume entry point. Current safe recovery is a new scan by
retry or restart.

No blocking recovery or integrity finding was evidenced. No production decision
semantics, schema, migration, dependency, frontend, provider, or secret boundary
changed. GF-12 remains STARTED, not complete; GF-12A2 still requires an
authorized human-review dataset. GF-11 remains IN PROGRESS, the waiver remains
ACTIVE, `GF11-PERF-100K-COLD-FULL` remains OPEN, and the 300-second target remains
unmet.

## GF-12B3 observability, runbook, and operational-readiness baseline

GF-12B3 is **VERIFIED** as a bounded validation/documentation unit. OR1-OR24
passed on one successful and one controlled failed group-first integration with
provider calls zero. Scan id, lifecycle status, timestamps, result ownership,
health/readiness, final identity-read readiness, and review/export availability
are operator-visible. Persisted orchestration stages, bounded failure categories,
GF2-GF6 counts, and provider-call counters reconcile with the authoritative
result, but several are not exposed through a public scan-status API.

The operator runbook truthfully documents synchronous HTTP submission, 200/409/
422 authority behavior, retry versus restart, and evidence capture. It explicitly
prohibits database/source repair, intermediate-result publication, failed-scan
review/export, provider enablement as recovery, and invented resume. The readiness
checklist retains public stage/failure-history telemetry, structured scan logging,
public group-provider status, enterprise database/storage, authentication,
authorization, tenancy, retention/deletion, human evidence, and final approvals as
open/not implemented/external-decision items.

One narrow operational-safety defect was corrected: unexpected scan exceptions
previously reached the HTTP 500 detail verbatim. The response now uses a fixed
`scan_failure` category/message, and a synthetic-secret regression proves the
unexpected exception text is absent. Scan decisions, lifecycle transitions,
retrieval, GF2-GF6, schema, dependencies, and frontend behavior are unchanged.

Resume, production cancellation, and production scan timeout remain
`NOT_IMPLEMENTED`. GF-12 remains STARTED, not complete; GF-12A2 still requires an
authorized human-review dataset. GF-11 remains IN PROGRESS, the waiver remains
ACTIVE, `GF11-PERF-100K-COLD-FULL` remains OPEN, and the 300-second target remains
unmet.

## GF-12C1 showable working product / demo readiness

The product owner explicitly sequenced a complete showable local working
product before deployment/integration architecture. GF-12C1 is **VERIFIED** for
that bounded milestone. The repository-owned `SYNTHETIC_ONLY` LLM demo fixture
now contains 17 records, including a third explicit synthetic motor variant to
exercise one 3-member identity hypothesis without a threshold or algorithm
change.

DEMO1-DEMO24 pass. Three fresh `group_first_primary`, provider-none scans each
completed with `visible_product_ready=true`, 10 GF2 proposals, 17 GF3
neighborhoods, 10 completed GF4 evidence edges, 4 GF5/GF6 accepted groups (1
likely and 3 review), 3 conflicts, 0 deferred work units, 8 unassigned records,
and provider calls zero. Their normalized production-semantic fingerprint is
identical. The authority-selected frontend/API flow covers summary, list,
detail/evidence, distinct conflict/deferred outcomes, append-only review create
and correction, System Group Export, and Reviewed Identity Export authority.
A controlled synthetic failed scan remains non-authoritative and cannot expose
final reads or exports.

The primary product presentation is group-first; pair evidence remains advanced
diagnostics only. The demo contract, non-Docker local runbook, 5–10 minute
presenter script, and acceptance checklist are recorded under `docs/`. Cross-
site duplicate identity is `NOT_AVAILABLE_IN_CURRENT_DEMO_FIXTURE` rather than
manufactured.

Milestone status is `SHOWABLE WORKING PRODUCT = VERIFIED` and `DEMO-READY =
YES`. Production deployment readiness is not claimed. Deployment architecture,
tenancy, application IAM/authorization, managed storage, cloud/platform work,
external integrations, production network/retention policy, and reference
hardware are deferred post-demo, not completed. GF-12 remains STARTED /
production validation incomplete; GF-12A2 remains
`HUMAN_REVIEW_DATASET_REQUIRED`. GF-11 remains IN PROGRESS, its waiver remains
ACTIVE, `GF11-PERF-100K-COLD-FULL` remains OPEN, and the unchanged 300-second
target remains unmet.
