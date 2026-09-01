# Product Recovery CEO User-Journey Audit

## PRM-3 completion addendum

PRM-3 is VERIFIED. The audited export-authority blocker is addressed with
separate System suggestions and Reviewed decisions sections, truthful
zero-confirmed and partial-review guidance, current chain-head supersession
wording, distinct filenames, and accessible success/error feedback. Export row
membership, review authority, and detector semantics remain unchanged. PRM-1
and PRM-2 remain verified. PRM-4 navigation, scan-history discoverability,
processing/progress confidence, and recovery guidance are now the smallest next
task.

## PRM-2 completion addendum

PRM-2 is VERIFIED. The audited human-review clarity blocker is addressed with
plain Confirm / Reject / Defer choices, pre-save consequences, explicit saved
Human decision outcomes, Change decision wording, and visibly distinct Current
and Previous history. Review-flow mojibake and ambiguous error feedback are fixed
without changing append-only authority or reviewed-set semantics. PRM-1 remains
verified. PRM-3 export-authority distinction is now the smallest next task.

## PRM-1 completion addendum

PRM-1 is VERIFIED. The audited count/raw-JSON comprehension blocker is addressed
by a bounded persisted-evidence explanation mapper and prominent list/detail UI.
Conflict and deferred outcomes use distinct non-duplicate language; human review
is still displayed separately and remains authoritative; advanced evidence is
retained. Detector and export semantics are unchanged. PRM-2 is now the smallest
next task: make Confirm / Reject / Defer unmistakable and polish saved-review
interaction without changing authority.

## Decision

Classification: `PRM0_PRODUCT_RECOVERY_AUDIT_COMPLETE`

The repository has a working human-in-the-loop group review product, but it is
not yet a first-time-user-ready CEO demonstration. The complete authority path
exists: CSV intake, synchronous current-product scan, authoritative group-first
read, append-only group review, human-confirmed reviewed identity sets, and
authority-selected exports. The smallest missing user-visible slice is a
plain-language, group-specific explanation assembled from evidence already
present in the authoritative group detail. Detector semantics do not need to
change to close it.

This audit starts the Product Recovery Milestone. Semantic detector work is
paused. R14-R18 remain valid history and future identity-engine research, but
R18 human-label execution is deferred. Deployment remains deferred. GF-11
remains in progress under its active waiver, and the detector remains
technically unfrozen because the R12 full-real quality freeze failed.

## Strategic reset and current product promise

The immediate product promise is:

> A user can provide an inventory, understand which duplicate identity groups
> the system considers suspicious, inspect the evidence, make an explicit
> human decision, and export only the human-confirmed identity sets as the
> operational result.

The product is a review tool, not an autonomous merger. A system group is an
analytical hypothesis. It never merges, deletes, rewrites, or writes inventory
back to an ERP. A reviewed identity set is scan-local human authority within
protected deterministic safety boundaries.

The immediate milestone does not require perfect autonomous identity,
production deployment, closure of GF-11, a full 5,327-row live demo, R18 label
execution, or new detector semantics.

## Evidence inspected and executed

The audit read the controlling SSOT, assessment, migration roadmap, showable
product acceptance and freeze records, R13-R18 evidence documents, and the
product/demo/runbook/presenter/review/export documentation. It traced the
actual React routes and components, FastAPI routes, current-product authority
selection, identity-read services, append-only review service, and CSV/XLSX
export services.

Execution evidence:

- 62 focused backend product, group-first graduation, review API, and XLSX
  export tests passed.
- 94 focused frontend group-first, review, authority, error-state, and export
  tests passed with Node test isolation disabled because the sandbox blocks
  child-process test isolation.
- The first default frontend test command was not applicable because the
  package has no `test` script. A parallel Node test-runner attempt was blocked
  by sandbox `spawn EPERM`; the same files passed in-process.
- Provider mode was forced to `none`; provider calls were zero.
- No production or runtime source was changed by this audit.

## Actual end-to-end journey

### 1. Open the app and provide inventory

What the user sees: the Dashboard describes candidate detection and offers
`Start new scan`. New Scan accepts one CSV, a scan name, scan mode, review
strictness, sensitive-data mode, and optional comparison conditions.

What the user may think: the app will identify possible duplicates without
changing the inventory. This is substantially correct, although the Dashboard
still headlines legacy `Candidates` and `Feedback` totals rather than identity
groups and reviewed sets.

What the user can do: select a CSV, validate it, resolve column mappings, and
run a scan. Validation shows record count, warnings, privacy behavior, and the
file fingerprint. Optional LLM column assistance is explicit and never applies
itself.

Confusion or missing behavior: Run Scan is available before a successful
Validate Only pass, and validation validity is not used to disable submission.
The page does not explain which file size is suitable for a live demo.

Good enough now: intake, mapping, privacy disclosure, validation errors, and
the required `PART_NO`/`DESCRIPTION` boundary are implemented.

### 2. Select current-product authority and process

What the implementation does: New Scan always submits
`product_authority=current_product`. The backend maps that typed value to the
current group-first orchestration mode. The frontend does not own or infer the
orchestration configuration.

What the user sees: the Run Scan button changes to `Scanning...` and all scan
buttons are disabled until the synchronous request returns. On success the
browser routes to `/scans/{scan_id}`.

What the user may think: work is continuing normally, but there is no stage,
elapsed time, progress percentage, expected duration, cancellation, timeout,
or durable resume contract.

Good enough now: a small supported scan has an honest loading state and a
single completion route. Not good enough for a full-real live demonstration:
the known run can approach 15 minutes and the HTTP request is synchronous.

### 3. Understand the completed result

What the user sees: `/scans/{scan_id}` loads scan metadata and the authoritative
`/identity-read/summary`. Identity Groups is the default view. Cards distinguish
system hypotheses, likely groups, groups needing review, conflicts, deferred
work, and records not safely assigned. The page explicitly says that unassigned
does not mean confirmed unique and that a 2..N group is not a collection of
pair decisions.

What the user may think: `Likely duplicate group` is a stronger system
hypothesis and `Possible duplicate group - review` is unresolved. This is
mostly correct, but there is no short on-page legend explaining why neither is
human-confirmed. `LIKELY` can still be misread as approval.

What the user can do: filter by accepted status and group size, page through
groups, switch to conflict/deferred outcomes, and deliberately open legacy
pair evidence under Advanced diagnostics.

Confusion or missing behavior: the Dashboard reports pair-era counters, and it
links only the latest scan. Older scans are reopenable through their direct URL
and backend list API, but the normal browser has no scan-history list.

Good enough now: group-first read authority is the only normal result path;
there is no legacy fallback when authority is unavailable.

### 4. Open a group and inspect members and evidence

What the user sees: a preview followed by all members with site, part number,
description, UOM, product category, and HSN/SAC. Validation mode and relationship
coverage are displayed, together with strong/review/neutral counts. Evaluated
relationship evidence is available inside an Advanced disclosure as formatted
raw JSON.

What the user may think: the system evaluated some relationships, but a
nontechnical first-time user cannot reliably tell why this specific set was
surfaced or which evidence should drive the review decision.

What the user can do: inspect every member and every persisted bounded evidence
item. The backend also returns existing `group_evidence_summary`,
`bridge_risk_summary`, `genericity_risk_summary`, and
`missing_evidence_summary` fields.

Confusion or missing behavior: no normal-view reason synthesizes matching
identity terms, model/type agreement, differing part numbers, specification
agreement, generic/copied text risk, protected contradiction, missing evidence,
or why review is required. Raw enum-shaped JSON is an audit surface, not a CEO
explanation.

Good enough now: the evidence is projection-safe, persisted, bounded, and
available without a provider call. PRM-1 can translate it without changing a
score, status, group membership, or detector rule.

### 5. Distinguish cautious outcomes

What the user sees: conflicts, deferred work, and not-safely-assigned records
are separate sections. Conflict cards show their persisted type and summary.
Deferred cards show their reason, unfinished evidence summary, affected count,
and an explicit statement that deferred is not unique, rejected, or conflict.

What the user may think: conflict means a protected incompatibility prevented
safe acceptance; deferred means the system could not safely finish. That is
correct.

What the user can do: inspect summary-level cautious outcomes and export
conflicts/deferred when present.

Confusion or missing behavior: conflict and deferred cards show counts but not
their member details in the normal UI. Human review controls intentionally
exist only for accepted/review group hypotheses, not conflict/deferred units.

Good enough now: all cautious states remain distinct and are not inflated into
duplicate groups.

### 6. Confirm, reject, defer, or adjust membership

What the user sees: every accepted group has a Human Review panel with five
choices:

- `Confirm all as one item` confirms the immutable group as one reviewed set.
- `Confirm selected as one item` confirms a selected subset and leaves the
  other members unresolved.
- `Split into identity sets` partitions every member into explicit sets.
- `Keep all separate` is the product's reject decision and requires an explicit
  acknowledgement.
- `Unsure - keep for later review` is the product's defer/abstain decision.

What the user may think: confirm is clear. Reject and defer are functionally
present but use domain phrases rather than the product promise's plain verbs.
The review-panel source also contains visible mojibake in dashes and ellipses,
which reduces confidence during the most important human-authority action.

What the user can do: enter reviewer and optional comment, preview derived
must-link/cannot-link counts, save a review, and later save a correction.

Good enough now: membership adjustment is bounded to the immutable group;
server validation enforces exact membership, valid partitions, and the
20-member review bound. Protected deterministic contradictions remain absolute.

### 7. Persist and reopen human decisions

What the implementation does: a review is an append-only, projection-scoped
event. A correction supersedes the exact current event; it never overwrites
history. A stale concurrent edit returns 409, reloads the latest state, and is
never automatically resubmitted. Effective reviewed sets are disjoint through
the scan-local human-constraint contract.

What the user sees: a current Human review label on the group card and panel,
plus expandable history marking Current versus Superseded, reviewer, timestamp,
partition sizes, relationship counts, and comment.

Confusion or missing behavior: the success copy says a decision affects the
`next explicit identity projection`, while the current reviewed export can use
the current review immediately. The UI does not provide a scan-wide Reviewed
Identity Sets view, so human authority is visible group by group and in the
download rather than as a complete in-app operational result.

Good enough now: review persistence, correction, history reopening, and system
status separation are real and covered by API/UI tests.

### 8. Export analytical and reviewed results

System Group Export is implemented as authority-selected CSV and XLSX. It is
member-shaped analytical output and includes unreviewed hypotheses. XLSX adds
Summary, Duplicate Groups, and Group Data sheets with formula-safe literal
values. It is not human confirmation.

Reviewed Identity Export is a separate authority-selected CSV. It emits only
current affirmative review partitions from Confirm All, Confirm Selected, or
Split. Keep All Separate and Unsure emit no operational identity set. With no
confirmed current review it is header-only. Every emitted row states
`HUMAN_CONFIRMED` operational authority.

What the user sees: `Export CSV`, `Export Excel`, and `Export Reviewed
Identities`, plus a generic authority-selected note.

Confusion or missing behavior: the first two controls do not say `System
Groups`; the page does not explain before download that those files are
unreviewed analytical output. A header-only reviewed download has no preview,
count, or explanatory empty-state message. There is no reviewed XLSX, which is
acceptable for this milestone if reviewed CSV is clearly explained.

Good enough now: both export authorities are technically separate, exact-scan,
provider-free, and fail closed for non-ready or inconsistent authority.

## First-time-user status distinctions

| State | Actual claim | Current communication verdict |
| --- | --- | --- |
| `LIKELY_DUPLICATE_GROUP` | Stronger system hypothesis, not confirmation | Usable, but needs an explicit `Not human-confirmed` legend |
| `POSSIBLE_DUPLICATE_GROUP_REVIEW` | Plausible set requiring human review | Correctly says review, but needs group-specific reasons |
| `CONFLICT` | Protected incompatibility blocks one accepted set | Distinct and appropriately cautious |
| `DEFERRED` | Work could not safely complete within evidence/bounds | Distinct and appropriately cautious |
| Human-confirmed reviewed set | Current affirmative human partition used by Reviewed Identity Export | Technically correct; needs a scan-wide visible reviewed-result summary |

## Explanation audit

R12's `TOO_GENERIC_FOR_DEMO` verdict remains accurate: current reason wording is
not misleading, but it is too generic for a decision-oriented demonstration.
The CSV carries structured summaries and the XLSX uses status-level templates.
The group page exposes relationship counts and raw internal evidence.

Useful evidence already available for a non-semantic presentation layer
includes normalized part-number/description evidence in persisted evaluations,
evidence class and source, validation coverage, group/genericity/bridge/missing
summaries, member fields, and protected conflict/deferred reasons. A bounded
view-model can convert only those persisted facts into statements such as:

- matching normalized identity terms or model/type evidence;
- agreeing technical specifications and differing part numbers;
- copied or generic descriptions requiring caution;
- conflicting side, role, object class, or variant where persisted;
- protected contradiction present;
- insufficient identity evidence or missing non-required relationships; and
- review required because the group status is review, not because the UI
  invented a new score.

The presenter must be able to point to evidence and answer `Why was this group
shown?` without opening JSON. That is the exact PRM-1 boundary. No inference,
new recognizer, threshold, reclassification, or membership change is allowed.

## Human-review workflow audit

| Question | Finding |
| --- | --- |
| Can the user confirm? | Yes: all, selected subset, or explicit partitions |
| Can the user reject? | Yes: `KEEP_ALL_SEPARATE`, though the UI should say Reject/keep separate |
| Can the user defer? | Yes: `UNSURE`, though the UI should say Defer/unsure |
| Can membership be adjusted? | Yes: selected-subset and complete partition controls |
| Are reviewed sets disjoint? | Yes, scan-local reviewed-set and effective-constraint validation preserve disjoint authority |
| Is review persisted? | Yes, in append-only current/superseded chains |
| Can history reopen? | Yes, whenever that scan/group is reopened |
| Is system suggestion separate? | Yes, system status remains unchanged and reviewed authority is separately labeled/exported |

Verdict: `USABLE_BUT_NEEDS_POLISH`. The complete functional contract exists.
Plain-language reject/defer labels, repaired typography, clearer saved-state
copy, and a scan-wide reviewed-set summary are needed for first-time use.

## Export authority audit

Verdict: `USABLE_BUT_NEEDS_POLISH`. Backend authority is correct and strong;
frontend naming and empty-state feedback are not yet sufficient. The product
must label System Group CSV/XLSX as analytical/unreviewed and show the current
confirmed-set count before the user downloads Reviewed Identity CSV.

## Runtime and honest demo plan

The full-real 5,327-row scan is not a live-demo action. The known current path
is synchronous and has approached 15 minutes. It also remains technically
unfrozen after R12 quality failure. No fake progress, hidden pre-run, or promise
of a fast full scan is acceptable.

Safest demo:

1. Before the session, start the provider-free local app and verify health,
   readiness, and current-product configuration.
2. Open a pre-completed authoritative full scan only to show realistic scale,
   group counts, cautious outcomes, and System Group XLSX. State that it is
   analytical and not a frozen quality-certified result.
3. Use the 17-row repository-owned synthetic fixture for the optional live
   Validate Only and Run Scan sequence. Show the real `Scanning...` state and
   say the request is synchronous.
4. On the completed synthetic result, show the group-first summary, one 3-member
   group, the future PRM-1 explanation panel, all members, validation evidence,
   a conflict, and the distinct empty deferred state.
5. Save one Confirm All review, then show current and superseded history if a
   correction is useful.
6. Download clearly labeled System Group Excel and Reviewed Identity CSV and
   explain their different authority.
7. State the limitations: synthetic live data, no accuracy claim, no writeback,
   no deployment claim, open GF-11 debt, and no production resume/cancel/timeout.

Demo-runtime verdict: `READY` only under this pre-completed-full plus optional
small-live strategy. A full-real live scan is `BLOCKED` as a credible demo step.

## Product readiness scorecard

| Area | Score | Evidence-backed reason |
| --- | --- | --- |
| A. Upload/intake | `READY` | CSV validation, mapping, privacy disclosure, warnings, and typed current-product submission work |
| B. Processing/progress | `MISSING_CRITICAL_SLICE` | Only synchronous `Scanning...`; no stage, elapsed time, progress, cancel, timeout, or resume |
| C. Result comprehension | `USABLE_BUT_NEEDS_POLISH` | Group-first summary is clear, but status education and Dashboard counters remain transitional |
| D. Group evidence/explanation | `MISSING_CRITICAL_SLICE` | Evidence exists, but normal users receive counts and raw JSON rather than a group-specific reason |
| E. Human review workflow | `USABLE_BUT_NEEDS_POLISH` | All five intents and corrections work; reject/defer wording and typography need repair |
| F. Reviewed-result authority | `USABLE_BUT_NEEDS_POLISH` | Exact human-confirmed sets exist and export correctly, but no scan-wide reviewed-set view exists |
| G. Export usability | `USABLE_BUT_NEEDS_POLISH` | Correct CSV/XLSX authorities exist; button names and header-only reviewed feedback are unclear |
| H. Error/empty-state resilience | `USABLE_BUT_NEEDS_POLISH` | 409/422, zero groups, provider, and export errors are safe; some views lack recovery guidance |
| I. Demo reliability | `READY` | Focused tests pass and the pre-completed-full plus small-live plan avoids the long-run trap |
| J. Visual/product polish | `USABLE_BUT_NEEDS_POLISH` | Functional layout exists, but review mojibake, raw JSON, and legacy Dashboard language undermine confidence |

## Four roadmap buckets

### 1. MUST HAVE BEFORE DEMO

- Plain-language, evidence-backed reasons on every group detail, with a clear
  system-hypothesis/human-confirmation boundary.
- Plain Confirm, Reject/keep separate, and Defer/unsure language; repair visible
  review typography and clarify the saved decision state.
- Explicit `System Groups - analytical/unreviewed` versus `Reviewed Identities -
  human-confirmed` labels, including a reviewed-set count/empty state.
- A rehearsed pre-completed-full plus optional 17-row live path that never asks
  the audience to wait for the 5,327-row run.

### 2. NICE TO HAVE BEFORE DEMO

- Group-first Dashboard totals and a recent scan/history list.
- Processing stage/elapsed-time feedback and clearer safe recovery actions.
- Member detail for conflict/deferred outcomes and compact evidence disclosure.
- Disable Run Scan until a current file/mapping validation succeeds.

### 3. IDENTITY-ENGINE R&D AFTER DEMO

- Resume R18 independent labels and adjudication only under separate authority.
- Re-evaluate R17 trusted-identity strategies against completed human labels.
- Continue the R14-R16 signature/signed-evidence path only after that evidence;
  do not start R19 from this milestone.
- Re-run full-real quality freeze only after an independently authorized,
  evidence-backed semantic change.

### 4. PRODUCTION / DEPLOYMENT AFTER PRODUCT PROOF

- Authentication, authorization, tenancy, SSO/RBAC, and audit policy.
- Production database/storage, retention/deletion, network, and cloud design.
- Background jobs, durable progress/resume, cancellation, timeout, and recovery.
- Structured observability, reference hardware, integration/writeback design,
  external-provider governance, and closure or replacement of the GF-11 gate.

## Finite Product Recovery Milestone

The milestone contains five tasks. Detector semantics remain frozen throughout.

### PRM-1 - Explain each group in plain language

User-visible objective: a first-time user can answer why a group was surfaced
from a short, group-specific evidence summary before opening advanced evidence.

Non-goals: no new evidence, extractor, score, status, threshold, detector rule,
group membership, persistence schema, provider call, or export authority.

PASS: representative likely and review groups display only persisted facts for
support, caution/conflict, missing evidence, and review rationale; golden UI/API
tests prove the explanation cannot change authority and never invents evidence.

### PRM-2 - Make human decisions unmistakable

User-visible objective: users see explicit Confirm, Reject/keep separate, and
Defer/unsure actions, clean typography, decision consequences, current state,
and correction history.

Non-goals: no review contract, constraint, schema, resolver, or membership
semantic change.

PASS: all five existing review intents save/reopen correctly; a first-time-user
script identifies confirm/reject/defer without translation; no mojibake remains
in the review path.

### PRM-3 - Present reviewed authority and exports clearly

User-visible objective: the result page shows current human-confirmed identity
set counts/state and clearly separates analytical System Group CSV/XLSX from
operational Reviewed Identity CSV before download.

Non-goals: no new export membership logic, reviewed XLSX requirement, automatic
merge, canonical-master choice, or writeback.

PASS: before review the reviewed result has an explicit empty state; after each
affirmative, reject, defer, and superseding decision the displayed count and
download exactly reconcile to current authoritative reviewed sets.

### PRM-4 - Recover navigation and processing confidence

User-visible objective: users can find recent/historical scans and understand
whether a scan is validating, running synchronously, completed, failed, or not
ready, with an honest next action.

Non-goals: no background worker, durable resume, cancellation, scan timeout,
runtime optimization, database migration, or new orchestration state.

PASS: Dashboard/recent scans reopen historical authoritative results; supported
loading/error/empty states show safe recovery copy; no UI invents progress that
the backend does not expose.

### PRM-5 - Freeze and rehearse the CEO demo path

User-visible objective: a presenter completes the exact honest journey using a
pre-completed authoritative full scan plus an optional small synthetic live
scan, with no long wait or authority ambiguity.

Non-goals: no full-real live promise, quality certification, R18 execution,
detector correction, performance closure, deployment, provider enablement, or
writeback.

PASS: a cold presenter rehearsal completes intake, result comprehension,
explanation, confirm/reject/defer, persisted current state, and both export
authorities within the declared demo window; provider calls remain zero.

## Milestone completion criteria

Product Recovery is complete only when a first-time user can open the app,
provide/select an inventory, reach a completed result, understand that groups
are review hypotheses, open a group, understand its evidence, confirm/reject/
defer, see the human decision and reviewed set clearly, and export authoritative
reviewed duplicate sets. The CEO demo must not depend on a live 5,327-row scan.

## Exact smallest next product task

Implement only `PRM-1 - Explain each group in plain language`: add a bounded
presentation model and normal-view group explanation using already persisted
authoritative detail evidence. Keep raw evidence under Advanced, keep every
system status and member unchanged, make zero provider calls, and add tests that
fail if the presentation invents evidence or implies human confirmation.
