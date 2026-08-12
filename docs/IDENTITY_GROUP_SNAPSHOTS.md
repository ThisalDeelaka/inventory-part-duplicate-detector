# Immutable identity-group snapshots

The identity-group architecture is deliberately layered:

- G0 classifies deterministic pair edges and enforces cannot-link safety.
- G1 computes a bounded constrained group projection in memory.
- G2 persists an immutable scan-time snapshot of that projection.

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
to the normal scan path and exposes no new production API. The additive migration
creates empty snapshot tables for historical databases and does not fabricate or
backfill groups for older scans.
