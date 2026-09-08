# GF-12C1-R10 directional side-variant identity correction

## Decision

```text
R10 bounded directional correction: VERIFIED
overall demo freeze: NOT READY
```

The bounded left/right correction succeeds. The required repeated semantic
audit finds one different false-group family, which blocks the demo freeze but
does not invalidate or prevent committing the verified directional correction.
R10 does not add another object class or copied-description rule.

## Protected baseline and inputs

- Starting HEAD: `576a710f82b0700512a1287d23d11d30242daf7d`.
- Branch: `llm-assisted-mvp`.
- Protected tag: `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Real CSV: 3,265,800 bytes, SHA-256
  `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- Unrelated XLSX: 1,508,088 bytes, SHA-256
  `7b4fca921dee032bc6fec6de8c46f41b4092dc42f7bdd68c8128cf70b2ef5cec`.
  It was not opened, modified, or staged.

## R9 blocker and pre-fix evidence

Scan 30 group suffix `25353d2b0aac` was a two-member
`LIKELY_DUPLICATE_GROUP`:

- row 4132, stable ref
  `6b814ac3fa22ef5f48982342adba9f7e4558ebdd17228b4e94a1bd7f53a2b685`,
  `FRONT L/S SHOCK`, description `Front L/S Shock`, PCS;
- row 4635, stable ref
  `cf424b2fadc825c5736b3a6514a006a0fd1b12de999c12476e88c3ad15a8730c`,
  `FRONT R/S SHOCK`, copied description `Front L/S Shock`, PCS.

The persisted edge was 99.17 `STRONG_SUPPORT`, with no protected conflict.
Normalization produced `front l s shock` and `front r s shock`; the existing
variant extractor recorded only shared `front`. Root causes are
`R10-F1_SIDE_VARIANT_NOT_EXTRACTED`,
`R10-F2_SIDE_ABBREVIATION_NOT_NORMALIZED`, and
`R10-F3_COPIED_DESCRIPTION_OVERRODE_PART_NUMBER_SIDE_SIGNAL`. This was not an
existing contradiction lost by GF4, so R10-F4 does not apply.

## Bounded side contract

`identity-discriminator-v3` adds `UNKNOWN`, `LEFT`, and `RIGHT` as record-local
directional qualifiers. Supported high-confidence forms are `LEFT`, `RIGHT`,
`LH`, `RH`, `L/H`, `R/H`, `L/S`, `R/S`, `LEFT SIDE`, `RIGHT SIDE`, `LEFT HAND`,
and `RIGHT HAND`.

Bare `LEFT`/`RIGHT` is trusted only in a part-number field. Description evidence
must use a compound side/hand form or bounded abbreviation. Bare `L` and `R`,
ordinary model-code characters, and substrings such as `LEFTOVER` do not match.
Front/rear is unchanged.

A protected conflict requires both records to resolve to opposite explicit
sides and to share a nonempty normalized side-free base from a field supporting
that resolved side. Thus `PUMP LEFT` versus `VALVE RIGHT` is not rejected merely
for handedness. Side-versus-unknown remains non-conflicting.

Part-number evidence is authoritative over a conflicting copied description.
For the real right-side record, the part number resolves `RIGHT` even though its
description says `LEFT`; the resulting shared base is `front shock`.

GF4 provenance uses `IDENTITY_SIDE_VARIANT` and
`EXPLICIT_TWO_SIDED_DIRECTIONAL_VARIANT`. Evidence includes canonical side,
source-specific matched normalized forms, side-free bases, and trust provenance.
The evaluator is `canonical-identity-evaluator-v4`. Existing signed evidence and
`CANNOT_LINK` semantics are reused; no schema is needed.

## Fixtures and regression controls

N1-N7 pass for LEFT/RIGHT, LH/RH, L/H/R/H, L/S/R/S, SIDE/HAND compounds,
copied-description precedence, and an A-B/B-C bridge with a protected A-C side
conflict. N8-N10 confirm no conflict for model-code letters/substrings or
side-versus-unknown.

P1-P12 preserve same-side variations, different part numbers, cross-site
same-side identity, missing side, Contact Cleaner, Francis Turbine Lower
Bearing, Fan Blade, F30, B38, model codes, and non-side prose. All R7 tyre,
wheel/tyre, and carbon-stick/pencil controls remain protected. All R9 rim/tyre,
table/nail, condition/discount, and mechanical-component controls remain
protected. The focused combined suite passes 148 tests.

## Fresh real scan 31

The ordinary browser-equivalent current-product request completed with
policy-v2, `group_first_primary`, visible `G2_V2`,
`visible_product_ready=true`, and zero provider calls. Wrapper wall runtime was
319.583995 seconds; orchestration runtime was approximately 316.601 seconds.

| Stage/result | Count or runtime |
|---|---:|
| GF1 catalog | 5,327 records; 1.356934 s |
| GF2 proposals | 20,395; discovery stage 58.171114 s |
| GF3 neighborhoods | 1,284 |
| GF4 edges | 20,395; signed-evidence stage 27.850366 s |
| GF4 strong / review / cannot / non-groupable | 269 / 939 / 139 / 19,048 |
| GF5 work units / partitions | 242 / 212,163; stage 219.099028 s |
| GF5 targeted requested/completed | 26 / 26 |
| GF6 groups | 203; projection stage 9.971441 s |
| likely / review | 114 / 89 |
| conflicts / deferred / unassigned | 30 / 30 / 4,898 |

Resolution fingerprint:
`be426daa0c5159a6ce09f45b74cf7026468b645c04d2c1872cb2a676780e79d7`.
G2-v2 manifest fingerprint:
`58723939bd677d510735560328c54ff7546e55107a0680ed8ee2547968608345`.

The target records are no longer in an accepted group. Both are members of one
`PROTECTED_CANNOT_LINK` conflict. Exactly one real GF4 edge carries
`IDENTITY_SIDE_VARIANT` provenance.

The full sweep covers 148 current GF4, targeted, and constraint cannot-link
pairs. Accepted co-memberships are zero. Direct evaluation of every accepted
group pair finds zero discriminator contradictions and zero side contradictions.
G2-v2 internal cannot-link rows are zero.

## Watchlist and export audit

Of the 22 R8 weak-review watchlist memberships, 21 are exact on scan 31. One
changed through ordinary discovery variation. None has an explicit side
contradiction and none was newly conflicted by R10.

IdentityRead, System Group CSV, and XLSX match exactly for scan 31: `G2_V2`,
203 group keys and 429 stable member references with identical statuses and
memberships. The 160,498-byte workbook has a valid OOXML archive, one
table-owned filter, no worksheet filter, 1,218 non-overlapping merged ranges,
and no corrupt package member.

## Repeated semantic audit

The exact stratified method produced 47 unique groups: first 10 likely size-2,
first 10 review size-2, up to 20 size-3-or-more, and 10 evenly spaced canonical
groups, deduplicated.

```text
A_STRONG_DUPLICATE_HYPOTHESIS: 4
B_PLAUSIBLE_REVIEW: 13
C_WEAK_REVIEW_CANDIDATE: 28
D_LIKELY_FALSE_GROUP: 1
E_INSUFFICIENT_DATA: 1
```

The remaining D group has suffix `d7c16998f587`: row 1512 `LG - BUFFER01` and
row 1511 `LG - MIRROR01` share the copied description `Seria/condition part`
and remain a likely group. Buffer and mirror are distinct explicit component
identities. This is a new object-class/copied-description coverage family, not
a directional-side defect. R10 intentionally leaves it unchanged.

## Performance and boundaries

A 20,000-evaluation microbenchmark measured 75.333 microseconds per side edge
and 64.700 microseconds per comparable neutral edge: approximately 10.633
microseconds incremental side-rule cost. GF4 took 27.850366 seconds and the full
real wall runtime was 319.583995 seconds. No all-pairs pass, external NLP, LLM,
or provider request was introduced.

R10 changes no threshold, retrieval, GF5 cap, group-size limit, status,
review/export authority, schema, migration, dependency, frontend, deployment,
or integration behavior. It does not claim human-validated accuracy. The D=1
result blocks only the broader demo freeze; R10A authorizes the verified bounded
directional implementation commit.

GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`. GF-11 remains `IN PROGRESS`,
its waiver remains `ACTIVE`, `GF11-PERF-100K-COLD-FULL` remains `OPEN`, and the
300-second target remains not met. Deployment/integration remains deferred.

The distinct next blocker remains `LG - BUFFER01` versus `LG - MIRROR01`.
