# GF-12 Group-First Production-Validation Contract

## Authority and scope

GF-12 validates duplicate identity sets/groups as the primary product object.
Pairs are supporting evidence and diagnostics only. This contract establishes
offline evaluation semantics and a synthetic/canonical baseline; it does not
grant final production graduation or human-reviewed production-quality
signoff.

The evaluation contract version is `gf12-group-quality-v1`. Canonical runs use:

- corpus `group-first-scale-corpus-v1`;
- corrected truth `group-first-scale-truth-v2`;
- seed 1101;
- policy-v2 `group_first_primary` production execution; and
- provider `none` on a unique disposable SQLite database.

Corpus and truth versions are explicit result fields and fingerprint inputs.
Unspecified truth versions never auto-upgrade or fall back. Historical
`group-first-scale-truth-v1` remains preserved but is rejected by this GF-12A1
evaluation boundary.

## Truth and production isolation

The only allowed flow is:

```text
production ScanRunner
  -> persisted GF-2/GF-3/GF-4/GF-5/GF-6 results
  -> authority-selected IdentityReadSnapshot
  -> offline GF-12 evaluator
  -> corrected truth-v2 comparison
```

Truth is validated before comparison. Production orchestration, retrieval,
scoring, fusion, GF-2, GF-3, GF-4, GF-5, and GF-6 neither import nor inspect the
evaluator or benchmark truth. Evaluation never writes a product result,
reproduces GF-5 grouping logic, or changes production fingerprints.

Truth validation fails closed on empty or singleton positive groups, unknown
members, duplicate group IDs, duplicate group membership, illegal positive
overlap, and positive/cannot-link contradiction. Evaluation does not repair,
filter, or reinterpret malformed truth.

## Product group and status scope

Accepted/review predictions are groups with status:

- `LIKELY_DUPLICATE_GROUP`; or
- `POSSIBLE_DUPLICATE_GROUP_REVIEW`.

Every such group must contain 2..N records. Accepted/review groups are disjoint
within one scan. Cannot-link remains absolute. `CONFLICT`, `DEFERRED`, and
`UNASSIGNED` remain separate cautious outcomes and never become accepted
duplicates for metric convenience.

## Primary group-level metrics

All member comparisons use exact source-row identity sets.

### GQ1 — Exact group precision

```text
predicted accepted/review groups exactly equal to one truth group
-----------------------------------------------------------------
all predicted accepted/review groups
```

### GQ2 — Exact group recall

```text
truth groups exactly equal to one predicted accepted/review group
---------------------------------------------------------------
all truth duplicate groups
```

### GQ3 — Exact group F1

The harmonic mean of GQ1 and GQ2. A zero denominator yields `N/A`, not a
fabricated zero. If both component ratios are defined but sum to zero, F1 is
zero.

### GQ4 — Member-weighted group coverage

For each truth group, find the largest predicted accepted/review group whose
complete membership is a subset of that truth group. Sum those recovered
memberships over all truth groups and divide by total truth-group memberships.
A merged prediction containing members outside the truth identity set receives
no coverage credit for that truth group. Only the largest clean subgroup counts,
so split fragments cannot double-count memberships. GQ4 supports exact recall;
it never replaces it.

### GQ5 — Split errors

Count truth groups intersecting more than one predicted accepted/review group.

### GQ6 — Merge errors

Count predicted accepted/review groups containing members belonging to more
than one distinct positive truth identity set.

### GQ7 — Missed truth groups

Count truth groups with no predicted accepted/review group recovering at least
two of their members. Conflict/deferred representation is reported separately
and remains missed for accepted-group quality.

### GQ8 — Spurious predicted groups

Count predicted accepted/review groups that are not a clean two-or-more-member
subset of one positive truth identity set. Exact and clean partial predictions
correspond to a truth identity; merged or unrelated groups are spurious.

No numeric GQ1–GQ8 acceptance threshold is authoritative:

```text
THRESHOLD NOT YET AUTHORIZED
```

## Supporting pair diagnostics

Pair precision, recall, and F1 are derived by enumerating co-membership pairs
inside truth and predicted groups. They are labeled:

```text
DIAGNOSTIC ONLY — NOT PRIMARY PRODUCT QUALITY
```

They cannot independently graduate GF-12 or override group-level outcomes.

## Hard safety metrics

The evaluator records:

- cannot-link accepted violations;
- duplicate accepted membership;
- singleton accepted groups;
- overlapping likely/review membership;
- cross-scan contamination; and
- source-record mutation when the harness exposes a comparable before/after
  fingerprint.

The authoritative target for every applicable violation counter is zero. Any
nonzero value fails GF-12A1 regardless of quality ratios. Source mutation is
reported `N/A` when the production harness does not expose both fingerprints;
the product's immutable catalog and no-writeback regressions remain separately
authoritative.

## Status-aware reporting

Truth groups are partitioned for reporting into:

- exactly recovered as likely;
- exactly recovered as review;
- represented only by conflict;
- represented only by deferred; or
- completely missed.

The result also reports predicted likely/review counts, conflict/deferred
outcome counts, and unassigned record count. Conflict and deferred outcomes are
not silently converted into false accepted duplicates or collapsed together.

## Group-size stratification

Truth groups use the fixed buckets:

- size 2;
- size 3;
- size 4–5;
- size 6–10; and
- size >10.

Each bucket records truth groups, exact matches, exact recall, split count, and
merge involvement. Empty buckets serialize ratio values as `N/A`.

## Scenario stratification

Only the generator's authoritative labels are used:

- S1: unique precision-shaft records;
- S2: positive duplicate-valued/canonical duplicate families;
- S3: generic-description records;
- S4: protected technical cannot-link cases;
- S5: cross-site positive duplicate families;
- S6: missing-value cases;
- S7: bridge/chained structures with positive subsets; and
- S8: repeated-family retrieval stress records.

For each present label the result records total records, positive truth groups,
exact recovery, conflict/deferred representation, complete misses, protected
cannot-link cases, and bridge cases. No label is inferred from product output.

## Deterministic result contract

The typed result contains evaluation version, corpus ID/version, truth version,
record count, seed, scan ID, production-result fingerprint, group counts,
GQ1–GQ8, pair diagnostics, safety counters, status/size/scenario breakdowns,
and evaluation fingerprint. Serialization is canonical JSON. The fingerprint
excludes timestamps and includes every semantic result field, corpus version,
and truth version. Raw descriptions, provider payloads, secrets, credentials,
and headers are absent.

## Evidence boundaries and decision use

Repository-owned synthetic/canonical truth validates evaluator semantics,
determinism, product behavior on known fixtures, and safety accounting. It is
not representative human-reviewed real inventory truth:

```text
canonical/synthetic benchmark quality != final human-reviewed production quality
```

GF-12A1 passes when truth integrity, isolation, deterministic serialization,
safety, required baseline execution, and regression gates pass. GQ metrics are
observability-only until a separately authorized threshold exists. A later
GF-12 unit must define or ingest an authorized human-reviewed validation sample
before any final production-quality signoff.
