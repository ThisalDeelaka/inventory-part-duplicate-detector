# GF-12 Canonical Truth Integrity Correction

> **GF-12A1 REMAINS NOT VERIFIED.**
>
> **THIS CORRECTION DOES NOT ITSELF ESTABLISH THE 50K QUALITY BASELINE.**

## Scope and version decision

This is a benchmark-only truth correction. It changes no production input
record, retrieval, scoring, evidence, resolution, G2 projection, schema,
migration, dependency, provider, or GF-11 waiver behavior.

The chosen strategy is **T1 — truth-only version correction**:

- `group-first-scale-corpus-v1` and its default historical truth behavior stay
  unchanged for existing GF-11 evidence and fingerprints.
- The historical truth behavior is explicitly named
  `group-first-scale-truth-v1`.
- Corrected offline evaluation truth is explicitly named
  `group-first-scale-truth-v2`.
- `generate_corrected_scale_corpus(...)` is the stable GF-12 resume seam; it
  retains corpus v1 production records and explicitly selects truth v2.

## Observed 50k defect and root cause

The historical 50k/seed-1101 result reproducibly contains:

```text
truth group: cross-site-3755308
members:     (31249,)
typed error: TRUTH_GROUP_SINGLETON
```

The primary classification is:

```text
A. PARTIAL_GROUP_AFTER_CORPUS_BOUNDARY
```

S5 intends a deterministic cross-site family of 2–4 members. Family 3755308
would select four members, but only one slot remained in the 6,250-record S5
partition. V1 generated the one in-bound production record and unconditionally
emitted a positive group for it; the remaining three intended members were
never generated because the requested scenario partition was full. No filter or
reference transformation removed them.

Truth v2 retains source row 31,249 and its authoritative S5 scenario label, but
does not claim an incomplete boundary family as positive duplicate identity.
Its boundary rule is: retain requested production records and scenario labels;
emit positive truth only when the complete generated scenario has at least two
members. The malformed group is absent rather than filtered by the evaluator.

The defect affects the required 50k scale only. The 500, 5k, 20k, and 100k
canonical samples contain no singleton positive truth group.

## Additional validator finding at 100k

The generation-boundary validator also found two historical duplicate truth
IDs at 100k:

```text
cross-site-4761961: (52298, 52299, 52300) and (57782, 57783, 57784)
dup-4825057:        (16917, 16918, 16919) and (22608, 22609, 22610)
```

This is classified as:

```text
E. TRUTH_ASSEMBLY_DEFECT
```

The random family number was used as an assumed-unique truth ID even though a
repeat is possible. Truth v2 preserves group ordering and membership and adds a
deterministic `@source-{first_source_row}` suffix only to colliding IDs. V1 IDs
and fingerprints remain unchanged.

## Generation-boundary integrity contract

Truth v2 is validated during generation and fails closed with typed
`BenchmarkTruthIntegrityError` codes for empty or singleton positive groups,
unknown references, duplicate members, illegal positive membership overlap,
positive/cannot-link contradictions, duplicate group IDs, or invalid scenario
membership. The evaluator's independent fail-closed checks are not weakened.

## Canonical integrity results

All counts below use corpus v1 records, truth v2, and seed 1101.

| Records | Positive groups | Size distribution | Empty | Singleton | Unknown refs | Duplicate IDs | Duplicate membership | Cannot-link contradiction |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | 60 | 2:34, 3:8, 4:15, 5:3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 5,000 | 591 | 2:322, 3:104, 4:115, 5:50 | 0 | 0 | 0 | 0 | 0 | 0 |
| 20,000 | 2,421 | 2:1,347, 3:481, 4:436, 5:157 | 0 | 0 | 0 | 0 | 0 | 0 |
| 50,000 | 5,960 | 2:3,224, 3:1,171, 4:1,121, 5:444 | 0 | 0 | 0 | 0 | 0 | 0 |
| 100,000 | 11,935 | 2:6,501, 3:2,305, 4:2,228, 5:901 | 0 | 0 | 0 | 0 | 0 | 0 |

Scenario counts are unchanged. At 500 they remain S1–S4:63 and S5–S8:62;
at 5k, 20k, 50k, and 100k every S1–S8 partition remains respectively 625,
2,500, 6,250, and 12,500 records.

## Cross-site coverage

| Records | V1 groups/members | V2 groups/members | V2 size distribution |
| ---: | ---: | ---: | --- |
| 500 | 20 / 62 | 20 / 62 | 2:7, 3:4, 4:9 |
| 5,000 | 204 / 625 | 204 / 625 | 2:61, 3:69, 4:74 |
| 20,000 | 850 / 2,500 | 850 / 2,500 | 2:308, 3:284, 4:258 |
| 50,000 | 2,084 / 6,250 | 2,083 / 6,249 | 2:693, 3:697, 4:693 |
| 100,000 | 4,166 / 12,500 | 4,166 / 12,500 | 2:1,370, 3:1,424, 4:1,372 |

The sole 50k reduction is the invalid one-record annotation. No valid
cross-site group or member is removed, and no replacement example is invented.

## Production-record compatibility

V1 and V2 production records are byte/field equivalent at every required
scale. Their record-only SHA-256 fingerprints are:

| Records | Shared record fingerprint |
| ---: | --- |
| 500 | `895ba978b9cb26527a05e7627831b4e6ff846b8be03c8cdc1ab27d5871af8868` |
| 5,000 | `7da578fff0214b52624c8125b85266b820a8db7175b89f66173119d950cd20ba` |
| 20,000 | `b379830d6651fd77c4df9d41fb19e6f3f8655000b98e05e524f5a8f47f44932e` |
| 50,000 | `16877c624acad8c672924209dd679ccba201be21ea1560c53fbe68a5700b5208` |
| 100,000 | `32d266cedaf113828552d427603fd18ea957fb4ecc2595c1e0689a2a600bb3c8` |

Historical v1 generator fingerprints remain exactly unchanged, including 50k
`42be1d818085d2562a6c20edf65355c34beb4d3e81e88f869c78920cdcdf1263`
and 100k
`dd14d58b8b094d7423f175a7d1766f0caef3101a484f5577acc20c4ebc4275c7`.
Truth-v2 fingerprints deliberately include the corrected truth-version identity
even where member semantics equal v1. At 50k the v2 truth fingerprint is
`a64b04bbb778202772c5f140727092a5906d49eefcd9a70df269afec9d29e67b`;
at 100k it is
`cc6ef5b38114e7f7bcbca5272a9d19b7f5ef64314dfd3f8b2eb7ff5e4a67e63d`.

## GF-12A1 resume boundary

GF-12A1 must explicitly select `group-first-scale-truth-v2`, preferably through
`generate_corrected_scale_corpus(...)`, before rerunning offline baselines. Its
preserved in-progress evaluator currently selects the historical default and
must be updated only by the separately authorized GF-12A1-RESUME task.

GF-11 remains IN PROGRESS with its performance waiver ACTIVE and
`GF11-PERF-100K-COLD-FULL` OPEN. GF-12 remains START AUTHORIZED, and GF-12A1
remains NOT VERIFIED.
