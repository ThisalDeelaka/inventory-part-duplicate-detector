# R18G Senior group-review handoff

Status: `R18G_AWAITING_GROUP_HUMAN_REVIEW`

Give both blinded workbooks to the same highly experienced Senior Functional
Consultant:

- `r18g_group_review_development.xlsx`
- `r18g_group_review_sealed_holdout.xlsx`

The Senior may complete both files in one review session. Ask them to decide
whether **all** records in each proposed group represent one underlying
physical/business inventory item. They must not guess when the visible source
information is inadequate. For `NOT_ONE_IDENTITY`, they should partition the
members where reasonably possible.

Do not show the reviewer system output, the internal mapping, pair-level human
labels or comments, prior reviewer comments, LLM output, or known controls. Do
not discuss individual groups with the reviewer while labeling.

After both workbooks are complete, return only the DEVELOPMENT workbook to
engineering first. Keep the completed SEALED HOLDOUT workbook outside the
repository and do not reveal its labels to Codex or engineering until the
relevant group-resolution or confidence rule has been frozen and its use is
explicitly authorized.

This is one Senior expert's evidence. It is not dual-reviewed, adjudicated, a
gold standard, or production-accuracy truth.
