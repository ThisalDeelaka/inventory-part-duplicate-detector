# PRM-4 navigation, progress, and recovery evidence

Classification: `PRM4_NAVIGATION_PROGRESS_VERIFIED`

## Baseline and scope

PRM-4 started from verified PRM-3 commit
`c44260e653b508e0187867161ccf35aa40100569`. PRM-1, PRM-2, and PRM-3 remain
verified. The implementation changes frontend navigation, scan-history
presentation, validation freshness, synchronous request confidence, and recovery
copy only. It does not change scan execution, detector semantics, product
authority, persistence, API contracts, schema, migrations, or dependencies.

## Dashboard and historical navigation

Dashboard now reads the existing authoritative `GET /api/scans` list. It keeps a
visually distinct Latest scan and lists all earlier entries under Recent scans.
Each entry shows its existing scan ID/name, plain-language status, record count,
and completed or started time, with an `Open results` link to the unchanged
`/scans/<id>` route. No demo ID, rename, archive, or deletion behavior was added.

Actual statuses map to Completed, Processing, Failed, or a neutral unavailable
label; orchestration and projection identifiers are not primary history labels.
No-scans, empty-history, one-scan, and no-completed-scan states have truthful,
actionable copy. A completed scan with zero groups remains a valid result and is
not described as duplicate-free.

Malformed and unavailable result IDs render `Scan not available` with Return to
Dashboard, View recent scans, and Start a new scan actions. They are never
silently redirected to another scan. Valid result headers identify scan ID,
status, record count, and threshold, and expose Dashboard and New Scan directly.

## Validation confidence and freshness

Run Scan now requires a successful validation for the current file generation,
selected comparison fields, explicit column mapping, and sensitive-data mode.
The validation context is deterministic and order-stable. Changing any of those
inputs makes the result visibly out of date and disables Run Scan until validation
passes again. Server-resolved mappings are included in the successful context.
Validation success, blocked validation, 422/mapping rejection, malformed input,
server failure, and connection interruption have distinct actionable messages.
Backend validation behavior is unchanged.

## Processing confidence and submission safety

The upload request remains synchronous. While it is active, the page announces
`Processing inventory`, `The scan is still running`, and a local elapsed
`MM:SS` clock. After one minute, wording reiterates that the request remains
active, large inventories can take several minutes, and the user should not
resubmit unless an error appears. This is wording-only escalation.

There is no percentage, ETA, invented stage, polling, WebSocket, worker,
auto-retry, cancellation, or resume behavior. Relevant inputs and actions are
disabled during the request. A synchronous ref guard prevents a duplicate click
before React rerenders. A valid response routes exactly once to its returned
`/scans/<scan_id>` path with no artificial delay.

## Failure recovery and accessibility

Safe recovery distinguishes validation/mapping rejection, 422, server failure,
network interruption, and an unexpected response. Where completion is unknown,
copy does not claim persistence: it directs the user to Recent scans before a
safe retry. Errors use alert semantics; processing and validation use live status
semantics; state is conveyed in text rather than color; history links and empty
state actions are keyboard accessible; elapsed time is not the sole processing
indicator.

## N1-N18 and equivalent verification

N1-N18 all pass: empty/one/multiple scan history, historical reopening, invalid
URL recovery, validation success/failure/freshness, active and long-running
processing, duplicate-submit protection, exact completion routing, 422 and
server/network recovery, zero-group truth, and reopened PRM-1 explanation,
PRM-2 review, and PRM-3 export authority continuity.

Equivalent component/utility/source integration verification was used because a
browser session was not required. No full-real scan was run.

- full frontend suite: 148 passed;
- focused backend validation/product API tests: 31 passed, with one pre-existing
  pytest configuration warning;
- production Vite build: passed;
- provider calls: 0;
- 5,327-row G2_V2 scan: not required.

## PRM-5 handoff and continuing governance

PRM-5 alone owns rehearsal of the complete CEO demonstration, verification of
the exact pre-completed full-result and optional small-live paths, remaining
presentation blockers, and the showable-product freeze. PRM-4 does not rehearse
or freeze the demo.

R18 remains dataset-prepared with human execution deferred. GF12A2 remains
incomplete. GF11 remains in progress under its active waiver with
`GF11-PERF-100K-COLD-FULL` open. Identity semantic work remains paused,
deployment remains deferred, and the detector remains technically unfrozen from
the R12 quality perspective.
