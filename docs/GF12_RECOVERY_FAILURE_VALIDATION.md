# GF-12B2 Recovery, Failure-Mode, and Transactional-Integrity Validation

## Scope and result

This validation exercises current recovery behavior without redesigning the
runtime. It uses deterministic synthetic records, disposable SQLite state, test-
only exceptions, and existing benchmark timeout contracts. It makes no provider
call and does not access environment files, secrets, customer inventory, or
external systems.

Result: **RECOVERY/FAILURE-MODE/TRANSACTIONAL-INTEGRITY BASELINE VERIFIED**.
The baseline proves fail-closed publication, caller-owned rollback, deterministic
fresh rerun, and cross-scan isolation. Resume status: `NOT_IMPLEMENTED`.

The terms are deliberately distinct:

- **RETRY** submits a new scan after correcting input or clearing a transient
  condition in a healthy process.
- **RESTART** restores a healthy process and then submits a new scan.
- **RESUME** would continue the same scan from an identity-bound durable
  checkpoint. The current runtime does not do this; reconstruction helpers are
  not resume checkpoints.

## State and transaction map

| Node | Reads | Writes | Flush boundary | Commit boundary | Rollback owner | Readable after stage? | Authority | Retry/restart | Durable resume seam |
|---|---|---|---|---|---|---|---|---|---|
| Scan validation | Input dataframe and selected fields | None | None | None | None | No scan exists on failure | Validation only | Correct input and retry | No |
| Scan/orchestration start | Validated request and frozen policy plan | `DuplicateScan(RUNNING)`, `ScanOrchestrationRun(RUNNING)` | Repository flushes as needed | Each start is committed before GF1 | Start repositories | Status/audit only | Intermediate | New scan; restart if process health is uncertain | No |
| CATALOG / GF1 | Usable source rows | Immutable canonical `ScanRecordSnapshot` rows | Batched catalog flush | Caller commits the complete catalog, then commits its stage audit | `ScanRunner` | Catalog may be inspected internally; not a final product | Intermediate prerequisite | New scan | No |
| DISCOVERY start | GF1 catalog and configuration | `IdentityDiscoveryRun(RUNNING)` | Service flush | Caller commits the RUNNING checkpoint | `ScanRunner` | Status-qualified checkpoint | Intermediate | New scan | No |
| GF2 proposals | Catalog, deterministic retrieval/scoring output | `IdentityNeighborProposal` rows and discovery metrics | Service flush | No GF2-only commit | `ScanRunner` | Not separately published | Intermediate | New scan | No |
| GF3 neighborhoods | GF2 proposals and catalog | Neighborhood/member rows; discovery becomes `COMPLETED` | Service flush | One caller commit publishes GF2+GF3 atomically | `ScanRunner` | Completed discovery is durable but not product authority | Intermediate | New scan | No |
| GF4 evidence | Completed GF2/GF3 state | Evidence run and signed edge snapshots | Service flush | Caller commits RUNNING checkpoint, then complete edge graph | `ScanRunner` | Durable evidence remains intermediate | Intermediate safety evidence | New scan | No |
| GF5 resolution | Completed same-scan GF1–GF4 and review constraints | Resolution run and child groups/conflicts/deferred/targeted rows | Service-owned flush/reload validation | Service commits RUNNING separately, then commits the complete validated result; failure commits only `FAILED` run | GF5 service | A completed GF5 row is not final without GF6/orchestration success | Intermediate resolution authority | New scan; manual intervention for corrupt prerequisites | No |
| GF6 G2-v2 projection | Completed same-scan GF5 and GF4 provenance | Projection run and complete read graph | Service-owned flush/reconstruction validation | Service commits RUNNING separately, then complete validated graph; failure commits only `FAILED` run | GF6 service | Not authoritative until orchestration selects it and completes | Candidate read projection | New scan; manual intervention for corruption | No |
| Orchestration publication | Persisted required stage results | Terminal orchestration flags and missing stage outcomes | Repository flush | `complete_scan_orchestration` commits; scan status commits afterward | Orchestration service then `ScanRepository` | Yes only when `visible_product_ready=true` and scan is `COMPLETED` | **Authoritative publication boundary** | New scan after failure | No |
| Review/read projection | Persisted terminal orchestration and selected projection | Append-only reviews only after a ready exact group is selected | Review service flushes | Review service commits append-only event | Review service | Ready scans only for authoritative GF9 reads | Authoritative read/review | Retry request; never resume scan | No |
| Embedding cache | Record fingerprint + model-scoped rows | Insert/update local vectors | Cache service flush only | None locally; surrounding retrieval caller owns commit | Caller (`ScanRunner`) | Optimization only | Non-authoritative shared cache | Retry/restart | No |
| Exports | Authority-selected identity-read snapshot | Response bytes only | None | None | None | Ready scan only; incomplete/failed returns controlled 409 | Authoritative output | Retry request after successful new scan | No |

Stage names do not imply transaction boundaries. In particular GF2 proposal
persistence and GF3 neighborhood persistence are one caller-owned transaction.
Consequently F5 is `NOT_APPLICABLE — NO SUCH DISTINCT BOUNDARY`.

## Authoritative publication boundary

Intermediate persistence is not publication. The product becomes externally
consumable only after the persisted orchestration plan has all required stages in
a successful terminal state, `complete_scan_orchestration` commits
`visible_product_ready=true`, the selected GF6 projection passes reconstruction,
and `DuplicateScan.status` commits as `COMPLETED`. `IdentityReadService` derives
authority from that persisted audit, validates same-scan GF5/GF6 provenance, and
rejects `FAILED` or incomplete runs.

The scan list may expose a failed status for observability. That is status-
qualified operational information, not an authoritative identity result.

## Failure taxonomy and injection evidence

The validation uses only:

- `EXPECTED_VALIDATION_FAILURE` for rejected input before persistence;
- `TRANSIENT_INFRASTRUCTURE_FAILURE` for a retryable healthy-state operational
  interruption (classified in the matrix; no external infrastructure invoked);
- `PERSISTENCE_FAILURE` for controlled flush/child/cache write exceptions;
- `CANCELLATION` for the inspected but unsupported production cancellation path;
- `TIMEOUT` for the existing isolated benchmark timeout seam;
- `CORRUPT_OR_INCONSISTENT_STATE` for invalid prerequisites or reconstruction;
- `UNEXPECTED_INTERNAL_FAILURE` for a controlled discovery helper exception.

Test-only monkeypatching and SQLAlchemy insert hooks inject failures at GF1, heavy
discovery, GF2, GF3, GF4, GF5 pre-validation, GF5 children, GF5 reload, GF6
children, and cache insertion. No production fault-injection branch exists.
Detailed outcomes are in [GF12_RECOVERY_FAILURE_MATRIX.md](GF12_RECOVERY_FAILURE_MATRIX.md).

## Cancellation behavior

The `/upload` production path invokes the synchronous `ScanRunner`; it is not a
background scan worker and accepts no cancellation token/event. Cancellation
before discovery, during CPU-bound discovery, between committed boundaries, and
during GF5/GF6 is therefore `UNSUPPORTED / NOT IMPLEMENTED`. This is a
**CANCELLATION GRANULARITY GAP**, not a false claim of cancellation safety.

Because no cancellation boundary returns from a production worker, worker-leak
validation is not applicable there. Ordinary injected exceptions do stop the
synchronous call, roll back the active transaction, mark the scan failed, and
publish no final result.

## Timeout behavior

There is no production scan-level timeout control, so production timeout is
`UNSUPPORTED / NOT IMPLEMENTED`. The existing isolated GF11 benchmark process is
the only relevant current timeout seam: it returns typed `TIMED_OUT`, never
`COMPLETED`, terminates and joins its worker, and inspects only its disposable
database/checkpoint. RF15-RF16 validate this contract without running 100k or
changing the 300-second production-graduation target.

## Rollback and cache behavior

GF1, GF2/GF3, and GF4 services flush under `ScanRunner` ownership. Controlled
exceptions prove that active rows roll back while earlier committed prerequisites
remain coherent. GF5 and GF6 deliberately commit a RUNNING checkpoint, validate a
fully reconstructed child graph, and then commit completion; on child or reload
failure they roll back the graph and commit only a terminal failed run.

The embedding cache never commits locally. RF13 overwrites a prior cache row and
attempts a new insert in one caller transaction, injects an insert failure, then
rolls back. The prior vector is restored and the new key is absent. This preserves
retrieval semantics and the legitimate shared model/fingerprint scope.

## Fresh rerun and idempotency evidence

RF18 injects a one-time GF2 persistence failure, submits a new scan without the
fault, and compares it with a clean disposable-database control. The proposal
payload/fingerprint set, neighborhood membership/fingerprint set, GF5 resolution
fingerprint, GF6 manifest/product fingerprint, and result counts are exactly
equal. Existing GF1, GF2, GF4, GF5, and GF6 tests separately prove same-identity
service idempotency where those service contracts permit repeat calls.

This validates `RECOVERABLE_BY_RETRY` for representative transient and persistence
failures. If the process or database connection is unhealthy, the deterministic
safe action is `RECOVERABLE_BY_RESTART` followed by a new scan.

## Resume capability and gap

Resume status: `NOT_IMPLEMENTED`. The RUNNING/COMPLETED/FAILED rows are durable
audit and atomic-publication checkpoints, but no production entry point accepts a
scan identity and resumes from GF1, GF3, GF4, GF5, or GF6. Failed discovery is
immutable and a retry requires a new scan. Load/reconstruction and service
idempotency helpers validate persisted artifacts; reconstruction helpers are not
resume checkpoints.

Therefore RF19 resume equality is not applicable. No semantic stage is skipped
and no unsupported `RESUMABLE_FROM_COMMITTED_STAGE` outcome is claimed. This does
not make current retry/restart recovery unsafe, but operational resume remains a
visible production-graduation gap.

## Corrupt state, cross-scan isolation, and output safety

RF20 removes one required GF6 child in disposable state. Reconstruction fails
closed as typed `IdentityReadAuthorityInconsistent(SELECTED_PROJECTION_INVALID)`;
the reader neither repairs nor silently serves the graph. Existing ownership
checks also reject mismatched scan IDs and invalid source references.

RF21 proves A-fails/B-succeeds: scan IDs and result ownership remain distinct,
scan A has no GF6 projection, and scan B has a complete authority-selected result.
No review or result cross-link is created. Cache sharing is restricted to its
legitimate fingerprint/model contract and failed cache writes roll back.

RF22-RF23 prove that a failed scan receives HTTP 409 from final identity read,
versioned review creation, System Group Export, Reviewed Identity Export,
conflict export, and deferred-work export. No authoritative CSV body is emitted.
Older compatibility analytical endpoints are not the group-first authoritative
publication contract and are not reclassified by this validation.

## Findings

### CRITICAL

None.

### HIGH

None.

### MEDIUM

None.

### LOW

None.

### OBSERVATION

- Production cancellation is `UNSUPPORTED / NOT IMPLEMENTED`, including a
  `CANCELLATION GRANULARITY GAP` inside CPU-bound helpers.
- Production scan timeout is `UNSUPPORTED / NOT IMPLEMENTED`; the validated
  timeout seam is benchmark-only.
- Durable same-scan stage resume is `NOT_IMPLEMENTED`; safe recovery is a new
  scan by retry/restart.
- GF2 has no independent post-commit/pre-GF3 boundary.

None of these observations creates false success, partial authoritative
publication, cross-scan contamination, rollback inconsistency, rerun inequality,
cannot-link bypass, or unsafe resume. There is no blocking GF-12B2 finding.

## Tests

`backend/tests/test_gf12_recovery_failure.py` defines RF1-RF26. Small deterministic
fixtures cover every applicable failure boundary and a complete GF2–GF6 equality
run. RF18 also runs the provider-free full production path at 500 records and
requires completion, all persisted safety invariants, zero providers, and one GF6
projection. The existing scale suite additionally verifies deterministic
fingerprints and isolated 64-record runs. The full backend regression remains the
release gate; the 50k/100k benchmark is intentionally not rerun here.
