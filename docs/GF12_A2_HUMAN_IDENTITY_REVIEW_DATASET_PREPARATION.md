# GF-12A2-R18 blinded human identity-label dataset preparation

## Result and architectural trigger

R18 is `R18_HUMAN_REVIEW_DATASET_PREPARED`. R16 found 12 trusted-identity and
240 lexical-only/unresolved edges among 252 accepted R12 edges. R17 then found
that no tested A-F generalization safely covered the seven legitimate controls:
`R17-G_NO_SAFE_GENERALIZATION_PROVEN`. R18 therefore prepares independent
human evidence; it does not choose or implement a semantic rule.

GF-12A2 is now `HUMAN_REVIEW_DATASET_PREPARED` with
`HUMAN_LABEL_EXECUTION_PENDING`. Human labels completed are **0**. This is not
verification, completion, ground truth, or a detector-quality claim.

## Authorized source candidate population

The user explicitly authorized R18 over the protected real CSV. Its verified
size is 3,265,800 bytes and SHA-256 is
`8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
The source population is the persisted, completed scan-31 GF2/GF4 population:
5,327 canonical records, discovery run 8, evidence run 7, and 20,395 unique
candidate edges. Discovery fingerprint is
`a2fb96cc6445e7295b7c414efdfebf77235921b8185316f73575d0175fd58629`.
No global all-pairs operation, fresh detector scan, provider call, or source
mutation occurred.

Population counts used by the deterministic sampler are:

| Stratum | Population | Selected |
|---|---:|---:|
| current CANNOT_LINK | 139 | 50 |
| STRONG / shadow trusted identity | 7 | 7 |
| STRONG / shadow lexical-only | 261 | 42 |
| STRONG / shadow mixed | 1 | 1 |
| REVIEW / shadow trusted identity | 41 | 41 |
| REVIEW / shadow lexical-only | 879 | 57 |
| REVIEW / shadow mixed | 1 | 1 |
| NON_GROUPABLE / shadow trusted identity | 16 | 16 |
| NON_GROUPABLE / shadow lexical-only | 4,911 | 45 |
| NON_GROUPABLE / shadow insufficient | 14,121 | 40 |
| REVIEW / shadow insufficient | 18 | 0 |

No required source stratum is unavailable. The small trusted and mixed strata
are included in full. The 300 selected evaluation pairs contain 45 accepted-
group-edge contexts, 78 conflict contexts, 172 deferred contexts, and 5 other
candidate contexts, so the evaluation panel is not accepted-edge-only.

## Panels and deterministic selection

Panel A contains 20 diagnostic pairs: all seven R17 legitimate controls and
H1-H13, where H10-H13 are the four R12 false-group pairs. This covers phrase
and abbreviation, structured model/type, copied/generic descriptions,
directional side, component/object contradictions, different part numbers,
cross-site evidence, and unresolved cases. Its deliberately enriched
composition cannot support population prevalence, precision, or recall.

Panel B contains 300 unique real candidate edges. Within each declared stratum,
selection orders pairs by SHA-256 of dataset version, seed 1201, stratum, and
canonical stable record references. Selection is independent of future human
labels. Four pairs occur in both panels; each appears once in the reviewer pack
with both memberships retained only in the private mapping. There are 316
unique reviewer rows.

## Blinding and review contract

Reviewer-visible evidence is limited to a neutral `review_pair_id` and each
side's part number, description in use, description, master description, type
designation, dimension/quality, UOM, part type, and site. Site is optional
context under the existing A2 protocol and never identity authority.

The reviewer files contain no stable hashes, source rows, panel/stratum,
detector score, GF4 class, group ID/status, R16 bucket, R17 family, expected
answer, or A-F outcome. The label is one of `SAME_IDENTITY`,
`DIFFERENT_IDENTITY`, or `INSUFFICIENT_INFORMATION`; confidence is HIGH,
MEDIUM, or LOW; one primary bounded reason code is selected, with optional free
text. No label, confidence, reason, or comment is prefilled.

Reviewer A and Reviewer B receive separate copies with identical pair content
and independent reviewer metadata. Neither file contains the other's answers.
The adjudication workbook contains neutral pair IDs and empty fields for both
reviewer labels, agreement, adjudicated label, adjudicator, and reason. It does
not auto-adjudicate and detector output cannot break a tie. If only one reviewer
participates later, the result must be classified `SINGLE_REVIEWER`, not ground
truth.

## Artifacts and integrity

Artifacts are generated under the ignored local path
`artifacts/gf12_a2_human_identity_review/` and are not committed:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `human_identity_review_reviewer_a.xlsx` | 40,682 | `682b4e4d5d83017a28f7c021124b2dd394431cf91c072a9934fd73d7025bb052` |
| `human_identity_review_reviewer_b.xlsx` | 40,683 | `7cd5a3fc656fe0ae4aac8a25dd75d9bbe0f5a36468baf98812762dd0e5e739ef` |
| `human_identity_review_internal_mapping.csv` | 107,437 | `cced4751a0442fde9fa643b3da7f70cc56797786334c99c8c2a70a0a3a87d092` |
| `human_identity_review_adjudication.xlsx` | 15,261 | `97ccd6dd38d601f7c775681b8cb36f945ab5469b09b80440deb40a187c621c06` |
| `human_identity_review_manifest.json` | 4,502 | `ac81d4829901243c5f87e7c87390b4a015d622755a07b5c69724fb9c79e763c9` |

Openpyxl successfully reopens all workbooks. Headers are stable and unique,
review sheets have filters/freeze panes and bounded dropdowns, A/B pair content
reconciles exactly, and the internal mapping has an exact one-to-one ID
reconciliation. Formula-like source values are escaped as text. Formula cells,
prefilled labels, and reviewer-visible detector leakage each count zero.
Deterministic ZIP metadata and canonical ordering make repeated generation
byte-identical.

## Future evaluation only

After independent humans complete both files, a separate task will validate and
import the labels, report reviewer agreement and disagreements, adjudicate only
actual disagreements, and count usable SAME/DIFFERENT/INSUFFICIENT outcomes.
Only then may current GF4, R16 shadow, and strategies A-F be compared against
adjudicated labels, including false-positive and false-negative examples.
Population metrics require a sampling design that supports them; the diagnostic
panel must never be used for population estimates.

## Preserved boundaries

Production detector semantics, identity signatures, signed evidence, GF4, GF5,
normalization, retrieval, thresholds, statuses, review/export authority, schema,
migrations, dependencies, frontend, providers, and deployment are unchanged.
Provider calls are 0 and a normal G2-v2 scan was not required. The detector
remains unfrozen; R12 remains `DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`; R16 remains
not ready; R17 remains no-safe-generalization; GF-11 remains `IN PROGRESS` with
its waiver `ACTIVE`, `GF11-PERF-100K-COLD-FULL` `OPEN`, and the 300-second target
unmet. Deployment and integration remain deferred.
