# R18G-A Group-Level Human Evidence Preparation

Classification: `R18G_AWAITING_GROUP_HUMAN_REVIEW`

R18G-A prepared a deterministic, blinded whole-group evidence package for the
same highly experienced Senior Functional Consultant. It did not collect or
infer labels, evaluate product quality, change detector behavior, or call a
provider.

## Why group evidence is required

The product result is a set of 2..N records, while the earlier R18 evidence was
pair-level. R18D found 115 current Review edges (99 native and 16 R18C-demoted),
with most in deferred or conflict context. Every tested Review-suppression rule
harmed Senior-SAME controls. GF5's implemented partition objective also
penalizes Review while the architecture describes maximizing it after Strong,
so pair evidence cannot establish a safe group-output correction.

The Senior therefore answers one fresh whole-set question: whether all records
in the proposed set represent one underlying physical/business inventory
identity.

## Review protocol and labels

Reference type: `SINGLE_SENIOR_DOMAIN_EXPERT_GROUP_EVIDENCE`.

The allowed labels are `SAME_ONE_IDENTITY`, `NOT_ONE_IDENTITY`, and
`INSUFFICIENT_INFORMATION`. Confidence is `HIGH`, `MEDIUM`, or `LOW`. The
reviewer also records one governed reason code, a qualitative comment, and
whether that comment is based on `SOURCE_VISIBLE`, `DOMAIN_EXTERNAL`, `MIXED`,
or `UNCLEAR` evidence. This preserves the distinction between source-observable
quality problems and knowledge absent from detector inputs.

For `NOT_ONE_IDENTITY`, the reviewer may assign each member to `P1` through
`P20`, or `UNRESOLVED`. A partition is not forced when the visible evidence is
insufficient. For `SAME_ONE_IDENTITY`, all members may be assigned to `P1`.

The claim is explicitly limited: this is not dual-reviewed, adjudicated, a gold
standard, or production-accuracy truth.

## Current-data construction

The generator uses the persisted Scan-31 canonical catalog and candidate/evidence
population. It re-evaluated all 1,208 persisted positive edges under the current
post-R18C deterministic evaluator and reused 19,187 persisted negative edges;
the R11 and R18C changes are monotonic safety changes and cannot promote those
negative edges. The resulting current evidence fingerprint is
`412fad0ff45c3e76bce1713e1901f9d7cbaeffbb1561bf76ced9e59c7d452df5`.

To avoid repeating global discovery or an irrelevant exhaustive search over the
degraded overlapping graph, each of the 203 persisted disjoint accepted source
groups was re-resolved as a bounded current GF5 work unit. Each source group has
at most five members. Current GF5 accepted 200 of them. Deferred and conflict
contexts remain real persisted topology, with candidate cliques checked against
current edges. Provider calls were zero.

Partition-policy challengers were generated only by deterministic exact set-
partition comparison for real work units of at most eight members. Current GF5
ordering and ADR-described ordering were compared without changing either.
Shadow alternatives containing a protected cannot-link were rejected.

## Sampling and governance

Seed `1807` selected 64 hypotheses from an eligible pool of 255:

| Split | Groups |
|---|---:|
| DEVELOPMENT | 48 |
| SEALED HOLDOUT | 16 |

The 64 groups contain 170 member rows. Their size distribution is 45 groups of
size 2, five of size 3, seven of size 4, six of size 5, and one of size 7.
Source kinds are 18 accepted-likely, 26 accepted-review, eight deferred-family,
eight conflict-context, three ADR partition challengers, and one generic
Bicycle family.

DEVELOPMENT contains the technically available seven-record Bicycle family and
three cases where the current and ADR-aligned partition objectives differ. The
reviewer is not told those identities or any source kind. Development and
holdout IDs are disjoint. After review, engineering receives DEVELOPMENT first;
the completed SEALED HOLDOUT remains outside the repository and hidden until a
relevant rule is frozen and evaluation is separately authorized.

## Blinding and integrity

Reviewer-visible workbooks contain only Instructions, Group Review, Members,
and Partition sheets. Visible member fields are part number, description in
use, description, master description, type designation, dimension/quality,
UOM, part type, and site where those fields exist in the persisted catalog.

Validation confirmed:

- 64 unique blinded group IDs and disjoint splits;
- every group has at least two members and all mapping members reconcile;
- no detector disposition, edge class, score, source kind, current/shadow flag,
  pair label/comment, prior reviewer content, or LLM output is visible;
- zero prefilled labels, confidence values, reasons, comments, partitions, or
  formulas in human-input cells;
- exact dropdown vocabularies and exact member/partition-sheet reconciliation;
- exact internal-mapping reconciliation;
- zero accepted-group cannot-links, duplicate accepted membership, or unsafe
  shadow cannot-link hypotheses.

## Artifacts

The files are under ignored `artifacts/gf12_a2_human_identity_review/` and do
not overwrite the earlier R18 pair-review artifacts.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `r18g_group_review_development.xlsx` | 21,373 | `814e748c45012558bc9a8f656ae39776693a25ff1b6aab430c58e5ab21f005d2` |
| `r18g_group_review_sealed_holdout.xlsx` | 12,390 | `4f0b31b7639b12ab3b28c8ca8a68c89c50090d2158e956b37417655a0128fb33` |
| `r18g_group_review_internal_mapping.csv` | 35,768 | `0816aca7d198b00bbe21ffbd3acb2cbb4fd5bc0643330b1954d78a3debc32a53` |
| `r18g_group_review_manifest.json` | 3,873 | `4ffd9eb734431e83604a4f9634e33eabb8f42a8e675d7112f8ad90bd6edc8cb8` |

## Verification and next action

Five focused R18G tests cover stable fingerprints and hashes, deterministic
development/holdout assignment, group-size failure, reconciliation, blinding,
empty human fields, dropdowns, partition reconciliation, current/shadow
mapping, cannot-link-safe challenger generation, and mandatory Bicycle and
partition-sensitive development inclusion. Existing resolver, R18C, R18D, and
Bicycle controls are also run before closeout.

Runtime detector, R18C, Review status, GF5 objective, group confidence, LLM,
exports, and frontend are unchanged. The architect must now follow
`docs/R18G_GROUP_HUMAN_REVIEW_INSTRUCTIONS.md`. No group-quality evaluation is
authorized until human evidence is returned under that protocol.
