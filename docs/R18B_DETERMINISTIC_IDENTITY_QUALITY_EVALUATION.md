# R18B Deterministic Identity-Quality Evaluation

## Classification

`R18B_PRIMARY_EXPERT_REFERENCE_INVALID`

R18B stopped at the mandatory Reviewer A validation gate. No human label was
treated as reference truth, no deterministic evidence was joined to a label,
and no quality metric or architecture conclusion was calculated.

## Baseline and safety

- Branch: `llm-assisted-mvp`.
- Starting HEAD: `a1a8282cdbe54af06e72a1f8c31605aa8bee54af`.
- Protected tag `deterministic-demo-v1` remained at
  `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Initial status contained only `?? List_20260709_093045.xlsx`; it was not
  inspected, modified, staged, deleted, or hashed.
- No `.env`, credential, API key, token, authorization header, or secret was
  accessed. Provider calls were 0. Docker and product services were not used.

## Approved reference-policy deviation

The intended diagnostic reference type was
`SINGLE_SENIOR_DOMAIN_EXPERT`, with Reviewer A as the primary domain-expert
reference and Reviewer B retained only as a non-authoritative junior-review
challenge signal. Adjudication was unavailable due to resource constraints,
and any valid result would have been limited to a blinded
single-senior-domain-expert diagnostic reference—not dual-reviewed,
adjudicated, gold-standard, or production-accuracy truth.

That policy cannot activate because the primary submission is structurally
invalid.

## Reviewer A fail-closed validation

Expected from the immutable R18 manifest/template:

- 316 unique pair IDs;
- the exact 23-column blinded schema on row 1;
- no formulas;
- original template size 40,682 bytes;
- original template SHA-256
  `682b4e4d5d83017a28f7c021124b2dd394431cf91c072a9934fd73d7025bb052`.

Observed in the submitted `human_identity_review_reviewer_a.xlsx`:

- current size: 16,136,153 bytes;
- current SHA-256:
  `6e27ce3a46f17834e8387879793cd18461d87295a1d28caa7b0aba0e3bbac7eb`;
- the header moved from row 1 to row 2;
- the schema contains 25 columns instead of 23;
- two formula-valued columns were inserted before the human-input fields;
- the worksheet used range expanded to 1,048,576 rows;
- the bounded expected data window still contains 316 unique expected pair IDs,
  with no missing or foreign ID in that window.

The pair-ID observation cannot override the schema and formula failures. Source
field equality and label validity cannot be certified against the original
blinded contract after the columns shifted. The workbook therefore fails the
required exact-schema, no-formula, and source-integrity gates.

The original human submission was not overwritten, repaired, normalized, or
re-saved. Its entries were not interpreted as reference labels.

## Reviewer B boundary

Reviewer B was not substituted for the invalid primary expert. A bounded
structural observation found 316 expected unique IDs and no inserted formula
header, but its header is also on row 2 rather than the required row 1. No label,
confidence, reason, agreement, one-class-response, or inconsistency analysis was
used because the primary gate had already failed. Reviewer B remains
`SECONDARY_ONLY` and non-authoritative.

Its submitted workbook was likewise left unchanged. Its current SHA-256 is
`579e2ebec1d2005fbffb92a442f4623fba05cfa4f37383f046e5817a015fd01e`.

## Evaluation not performed

The following required outputs are intentionally absent rather than fabricated:

- frozen Reviewer A reference CSV and reference hash;
- Evaluation-versus-Diagnostic panel analysis;
- the 3-by-4 human/system matrix;
- SAME, DIFFERENT, and INSUFFICIENT safety metrics;
- expert-confidence stratification;
- generic/copied-description analysis;
- evidence-provenance and known-control analysis;
- Reviewer B secondary agreement analysis;
- weighted candidate-population estimates;
- severe deterministic-disagreement list;
- `r18b_deterministic_quality_evaluation.csv`.

`WEIGHTED_FULL_POPULATION_ESTIMATE = NOT_VALID` because there is no valid
primary reference, before considering the sampling design.

## Governance and next recommendation

Runtime detector behavior remains unchanged. Copied/generic trust is unmeasured
and unmodified in R18B. External demo readiness remains
`BLOCKED_BY_IDENTITY_OUTPUT_QUALITY`. Group confidence, LLM advisory, and client
XLSX vNext remain not started. The 316 pairs must remain evaluation-only; if
future development uses their labels, a new untouched holdout or independent
human-labelled set is required before any post-change quality claim.

Formal recommendation: `NEXT = RETAIN_CURRENT_GENERIC_GUARD`.

Operationally, the architect must first obtain a new Reviewer A submission
created from the original 23-column blinded template, preserving row 1 headers,
all source cells and pair IDs, and containing no added formulas. R18B may then be
rerun from the primary validation gate. No R18C correction or R18G evidence work
is authorized from this invalid reference.

## Runtime and verification

No source, test, detector, retrieval, GF4, GF5, signature, API, frontend,
review, export, provider, schema, dependency, or artifact file was changed.
This blocker is documentation-only. Provider calls remained 0.
