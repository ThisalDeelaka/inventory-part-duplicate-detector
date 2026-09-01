# PRM-5 Demo Rehearsal and Showable-Product Freeze

## Decision

`PRM5_SHOWABLE_PRODUCT_FROZEN`

The showable human-in-the-loop product/demo baseline is frozen. Product Recovery
PRM-1 through PRM-4 remain verified, and the PRM-5 primary path is coherent,
truthful, recoverable, and free of demonstrated-path presentation blockers.

## Baseline and protected inputs

- Starting HEAD: `74e4251e22448ba920f967df2a67a012d6809141` (`Improve scan navigation and processing confidence`).
- Branch: `llm-assisted-mvp`.
- Protected tag: `deterministic-demo-v1` at `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Initial worktree: only `?? List_20260709_093045.xlsx`; nothing staged.
- Protected XLSX SHA-256: `7b4fca921dee032bc6fec6de8c46f41b4092dc42f7bdd68c8128cf70b2ef5cec`.
- Protected CSV SHA-256: `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- The unrelated XLSX was not inspected, modified, or staged. No full-real scan was run.

## Pre-completed full-result path

The normal local product history contains saved scan 31,
`R10 directional-side corrected real verification`, started 2026-08-31 and
completed 2026-08-31. Read-only persisted evidence establishes:

- scan status `COMPLETED`;
- orchestration `group_first_primary`, status `COMPLETED`;
- primary pipeline `GROUP_FIRST_GF1_GF6`;
- visible projection `G2_V2`, visible product ready;
- 5,327 canonical records;
- 203 accepted groups: 114 Likely and 89 Review;
- 30 Conflicts, 30 Deferred work units, and 4,898 unassigned records;
- source resolution provider request count 0.

The Dashboard uses the existing scan-list history contract and selects the latest
saved scan, so scan 31 is reachable through Latest/Recent navigation without a
typed result URL. The authority reader selected `G2_V2`; no `G2_V1` fallback was
used.

## Acceptance and bounded spot-check

The read-only authority service loaded scan 31 successfully. System CSV produced
430 lines (header plus 429 member rows); System XLSX produced a valid in-memory
160,498-byte workbook. Reviewed CSV produced its 480-byte header only because
the preserved scan has no current human-confirmed sets. That behavior is
truthful and is explicitly handled by the runbook.

The first five deterministically ordered Likely groups and first five Review
groups were inspected. All ten explanations had bounded supporting/caution
content and none used the checked overclaims `confirmed duplicate`, `same
physical item`, `guaranteed`, or `100%`. The first visible Conflict explanation
says records were not grouped automatically. The first visible Deferred
explanation says there is no duplicate conclusion. System explanation, Human
decision, and export authority remain separate.

This was a presentation-truth check only. It did not classify semantic quality,
change group selection, hide results, modify inventory data, or add identity
rules. R12 remains `DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`; autonomous detector
quality is not frozen or claimed.

## Optional small-live path

`data/llm_assisted_mvp_demo.csv` is the existing 17-row synthetic fixture. The
current-product acceptance harness exercises three independent in-memory scan
runs, navigation/API result reads, explanations, Confirm/Defer decision history,
System/Reviewed exports, and a deliberate failure path with provider calls 0.
It is retained in the primary script because it is bounded and has the immediate
fallback of opening scan 31. Reject behavior is covered by focused append-only
review tests; all review demonstrations use disposable test state rather than
the preserved full result.

## Rehearsal

The scripted timing is 7:00: Dashboard 0:35; optional live path 1:10; full result
1:10; explanation 1:10; human decision 1:05; human authority 0:40; exports 0:45;
close 0:25. The no-live fallback is approximately 5:50. Both fit the 5-8 minute
target without claiming that a full-real scan is instantaneous.

Scenes 1-8 passed by contract and persisted-evidence rehearsal: Dashboard/history;
optional New Scan lifecycle; saved full result; group explanation; disposable
human decision; current/previous human authority; separate exports; and return
to Dashboard with the `discover, explain, review, confirm, export` close.

The only proven presentation blocker was stale pre-PRM runbook/script wording.
It was corrected in documentation. No production/runtime source correction was
needed. Browser/network, optional-live, and zero-reviewed-set fallback paths are
defined in `docs/PRODUCT_RECOVERY_PRM5_CEO_DEMO_RUNBOOK.md`.

## Verification and data integrity

Verification covers Dashboard/history, New Scan validation/lifecycle, Scan
Results, SystemExplanation, GroupReviewPanel, ExportAuthorityPanel, historical
reopening, and empty/error states. The focused backend current-product, review,
explanation, export, XLSX, and showable-demo suites passed **96 tests**; the
three-run disposable demo fixture setup completed in **2.42 seconds**. The full
frontend suite passed **148 tests**, and the Vite production build completed
successfully. The full backend suite was not required because no backend runtime
source changed.

No `.env`, secret, credential, token, authorization header, or provider was
accessed. Provider calls remain 0. No schema, migration, dependency, detector,
review-authority, or export-authority change was made.

## Frozen and deferred state

### Showable product - frozen

Upload, scan, history, results, explanations, human review, review authority,
authority-separated exports, and the demo workflow are frozen for presentation.
Make no further product changes before the CEO demo unless this exact path has a
reproduced presentation blocker.

### Deferred identity R&D

R18 human labels, adjudication, any future identity-evidence gate, and general
semantic-quality validation remain deferred. Identity-engine semantics are
paused. GF12A2 remains incomplete at human-label execution.

### Deferred production work

GF11 remains in progress under its active waiver and
`GF11-PERF-100K-COLD-FULL` remains open. Background execution, IAM/tenancy,
storage, deployment, monitoring, integrations, and reference-hardware work are
deferred until product proof.

Product Recovery Milestone: `COMPLETE`. Showable product: `FROZEN`. Immediate
next action: demo/presentation only. Deployment: `DEFERRED UNTIL PRODUCT PROOF`.
