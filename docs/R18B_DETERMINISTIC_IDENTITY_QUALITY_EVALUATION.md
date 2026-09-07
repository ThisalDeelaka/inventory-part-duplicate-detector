# R18B Deterministic Identity-Quality Evaluation

## R18B-R1 recovery and completed evaluation

`R18B_GENERIC_TRUST_TOO_WEAK`

R18B-R1 recovered and froze the Senior Functional Consultant reference after
proving 316/316 pair IDs, 5,688/5,688 unchanged visible source cells, literal
human fields, and complete valid inputs against a byte-identical reconstruction
of the original immutable template. See
`R18B_PRIMARY_EXPERT_REFERENCE_RECOVERY.md`. The initial fail-closed result
below remains preserved as history; its structural concerns were real, but the
authorized forensic checks prove the two inserted formula columns were
non-authoritative and the Senior judgments were recoverable.

### Reference policy and artifacts

The reference is a **blinded single-senior-domain-expert diagnostic reference
set, with a secondary junior-review challenge signal retained separately**. It
is not dual-reviewed, adjudicated, gold-standard, or production-accuracy truth.

- Senior submission SHA-256:
  `6e27ce3a46f17834e8387879793cd18461d87295a1d28caa7b0aba0e3bbac7eb`.
- Immutable template SHA-256:
  `682b4e4d5d83017a28f7c021124b2dd394431cf91c072a9934fd73d7025bb052`.
- Recovered reference: 316 rows, SHA-256
  `24a8abd5505a535fd1d4acbec493cda8ac5ae1a6e017ef3d1b84e6110590ae02`.
- Evaluation CSV: 316 rows, SHA-256
  `e49a69f66580a9771e6592433ff832be29cdc0743a205f121e0c759fac8ba609`.

Both derived files and the deterministic JSON summary remain in the ignored
R18 artifact directory. No original workbook was changed.

### Panel discipline and sampling caveat

The headline matrix uses exactly 300 unique Evaluation memberships. The 20
Diagnostic memberships are used only below for qualitative control inspection;
four overlapping pairs remain one physical evaluation row and are not double-
counted. The 300 rows are stratified across evidence buckets, not a simple
random sample of arbitrary inventory pairs, so no naked production "accuracy"
claim is valid.

One population stratum—`REVIEW_SUPPORT__SHADOW_INSUFFICIENT`, 18 of 20,395
candidate edges—has no evaluation sample. Therefore
`WEIGHTED_FULL_POPULATION_ESTIMATE = NOT_VALID`. A descriptive expansion over
only the 20,377 covered candidates estimates 79.020% DIFFERENT, 19.126%
INSUFFICIENT, and 1.853% SAME. These are covered-candidate diagnostic estimates,
not production accuracy, and no inference is made for the 18 unsampled edges.

### Primary 3-by-4 matrix

Counts (300 Evaluation pairs):

| Expert \ System | Strong | Review | Non-groupable | Cannot-link | Row total |
|---|---:|---:|---:|---:|---:|
| SAME | 39 | 21 | 1 | 2 | 63 |
| DIFFERENT | 10 | 51 | 82 | 41 | 184 |
| INSUFFICIENT | 1 | 27 | 18 | 7 | 53 |
| Column total | 50 | 99 | 101 | 50 | 300 |

Row percentages:

| Expert \ System | Strong | Review | Non-groupable | Cannot-link |
|---|---:|---:|---:|---:|
| SAME | 61.905% | 33.333% | 1.587% | 3.175% |
| DIFFERENT | 5.435% | 27.717% | 44.565% | 22.283% |
| INSUFFICIENT | 1.887% | 50.943% | 33.962% | 13.208% |

Column percentages:

| Expert label within column | Strong | Review | Non-groupable | Cannot-link |
|---|---:|---:|---:|---:|
| SAME | 78.000% | 21.212% | 0.990% | 4.000% |
| DIFFERENT | 20.000% | 51.515% | 81.188% | 82.000% |
| INSUFFICIENT | 2.000% | 27.273% | 17.822% | 14.000% |

### Safety-oriented interpretation

- Expert SAME: Strong 39/63, Review 21/63, combined support 60/63
  (95.238%); one non-groupable miss (1.587%); two severe cannot-link false-
  separations (3.175%).
- Expert DIFFERENT: cannot-link 41/184 (22.283%) and non-groupable 82/184
  (44.565%) are safety-aligned; Review 51/184 (27.717%) is noisy review burden;
  Strong 10/184 (5.435%) is the highest-risk false-support signal.
- Expert INSUFFICIENT: Strong 1/53, Review 27/53, non-groupable 18/53, and
  cannot-link 7/53. The 35 decisive support/cannot-link outcomes are overcommit
  signals, not automatically proven errors.

There are 12 severe sample disagreements: ten Strong-on-DIFFERENT (three HIGH,
seven MEDIUM) and two cannot-link-on-SAME (one HIGH, one LOW). They are retained
by stable pair ID in the ignored evaluation artifact; no corrected label was
generated.

### Senior confidence stratification

| Confidence and expert label | Strong | Review | Non-groupable | Cannot-link | Total |
|---|---:|---:|---:|---:|---:|
| HIGH SAME | 14 | 1 | 0 | 1 | 16 |
| HIGH DIFFERENT | 3 | 27 | 74 | 11 | 115 |
| HIGH INSUFFICIENT | 0 | 2 | 0 | 0 | 2 |
| MEDIUM SAME | 16 | 1 | 0 | 0 | 17 |
| MEDIUM DIFFERENT | 7 | 22 | 8 | 30 | 67 |
| MEDIUM INSUFFICIENT | 1 | 25 | 18 | 7 | 51 |
| LOW SAME | 9 | 19 | 1 | 1 | 30 |
| LOW DIFFERENT | 0 | 2 | 0 | 0 | 2 |
| LOW INSUFFICIENT | 0 | 0 | 0 | 0 | 0 |

The highest-priority evidence is the three HIGH-confidence Strong-on-DIFFERENT
cases and the one HIGH-confidence cannot-link-on-SAME case. Lower-confidence
rows remain present and are not discarded.

### Generic and copied/lexical analysis

The exact `GENERIC_DESCRIPTION` guard is cautious in its 16 sampled rows: eight
expert DIFFERENT (seven non-groupable, one Review), six INSUFFICIENT (five non-
groupable, one Review), and two LOW-confidence SAME (both Review). It emits no
Strong result here, suppresses no expert SAME as non-groupable, and therefore is
not shown to be too strict. It should not be weakened.

The broader lexical-only/unresolved boundary is materially too permissive:

| System class in 177 lexical-only rows | SAME | DIFFERENT | INSUFFICIENT |
|---|---:|---:|---:|
| Strong | 32 | 9 | 1 |
| Review | 10 | 35 | 12 |
| Non-groupable | 0 | 34 | 11 |
| Cannot-link | 0 | 29 | 4 |

Among 107 expert DIFFERENT lexical-only rows, 44 receive positive support: nine
Strong (two HIGH, seven MEDIUM) and 35 Review (16 HIGH, 17 MEDIUM, two LOW).
Among 42 expert SAME lexical-only rows, none is suppressed as non-groupable;
ten remain only Review (one HIGH, one MEDIUM, eight LOW). Among 28 lexical-only
INSUFFICIENT rows, one is Strong and 12 are Review, which are overcommit signals.

This is a one-directional trust problem in broad copied/description-dominant
lexical support, not evidence for weakening the exact generic guard. The sample
supports `R18B_GENERIC_TRUST_TOO_WEAK`, not a bidirectional classification.

### Evidence provenance

| Frozen shadow provenance | N | SAME | DIFFERENT | INSUFFICIENT | HIGH | System classes |
|---|---:|---:|---:|---:|---:|---|
| Trusted identity present | 66 | 18 (27.3%) | 34 (51.5%) | 14 (21.2%) | 22 | Strong 7, Review 41, Non-groupable 16, Cannot-link 2 |
| Lexical-only/unresolved | 177 | 42 (23.7%) | 107 (60.5%) | 28 (15.8%) | 73 | Strong 42, Review 57, Non-groupable 45, Cannot-link 33 |
| Mixed evidence | 14 | 3 (21.4%) | 7 (50.0%) | 4 (28.6%) | 3 | Strong 1, Review 1, Cannot-link 12 |
| Insufficient shadow | 42 | 0 | 35 (83.3%) | 7 (16.7%) | 34 | Non-groupable 40, Cannot-link 2 |
| Explicit contradiction | 1 | 0 | 1 (100%) | 0 | 1 | Cannot-link 1 |

Trusted evidence is directionally stronger only when interpreted with the
system class: trusted Strong is 6 SAME, one DIFFERENT; lexical Strong is 32
SAME, nine DIFFERENT, one INSUFFICIENT. Trusted Review is still heterogeneous
(11 SAME, 16 DIFFERENT, 14 INSUFFICIENT), so a provenance name alone is not a
quality guarantee.

### Per-stratum expert labels

| Evaluation stratum | N | SAME | DIFFERENT | INSUFFICIENT |
|---|---:|---:|---:|---:|
| Cannot-link | 50 | 2 | 41 | 7 |
| Non-groupable / insufficient | 40 | 0 | 33 | 7 |
| Non-groupable / lexical | 45 | 0 | 34 | 11 |
| Non-groupable / trusted | 16 | 1 | 15 | 0 |
| Review / lexical | 57 | 10 | 35 | 12 |
| Review / mixed | 1 | 0 | 0 | 1 |
| Review / trusted | 41 | 11 | 16 | 14 |
| Strong / lexical | 42 | 32 | 9 | 1 |
| Strong / mixed | 1 | 1 | 0 | 0 |
| Strong / trusted | 7 | 6 | 1 | 0 |

### Diagnostic controls

These are qualitative, enriched controls only. Senior judgments are preserved
even where they disagree with prior architect expectations.

| Present control | Senior label / confidence | Frozen system evidence | Result |
|---|---|---|---|
| Francis Turbine Lower Bearing | SAME / MEDIUM | Strong, lexical | support aligned |
| Dust Cap vs Coil Spring | SAME / MEDIUM | Cannot-link, mixed | false separation |
| Rim vs Tyre | DIFFERENT / MEDIUM | Cannot-link, mixed | safety aligned |
| Condition vs Discount | DIFFERENT / MEDIUM | Cannot-link, mixed | safety aligned |
| Brush vs Paint | SAME / MEDIUM | Strong, lexical | support aligned |
| Coil Spring vs Staplers | SAME / MEDIUM | Strong, lexical | support aligned |
| Carbon Stick vs Pencil | SAME / HIGH | Cannot-link, mixed | false separation |
| Buffer vs Mirror | SAME / HIGH | Strong, mixed | support aligned |
| Fan Blade aliases | SAME / MEDIUM | Strong, lexical | support aligned |
| Turbine Lubricating Oil | SAME / HIGH | Strong, lexical | support aligned |
| Clutch vs Coil Spring | SAME / MEDIUM | Cannot-link, mixed | false separation |
| Clutch vs Dust Cap | SAME / MEDIUM | Cannot-link, mixed | false separation |
| Left vs Right | SAME / HIGH | Cannot-link, mixed | false separation |
| B38 aliases | SAME / HIGH | Strong, lexical | support aligned |
| Table vs Nail | INSUFFICIENT / MEDIUM | historical diagnostic only | not comparable |
| Contact Cleaner | SAME / HIGH | Review, lexical | support aligned but unresolved |
| Wood vs Steel Frame | SAME / MEDIUM | historical diagnostic only | not comparable |
| Model S vs Model X | SAME / MEDIUM | Strong, lexical | support aligned |
| F30 aliases | SAME / HIGH | Strong, lexical | support aligned |
| Pump X500 | DIFFERENT / HIGH | historical diagnostic only | not comparable |

The surprising labels are a reason to retain the single-expert claim limit and
obtain an untouched holdout before post-change claims; they are not permission
to rewrite the Senior's answers.

### Reviewer B secondary signal

Reviewer B selected `DIFFERENT_IDENTITY` for all 316 rows: confidence 58 HIGH,
255 MEDIUM, three LOW; reasons were 174 `DIFFERENT_OBJECT`, 83
`DIFFERENT_MODEL_OR_TYPE`, 56 `DIFFERENT_VARIANT_OR_SIDE`, and three internally
inconsistent `SAME_MODEL_AND_OBJECT`. Therefore
`SECONDARY_REVIEW_STATUS = DEGRADED_ONE_CLASS_RESPONSE`.

Raw A/B agreement is 185/316 (58.544%), entirely the Senior DIFFERENT rows.
Agreement by Senior label is DIFFERENT 185/185, SAME 0/77, INSUFFICIENT 0/54.
Agreement by Senior confidence is HIGH 116/139 (83.453%), MEDIUM 67/145
(46.207%), and LOW 2/32 (6.250%). These figures diagnose Reviewer B's response
pattern; they neither validate A nor make B reference authority.

### Architecture decision and boundaries

The evidence justifies a future general correction at the broad lexical/copied-
text trust boundary, prioritizing Strong-on-high-confidence-DIFFERENT errors and
then noisy Review support. It does not justify noun-specific patches, weakening
the existing exact generic guard, or treating missing data as positive proof.

Primary result: `R18B_GENERIC_TRUST_TOO_WEAK`.

Recommendation: `NEXT = R18C_EVIDENCE_BACKED_GENERIC_TRUST_CORRECTION`.

R18C is not started here. Because these 316 labels now inform that architecture
choice, any post-change quality claim requires a new untouched holdout or an
independent human-labelled evaluation set. Pair evidence does not authorize
client-visible group confidence; that still requires group-level human evidence,
safe aggregation, and calibration.

Runtime detector behavior is unchanged. Copied/generic trust is measured but
not modified. External demo readiness remains blocked pending architect review.
Group confidence, LLM, client XLSX vNext, deployment, and GF11 remain out of
scope. Provider calls remained 0. Focused verification passed 20 tests with one
existing pytest configuration warning.

## Initial fail-closed attempt (historical)

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
