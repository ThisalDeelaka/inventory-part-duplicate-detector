# Current project assessment

## Document role

This document describes the observed repository state. It is not a requirements or architecture authority and never overrides `PROJECT_SSOT.md` or the approved group-first architecture package.

## Assessed baseline

- Branch: `llm-assisted-mvp`.
- Baseline HEAD before the GF-1 implementation commit: `bdefe9dad25b112c92f7f40af358e361d37e59f0`.
- Baseline HEAD before the GF-0 governance commit: `f58b3f881a70a2c0d704092c929df55cd878dc90`.
- Architecture package commit: `f58b3f881a70a2c0d704092c929df55cd878dc90` (`Define group-first identity architecture`).
- Protected tag `deterministic-demo-v1`: `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Previously observed legacy `MVP_LLM_DEMO_SSOT.md` blob: `4538df1668cf189394bc3eb728fee946c6e490ee`.

The current system classification is hybrid/transitional. The STAGE-1B deterministic/group product smoke test passed, and a normal scan currently generates G2 groups. The discovery and decision core remains pair-first, while group APIs, UI, exports, review, and advisory boundaries project or consume group results.

The group-first architecture is approved and documented but is not yet implemented as the normal discovery and resolution core. GF-0 is verified. GF-1 is verified. GF-2 and all later production implementation phases have not started.

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

With GF-0 and GF-1 verified, the only approved next production implementation phase is GF-2, Discovery-Run and Neighbor-Proposal Contracts. No later GF phase should begin by skipping its prerequisites.
