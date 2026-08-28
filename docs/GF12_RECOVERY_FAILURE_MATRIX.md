# GF-12B2 Recovery and Failure Matrix

## Classification contract

Recovery outcomes in this matrix use only `RECOVERABLE_BY_RETRY`,
`RECOVERABLE_BY_RESTART`, `RESUMABLE_FROM_COMMITTED_STAGE`,
`MANUAL_INTERVENTION_REQUIRED`, or `UNSUPPORTED / NOT IMPLEMENTED`. Failure
types use only the GF-12B2 taxonomy. A retry means a new scan request in the
same healthy process. A restart means a fresh process followed by a new scan.
Resume means continuing the same scan from a durable checkpoint; that capability
does not exist in the current production runner.

## Stage-boundary matrix

| ID | Failure location | Failure type | State persisted | Transaction result | Externally visible state | Safe next action | Resume? | Rerun equality? | Finding |
|---|---|---|---|---|---|---|---|---|---|
| F1 | Before scan persistence: input validation | `EXPECTED_VALIDATION_FAILURE` | None | No transaction begins | No scan and no final result | `RECOVERABLE_BY_RETRY` after correcting input | No | Yes, valid retry follows the normal deterministic path | PASS |
| F2 | GF1 catalog after materialization/flush, before commit | `PERSISTENCE_FAILURE` | Failed scan and failed orchestration audit only | Catalog transaction rolls back; no partial catalog rows | Failed status is observable; no authoritative identity read | `RECOVERABLE_BY_RETRY` with a new scan | No | Covered by deterministic fresh-run evidence | PASS |
| F3 | DISCOVERY computation before GF2 persistence | `UNEXPECTED_INTERNAL_FAILURE` | Completed GF1 catalog; failed discovery/run audit | Uncommitted discovery work rolls back; discovery checkpoint becomes `FAILED` | Status-qualified failure only | `RECOVERABLE_BY_RETRY`; restart if process health is uncertain | No | Covered by deterministic fresh-run evidence | PASS |
| F4 | GF2 proposal persistence | `PERSISTENCE_FAILURE` | GF1 plus failed discovery/audit | GF2 rows roll back | No GF2/GF3/final authoritative output | `RECOVERABLE_BY_RETRY` with a new scan | No | Exact clean-control equality verified in RF18 | PASS |
| F5 | After GF2 commit but before GF3 completion | `PERSISTENCE_FAILURE` | `NOT_APPLICABLE` | **NOT_APPLICABLE — NO SUCH DISTINCT BOUNDARY**: GF2 and GF3 flush into one caller-owned transaction and commit together | No separately published GF2 checkpoint exists | `UNSUPPORTED / NOT IMPLEMENTED` as a resume point | No | Not applicable | OBSERVATION |
| F6 | GF3 neighborhood persistence | `PERSISTENCE_FAILURE` | GF1 plus failed discovery/audit | GF2 and GF3 roll back together | No proposals, neighborhoods, or final result | `RECOVERABLE_BY_RETRY` with a new scan | No | Covered by deterministic fresh-run evidence | PASS |
| F7 | GF4 evidence persistence | `PERSISTENCE_FAILURE` | Completed GF1–GF3; failed evidence run; failed scan/audit | Partial GF4 edges roll back | No authoritative identity result | `RECOVERABLE_BY_RETRY` with a new scan | No | Covered by deterministic fresh-run evidence | PASS |
| F8 | GF5 pre-persistence validation/invocation | `CORRUPT_OR_INCONSISTENT_STATE` | Completed GF1–GF4; no GF5 run | No GF5 transaction is published | No authoritative identity result | `MANUAL_INTERVENTION_REQUIRED` for actual inconsistent prerequisites; retry for a transient injected exception | No | Not claimed for corrupt prerequisites | PASS, fail closed |
| F9 | GF5 child persistence | `PERSISTENCE_FAILURE` | Completed GF1–GF4 and a terminal `FAILED` GF5 run | GF5 children roll back; failure checkpoint commits | No authoritative identity result | `RECOVERABLE_BY_RETRY` with a new scan | No | Covered by deterministic fresh-run evidence | PASS |
| F10 | GF5 persisted-child reload/reconstruction before completion commit | `CORRUPT_OR_INCONSISTENT_STATE` | Completed GF1–GF4 and a terminal `FAILED` GF5 run | Candidate GF5 payload and completion mutation roll back | No authoritative identity result | `MANUAL_INTERVENTION_REQUIRED` for real corruption; new scan after infrastructure repair for transient reload failure | No | Not claimed for deliberately corrupt state | PASS, fail closed |
| F11 | GF6 child persistence/reconstruction | `PERSISTENCE_FAILURE` | Completed GF1–GF5 and a terminal `FAILED` GF6 run | GF6 children roll back; GF5 remains an intermediate committed result | Failed status only; the read authority rejects the incomplete product | `RECOVERABLE_BY_RETRY` with a new scan | No | Covered by deterministic fresh-run evidence | PASS |
| F12 | Embedding-cache save insert after existing-row mutation | `PERSISTENCE_FAILURE` | Prior committed cache entry only | Caller rollback restores the prior value and removes the new value | Cache is not an authoritative product result | `RECOVERABLE_BY_RETRY`; restart if database connection health is uncertain | No | Cache semantics and deterministic fresh rerun verified | PASS |

## Cancellation and timeout matrix

| Boundary | Failure type | Current behavior | Safe next action | Resume? | Finding |
|---|---|---|---|---|---|
| Before DISCOVERY heavy work | `CANCELLATION` | The synchronous production `ScanRunner` accepts no cancellation token/event | `UNSUPPORTED / NOT IMPLEMENTED`; do not report cancellation as success | No | `CANCELLATION GRANULARITY GAP` |
| During DISCOVERY CPU work | `CANCELLATION` | No cooperative cancellation seam exists | `UNSUPPORTED / NOT IMPLEMENTED`; process restart is operational termination, not same-scan resume | No | `CANCELLATION GRANULARITY GAP` |
| Between committed stages | `CANCELLATION` | No production cancellation request/state exists | `UNSUPPORTED / NOT IMPLEMENTED`; retry as a new scan after process health is established | No | `CANCELLATION GRANULARITY GAP` |
| During GF5/GF6 | `CANCELLATION` | No cooperative cancellation seam exists; ordinary exceptions remain fail-closed | `UNSUPPORTED / NOT IMPLEMENTED` as cancellation | No | `CANCELLATION GRANULARITY GAP` |
| Production scan timeout | `TIMEOUT` | No production scan-level timeout seam exists | `UNSUPPORTED / NOT IMPLEMENTED`; an operator may restart and submit a new scan | No | OBSERVATION |
| Isolated GF11 benchmark process timeout | `TIMEOUT` | Parent terminates and joins the worker; result is typed `TIMED_OUT`, never `COMPLETED` | `RECOVERABLE_BY_RESTART` of the isolated benchmark | No | PASS; benchmark-only behavior |

## Cross-scan and publication findings

- A failed scan retains only stage-appropriate audit/intermediate state. Scan B
  receives a distinct scan identity and produces a complete GF6 result without
  reusing scan A's partial GF2, GF3, GF5, review, or projection rows.
- Shared embedding-cache rows remain legitimately keyed by record fingerprint and
  model version. Failed caller-owned writes roll back, so this shared optimization
  cannot introduce failed-write residue into later retrieval semantics.
- A scan becomes authoritative only after the required orchestration stages are
  terminal-successful, `visible_product_ready` is true, and the scan status commits
  as `COMPLETED`. GF1–GF5 rows are intermediate even when durably committed.
- Failed scans return a controlled not-ready response from authority-selected
  identity reads, reviews, and all four authoritative CSV exports.
