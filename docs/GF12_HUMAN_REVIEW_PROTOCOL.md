# GF-12 Human Group-Quality Review Protocol

## Authority and bounded purpose

This protocol is the smallest human-quality validation unit after GF-12A1. It
tests whether reviewers can apply a group-first partition schema and whether
accepted, review, conflict, deferred, and bounded unassigned-neighborhood
regions contain human-confirmed duplicate identity sets.

It is not final production-quality signoff, a population-recall study, a
production threshold-tuning process, or an annotation platform. Human review
labels remain downstream/offline evidence and never enter production
discovery, evidence, resolution, G2, review authority, or provider execution.

Versions are:

```text
review protocol: gf12-human-group-review-v1
review pack:     gf12-blinded-review-pack-v1
label schema:   gf12-human-group-label-v1
evaluation:     gf12-human-review-evaluation-v1
sampling seed:  1201
```

## Dataset authorization gate

Every dataset descriptor is classified as exactly one of:

```text
AUTHORIZED_HUMAN_VALIDATION_DATASET
SYNTHETIC_ONLY
UNSPECIFIED/NOT_AUTHORIZED
```

Only the first classification may produce an evidence-eligible pilot pack.
The normal pack builder fails closed with `HUMAN_REVIEW_DATASET_REQUIRED` for
either other classification. A separate synthetic-smoke builder exists only
for automated fixture coverage and stamps both artifacts
`SYNTHETIC_TEST_FIXTURE_ONLY`; those labels and metrics are never human
evidence.

Authorization must be explicit repository/customer governance metadata. An
ordinary upload, demo CSV, illustrative labeled-pair file, or customer file is
not implicitly authorized. No raw authorized inventory is committed by this
protocol.

## Primary review unit and task

The primary unit is one bounded candidate identity set or authoritative
candidate neighborhood, not an A/B pair. The reviewer partitions all presented
records into:

- zero or more same-underlying-physical-item sets of at least two records;
- explicit unmatched/singleton records; and
- explicit insufficient-evidence records or candidate subsets.

This supports two-record and 3+ member identities, mixed candidate sets,
splits, merges, and abstention. Pair judgments are derived only as diagnostics.

Preferred units contain 2..12 records. A larger authoritative unit is not
truncated. The v1 pilot excludes it with `LARGE_REVIEW_UNIT_EXCLUDED` and
reports the exclusion. Units below two records are likewise not review units.

## Blinded record field classification

| Field | Classification | Rationale |
| --- | --- | --- |
| stable record reference | REQUIRED_FOR_IDENTITY_REVIEW | Stable partition member identity |
| source row reference | REQUIRED_FOR_IDENTITY_REVIEW | Distinguishes duplicate-valued source rows |
| part number | REQUIRED_FOR_IDENTITY_REVIEW | Direct item evidence when present |
| description | REQUIRED_FOR_IDENTITY_REVIEW | Primary human-readable technical evidence |
| product category | REQUIRED_FOR_IDENTITY_REVIEW | Bounded physical-item context |
| HSN/SAC | REQUIRED_FOR_IDENTITY_REVIEW | Bounded category/technical context |
| site/contract | OPTIONAL_CONTEXT | Context only, never a hard identity rule |
| UOM | OPTIONAL_CONTEXT | Mapping context only, never identity authority |
| status, score, channel, fusion/RRF, GF4/GF5 decision | NOT_REQUIRED | Would bias review |
| benchmark truth, expected label, sample stratum | NOT_REQUIRED | Hidden evaluation information |
| arbitrary source columns, full rows, personal/unrelated fields | NOT_REQUIRED | Outside minimum data purpose |

No credentials, tokens, keys, authorization headers, environment values,
provider payloads, or unrelated personal information are fields in either
artifact.

## Artifact separation

### `BLINDED_REVIEW_PACK`

The reviewer-visible artifact contains only protocol/pack versions, dataset
identity and fingerprint, evidence classification, seed, opaque review-unit
IDs, allowlisted record views, size classification, and pack fingerprint.

It contains no system status, score, retrieval provenance, fusion score,
decision, truth, expected label, sample stratum, or private evidence.

### `PRIVATE_EVALUATION_MANIFEST`

The private artifact contains the opaque review-unit ID, internal source-unit
reference, source record references, system status, system grouping, sampling
stratum, bounded internal evidence references, production-result fingerprint,
stratum counts/shortages, large-unit exclusions, pack fingerprint, and manifest
fingerprint. A reviewer neither needs nor receives this artifact.

## Deterministic sampling

For an explicitly authorized dataset, seed 1201 selects independently within:

| Stratum | Maximum |
| --- | ---: |
| `LIKELY_DUPLICATE_GROUP` | 15 |
| `POSSIBLE_DUPLICATE_GROUP_REVIEW` | 15 |
| `CONFLICT` | 10 |
| `DEFERRED` | 10 |
| `UNASSIGNED/CANDIDATE-NEIGHBORHOOD` | 10 |

Each unit receives an opaque SHA-256-derived stable ID from dataset identity,
dataset fingerprint, production-result fingerprint, pack version, and canonical
record references. Selection rank is a SHA-256 function of that ID, pack version,
and seed. Short strata are
reported and never replenished from another stratum. Unassigned units must be
supplied by an already-authoritative candidate/neighborhood boundary; the pack
tool creates no candidate-search semantics.

Given the same dataset fingerprint, production-result fingerprint, seed, pack
version, and candidates, both canonical JSON artifacts and fingerprints are
byte-identical. Timestamps are absent from fingerprint inputs.

## Human label contract

Each deterministic label file records:

```text
label_schema_version
review_protocol_version
review_pack_version
review_unit_id
dataset_id / dataset_version
reviewer_code
reviewer_role: REVIEWER | ADJUDICATOR
record_refs_presented
same_item_groups
unmatched_record_refs
insufficient_evidence_refs
insufficient_evidence_groups
confidence: HIGH | MEDIUM | LOW | UNSPECIFIED
structured reason_codes
completion_state: DRAFT | COMPLETE
```

Free text is neither required nor present in v1. Reviewer codes are bounded
pseudonymous identifiers. Canonical ordering is required rather than silently
repaired.

Validation fails closed on wrong versions, unknown review units or records,
record-set mismatch, duplicate presented references, a same-item group smaller
than two, one record in multiple partition categories, noncanonical ordering,
unknown dataset context, or an omitted record in a complete label. Draft labels
are never evaluated as completed evidence.

## Reviewer independence and adjudication

Reviewer A and reviewer B use separate pseudonymous codes and independently
receive the blinded pack. The same code cannot constitute two independent
reviews. If completed reviewer partitions disagree, the evaluation requires a
separate completed adjudicator label before selecting an effective label. A
single reviewer is sufficient only for process testing and never final
human-reviewed production signoff.

Agreement outputs are explicitly labeled:

```text
REVIEWER AGREEMENT DIAGNOSTICS
```

They contain exact partition agreement, pairwise co-membership agreement, and
directional pairwise precision/recall/F1 between reviewers. Records marked
insufficient by either reviewer are excluded from comparable partition pairs.
No agreement threshold is authorized.

## Human-outcome metrics

Accepted/review strata report exact system/human group match rate,
human-confirmed same-item membership rate, observed merge errors, observed
split errors, and insufficient-evidence rate.

Conflict, deferred, and unassigned-neighborhood strata report latent duplicate-
set yield, duplicate sets and records identified by reviewers, and
insufficient-evidence rate. Stratum yields are not extrapolated into whole-
population recall or precision without a separately authorized probability
sample and weighting design.

GF-12A1 may be compared only directionally: its canonical baseline suggested
increasing exact precision and declining exact recall with scale. This pilot
may examine whether accepted groups are conservative and whether latent
positives occur in cautious/non-accepted regions. It does not numerically tune
the engine. Any threshold or semantic change requires a separate governance
task.

## Isolation and safety

The implementation is under `backend/app/benchmarks/` and uses pure immutable
contracts. It imports no database, scan runner, provider, network client, or
production orchestration module. Reverse-import tests prove production modules
do not import the protocol, pack, or evaluator. There are no schema, migration,
dependency, API, frontend, provider, source-data, or production-semantic
changes.
