# GF-12A2 Blinded Human-Review Pilot Status

## Result

```text
GF-12A2 protocol/tooling: VERIFIED
human pilot:              NOT EXECUTED
human labels:             NONE
human-quality metrics:    NONE
state:                    HUMAN_REVIEW_DATASET_REQUIRED
```

No final human-reviewed production-quality signoff or GF-12 completion is
claimed.

## Repository dataset authorization audit

The repository contains no explicitly authorized, representative,
non-synthetic dataset for human quality validation.

| Repository data source | Classification | Decision |
| --- | --- | --- |
| `data/llm_assisted_mvp_demo.csv` | `SYNTHETIC_ONLY` | Demo guide explicitly identifies every row as synthetic; not human evidence |
| GF-11/GF-12 scale generator | `SYNTHETIC_ONLY` | Fixed-seed canonical benchmark truth; not representative real inventory |
| `data/sample_inventory_parts.csv` | `UNSPECIFIED/NOT_AUTHORIZED` | Demo upload file with no human-validation authorization |
| `data/evaluation_pairs.csv` | `UNSPECIFIED/NOT_AUTHORIZED` | Small illustrative pair examples, not a group-first approved reviewed set |
| Ordinary uploaded/customer inventory | `UNSPECIFIED/NOT_AUTHORIZED` | Sensitive data; an upload does not grant validation authorization |

Consequently, no repository or customer inventory was loaded into the pilot,
no evidence-eligible pack was generated, and no labels or human metrics were
invented.

## Intended pilot when a dataset is authorized

The approved deterministic design uses seed 1201 and up to 60 units:

```text
LIKELY_DUPLICATE_GROUP                  up to 15
POSSIBLE_DUPLICATE_GROUP_REVIEW         up to 15
CONFLICT                                up to 10
DEFERRED                                up to 10
UNASSIGNED/CANDIDATE-NEIGHBORHOOD       up to 10
```

Current selected counts are `N/A` because sampling is prohibited until a
dataset is explicitly authorized. Shortages will be reported per stratum and
will not be backfilled from another stratum. Units are preferably 2..12
records; larger units are excluded with an explicit reason, never truncated.

The unassigned stratum may use only already-authoritative internal candidate or
neighborhood membership. No new pair search, truth-guided oversampling, or
production decision behavior is introduced.

## Tooling verification without real labels

Synthetic test fixtures exercise the complete offline process:

```text
authorized-dataset rejection
synthetic-fixture-only pack generation
blind/private-manifest separation
deterministic stratified selection and fingerprints
group-first partition validation
unknown/duplicate/omitted record rejection
reviewer A/B agreement
adjudication selection
accepted/review metrics
conflict/deferred/unassigned latent-positive metrics
large-unit exclusion and stratum shortage reporting
```

Every synthetic artifact is stamped `SYNTHETIC_TEST_FIXTURE_ONLY`. Mock labels
are test code only, are not committed as evidence artifacts, and are not
reported as human observations.

The fixed smoke fixture selected 15 units (three per stratum) and repeated with
byte-identical artifacts. Its non-evidence fingerprints are:

```text
blinded pack:     fdc16f6dd46255dd33f86a39e2b34d87d27e6bd273c6199f100cd34a753ed61e
private manifest: 0d2e6c3c45b649f4723825145f53a940f270c714c6539c714710b22774bc63bd
```

## Evidence boundary

The GF-12A1 synthetic baseline showed scale-dependent exact-recall decline,
but this unit neither declares a production defect from that signal nor ignores
it. The future blinded pilot will examine whether accepted groups are
conservative/high precision and whether latent duplicate sets concentrate in
review, conflict, deferred, or unassigned candidate regions.

Pilot stratum yields cannot establish population precision or recall. No
quality, agreement, or acceptance threshold is authorized. No engine
calibration, retrieval/resolution tuning, provider validation, source mutation,
or writeback occurs here.

## Governance state

GF-12 remains STARTED. GF-12A1 remains VERIFIED. GF-12A2 protocol/tooling is
VERIFIED with the pilot blocked on an explicitly authorized representative
non-synthetic validation dataset.

GF-11 remains IN PROGRESS, its bounded performance waiver remains ACTIVE,
`GF11-PERF-100K-COLD-FULL` remains OPEN, and the unchanged 300-second target
remains unmet.

## R18 pair-review extension

R18 received explicit authorization for the protected real dataset and
prepared a separate pair-label package required by the R17 architecture gate.
It preserves this document's group-first pilot conventions and does not
reinterpret the earlier unexecuted group-partition pilot. The R18 package uses
independent Reviewer A/B copies, neutral identifiers, allowlisted source
fields, a private mapping, and empty adjudication. Its status is
`HUMAN_REVIEW_DATASET_PREPARED` / `HUMAN_LABEL_EXECUTION_PENDING`; zero human
labels or metrics exist.
