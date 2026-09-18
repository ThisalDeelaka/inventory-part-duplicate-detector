# GF5 Targeted-Evidence Score Persistence V1

## Classification

```text
GF5_TARGETED_SCORE_PERSISTENCE_VERIFIED
DEMO_SAFE_WITH_TARGETED_SCORE_PERSISTENCE
```

This change preserves an already-computed deterministic pair score. It does
not calculate a new score, change duplicate detection, or expose Match Strength
to users.

## Blocker addressed

The Match Strength V2 evidence audit found that ordinary GF4 proposal evidence
persisted `deterministic_score`, while the GF5 targeted-evidence path discarded
that value. Final groups can contain targeted-only internal relationships, so a
future read-only projection could not obtain every evaluated pair's continuous
score without rerunning the evaluator.

This change closes only that loss seam.

## Exact data path

### Score creation

`backend/app/engine/decision_engine.py::evaluate_candidate` creates the
bounded `final_score`. The canonical evaluator in
`backend/app/engine/identity_evidence_evaluator.py` exposes the exact value as
`EvaluatedIdentityRelationship.deterministic_score`.

### Previous loss seam

`backend/app/resolution/validation.py::targeted_result_from_evaluation`
adapted the canonical evaluator result into `TargetedEvidenceResult` but did
not copy `deterministic_score`. Consequently:

- `IdentityResolutionTargetedEvidence` had no score column;
- `_persist_result` could not store a score;
- `load_persisted_resolution_result` could not reload one;
- `G2V2InternalEvidence` and its row model had no score;
- the G2-v2 adapter could preserve only the signed category and provenance.

### New score-preserving path

```text
EvaluatedIdentityRelationship.deterministic_score
  -> targeted_result_from_evaluation
  -> TargetedEvidenceResult.deterministic_score
  -> identity_resolution_targeted_evidence.deterministic_score
  -> load_persisted_resolution_result
  -> G2V2InternalEvidence.deterministic_score
  -> g2_v2_internal_evidence.deterministic_score
  -> load_persisted_g2_v2_manifest
```

No load or read function invokes the evaluator to recover the value.

## Evidence contract version

The targeted-evidence sub-contract is now explicit:

```text
targeted-evidence-v1
targeted-evidence-v2-score-preserving
```

`targeted-evidence-v2-score-preserving` means all prior targeted relationship
semantics plus the exact deterministic score returned by the canonical
evaluator. The active product projection remains G2-v2; this task does not
create a new product/read authority, change projection selection, or expand UI
and export contracts. G2-v2 internal evidence carries the source targeted
sub-contract version so new and legacy rows cannot be confused.

## Field semantics and numeric representation

The field is named `deterministic_score`, matching ordinary GF4 evidence. It
means exactly:

> The deterministic `final_score` already produced by the canonical evaluator
> for this relationship.

The existing evaluator clamps the score to 0 through 100 and rounds its normal
weighted result to two decimal places. The persistence path stores the Python
float directly in SQL `FLOAT` columns and performs no additional rounding,
normalization, category mapping, weighting, capping, or rescoring.

Version-v2 validation requires a numeric, non-boolean value in the inclusive
0-100 range. Legacy v1 evidence must not claim a score.

## Persistence and legacy compatibility

Two additive nullable columns are introduced on each relevant SQLite table:

```text
identity_resolution_targeted_evidence
  evidence_contract_version VARCHAR(80) NULL
  deterministic_score FLOAT NULL

g2_v2_internal_evidence
  source_evidence_contract_version VARCHAR(80) NULL
  deterministic_score FLOAT NULL
```

The existing startup migration functions add missing columns without rewriting
or backfilling rows. Fresh schemas receive the same columns through SQLAlchemy
metadata.

Legacy behavior is intentionally fail-closed:

```text
null targeted contract version -> targeted-evidence-v1
legacy deterministic_score     -> null / unavailable
```

No old row is rescored and no historical value is fabricated. Legacy G2-v2
internal evidence keeps both new fields null, so its old group fingerprint
payload is preserved and it remains readable.

## Fingerprints and provenance

- Targeted request fingerprints are unchanged. They depend only on the request
  identity and inputs.
- GF5 resolution-result fingerprints are unchanged. They continue to protect
  the existing targeted evidence fingerprint rather than introducing score as
  a resolver decision input.
- The canonical evaluator evidence fingerprint is unchanged and already
  includes `deterministic_score` in its signed payload. New targeted evidence
  reuses that exact fingerprint.
- New G2-v2 targeted internal evidence includes its source contract version and
  score in the group fingerprint payload. Therefore new group/manifest output
  fingerprints intentionally protect the preserved fields.
- Legacy G2-v2 rows omit the absent optional fields from fingerprint payloads,
  preserving historical fingerprint semantics.

## GF4 and GF5 authority boundary

GF4 is unchanged:

- no scoring formula or component change;
- no review/strong threshold change;
- no safety-cap or relationship-classification change;
- no selected-field or Site rule change.

GF5 receives two additional provenance fields on `TargetedEvidenceResult`, but
its resolver does not read either field for partition selection, objective
ordering, membership, status, conflicts, cannot-links, deferred work, or
unassigned records. The score is written only after the existing canonical
evaluation and is reloaded only as immutable evidence.

## Round-trip and no-recomputation evidence

Focused tests prove:

- adapter output score equals evaluator output score exactly;
- v2 score and contract version survive GF5 persistence and reload;
- targeted-only internal relationships carry the score through G2-v2
  persistence and reload;
- reload succeeds while the canonical evaluator is patched to raise if called;
- legacy null rows load as v1 with no score;
- legacy SQLite schemas gain nullable columns and retain null values;
- changing the persisted targeted score changes the new G2 group fingerprint;
- request and GF5 resolution fingerprints remain unchanged.

## Fresh 5,327-record coverage audit

The approved historical CSV Git object was loaded directly into a disposable
SQLite database. The protected workbook and local application database were
not accessed. Providers were explicitly disabled.

| Configuration | Targeted rows | Score-producing rows | Persisted scores | Missing scores | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Site + UOM selected | 74 | 74 | 74 | 0 | 100% |
| UOM selected, Site unselected | 27 | 27 | 27 | 0 | 100% |

Every new-format targeted relationship was produced by the canonical evaluator
and used `targeted-evidence-v2-score-preserving`.

## Real-data regression

### Site selected

| Metric | Result |
| --- | ---: |
| Records | 5,327 |
| Candidate groups | 208 |
| Stronger Evidence | 82 |
| Review Evidence | 126 |
| Conflicts | 32 |
| Deferred | 32 |
| Records in groups | 436 |
| Unassigned | 4,891 |
| Cross-site groups | 0 |
| Provider calls | 0 |

Request fingerprint:

```text
fab4c9e6de6bad086bd14b4582d16b9ad64ecb2330b7663f2cf7cab5fff3faff
```

### Site unselected

| Metric | Result |
| --- | ---: |
| Records | 5,327 |
| Candidate groups | 42 |
| Stronger Evidence | 12 |
| Review Evidence | 30 |
| Conflicts | 6 |
| Deferred | 6 |
| Records in groups | 94 |
| Unassigned | 5,233 |
| Cross-site groups | 18 |
| Provider calls | 0 |

Request fingerprint:

```text
6742e55aeecdd734e7e37875abbcf79f8c8ec8a1531d4c06bca6f3ebed49a85a
```

For both runs, every S0-S10 semantic fingerprint matched the committed
request-scoped Site acceptance artifact. This proves unchanged canonical
records, proposals, GF4 evidence, GF5 inputs, selected group IDs/members,
conflicts, deferred work, unassigned records, and visible G2-v2 group
projection.

## User-facing behavior

There are no frontend, API schema, CSV, or XLSX presentation changes. The XLSX
five-sheet and formula-free contracts remain unchanged. Match Strength V2 is
not implemented or claimed by this task.

## Future dependency

This persistence seam is now available for a new Match Strength V2 evidence
audit. Integration into the stable branch and the renewed audit both require
separate authorization.
