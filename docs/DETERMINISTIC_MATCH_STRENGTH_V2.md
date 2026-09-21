# Deterministic Match Strength V2

`DETERMINISTIC_MATCH_STRENGTH_V2` is a read-only, post-GF5 advisory projection.
It summarizes persisted, verified deterministic supporting evidence; it does not
change discovery, evidence classification, group membership, review authority,
or any source record.

## Why V1 was rejected

The historical V1 mostly mapped `REVIEW_SUPPORT` to 50 and `STRONG_SUPPORT` to
100. That category-to-number conversion provided only two practical values and
lost the discrimination already present in the canonical evaluator. V2 instead
uses its persisted continuous 0-100 score. In the audited two-member population,
190 groups retained 117 distinct values.

That continuous value is produced by the existing canonical deterministic
evaluator and persisted with its evidence. V2 adds no scorer, similarity model,
group-size bonus, AI signal, or category-to-number mapping.

## Calculation

- Two-member groups retain the exact persisted deterministic edge score.
- For groups of three or more members, supporting scores are sorted and the
  25th percentile is calculated by exact linear interpolation at
  `(n - 1) * 0.25`.
- Each member's best support is the maximum incident supporting-edge score.
- The weakest member anchor is the minimum of those member-best values.
- The base score is the minimum of the 25th percentile and weakest member
  anchor.
- The final score is `base score * supporting-edge density`, rounded to two
  decimal places using deterministic half-even decimal rounding.

The bands are `HIGH_MATCH` at 90 or above, `MODERATE_MATCH` from 60 through
89.99, and `BORDERLINE_MATCH` below 60. A band is separate from the signed GF5
evidence tier and from human review authority.

The 90 and 60 boundaries come from the canonical evaluator's longstanding
ordinary numeric decision thresholds. They are reviewer-facing bands only:
safety rules may cap or downgrade a relationship, and a high numeric value can
therefore coexist with a Review Evidence tier. The UI explicitly explains this
crossover instead of capping or relabeling the score.

Created Date is not included in Match Strength. It contributes zero, does not
change any band, and is not added as an unrequested temporal signal.

## Fail-closed boundary

A group is explicitly unscored when a supporting score is missing, score
semantics cannot be verified, the evidence snapshot is incompatible, a final
group contains cannot-link evidence, or any member lacks supporting evidence.
Unknown evidence is never represented as zero. The projection does not invoke
the deterministic evaluator or an LLM provider.

## Presentation and export

The authoritative identity-read API adds typed score, band, status, diagnostic,
and safety-crossover fields. The UI presents the value as a deterministic
evidence summary, never as a probability. CSV and the five-sheet client XLSX
carry the same projection; the workbook overview contains band counts and its
technical sheet contains the version, status, reason, and derivation metrics.
Human-review fields and workflow remain unchanged.

## Shadow validation

Before visible integration, the provider-disabled 5,327-row protected CSV
shadow run reproduced the authoritative detector baseline exactly: 208 groups
(82 stronger-evidence and 126 review-evidence), 32 conflicts, 32 deferred work
units, 436 grouped records, 4,891 unassigned records, and zero cross-site
groups. All 208 groups were scored, including all 190 two-member groups and all
18 multi-member groups. The distribution was 117 high, 91 moderate, zero
borderline, and zero unscored. Detector invariants S0-S10 and the frozen request
fingerprint were identical before and after projection; provider calls were
zero.

## Edge cases and limitations

The projection rejects malformed groups, duplicate/self edges, out-of-range
scores, unsupported edge classes, cannot-link evidence in a final group, and
members with no support. Incomplete but valid graphs are density-penalized; a
missing score on a relationship classified as supporting is unscored rather
than silently treated as zero.

Match Strength is not probability, confidence, precision, recall, accuracy, or
calibration. The acceptance population has complete support density for every
multi-member group, so density behavior is proven by golden tests but is not
empirically discriminating in that particular dataset. Scores from different
request configurations are not assumed exchangeable because selected fields
and Site mode affect the underlying evaluator context.

Future calibration requires collecting real confirmed and rejected reviewer
outcomes, conducting a separate calibration study, and only then considering a
distinct probability model under a new contract version. V2 does not perform
or claim that calibration.
