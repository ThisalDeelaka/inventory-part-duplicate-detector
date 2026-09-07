# R18A Blinded Human Label Execution

## R18B continuation blocker

The returned primary Reviewer A workbook did not preserve this Stage-A
contract: its header shifted to row 2, two formula columns were inserted, and
the used range expanded to the worksheet maximum. R18B therefore classified
the primary expert reference as invalid and stopped without interpreting
labels or substituting Reviewer B. A new submission from the unchanged blinded
template is required. See
`R18B_DETERMINISTIC_IDENTITY_QUALITY_EVALUATION.md`.

## Classification and baseline

`R18A_AWAITING_HUMAN_LABELS`

- Branch: `llm-assisted-mvp`.
- Starting HEAD: `c5605c4625334018bd515bc29256387b383048a6`.
- Protected tag `deterministic-demo-v1` remained at
  `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Initial status contained only `?? List_20260709_093045.xlsx`; it was not
  inspected, modified, staged, deleted, hashed, or otherwise touched.
- No environment file, credential, token, key, authorization header, or secret
  was accessed. Provider calls were 0. Docker and product services were not
  started.

R18A is evidence-collection infrastructure, not detector tuning. It changes no
production detector, review, API, frontend, export, provider, or authority
behavior.

## Prepared package and exact counts

The committed R18 preparation contract and ignored local artifact package are
present and reconcile:

- 5,327 canonical records in persisted Scan 31;
- discovery run 8 and evidence run 7;
- 20,395 unique candidate edges;
- 20 diagnostic-panel pairs;
- 300 evaluation-panel pairs;
- four pairs shared by both panels;
- 316 unique reviewer pair IDs;
- 0 completed human labels;
- 0 provider calls.

The existing package was not regenerated. Reviewer workbooks and their private
mapping remain under ignored `artifacts/gf12_a2_human_identity_review/` and are
not committed.

## Blinding verification

Reviewer A and Reviewer B each have exactly 316 rows with identical source-side
pair content, separate reviewer metadata, zero prefilled human-input cells, and
zero formula cells. Visible columns contain only a neutral pair ID; each side's
part number, descriptions, type designation, dimension/quality, UOM, part type,
and site; and label, confidence, reason, and optional note fields.

Neither workbook exposes a detector or similarity score, detector/GF4/GF5
status, group outcome, LLM output, sampling stratum, known-control category,
expected label, private stable references, or private mapping. All 316 pair IDs
reconcile one-to-one with the private mapping. Blinding is valid.

## Human contract and validation mechanism

`docs/R18A_HUMAN_REVIEW_INSTRUCTIONS.md` states the exact identity question,
the three labels (`SAME_IDENTITY`, `DIFFERENT_IDENTITY`,
`INSUFFICIENT_INFORMATION`), HIGH/MEDIUM/LOW confidence, physical identity
versus ERP context, relevant identity-defining evidence, and the requirement
not to guess or consult detector/AI output.

The offline validator in
`backend/app/benchmarks/human_identity_review_execution.py` compares each
submission with its original blinded workbook. It fails closed on missing,
duplicate, or foreign pair IDs; changed instructions, headers, reviewer code,
or source fields; formulas; invalid labels, confidence, or reason codes;
partial label entries; and any blank label when a workbook is declared
complete. It preserves row order independence by reconciling through stable
pair IDs. It never reads the private detector mapping to create a human answer.

The same module can create a disagreement-only adjudication workbook after two
complete valid submissions. That future artifact contains source-side fields
and the two reviewers' exact entries, but no detector/GF4/GF5/LLM or expected
answer. It has empty adjudicated label, confidence, and reason fields and does
not auto-adjudicate.

## Execution state

| Stage | Status |
|---|---|
| Reviewer A | `AWAITING_HUMAN_LABELS` (0/316 complete) |
| Reviewer B | `AWAITING_HUMAN_LABELS` (0/316 complete) |
| Reviewer agreement | `NOT_CALCULATED` |
| Adjudication | `NOT_STARTED` |
| Frozen human reference dataset | `NOT_CREATED` |

Codex did not fill a label, infer a known control, copy between workbooks, or
substitute for a reviewer. Agreement is not detector accuracy. Stage B cannot
start until both independent completed human workbooks are supplied and pass
validation.

## Secondary GF5 governance debt

`GF5-PARTITION-OBJECTIVE-GOVERNANCE` is `OPEN`.

- `causal_to_bicycle: NO`
- `runtime_change_authorized: NO`
- `review_after: human evidence / architect review`

The implementation's non-generic partition objective and the ADR's stated
Review-support ordering require later governance review. This does not weaken
the generic-family guard and does not delay human collection.

## Verification and next step

Focused package/blinding, pair-ID, submission-validation, reviewer-agreement,
and disagreement-packaging tests passed: **40 passed** with one existing pytest
configuration warning. Both real blank workbooks also passed the validator as
drafts with 316 reconciled IDs, unchanged source fields, and 0 completed labels.
Production runtime changes are none and provider calls remain 0.

Next: two actual humans independently complete Reviewer A and Reviewer B using
the instructions and return both files through the authorized private channel.
Then continue R18A Stage B to validate, measure agreement, and prepare human
adjudication if necessary. Do not begin
`R18B_DETERMINISTIC_IDENTITY_QUALITY_EVALUATION` until final human reference
labels are verified.
