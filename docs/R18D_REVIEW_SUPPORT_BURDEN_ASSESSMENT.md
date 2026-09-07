# R18D Review-Support Burden Assessment

## Classification and scope

`R18D_GF5_PARTITION_POLICY_CONFOUNDED`

R18D is assessment-only. Runtime detector behavior is unchanged, the R18C
Strong-to-Review correction is preserved, and Review support is measured but
not modified. The Senior judgments are development/diagnostic evidence; the
300-row Evaluation panel below is a `POST_R18C_DEVELOPMENT_EFFECT`, not
independent validation or a production precision/recall claim.

Starting baseline was `244d454bd4c307f62d53e4ab024df5ffd9b9d104` on
`llm-assisted-mvp`. The protected tag remained
`d510cf3c18b3a8448d0f79be3e59c398efb32eae`. The unrelated untracked
`List_20260709_093045.xlsx` was not inspected, modified, hashed, staged, or
deleted. No environment file, key, credential, token, authorization header, or
secret was accessed. Provider calls were 0; Docker and services were not used.

## Post-R18C development matrix

| Senior label | Strong | Review | Non-groupable | Cannot-link | Total |
|---|---:|---:|---:|---:|---:|
| SAME | 31 (49.206%) | 29 (46.032%) | 1 (1.587%) | 2 (3.175%) | 63 |
| DIFFERENT | 3 (1.630%) | 58 (31.522%) | 82 (44.565%) | 41 (22.283%) | 184 |
| INSUFFICIENT | 0 (0%) | 28 (52.830%) | 18 (33.962%) | 7 (13.208%) | 53 |
| Total | 34 | 115 | 101 | 50 | 300 |

Column composition is: Strong 91.176% SAME and 8.824% DIFFERENT; Review
25.217% SAME, 50.435% DIFFERENT, and 24.348% INSUFFICIENT; Non-groupable
0.990% SAME, 81.188% DIFFERENT, and 17.822% INSUFFICIENT; Cannot-link 4% SAME,
82% DIFFERENT, and 14% INSUFFICIENT.

| Senior label | HIGH Review | MEDIUM Review | LOW Review |
|---|---:|---:|---:|
| SAME | 4 | 5 | 20 |
| DIFFERENT | 29 | 27 | 2 |
| INSUFFICIENT | 2 | 26 | 0 |

Review provenance is 73 lexical-only/unresolved, 41 trusted-identity-present,
and one mixed-evidence row. Complete class-by-confidence and
class-by-provenance matrices are retained in the deterministic JSON artifact.

## Review population and origin

There are 115 current Review rows: 29 Senior SAME, 58 DIFFERENT, and 28
INSUFFICIENT. The row audit captures pair ID, judgment/confidence/reason,
sampling stratum, provenance, exact-generic state, `LexicalTrustAssessment`,
origin, reason codes, identity and part-number support, description dominance,
unresolved discriminators, typed support, technical mismatch, cannot-link
state, and group-impact trace.

| Origin | SAME | DIFFERENT | INSUFFICIENT | Total |
|---|---:|---:|---:|---:|
| `NATIVE_REVIEW` | 21 | 51 | 27 | 99 |
| `R18C_DEMOTED_STRONG_TO_REVIEW` | 8 | 7 | 1 | 16 |

The 16 R18C demotions are intentional safety outcomes, not automatically open
defects. Analysis-only usefulness categories are:

| Category | Count | Interpretation |
|---|---:|---|
| `USEFUL_REVIEW_SUPPORT` | 29 | Senior SAME; human review is appropriate |
| `NOISY_REVIEW_SUPPORT` | 14 | Senior DIFFERENT plus weak/description-dominant risk |
| `OVERCOMMITTED_REVIEW_SUPPORT` | 28 | Senior INSUFFICIENT but system presents positive support |
| `AMBIGUOUS_REVIEW_SUPPORT` | 44 | Evidence does not authorize a safe policy change |

These categories are report-only and are not production contracts.

## General patterns and SAME controls

| Candidate pattern | DIFFERENT Review | SAME Review | SAME Strong | Finding |
|---|---:|---:|---:|---|
| R18C lexical-independence risk | 8 | 10 | 0 | Review controls collide more often than DIFFERENT cases |
| Higher-specificity description-dominant risk | 7 | 8 | not used | Still harms more SAME Review controls |
| Exact generic-only Review | 1 | 2 | not used | Little benefit and conflicts with Bicycle preservation |

DIFFERENT rows show combinations of description dominance, weak independent
part-number coherence, unresolved discriminators, populated cross-field
mismatch, and generic/copy risk. None of the tested general patterns is safe
for Review suppression. No noun-specific or expert-label-dependent runtime
rule, model fitting, or training was used.

## Group-impact trace

The Evaluation pairs belong to persisted Scan 31. Its G2_V2 state is a
pre-R18C historical projection, used only for bounded topology/burden tracing;
it is not represented as a current post-R18C rerun.

| Group-impact category | Review edges |
|---|---:|
| `SUPPORTS_ACCEPTED_LIKELY_GROUP` | 7 |
| `SUPPORTS_ACCEPTED_REVIEW_GROUP` | 16 |
| `CONTRIBUTES_TO_DEFERRED_FAMILY` | 80 |
| `CONTRIBUTES_TO_CONFLICT_CONTEXT` | 10 |
| `BRIDGE_OR_PARTITION_RELEVANT` | 2 |

Thus 92/115 Review edges are outside accepted groups and mainly carry
deferred/conflict context. Pair burden is not client group burden.

## Bounded counterfactual group sensitivity

The shadow removes only selected sampled Review edges from persisted support
graphs. It does not mutate evidence or claim to reproduce GF5 partition
selection under a changed policy.

| Policy | Edges | Groups touched/lost | SAME-supported groups harmed | Deferred families touched |
|---|---:|---:|---:|---:|
| lexical-independence risk | 21 | 1 / 1 | 1 | 6 |
| higher-specificity risk | 17 | 1 / 1 | 1 | 6 |
| exact generic-only | 4 | 2 / 2 | 2 | 1 |

All lost accepted groups are Review groups. No Likely group loses connectivity
and cannot-link evidence is unchanged. Every candidate harms an expert-SAME-
supported group, while the exact partition result is unknown under the
unresolved GF5 objective. No safe client benefit is demonstrated.

## Client XLSX burden

Persisted Scan 31 exposes 89 Review groups containing 190 members in the System
Group XLSX. In the bounded Evaluation trace, 16 Review edges directly support
accepted Review groups. The tested policies touch one or two and safely remove
none. The export was not generated, opened, or changed.

Future XLSX work must distinguish Review caution, lexical-only support,
R18C-demoted Strong, unresolved identity differences, and why review is
required. These are requirements only; XLSX vNext remains not started.

## Scan-33 and Bicycle safety

The exact verified R18C in-memory Scan-33 reference remains the bounded control:
1,124 proposals/evidence edges, 21 cross-site proposals, 21/21 Bicycle
relationships at generic-only Review, two accepted Review groups, four
conflicts, three deferred work units, 113 unassigned records, and zero provider
calls. Head Light versus Tail Light remains `CANNOT_LINK`.

Blanket generic Review suppression would erase all 21 Bicycle edges although
GF5 already safely defers that family. Pair-level Review can therefore be useful
upstream even when it produces no accepted group. R18D changes no runtime code,
and focused Scan-33/Bicycle/Head-Tail regressions pass.

## GF5 partition-policy confound

The current objective remains:

```text
(covered, likely_members, strong, -review, -group_count)
```

The architecture describes maximizing Review after Strong, while implementation
penalizes Review. Suppression changes a negatively weighted term and can alter
which equal-coverage partition wins. Connectivity shadows cannot establish a
group-output improvement. The conclusion is
`GF5_PARTITION_POLICY_CONFOUNDED`; R18D does not fix the objective or authorize
a Review correction.

## Future group evidence, confidence, and exports

Future group confidence must distinguish Strong, native Review, R18C-demoted
Review, generic-only Review, independent identity evidence, Review burden,
partition ambiguity, and cannot-link presence. Pair labels cannot calibrate
group confidence; new blinded group-level human evidence is required.

Reviewer B remains `DEGRADED_ONE_CLASS_RESPONSE / SECONDARY_ONLY` and was not
used as truth. No LLM, group confidence, export redesign, or corrected human
label was created.

## Artifacts and tests

| Ignored artifact | Bytes | SHA-256 |
|---|---:|---|
| `r18d_review_support_analysis.csv` | 511,557 | `1111b3e96bec26952308578bd1481f7ef3fc626c016016c9ac9c7e4f86c261f9` |
| `r18d_group_impact_analysis.csv` | 16,258 | `49e12765572b98a1378a1c0dd2f1a0f91cf5c2a790119dda21f90b14ba59b8ff` |
| `r18d_shadow_counterfactual_summary.json` | 11,256 | `74c909a665147327ffec24162fc1039f97a6defe479edad8d2e06266c26cec4b` |

Focused verification passed 40 tests with one existing pytest configuration
warning. Production detector, resolver, projection, API, frontend, review,
export, schema, migration, and dependency code are unchanged.

## Decision

Primary classification: `R18D_GF5_PARTITION_POLICY_CONFOUNDED`.

Secondary findings: Review burden is concentrated in deferred/conflict context;
candidate patterns collide with SAME controls; pair Review noise is not proven
to yield safely removable client groups; and group evidence is the main
remaining uncertainty.

`NEXT = R18G_GROUP_LEVEL_HUMAN_EVIDENCE`

## R18G-A follow-up

R18G-A subsequently prepared the governed group-level package and is
`R18G_AWAITING_GROUP_HUMAN_REVIEW`: 48 DEVELOPMENT and 16 SEALED HOLDOUT
hypotheses, zero labels, and zero provider calls. R18D's classification remains
unchanged, and no Review suppression or GF5 objective change was authorized.
