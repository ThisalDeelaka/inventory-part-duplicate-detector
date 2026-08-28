# GF-12 Operator Runbook

## 1. System purpose and product boundary

The service identifies scan-local 2..N inventory-record identity hypotheses. The
deterministic group-first result is analytical until human review. It never
merges, deletes, rewrites, or writes inventory records back to an ERP. Pair data
is compatibility/diagnostic evidence, not the normal product result.

The System Group Export contains system hypotheses. Only confirmed reviewed
identity sets in the Reviewed Identity Export are operationally human-authoritative.

## 2. Supported current execution mode

The supported application path is a synchronous HTTP scan. `POST
/api/scans/upload` does not enqueue a background group-first job: the request
returns only after the scan completes or fails. The UI **New Scan** workflow is
the normal submission interface. API request shapes are available from
`http://127.0.0.1:8000/docs`.

For local non-Docker operation, use the repository-supported commands:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Group-first validation requires the deployed configuration to select
`IDENTITY_ORCHESTRATION_MODE=group_first_primary`. Configuration changes create
a different semantic run; they never resume an existing scan.

## 3. Pre-run checks

Before accepting a scan:

1. `GET /health` must return `status=healthy`. This is liveness only.
2. `GET /ready` must return `status=ready` and `database=connected`. This is a
   narrow database/application readiness check, not production graduation.
3. `GET /api/diagnostics/summary` must return `service_status=healthy` and
   `database_status=connected`.
4. Confirm the intended orchestration configuration is group-first primary.
5. Confirm `GROUP_LLM_PROVIDER=none` from the approved deployment configuration.
6. Confirm storage is the intended database and has sufficient space. SQLite is
   the current demo/local store, not an enterprise tenancy boundary.
7. Confirm the input is authorized and within the configured upload/record caps.

Do not print the full environment or inspect/record secret values during these
checks.

## 4. Provider-none expectation

The deterministic pipeline requires zero provider calls. The authoritative
default is `GROUP_LLM_PROVIDER=none`. `GET /api/llm/status` safely reports the
legacy/demo LLM provider state and configuration readiness without exposing a
key; it does **not** currently expose `GROUP_LLM_PROVIDER`. Therefore group-
provider observability is `PARTIAL`: verify the variable name and the approved
non-secret value `none` in deployment configuration, never a credential.

Do not enable Groq or Claude to diagnose or bypass a deterministic failure.

## 5. Start or submit a scan

Use **New Scan**, validate the CSV mapping, and submit it. The equivalent current
API is the documented multipart `POST /api/scans/upload`. Validation-only is
`POST /api/scans/validate-only`. The scan request is synchronous; loss of the
client connection is not a supported cancellation request.

Record the returned `id`/`scan_id` immediately. Do not use the scan name as the
correlation key because names are not unique.

## 6. Identify and correlate a scan

- `GET /api/scans` lists scan identifiers, names, lifecycle status, record/result
  counters, start/end timestamps, scan mode, and model version.
- `GET /api/scans/{scan_id}` returns the same scan identity plus available hybrid
  retrieval metrics.
- A ready `GET /api/scans/{scan_id}/identity-read/summary` returns projection,
  orchestration, and resolution run identifiers plus a snapshot fingerprint.
- Versioned group keys and every authoritative CSV include scan/projection
  ownership. Preserve these identifiers together when escalating a case.

## 7. Determine RUNNING, FAILED, or COMPLETED

Use `GET /api/scans/{scan_id}`. `RUNNING` means no final product may be consumed.
`FAILED` is terminal non-success. `COMPLETED` is necessary but the authoritative
identity-read boundary must still be checked.

The current HTTP submission is synchronous, so another client must query the scan
endpoint to observe a persisted `RUNNING` scan while the request remains active.
No progress percentage exists.

## 8. Determine authoritative result readiness

Call `GET /api/scans/{scan_id}/identity-read/summary`:

- HTTP 200 with `read_ready=true` and `snapshot_available=true` identifies the
  selected authoritative read projection.
- HTTP 409 means the result is not ready; do not treat committed intermediate
  rows as output.
- HTTP 422 means selected persisted authority is inconsistent; preserve evidence
  and escalate for manual intervention.

Internally, publication also requires terminal successful orchestration,
`visible_product_ready=true`, valid same-scan GF5/GF6 provenance, and scan status
`COMPLETED`. Those orchestration fields and stage rows are persisted but have no
public production API; stage observability is therefore `PARTIAL`.

## 9. Read, review, and export availability

Only a ready identity-read snapshot may use:

- `GET /api/scans/{scan_id}/identity-read/groups`
- versioned identity-read group detail and review routes
- `identity-read/system-groups/export.csv`
- `identity-read/reviewed-identities/export.csv`
- `identity-read/conflicts/export.csv`
- `identity-read/deferred/export.csv`

HTTP 409/422 is a safety result, not permission to use compatibility pair exports
as substitute group authority. Never create a review or Reviewed Identity Export
for a failed/incomplete scan.

## 10. Failure categories and safe action

| Observable condition | Current evidence | Safe action |
|---|---|---|
| Input rejected before scan creation | Validation response; no scan id | Correct authorized input/mapping and retry |
| Unexpected scan failure | Fixed `scan_failure` HTTP response plus persisted `FAILED` scan when created | Record scan id, preserve storage, retry only if process/database is healthy; otherwise restart then submit a new scan |
| Persisted stage failure | Failed scan; bounded stage category is persisted internally but not publicly exposed | Escalate with scan id; maintainers may inspect persisted audit read-only |
| Identity authority not ready | HTTP 409 | Wait only if the synchronous submission is still active; otherwise treat failed terminal state according to scan status |
| Inconsistent selected projection | HTTP 422 | Manual intervention; preserve database and diagnostic identifiers |
| Cache persistence failure | Scan fails and caller rollback restores cache transaction | Retry a new scan after database health is confirmed; restart if connection/process health is uncertain |

Do not promise that the public error response identifies every low-level root
cause. Historical failure-category and last-stage API visibility is an open
observability gap.

## 11. Retry, restart, and resume

- **Retry**: submit a new scan in the same healthy process after correcting input
  or clearing a transient condition.
- **Restart**: restore a healthy backend/database connection, then submit a new
  scan.
- **Resume**: continue the same scan from a durable stage checkpoint.

Resume is **NOT_IMPLEMENTED**. Persisted stage history, reconstruction helpers,
and idempotent services are not a production resume entry point.

## 12. Cancellation and timeout status

Production scan cancellation is **NOT_IMPLEMENTED**. Production scan-level
timeout is **NOT_IMPLEMENTED**. CPU-bound discovery has a cancellation-granularity
gap. Client disconnection, process termination, or the benchmark-only timeout
worker must not be described as production cancellation/resume support.

## 13. Cache failure note

The embedding cache is a non-authoritative optimization keyed by record
fingerprint and model version. It flushes but does not commit locally. The scan
caller owns rollback. Never edit cache rows to force a scan result.

## 14. Provider-call expectation

Normal deterministic execution and all GF-12B3 validation runs require provider
calls `0`. A provider advisory, when separately authorized, is optional and never
changes deterministic evidence or authority.

## 15. Performance waiver

- `GF11-PERF-100K-COLD-FULL = OPEN`
- 100k cold-full `<=300 s` target = **NOT MET**
- GF-11 performance waiver = **ACTIVE**

This accepted governance state is not itself an incident. It is also not a
performance pass. Any material retrieval, discovery, or orchestration change
requires the canonical 100k cold-full benchmark to be rerun before GF-12 final
signoff. Do not revise the target from this runbook.

## 16. Human-validation dependency

- GF-12A2 human-review tooling = **VERIFIED**
- Authorized human-validation dataset = **REQUIRED**
- Human pilot = **NOT EXECUTED**
- Final human-quality signoff = **NOT AVAILABLE**

Tooling completion must never be presented as quality acceptance.

## 17. Observable-state inventory

| Signal | Classification | Current surface |
|---|---|---|
| `scan_id` / correlation id | `AVAILABLE` | Scan list/detail/upload response and authoritative projection ownership |
| Scan status | `AVAILABLE` | Scan list/detail and diagnostics last scan |
| Stage status / last completed stage | `PARTIAL` | Persisted immutable orchestration audit; no public API |
| Record count | `AVAILABLE` | Scan detail after terminal update; zero/default while running |
| Start/end timestamps | `AVAILABLE` | Scan detail; end is null while running |
| Stage durations | `PARTIAL` | Derivable from persisted stage timestamps; no public API |
| Failure category | `PARTIAL` | Generic safe HTTP category plus persisted bounded stage/run categories |
| Safe failure message | `AVAILABLE` | Fixed/sanitized HTTP detail; no raw unexpected exception |
| Legacy/demo provider mode | `AVAILABLE` | `/api/llm/status` |
| Group provider mode | `PARTIAL` | Approved configuration; no public status field |
| Provider-call count | `PARTIAL` | Persisted deterministic GF2/GF5 zero counters and benchmark reports; no scan-summary API |
| GF2 proposal count | `PARTIAL` | Persisted discovery run; benchmark telemetry; no public scan API |
| GF3 neighborhood count | `PARTIAL` | Persisted discovery run; benchmark telemetry; no public scan API |
| GF4 evidence status/count | `PARTIAL` | Persisted evidence run; no public scan API |
| GF5 outcome counts | `PARTIAL` | Persisted resolution and authoritative read summary expose overlapping subsets |
| GF6 projection counts | `PARTIAL` | Authoritative read summary plus persisted projection |
| `visible_product_ready` | `PARTIAL` | Persisted orchestration; authoritative 200/409/422 read contract externally represents it |
| Review/export availability | `AVAILABLE` | Authority-selected APIs return 200/409/422 |
| Production progress percentage | `NOT_AVAILABLE` | No production progress model |
| Production logs with scan correlation | `NOT_AVAILABLE` | No declared structured scan logging contract |
| Benchmark checkpoints/stage timing | `BENCHMARK_ONLY` | GF11 isolated benchmark artifacts |
| GF-11 waiver/debt | `DOCUMENTATION_ONLY` | SSOT, waiver, assessment, and this runbook |

## 18. Evidence to capture for escalation

Capture only:

- scan id, scan name if non-sensitive, scan status, scan mode, model version;
- start/completion timestamps and safe HTTP status/category;
- projection/orchestration/resolution ids and snapshot fingerprint when ready;
- `/health`, `/ready`, and diagnostics status without environment dumps;
- approved configuration version and provider mode name, never a key;
- database engine/version and free-space evidence without credentials;
- exact application commit and reproduction steps using synthetic/minimized input.

Do not attach raw customer CSVs, secrets, authorization headers, environment
dumps, benchmark truth, private human labels, or unrestricted database exports.

## 19. Actions operators must not take

Operators must not:

- manually edit GF2–GF6 rows to “repair” a scan;
- treat persisted intermediate state as final;
- create reviews or Reviewed Identity Export from failed scans;
- compare a retry using altered semantic configuration as if it were the same scan;
- enable providers to bypass deterministic failures;
- delete or mutate source records to force completion;
- claim resume when a restart/new scan is required;
- expose `.env`, credentials, raw provider responses, or full customer records;
- change the 300-second target or close its debt as incident remediation.

## 20. Final-signoff limitations

Passing health/readiness and this runbook does not establish tenant isolation,
authentication/authorization, retention/deletion policy, representative human
quality, the 100k performance target, or final production readiness. GF-12 remains
started, not complete.
