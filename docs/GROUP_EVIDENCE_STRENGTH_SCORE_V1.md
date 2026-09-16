# Group Evidence Strength Score V1

## Status

`GROUP_EVIDENCE_SCORE_V1_VERIFIED`

Demo classification: `DEMO_SAFE_WITH_GROUP_EVIDENCE_SCORE`.

## Purpose and interpretation

Group Evidence Strength answers: **How strongly is this already-generated
candidate group supported by deterministic evidence?** It is a read-only
engineering index, not a duplicate probability, AI confidence, human decision,
accuracy result, or automatic merge instruction.

The projection runs strictly after authoritative GF4 relationship
classification and GF5 group formation:

```text
canonical records -> GF4 -> GF5 -> final candidate group
                  -> Group Evidence Strength projection -> API/UI/XLSX
```

GF4 and GF5 do not import or consume the scoring module. The score is absent
from group identity, membership, read fingerprints, request fingerprints,
review persistence, and database schema.

## Versioned V1 rubric

Version: `GROUP_EVIDENCE_SCORE_V1`.

Each authoritative internal relationship contributes:

- `STRONG_SUPPORT`: 1.0 point
- `REVIEW_SUPPORT`: 0.5 point
- `NON_GROUPABLE`: 0 points
- `CANNOT_LINK`: invariant violation; no normal score

For `n` group members:

```text
possible relationships = n * (n - 1) / 2
score = 100 * (Strong + 0.5 * Review) / possible relationships
```

Band assignment uses the unrounded score:

- High Evidence: 75–100
- Moderate Evidence: 50–74.999…
- Limited Evidence: 0–49.999…

The projection also exposes possible, Strong, Review, and Non-groupable
relationship counts, support density `(Strong + Review) / Possible`, and the
Strong share `Strong / (Strong + Review)`. A zero supported-relationship
denominator yields a safe zero Strong share.

Cannot-link inside a final group fails closed with
`SCORE_INVARIANT_VIOLATION`. Historical G2-v1 and progressive snapshots that
do not retain a classification for every possible pair remain explicitly
unscored; V1 does not invent missing relationship states.

## Created-date decision

`CREATED_DATE_NOT_IDENTITY_EVIDENCE_V1`

Created date is excluded from the formula, band, group membership, GF4, GF5,
and cannot-link behavior. Creation time can reflect migration, cutover, bulk
import, cleanup, replication, re-keying, or legitimate later creation. Equal
dates do not prove identity, and different dates do not disprove it. A future
Temporal Context feature would require separate evidence and validation.

## Product presentation

The additive API read model exposes the versioned score, band, counts, support
density, and Strong share. The frontend shows `Evidence Strength`, an `x / 100`
index, its band, compact relationship diagnostics, `Human Review Required`,
and the statement that the score is not a probability of duplication. Default
group order and visibility are unchanged.

The application summary and XLSX Overview show High, Moderate, and Limited
counts with visible ranges. `Review Groups` adds group-level Evidence Score,
Evidence Band, and Support Density columns using the existing safe vertical
merge rule. `Group Index` adds sortable Evidence Score and Evidence Band
columns. `Technical Reference` records the name, version, formula, ranges,
read-only authority boundary, and Created-date policy. The workbook remains
formula-free and retains exactly its existing five sheets.

## Real 5,327-record shadow validation

The safe persisted canonical scan-34 records were replayed in an isolated
in-memory database using the verified Site + UOM request and provider `none`.
The protected workbook was not accessed. The current result exactly preserved
208 candidate groups, 82 Stronger Evidence groups, 126 Review Evidence groups,
436 group members, 32 conflicts, 32 deferred work units, and 4,891 unassigned
records.

Score results:

| Measure | Result |
|---|---:|
| Scored groups | 208 of 208 |
| Minimum / maximum | 50 / 100 |
| Mean | 70.1122 |
| Median | 50 |
| High Evidence | 83 |
| Moderate Evidence | 125 |
| Limited Evidence | 0 |

Distribution by the existing authoritative tier:

| Existing tier | High | Moderate | Limited |
|---|---:|---:|---:|
| Stronger Evidence | 82 | 0 | 0 |
| Review Evidence | 1 | 125 | 0 |

The five highest inspected groups were two-member all-Strong groups scoring
100. The five lowest and five nearest the 50 boundary were all-Review groups
scoring 50. The closest groups below 75 were three-member groups with one
Strong and two Review relationships, scoring 66.6667. The notable divergence
was one three-member Review Evidence group with two Strong and one Review
relationship, scoring 83.3333 / High. This is intelligible: the existing tier
and the new index answer different questions, and V1 deliberately does not
rewrite tier logic to force alignment.

The generated shadow artifact is
`artifacts/group_evidence_score_v1/site_selected_shadow.json`. It records the
unchanged request fingerprint
`fab4c9e6de6bad086bd14b4582d16b9ad64ecb2330b7663f2cf7cab5fff3faff`
and provider calls `0`.

## Authority, determinism, and future calibration

The score has no randomness, clock, environment, LLM, Created-date, group-size
bonus, human-review outcome, or direct Site/UOM input. Site and UOM can affect
the authoritative relationship/group pipeline, but V1 consumes only the final
relationship classes and never double-counts their raw values. Human review
continues to be the sole operational authority.

A genuine probability model is future work only:

```text
Evidence Score V1
  -> collect sufficient human-confirmed and rejected groups
  -> evaluate calibration by score bucket
  -> if statistically justified, create a separate calibrated model/version
```

No accuracy, precision, recall, or probability-calibration claim is made.
