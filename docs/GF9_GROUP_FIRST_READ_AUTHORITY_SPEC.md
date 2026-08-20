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

## GF-9B verified backend boundary

GF-9B implements `IdentityReadRepository` and `IdentityReadService` as the
canonical backend product-reader boundary. The service reads the persisted
orchestration run and exact stage source references, calls the GF-9A decision,
loads only the selected source, adapts and validates it, and accepts no current
configuration input.

Historical/no-audit and legacy-primary scans read v1. Completed
group-first-primary scans read v2 even when compatibility v1 exists. Missing or
failed v2 maps to HTTP 409. Invalid, cross-scan, provenance-incompatible, or
projection-mismatched authority maps to HTTP 422. There is no v1 fallback.

### API identity and compatibility

Existing `/identity-groups/{group_snapshot_id}` routes use v1 auto-increment
IDs and cannot encode projection-scoped targets. They remain v1-only
compatibility routes until GF-9C.

New `/identity-read` summary, list, detail, outcome, review, and advisory
eligibility routes use deterministic URL-safe `igk1` serialization of
`(scan_id, projection_contract, group_reference)`. Responses carry projection
and source-run metadata, validation mode and coverage, and fingerprints. V2
conflicts, deferred work, and unassigned records remain distinct typed outcomes.

A progressive three-member fixture remains two evaluated of three possible,
one missing non-required, and two evidence entries. No synthetic pair is
created. Pair/candidate routes remain compatibility diagnostics and never
construct authoritative groups, reviews, or advisories.

### Version-scoped G6 review

Historical G6 tables remain unchanged and semantically `G2_V1` only.
Authority-selected v1 review delegates to that chain. Additive append-only
versioned event, partition, member, and constraint tables hold v2 review
history; no historical row is rewritten or backfilled.

Chain-head lookup uses the exact opaque target. Actions validate the selected
read group's immutable stable references and retain existing safety bounds.
Derived constraints persist projection, source run, group key, source review,
and canonical endpoints. The normalized constraint loader can consume both
histories, but review never automatically re-runs or mutates GF-5/GF-6.

### Version-scoped G7 advisory

Authority-selected eligibility and requests use the opaque key. Canonical
request content and fingerprints include projection contract, source projection
run, versioned key, and source group fingerprint. Existing G7 execution is
provider-neutral and in-memory; there is no durable group-advisory table to
migrate. Historical legacy request construction defaults explicitly to v1.

A v2 `COMPLETE_PAIRWISE` review group may be eligible only when every frozen
G7 rule passes. `PROGRESSIVE_TARGETED` is ineligible with
`INELIGIBLE_PROGRESSIVE_VALIDATION_NOT_SUPPORTED`; likely groups remain
ineligible. A v1 review does not block v2, while a current review of the exact
v2 target does.

### Selector and export transition

`IdentityReadService` is canonical for new product backend reads. The old v1
latest/current selector remains unchanged for compatibility internals.

System Group Export is not inverted in GF-9B. Historical and legacy-primary
output remains unchanged. Group-first-primary export is temporarily rejected
with `Authoritative group-first System Group Export is pending GF-9C`, mapped
to HTTP 409, rather than exporting v1 compatibility data as authority. Reviewed
Identity Export remains unchanged. GF-9C owns frontend and final export work.

## GF-9C verified product graduation

### Canonical frontend reads and identity

The normal frontend consumes only `/identity-read/summary`, paged
`/identity-read/groups`, lazy group detail, and typed outcomes. Persisted-mode
authority remains entirely in `IdentityReadService`; the frontend does not read
`IDENTITY_ORCHESTRATION_MODE`, current configuration, selectors, or v1/v2
tables. HTTP 409 read-not-ready and HTTP 422 authority-inconsistent responses
are explicit product states and never trigger a legacy fallback.

Opaque `igk1` keys are passed unchanged to detail, versioned G6 review, and G7
eligibility routes. Group cards show a bounded member preview, categorical
status, exact validation mode/coverage, and exact projection-scoped review
state. Detail loads every member and only materialized evidence. Legacy v1 is
labelled `LEGACY_COMPLETE_PAIRWISE`; v2 preserves `COMPLETE_PAIRWISE` or
`PROGRESSIVE_TARGETED`. A progressive three-member group with two evaluated of
three possible relationships displays two evaluated and one missing
non-required relationship without synthesizing evidence.

### Product UX and typed outcomes

The headline is records plus potential 2..N identities, likely groups, review
groups, conflicts, deferred work, and records not safely assigned. Conflict and
deferred outcomes have separate sections, and unassigned is never called
unique. Pair candidates are available only under Advanced legacy diagnostics;
they are not the default result, review target, advisory target, headline, or
primary export.

Advisory rendering consumes backend eligibility as authority. Complete-pairwise
review groups may show eligibility; progressive groups display
`INELIGIBLE_PROGRESSIVE_VALIDATION_NOT_SUPPORTED`; likely groups remain
ineligible. The frontend starts no provider execution.

### Authority-selected exports

Canonical exports are:

```text
GET /api/scans/{scan_id}/identity-read/system-groups/export.csv
GET /api/scans/{scan_id}/identity-read/reviewed-identities/export.csv
GET /api/scans/{scan_id}/identity-read/conflicts/export.csv
GET /api/scans/{scan_id}/identity-read/deferred/export.csv
```

All load `IdentityReadSnapshot`; historical/no-audit and legacy-primary scans
therefore use v1 while group-first-primary uses v2 with no fallback. The System
Group Export has one row per member and carries projection, source-run, opaque
group key, status, validation mode, and exact coverage. It has no Part A/Part B,
pair score, synthetic pair, or averaged group confidence columns. Conflict and
deferred CSVs remain separate typed, outcome/member-shaped analytical exports.

The canonical Reviewed Identity Export is confirmed-only operational output.
V1 is derived from the unchanged historical G6 chain; v2 bulk-loads only the
current exact versioned chain. `CONFIRM_ALL`, `CONFIRM_SELECTED`, and `SPLIT`
produce their frozen confirmed partitions; `KEEP_SEPARATE` and `UNSURE` produce
no operational duplicate identity set, and unselected members are not inferred
as singletons. Existing G5/G6 CSV routes and schemas remain compatibility
routes and retain their established bytes and audit behavior.

### Graduation evidence and compatibility

A decisive fixture with compatibility v1 `{A,B,C}` and authoritative v2
`{A,B}` plus deferred `C` shows, reviews, and exports only v2 truth. Historical
and legacy-primary fixtures remain v1 without read-time v2 creation. A missing
required v2 produces authority errors across UI and exports, while a completed
zero-group snapshot produces a valid empty result/export.

The frontend makes one paged list request and one detail request when a group is
opened; review and advisory state are separate on-demand requests rather than
per-member or per-pair calls. Controlled v2 System Group and Reviewed Identity
exports used 16 and 17 SELECTs. This is bounded query-shape evidence, not a
100k-readiness claim. GF-9 is complete; GF-10 owns pair-write deprecation.
