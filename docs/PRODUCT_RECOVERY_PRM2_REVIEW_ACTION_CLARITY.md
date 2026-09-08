# PRM-2 Human Review Action Clarity

## Baseline and boundary

PRM-2 starts from verified PRM-1 commit
`c0f8a29a7f3758a1c5c53b15033e7af9c5148ac7`. It changes only frontend review
presentation and interaction state. The persisted enums, append-only review
service, immutable target, supersession token, concurrency rules, constraint
derivation, reviewed identity-set construction, exports, detector, providers,
database schema, migrations, and dependencies remain unchanged.

## User-facing decisions

- **Confirm as same item** maps to `CONFIRM_ALL_AS_ONE` and creates one
  human-confirmed reviewed identity set. For groups above two records it says
  **Confirm all as same item**.
- **Reject duplicate hypothesis** maps to `KEEP_ALL_SEPARATE`, says to keep the
  records separate, and explains that no reviewed duplicate set is created.
- **Defer decision** maps to `UNSURE`, says there is not enough information / to
  review later, and leaves the group unresolved.

The advanced multi-member choices remain available for groups of three or more.
**Confirm selected records as same item** maps to `CONFIRM_SELECTED`, shows the
selected count, and says unselected records stay unresolved. **Split into separate
identity sets** maps to `SPLIT_PARTITIONS`, requires every record in exactly one
set, and explains that records in different sets stay separate.

## Saved state, correction, and history

The Human decision region shows the current decision, its authoritative result,
and whether reviewed identity sets were produced. No reviewed-set identifier is
invented. It states that the current decision controls Reviewed Identity Export.
`Change decision` preloads the current choice and submits its exact review event as
the supersession token. The prior event remains visible as Previous decision and
is explicitly no longer operationally authoritative. Append-only history and one
current chain head are unchanged.

## Confirmation and interaction safety

Confirm states that the records represent the same underlying inventory item.
Reject retains the existing explicit keep-separate acknowledgement. Defer states
that no identity decision is made yet. The initial form requires an explicit
choice rather than defaulting to Defer. Saving and cancel controls expose disabled
and `aria-busy` state while the authoritative request is pending.

Success appears only after the POST succeeds. If the subsequent history refresh
fails, the successful response is retained locally and the UI truthfully asks for
a reload before another change. A 409 reloads the latest state and never
auto-resubmits. A 422 asks the user to check selections, sets, and reviewer data.
Network/API failure says the decision was not saved and offers a retry path.

## Typography and accessibility

Review-flow mojibake was replaced with valid Unicode em dashes and ellipses.
Normal review labels no longer expose backend enum names. The region has an
accessible heading, busy state, labelled controls, native fieldsets/checkboxes,
live decision previews, status/alert roles, textual Current/Previous labels, and
a keyboard-accessible reload action. Status is not conveyed by color alone.

## Representative verification

R1-R14 cover two-member Confirm/Reject/Defer, multi-member Confirm all,
Confirm-selected and split flows, saved confirmed/rejected/deferred outcomes,
superseded affirmative/rejected/deferred decisions, 409 recovery, 422 handling,
and correction/history behavior. PRM-1 System explanation remains before and
separate from Human decision. Focused backend authority/API/export tests verify
current-chain uniqueness, retained superseded history, disjoint partitions,
non-affirmative behavior, and chain-head export authority.

## Verification results

- Frontend component/contract suite: 116 passed.
- Focused backend review/API/authority/export tests: 90 passed, with one existing
  pytest configuration warning.
- Production frontend build: passed.
- Full backend suite: not required because no backend runtime or API source changed.
- Normal 5,327-row G2-v2 scan: not required.
- Provider calls: zero.

No browser session or detector rerun was started. Utility/component contract tests,
backend integration tests, and the production build provide equivalent local
verification.

## Deferred work and continuing governance

PRM-3 export distinction and feedback remain deferred. PRM-2 does not change
System Group Export or Reviewed Identity Export semantics. PRM-1 remains verified.
R18 remains `HUMAN_REVIEW_DATASET_PREPARED` with human-label execution deferred;
GF-12A2 remains incomplete. GF-11 remains in progress with its waiver active and
`GF11-PERF-100K-COLD-FULL` open. Identity-engine semantic work is paused,
deployment is deferred, and the detector remains technically unfrozen from the
R12 quality perspective.
