# GF-9 group-first read authority specification

## Scope and phase boundary

GF-9 remains the frozen roadmap phase for group-first API, UI, and export
inversion. Its bounded delivery units are:

1. GF-9A — read-authority/projection contracts and pure v1/v2 adapters;
2. GF-9B — backend current-reader, API, review, and advisory inversion;
3. GF-9C — frontend and export inversion plus end-to-end graduation.

GF-9A defines no persistence and switches no current reader. G2-v1 remains the
current source for existing G3, G5, G6, and G7 behavior until GF-9B. It changes
no scan stage, readiness rule, API, frontend, export, review, advisory,
provider, pair write, scorer, resolver, or G2 persistence behavior.

## Persisted-mode authority

Future readers must use the orchestration audit persisted for the scan, never
the process's current configuration:

| Persisted scan history | Required read projection |
| --- | --- |
| No GF-8 orchestration audit | `G2_V1` |
| Completed `legacy_primary` | `G2_V1` |
| Completed `group_first_primary` | `G2_V2` |

Historical scans are not backfilled or reinterpreted, and reads create no v2
data. A running, incomplete, or failed orchestration is not read-ready.

For a completed group-first-primary scan, missing or failed v2 is
`READ_NOT_READY`; cross-scan, provenance-incompatible, or invalid v2 is
`READ_AUTHORITY_INCONSISTENT`. Existing compatibility v1 must never silently
replace required v2 truth.

## Neutral snapshot and versioned identity

`IdentityReadSnapshot` carries its `G2_V1` or `G2_V2` projection contract,
source projection and orchestration identities, optional v2 resolution source,
accepted groups, conflicts, deferred work, unassigned records, typed counts,
and a semantic fingerprint. Pairs are not primary read entities; pair
candidates and pair diagnostics remain advanced/internal diagnostics.

`VersionedIdentityGroupKey` is `(scan_id, projection_contract,
group_reference)`. Therefore a textual group `X` in v1 is not the same review
or advisory target as textual group `X` in v2, even when membership happens to
match. GF-9B will use this identity when it changes G6/G7 targeting; GF-9A does
not modify their persistence.

## Adapter semantics

The v1 adapter preserves accepted status, membership, member order, stable
source-row identity, display fields, and legacy complete N-choose-2 validation.
It invents no v2 conflict, deferred, progressive, targeted-evidence, risk, or
resolution provenance.

The v2 adapter preserves accepted status and membership, `COMPLETE_PAIRWISE` or
`PROGRESSIVE_TARGETED` mode, exact validation coverage, bounded internal
evidence, group evidence and risk summaries, conflicts, deferred work,
unassigned records, and source-resolution provenance. A progressive three
member review group with two evaluated of three possible pairs remains two
evaluated with one missing non-required pair; no synthetic third edge is
created.

Duplicate-valued source rows remain distinct through record ID, stable GF-1
reference, and source-row index. Allowlisted inventory display fields are
carried for future group UI and export adapters.

## Validation and fingerprints

Pure validators reject cross-scan data, duplicate accepted membership,
singletons, count or coverage drift, invalid status/projection combinations,
v1 progressive claims, loss of v2 progressive semantics, duplicate versioned
keys, invalid conflict/deferred references, accepted/unassigned overlap, and
group or snapshot fingerprint mismatch.

Fingerprints use canonical SHA-256 over projection, scan, stable record
references, source rows, ordered membership, status, validation mode and
coverage, summaries, evidence, outcomes, and source semantic fingerprints.
Collection input order, current configuration, timestamps, provider data,
secrets, randomness, and avoidable database run IDs do not affect them.

## Future API and export rules

The future System Group Export source is the authority-selected
`IdentityReadSnapshot`: historical and legacy-primary scans use v1;
group-first-primary scans use v2. Reviewed Identity Export remains separate and
human-authoritative.

Future APIs add projection and source metadata without discarding v2-only
coverage, conflict, deferred, and unassigned semantics. Those reader, API,
review, advisory, UI, and export changes belong exclusively to GF-9B/GF-9C.
