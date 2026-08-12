# Immutable identity-group snapshots

The identity-group architecture is deliberately layered:

- G0 classifies deterministic pair edges and enforces cannot-link safety.
- G1 computes a bounded constrained group projection in memory.
- G2 persists an immutable scan-time snapshot of that projection.
- G3 exposes those persisted snapshots through a typed, read-only API.

Persisted G2 groups are scan-time hypotheses, not permanent identity truth. They
do not merge inventory, select a canonical item, or create an identity that spans
scans. Cross-scan durable identity entities are deferred until later phases.

## Snapshot contract

One `IdentityGroupProjectionRun` records the scan, projection algorithm,
classifier identifier, deterministic engine version, evidence fingerprint,
validation bound, and G1 metrics. Its accepted groups and diagnostic families
reference scan-local `ScanRecordSnapshot` rows through ordered member rows.
Accepted groups retain the exact G1 status, pair counts, evidence completeness,
reason codes, and a separate UOM/mapping summary. Conflicting, oversized, and
ambiguous families are diagnostic snapshots and never accepted groups.

Each bounded internal edge records its class, reasons, ordered endpoints, and one
of these provenance sources:

- `PERSISTED_CANDIDATE`
- `PERSISTED_EXCLUSION`
- `HUMAN_FEEDBACK`
- `G1_LOCAL_RESCORING`

G1 locally rescored internal relationships are persisted only as group-snapshot
provenance and do not become ordinary candidate rows. LLM advisory data is not
an identity-edge authority.

## Immutability, idempotency, and transactions

The idempotency identity is `(scan_id, projection_algorithm_version,
evidence_fingerprint)`. Repeating an identical projection returns the existing
run and graph. A changed deterministic evidence manifest receives a new run;
existing snapshots are never updated or overwritten.

Record, run, group, diagnostic, member, and edge rows are written in one database
transaction. Validation rejects inconsistent counts, non-canonical membership,
incomplete internal-pair evidence, or a cannot-link inside an accepted group
before commit. Any persistence failure rolls back the complete graph.

G2 is invoked explicitly through the internal snapshot service. It is not added
to the normal scan path. The additive migration
creates empty snapshot tables for historical databases and does not fabricate or
backfill groups for older scans.

## G3 read-only API

G3 exposes persisted scan-time hypotheses; it does not calculate, recompute, or
modify identity. Accepted groups are not confirmed duplicates, and likely status
is not a human confirmation. Conflicting, oversized, and ambiguous diagnostic
families remain separate from accepted groups. Existing pair APIs and the legacy
connected-component route remain available unchanged for compatibility and
pair-level diagnostics.

The snapshot endpoints are:

- `GET /api/scans/{scan_id}/identity-group-projections`
- `GET /api/scans/{scan_id}/identity-groups/summary`
- `GET /api/scans/{scan_id}/identity-groups`
- `GET /api/scans/{scan_id}/identity-groups/{group_snapshot_id}`
- `GET /api/scans/{scan_id}/identity-group-diagnostics`
- `GET /api/scans/{scan_id}/identity-group-diagnostics/{diagnostic_snapshot_id}`

List and detail endpoints use the latest completed projection by default. An
explicit `projection_run_id` selects only that immutable completed run; runs from
another scan are not accepted and failed runs are never substituted. Group lists
use `limit`/`offset` pagination (maximum 100), optional accepted-status and size
filters, and deterministic status/size/key ordering. Diagnostics have their own
bounded list and detail responses. Historical scans without a snapshot return a
typed empty summary/list and never trigger projection.

Group detail exposes ordered persisted members and bounded internal-edge evidence.
The UOM/mapping summary is a separate structure and is not an identity decision.
`G1_LOCAL_RESCORING` remains an explicit evidence source with no implied candidate
row. G3 provides no write, review, merge, export, UI, or LLM operation.
