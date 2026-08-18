# Current project assessment

## Document role

This document describes the observed repository state. It is not a requirements or architecture authority and never overrides `PROJECT_SSOT.md` or the approved group-first architecture package.

## Assessed baseline

- Branch: `llm-assisted-mvp`.
- Baseline HEAD before the GF-4-PRE safety correction: `d294b6ca5b77a9d8a6b185b514484b75fa20424a`.
- Baseline HEAD before the GF-3 implementation commit: `b5ca5be28475c9e7205c7cc4544d685d2c749578`.
- Baseline HEAD before the GF-2 implementation commit: `7614a1ea84eef0649caecbd11a011b041d3a9ba7`.
- Baseline HEAD before the GF-1 implementation commit: `bdefe9dad25b112c92f7f40af358e361d37e59f0`.
- Baseline HEAD before the GF-0 governance commit: `f58b3f881a70a2c0d704092c929df55cd878dc90`.
- Architecture package commit: `f58b3f881a70a2c0d704092c929df55cd878dc90` (`Define group-first identity architecture`).
- Protected tag `deterministic-demo-v1`: `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Previously observed legacy `MVP_LLM_DEMO_SSOT.md` blob: `4538df1668cf189394bc3eb728fee946c6e490ee`.

The current system classification is hybrid/transitional. The STAGE-1B deterministic/group product smoke test passed, and a normal scan currently generates G2 groups. The discovery and decision core remains pair-first, while group APIs, UI, exports, review, and advisory boundaries project or consume group results.

The group-first architecture is approved and documented but is not yet implemented as the normal resolution core. GF-0, GF-1, GF-2, and GF-3 are verified. GF-4 and all later production implementation phases have not started.

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

GF-4 remains not started. Its initial implementation review correctly identified that an identical one-token category description could bypass the existing generic-description lexicon and become strong identity support from text and matching context alone.

- The deterministic genericity guard now treats a single alphabetic token as insufficiently specific while preserving alphanumeric model-like tokens on the normal scoring path.
- Generic text without independent strong identity evidence cannot produce `LIKELY_DUPLICATE` or `STRONG_SUPPORT`. Identical generic text remains review evidence rather than proof of difference.
- The only current rescue is the scorer's existing strong part-number relationship at its established threshold; site, UOM, accounting, category, or fuzzy/TF-IDF agreement does not rescue generic text.
- Protected technical contradictions remain `CANNOT_LINK`, context differences alone remain non-terminal, and specific clear matches retain their existing results.
- Focused scoring and G0/G1/G2 safety regressions plus the complete backend, frontend, and build gates verify the correction. GF-4 may now resume; its evidence persistence remains not started.

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

Current pair machinery remains operational for compatibility and as internal evidence. It is still central to current discovery and decision computation.

The approved target makes groups the business-domain center. Pair machinery will be reduced non-destructively after independent discovery, evidence, resolver, G2 adapter, and shadow-graduation prerequisites exist. Historical pair data remains readable.

## Next phase boundary

With GF-0 through GF-3 verified, the only approved next production implementation phase is GF-4, Independent Signed Identity Evidence. No later GF phase should begin by skipping its prerequisites.
