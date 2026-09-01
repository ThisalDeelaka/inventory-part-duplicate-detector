# PRM-3 export authority clarity evidence

Classification: `PRM3_EXPORT_AUTHORITY_VERIFIED`

## Baseline and scope

PRM-3 started from the verified PRM-2 commit
`0b6ce6bd9b3fe9fd3594ab9e9b34a077ac49cbf7`. PRM-1 and PRM-2 remain
verified. This change is limited to frontend wording, action grouping,
presentation filenames, feedback, and tests. Backend/API behavior, detector
semantics, review authority, and export row membership are unchanged.

## Existing export semantics verified

The canonical System Group CSV and XLSX endpoints export machine-generated
group hypotheses. The canonical Reviewed Identity CSV endpoint exports only
sets produced by current affirmative human-review chain heads. Current Reject
and Defer decisions, superseded affirmative decisions, and unreviewed groups do
not contribute reviewed identity sets. The intentional header-only backend
behavior for zero affirmative sets remains unchanged; the frontend now prevents
a misleading empty download after deriving availability from the authoritative
current group review state.

## Product wording and behavior

The scan result now groups exports under `Export authority` with two textually
distinct cards:

- `System suggestions` / `System Group Export`: system-generated groups for
  analysis and review, explicitly not human-confirmed duplicate identities.
- `Reviewed decisions` / `Reviewed Identity Export`: current human-confirmed
  identity sets only, identified as the operationally authoritative export.

The reviewed action is `Export confirmed duplicate sets (CSV)`. When no current
affirmative set exists it is disabled and explains that review and confirmation
are required. Reject-only and Defer-only states explicitly create no reviewed
duplicate set. A partially reviewed scan explains that only currently confirmed
sets are included and that unreviewed, rejected, deferred, and superseded work
is excluded. No reviewed XLSX action was invented.

Review saves refresh export availability. Thus a current Confirm enables the
reviewed action, while a current Reject or Defer does not. Because availability
uses only the API's current review state, Confirm-to-Reject and
Confirm-to-Defer remove prior affirmative authority, while Reject-to-Confirm
adds current affirmative authority. Previous decisions remain visible in
append-only history but are not current reviewed-export authority.

## Feedback, accessibility, and filenames

Buttons have distinct accessible names for System CSV, System Excel, and
Reviewed CSV. The panel announces busy state with `aria-busy`; success/empty
messages use status semantics and failures use an alert. Error copy distinguishes
404, 409, 422, and network/request failures. Failed availability checks fail
closed and provide a reload action.

Only browser download names changed:

- `scan-<id>-system-group-suggestions.csv`
- `scan-<id>-system-group-suggestions.xlsx`
- `scan-<id>-reviewed-identity-sets.csv`

API routes and response shapes are unchanged.

## Representative verification

Automated E1-E14 cases passed for zero reviews, Reject only, Defer only, one
Confirm, multiple Confirm forms, all three supersession directions, partial
review, remaining unreviewed groups, System CSV, System XLSX, Reviewed CSV, and
404/409/422/network feedback. Source/component integration is the equivalent
product verification because no browser session was required or used.

Verification results:

- frontend tests: 130 passed;
- focused backend export/authority tests: 25 passed, with one pre-existing
  pytest configuration warning;
- production frontend build: passed;
- provider calls: 0;
- normal 5,327-row G2_V2 scan: not required.

## Deferred work

PRM-4 navigation, scan-history discoverability, processing/progress confidence,
and recovery guidance remain explicitly deferred. R18 human label execution,
identity-engine semantic work, GF11 performance debt, GF12A2 completion, and
deployment also remain outside PRM-3.
