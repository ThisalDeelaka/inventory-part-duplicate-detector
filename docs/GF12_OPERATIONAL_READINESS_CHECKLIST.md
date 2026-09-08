# GF-12 Operational-Readiness Checklist

Allowed checklist states are `VERIFIED`, `OPEN`, `NOT_IMPLEMENTED`,
`NOT_APPLICABLE`, and `REQUIRES_EXTERNAL_DECISION`. A missing decision or
capability never receives an implied green status.

| Category | Item | Status | Evidence / required action |
|---|---|---|---|
| Build/test | GF-12B3 focused observability regression | `VERIFIED` | OR1–OR24 pass |
| Build/test | Full backend regression | `VERIFIED` | Required release-gate suite passes; optional sparse-dot tests may skip |
| Database/storage | Current ORM/schema startup and disposable integration | `VERIFIED` | Health/readiness and bounded integration exercise current persistence |
| Database/storage | Enterprise production database/storage architecture | `OPEN` | Current SQLite/local mode is not a final enterprise deployment claim |
| Provider mode | Deterministic/group provider configured as `none` | `VERIFIED` | Approved configuration plus zero provider counters/tests |
| Provider mode | Public group-provider status field | `OPEN` | Legacy `/api/llm/status` does not expose `GROUP_LLM_PROVIDER` |
| Scan execution | Synchronous HTTP submission documented | `VERIFIED` | UI and `POST /api/scans/upload` are current interfaces |
| Scan execution | Background job orchestration | `NOT_IMPLEMENTED` | Out of GF-12B3 scope |
| Observability | Scan id, lifecycle status, timestamps, counts | `VERIFIED` | Scan list/detail APIs |
| Observability | Authoritative-read readiness | `VERIFIED` | Identity-read 200/409/422 boundary |
| Observability | Public stage/last-checkpoint/failure-category API | `OPEN` | Durable audit exists, but there is no public operator API |
| Observability | Structured scan-correlated production logging | `NOT_IMPLEMENTED` | No declared structured logging contract |
| Observability | Production progress percentage | `NOT_IMPLEMENTED` | No percentage model is invented |
| Observability | Health and readiness endpoints | `VERIFIED` | `/health`, `/ready`, and diagnostics are narrow and secret-safe |
| Failure/recovery | Failed scans remain non-authoritative | `VERIFIED` | GF-12B2 and OR failure integration |
| Failure/recovery | Retry/restart guidance | `VERIFIED` | Operator runbook distinguishes both actions |
| Failure/recovery | Durable same-scan resume | `NOT_IMPLEMENTED` | New scan required |
| Failure/recovery | Production cancellation | `NOT_IMPLEMENTED` | Cancellation-granularity gap remains visible |
| Failure/recovery | Production scan timeout | `NOT_IMPLEMENTED` | GF11 timeout is benchmark-only |
| Review/export | Final read/review/export authority | `VERIFIED` | Failed/incomplete scans receive controlled 409/422 responses |
| Privacy/security | Secret-safe health/status/failure diagnostics | `VERIFIED` | Synthetic sentinel regression and fixed unexpected-error response |
| Privacy/security | Raw-record/truth/human-label exclusion | `VERIFIED` | Operator surfaces and evidence checklist exclude these fields |
| Privacy/security | Authentication and role authorization | `OPEN` | Current application has no final production authorization boundary |
| Human quality | GF-12A2 tooling | `VERIFIED` | Protocol/tooling exists |
| Human quality | Authorized representative dataset | `REQUIRES_EXTERNAL_DECISION` | `HUMAN_REVIEW_DATASET_REQUIRED` |
| Human quality | Human pilot and final quality signoff | `OPEN` | Pilot not executed; signoff unavailable |
| Performance | GF-11 waiver | `VERIFIED` | Waiver is ACTIVE and represented truthfully |
| Performance | `GF11-PERF-100K-COLD-FULL` | `OPEN` | `<=300 s` target remains NOT MET |
| Performance | Rebenchmark after material retrieval/discovery/orchestration change | `OPEN` | Required before GF-12 final signoff when such a change occurs |
| Retention/policy | Data/artifact retention and deletion policy | `REQUIRES_EXTERNAL_DECISION` | Current policy remains `UNSPECIFIED` |
| Deployment | Production tenancy model | `REQUIRES_EXTERNAL_DECISION` | No approved tenant-isolation contract |
| Deployment | Deployment-specific authorization policy | `REQUIRES_EXTERNAL_DECISION` | Requires owner/security decision |
| Deployment | Monitoring vendor/telemetry service | `NOT_APPLICABLE` | No vendor is selected or required by GF-12B3 |
| Final signoff | GF-11 100k performance gate | `OPEN` | Waived only for independent GF-12 work, not graduated |
| Final signoff | Representative human-quality evidence | `OPEN` | Dataset authorization and pilot remain outstanding |
| Final signoff | Architecture/product/data-steward approval | `REQUIRES_EXTERNAL_DECISION` | Graduation approvals have not been issued |
| Final signoff | GF-12 production graduation | `OPEN` | GF-12 remains STARTED, not complete |

## Release-review decision

The current baseline is operable as the documented synchronous, local/pilot
system with fail-closed identity authority. It is not final enterprise-production
signoff. Release reviewers must carry every `OPEN`, `NOT_IMPLEMENTED`, and
`REQUIRES_EXTERNAL_DECISION` item forward rather than silently accepting it.
