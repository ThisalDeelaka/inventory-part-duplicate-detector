# Targeted Pair-Explanation Evidence V1

## Status

- Primary classification: `TARGETED_PAIR_EXPLANATION_PERSISTENCE_VERIFIED`
- Targeted contract: `targeted-evidence-v3-explanation-preserving`
- Internal projection: `deterministic-pair-explanation-v1`
- New-format availability: `COMPLETE`
- Legacy v1/v2 availability: `PARTIAL_LEGACY`
- Provider calls: 0

This foundation preserves already-computed deterministic facts. It does not
add an explanation engine, renderer, LLM, API field, UI, export field, score,
classification rule, or group-resolution rule.

## Audited loss seam

The canonical source is
`app.engine.identity_evidence_evaluator.EvaluatedIdentityRelationship`, emitted
by `evaluate_canonical_identity_relationship()`. Before adaptation it contains:

- signed `edge_class` and `classification_reason_codes`;
- evaluator version and evaluator evidence fingerprint;
- deterministic score;
- canonical component-score JSON;
- rule decision and rejection reason;
- canonical protected-conflict, generic-evidence, technical-evidence,
  UOM-context, and evaluation-context JSON.

The proposal path stores all of those fields in
`IdentityEvidenceEdgeSnapshot`. The former targeted adapter,
`app.resolution.validation.targeted_result_from_evaluation()`, retained only
the signed class, reason codes, rule decision as `evidence_summary`, evaluator
version, evaluator evidence fingerprint, generic-only flag, and (under v2)
score. `IdentityResolutionTargetedEvidence` persisted only that reduced shape,
and `load_persisted_resolution_result()` could not recover the discarded facts.

The change closes that exact seam. It does not alter the canonical evaluator or
proposal persistence.

## Versioned contracts

The existing versions retain their historical meanings:

- `targeted-evidence-v1`: signed relationship provenance without a persisted
  score or rich explanation facts.
- `targeted-evidence-v2-score-preserving`: v1 semantics plus the already
  computed deterministic score.
- `targeted-evidence-v3-explanation-preserving`: v2 semantics plus canonical,
  structured evaluator evidence, explanation projection version, and an
  independent explanation fingerprint.

`TargetedEvidenceResult` gained three nullable fields:

- `explanation_evidence_json`
- `pair_explanation_contract_version`
- `pair_explanation_fingerprint`

The JSON object contains only evaluator outputs:

```text
component_scores
rule_decision
rejection_reason
protected_conflicts
generic_evidence
technical_evidence
uom_context
evaluation_context
```

The signed relationship, reason codes, score, evaluator version, and source
evidence fingerprint remain typed top-level targeted fields. They are also
covered by the pair-explanation fingerprint and are not duplicated inside the
JSON payload.

## Internal deterministic projection

`app.resolution.pair_explanation.DeterministicPairExplanationV1` is an internal,
non-authoritative read projection with:

- stable endpoints and relationship identity;
- deterministic score and signed relationship;
- component scores;
- classification reason codes, rule decision, and rejection reason;
- protected conflicts and generic evidence;
- technical evidence, including normalized values, discriminator evidence,
  and lexical-trust details where the evaluator produced them;
- UOM and selected-field/evaluation context;
- evaluator/source provenance;
- `COMPLETE` or `PARTIAL_LEGACY` availability;
- explicit missing fields for legacy evidence; and
- a projection contract version and fingerprint.

`project_targeted_pair_explanation()` reads only the targeted result. It never
calls the evaluator. `project_proposal_pair_explanation()` projects the same
contract directly from either an evaluator result or existing rich GF4 row.
Proposal data is not duplicated.

The base pair projection deliberately does not claim that an edge caused a
group. A future group read projection may label an actual final internal edge
`SUPPORTS_FINAL_GROUP`. It must not emit `DECISIVE_PAIR`, `CAUSED_GROUP`, or
equivalent unsupported GF5 causality.

## Field parity

| Field | Proposal/GF4 | New targeted v3 | Status |
|---|---|---|---|
| deterministic score | typed persisted field | typed persisted field | `PRESERVED_IDENTICALLY` |
| signed relationship | typed edge class | typed edge class | `PRESERVED_IDENTICALLY` |
| classification reasons | canonical ordered codes | canonical ordered codes | `PRESERVED_IDENTICALLY` |
| component scores | canonical JSON column | canonical explanation JSON | `PRESERVED_IDENTICALLY` |
| protected conflicts | canonical JSON column | canonical explanation JSON | `PRESERVED_IDENTICALLY` |
| generic evidence | canonical JSON column | canonical explanation JSON | `PRESERVED_IDENTICALLY` |
| technical/normalized evidence | canonical JSON column | canonical explanation JSON | `PRESERVED_IDENTICALLY` |
| lexical-trust/safety evidence | nested technical evidence | nested technical evidence | `PRESERVED_IDENTICALLY` |
| UOM context | canonical JSON column | canonical explanation JSON | `PRESERVED_IDENTICALLY` |
| selected-field/evaluation context | canonical JSON column | canonical explanation JSON | `PRESERVED_IDENTICALLY` |
| rule decision | typed string | typed summary plus structured payload | `PRESERVED_EQUIVALENTLY` |
| rejection reason | typed string | canonical explanation JSON | `PRESERVED_IDENTICALLY` |
| evaluator version | typed string | typed string | `PRESERVED_IDENTICALLY` |
| evaluator evidence fingerprint | typed string | typed string | `PRESERVED_IDENTICALLY` |
| proposal discovery reason | proposal-only source metadata | not a targeted concept | `NOT_APPLICABLE` |
| targeted request reason | not a proposal concept | existing request field | `NOT_APPLICABLE` |

For v1/v2 targeted rows, rich fields are `LEGACY_UNAVAILABLE`; none is
fabricated. No field is `BLOCKED` for new v3 rows.

## Persistence and reload

`IdentityResolutionTargetedEvidence` adds three nullable columns matching the
new `TargetedEvidenceResult` fields. The SQLite demo migration adds the same
columns without backfill. Existing rows remain null.

Persistence copies the canonical payload/version/fingerprint exactly. Reload
constructs `TargetedEvidenceResult` directly from stored columns. Projection
then validates canonical JSON and the independent fingerprint. No candidate
generation, evaluator, provider, or LLM call occurs during reload/projection.

Legacy behavior:

| Stored version | Score | Rich payload | Availability |
|---|---|---|---|
| null / v1 | unavailable | unavailable | `PARTIAL_LEGACY` |
| v2 | preserved | unavailable | `PARTIAL_LEGACY` |
| v3 | preserved | preserved and verified | `COMPLETE` |

An old row with missing rich fields cannot be represented as complete. A v3
row with a missing field, non-canonical serialization, or fingerprint mismatch
fails validation rather than silently degrading or inventing evidence.

## Canonicalization and fingerprint separation

Canonical serialization uses UTF-8 JSON, ASCII escaping, recursively sorted
object keys, and compact separators. The SHA-256 pair-explanation fingerprint
covers:

- projection contract version;
- canonical endpoint references;
- deterministic score and signed relationship;
- sorted classification reason codes;
- evaluator version and evaluator evidence fingerprint;
- source kind and targeted request fingerprint where applicable;
- availability; and
- the exact structured explanation evidence object.

The following existing fingerprint implementations were not changed:

- targeted request fingerprint;
- evaluator evidence fingerprint;
- GF5 hypothesis and resolution fingerprints;
- G2-v2 group/manifest fingerprints.

The new fields are deliberately absent from GF5 decision inputs. Fresh
acceptance reproduced every frozen S0-S10 fingerprint, confirming that the new
payload is provenance-only.

## Real-data acceptance

The approved historical CSV Git blob
`f6889ef3b05cee89369af232a8344aff12f969a7:data/List_20260709_093045.csv`
was verified against its frozen SHA-256 and loaded into disposable SQLite
databases. The protected workbook and application database were not accessed.
Providers were explicitly disabled.

### Site selected (`CONTRACT`, `UNIT_MEAS`)

Request fingerprint:
`fab4c9e6de6bad086bd14b4582d16b9ad64ecb2330b7663f2cf7cab5fff3faff`

| Measure | Result |
|---|---:|
| Records | 5,327 |
| Groups | 208 |
| Stronger Evidence | 82 |
| Review Evidence | 126 |
| Conflicts | 32 |
| Deferred | 32 |
| Grouped records | 436 |
| Unassigned | 4,891 |
| Cross-site groups | 0 |
| Provider calls | 0 |
| Match Strength scored/unscored | 208 / 0 |
| High / Moderate / Borderline | 117 / 91 / 0 |

Explanation coverage:

| Measure | Result |
|---|---:|
| Supporting relationships | 251 |
| Complete | 251 |
| Partial/generic/rerun/unknown | 0 / 0 / 0 / 0 |
| Proposal complete | 242 |
| Targeted complete | 9 |
| Two-member groups complete | 190 / 190 |
| Multi-member groups complete | 18 / 18 |
| High-Match/Review exact reasons | 35 / 35 |

Every S0-S10 count and fingerprint matched the frozen Site-selected artifact.

### Site unselected (`UNIT_MEAS`)

Request fingerprint:
`6742e55aeecdd734e7e37875abbcf79f8c8ec8a1531d4c06bca6f3ebed49a85a`

| Measure | Result |
|---|---:|
| Records | 5,327 |
| Groups | 42 |
| Stronger Evidence | 12 |
| Review Evidence | 30 |
| Conflicts | 6 |
| Deferred | 6 |
| Grouped records | 94 |
| Unassigned | 5,233 |
| Cross-site groups | 18 |
| Provider calls | 0 |
| Match Strength scored/unscored | 42 / 0 |
| High / Moderate / Borderline | 26 / 14 / 2 |
| Supporting relationships complete | 68 / 68 |
| Proposal complete | 58 |
| Targeted complete | 10 |
| Two-member groups complete | 36 / 36 |
| Multi-member groups complete | 6 / 6 |
| High-Match/Review exact reasons | 14 / 14 |

Every S0-S10 count and fingerprint matched the frozen Site-unselected artifact.

## Authority and product boundaries

The preserved payload is explanatory provenance only. It is not read by
candidate generation, pair scoring, GF4 classification, GF5 partitioning or
objective logic, membership selection, cannot-link processing, Match Strength,
Evidence Tier, Site policy, or human review.

No API schema, frontend, CSV, XLSX, group summary, relationship map, or Docker
image changed. `PROJECT_SSOT.md` and `docs/CURRENT_PROJECT_ASSESSMENT.md` are not
updated on this isolated branch because the foundation has not been integrated
into the authoritative branch.

## Deterministic rendering and LLM dependency

The contract now contains the persisted fields needed for a future renderer to
separate supporting components, weakening/safety facts, protected conflicts,
and final classification reasons without inferring from score. Rendering rules
and user-facing wording remain future work.

The evidence foundation is ready for controlled integration. It does not
authorize LLM behavior. Any later LLM may only paraphrase a deterministic
rendering of these facts and may not change score, class, tier, membership, or
human-review authority.
