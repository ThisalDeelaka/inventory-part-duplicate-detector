# R18C Evidence-Backed Lexical Strong-Support Trust Correction

## Classification

`R18C_LEXICAL_STRONG_TRUST_CORRECTION_VERIFIED`

Starting baseline: `c7a090855dbb2999868d2c5eb1025ebd3a388018` on
`llm-assisted-mvp`. The protected tag remained at
`d510cf3c18b3a8448d0f79be3e59c398efb32eae`. The unrelated untracked
`List_20260709_093045.xlsx` was not inspected, modified, hashed, staged, or
deleted. No environment file or secret was accessed. Provider calls were 0.

## Evidence and governance

R18B's recovered Senior reference contains 316 complete judgments and a
300-pair Evaluation panel. Its lexical-only panel had 9 Strong-on-DIFFERENT,
32 Strong-on-SAME, and 1 Strong-on-INSUFFICIENT outcome. The exact
`GENERIC_DESCRIPTION` rows emitted no Strong result and therefore did not
justify weakening that guard.

The R18 labels influenced this design and are permanently classified as
`DEVELOPMENT_DIAGNOSTIC_EVIDENCE`. The before/after measurements below are a
same-set development effect, not independent validation, precision, recall, or
production accuracy. Any post-change quality claim requires a new untouched
human-labelled holdout or independent client/domain validation.

## Nine risky cases and 32 positive controls

The nine lexical-only Strong-on-DIFFERENT cases were inspected by stable pair
ID with the expert confidence/reason, both immutable canonical source records,
normalized part numbers and descriptions, score components, frozen provenance,
generic state, technical/discriminator evidence, and the proposed trust
assessment. The complete 316-row audit is retained in the ignored artifact
`r18c_lexical_trust_shadow.csv` (1,104,225 bytes, SHA-256
`c3da061c6b93fb86af5811f2972d84d9271106a6e5a9a2573315ea6cf333abae`).

| Pair ID | Expert | General observation | Shadow result |
|---|---|---|---|
| `R18-08459269681B3230` | DIFFERENT / MEDIUM | substantial part-number coherence, populated type agrees | Strong retained |
| `R18-1399A7BBE139DC06` | DIFFERENT / MEDIUM | description-dominant; weak independent part-number coherence | Review |
| `R18-2A2A317E942B02B2` | DIFFERENT / MEDIUM | description-dominant; weak independent part-number coherence | Review |
| `R18-5555DF0C680FAA81` | DIFFERENT / MEDIUM | weak part-number coherence plus populated type mismatch | Review |
| `R18-63C1E19C1EAE5AA7` | DIFFERENT / MEDIUM | current typed signature recognizes identity-role evidence | Strong retained |
| `R18-6AC8CED9FAB6FCE6` | DIFFERENT / HIGH | populated cross-field type mismatch | Review |
| `R18-AC08DE82C654A08D` | DIFFERENT / MEDIUM | description-dominant; weak independent part-number coherence | Review |
| `R18-E6ADB88AC92AA8B7` | DIFFERENT / HIGH | description-dominant; weak independent part-number coherence | Review |
| `R18-FF605311CB343C1C` | DIFFERENT / MEDIUM | description-dominant; weak independent part-number coherence | Review |

The comparison against all 32 lexical-only Strong-on-SAME controls showed
that a blanket lexical-only prohibition would be unjustified. The chosen gate
downgrades 8 of those 32 to Review and retains 24 as Strong. None becomes
non-groupable or cannot-link; every HIGH-confidence SAME remains supported.
Fan Blade, F30, B38, Turbine Lubricating Oil, and Contact Cleaner remain at
least Review. No item name or Senior label appears in the runtime rule.

## General deterministic abstraction

`LexicalTrustAssessment` v1 is deterministic, source-aware, auditable, and
provider-free. It uses the existing identity-signature/signed-evidence
contracts and the scorer's existing component evidence. A description-
dominant lexical-only Strong candidate is downgraded to Review when it lacks
both typed identity support and substantial independent part-number coherence.
A populated part-type mismatch is independently sufficient for the same
cautious downgrade; it is not a cannot-link.

The part-number coherence floor is 80. It is not a duplicate threshold and
cannot promote any pair. Sensitivity checks across 80, 85, and 90 all removed
the same required 7/9 risky cases; the lower edge was selected to preserve more
legitimate Strong aliases. Two bounded preservation signals avoid blanket
demotion: a meaningful token present coherently across both part-number and
description fields, and a short compact alphanumeric model code with an exact
formatting alias. These are general naming/source patterns, not noun-specific
rules.

Persisted downgraded edges carry the applicable deterministic reason codes:

- `LEXICAL_SUPPORT_NOT_INDEPENDENT`
- `CROSS_FIELD_IDENTITY_INCOHERENCE`

The complete assessment is also stored inside `technical_evidence_json` for
later caution/explanation work. Missing fields never count as agreement.

## Shadow and development-set effect

All required shadow gates passed before runtime integration. The rule permits
only `STRONG_SUPPORT -> REVIEW_SUPPORT` and produced no promotions.

| Expert label | Before Strong / Review / Non-groupable / Cannot-link | After Strong / Review / Non-groupable / Cannot-link |
|---|---|---|
| SAME | 39 / 21 / 1 / 2 | 31 / 29 / 1 / 2 |
| DIFFERENT | 10 / 51 / 82 / 41 | 3 / 58 / 82 / 41 |
| INSUFFICIENT | 1 / 27 / 18 / 7 | 0 / 28 / 18 / 7 |

Within lexical-only Strong, DIFFERENT falls from 9 to 2 and SAME from 32 to
24. Both HIGH-confidence lexical Strong-on-DIFFERENT cases become Review.
The ignored JSON summary is 2,061 bytes with SHA-256
`59b87a21d1e5869e7f60f6f10731dd6e2c89503efc8f3c558ef0ab26d8dedea70`.

## Protected behavior and bounded runtime regression

The exact generic guard was not edited. All exact generic rows were unchanged,
all cannot-links were unchanged, and the strict copied-description xfail now
passes through the general trust gate without a fixture-specific exception.
Whole-group cannot-link validation remains unchanged.

An in-memory rerun from the read-only persisted Scan-33 canonical catalog used
the persisted bounded configuration and current production orchestration:

| Metric | R18C result |
|---|---:|
| Runtime | 3.918 seconds |
| Proposals / evidence edges | 1,124 / 1,124 |
| Cross-site proposals | 21 |
| Strong / Review / Cannot-link / Non-groupable edges | 1 / 57 / 21 / 1,045 |
| GF5 work units | 9 |
| Accepted / likely / review groups | 2 / 0 / 2 |
| Conflicts / deferred / unassigned | 4 / 3 / 113 |
| Provider calls | 0 |

All 21 Bicycle relationships still reach evidence/GF5 as Review and retain the
existing generic-family deferral. Head Light versus Tail Light remains a
protected cannot-link. Retrieval, site discovery, GF5 generic cohesion,
resolver partition policy, review authority, exports, frontend, dependencies,
schema, and migrations were not changed.

The persisted Scan-32/31 evidence was used only for the bounded R18 shadow risk
screen; no 5,327-row retrieval rerun was performed and prior architect labels
were not treated as truth.

## Verification and remaining work

Focused lexical/shadow and preservation suites pass. The synthetic showable
product retains its frozen four groups, including its likely group, and the
controlled v1/v2 shadow parity remains exact. The copied/generic strict xfail
was converted to PASS because this general rule satisfies its stated Strong-
support contract; this does not claim that generic/Review burden is solved.

Final verification: 147 focused regression tests passed. The complete backend
suite passed 1,764 tests with 15 skipped, zero xfails, and one existing unknown
pytest-configuration-option warning. Frontend tests were not required because
no frontend source changed.

R18D subsequently measured 115 post-R18C Review rows (99 native and 16 R18C
demotions) without modifying runtime. Candidate suppression patterns collide
with SAME controls, and the unresolved GF5 partition objective confounds a safe
group-output conclusion. See
`docs/R18D_REVIEW_SUPPORT_BURDEN_ASSESSMENT.md`.
