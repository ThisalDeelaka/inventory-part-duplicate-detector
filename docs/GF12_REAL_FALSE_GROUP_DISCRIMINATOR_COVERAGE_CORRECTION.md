# GF-12C1-R9 real false-group discriminator coverage correction

## Decision

`R9_QUALITY_CORRECTION_PARTIAL_NEW_BLOCKER`

R9 corrects all four false identity groups that failed the R8 freeze. A fresh
deterministic 45-group audit then found one different, repeatable semantic gap:
left-side and right-side shock abbreviations are not extracted as mutually
exclusive directional variants. That family is intentionally not added to R9.

## Protected inputs and baseline

- Starting commit: `f197342e49b07f967446e0604749b1e034cca456`.
- Branch: `llm-assisted-mvp`.
- Protected tag: `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Real CSV: 3,265,800 bytes; SHA-256
  `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- Unrelated XLSX: 1,508,088 bytes; SHA-256
  `7b4fca921dee032bc6fec6de8c46f41b4092dc42f7bdd68c8128cf70b2ef5cec`;
  its contents were not inspected and it was not changed or staged.

## Frozen R8 failures and root causes

Persisted scan 29 reproduced all four groups before production edits.

| Case | Suffix | Source rows and bounded evidence | Pair evidence | Root causes |
|---|---|---|---|---|
| D1 | `22f757478113` | 2869 `CS-RIM17` / CS Rim 17 / PCS; 3554 `CS-TIRE 17` / CS Tire 17 / PCS | 64.16, `REVIEW_SUPPORT`; rim unknown, tyre known | F1 alias missing and F3 relation unreachable because rim was not canonicalized as wheel |
| D2 | `237359b9bce0` | 5136 `NS-TABLE-PRODUCT`; 5134 `NS-NAILS`; both copied description `NSUDLK TEST`, PCS | 88.81, `REVIEW_SUPPORT`; no class conflict | F2 vocabulary, F5 copied-description coverage, F6 part-number class extraction, F7 generic/copy overweight |
| D3 | `2fc76089884a` | 3848 `CONDITION01`; 3802 `DISCOUNT-X` with copied `CONDITION-X`; 3801 `CONDITION-X` | 84.01/87.81 review and 96.09 strong; no construct conflict | F4 commercial construct class, F6 extraction, F7 copied description |
| D4 | `398549408563` | 4129 `CLUTCHDISK` with copied `DUSTCAPS`; 4127 `DUSTCAPS`; 4634 `COILSPRING` with copied `DUSTCAPS` | 90.45 strong, 89.17/88.64 review; no component conflict | F2 vocabulary, F5 copied-description coverage, F6/F7, and F8 multiple component classes |

The defect is coverage at the existing GF4 discriminator seam, not a GF4
promotion or GF5 resolver defect. Two bounded clusters share that contract:

1. physical class alias/vocabulary/incompatibility coverage (D1, D2, D4);
2. explicit part-number commercial-construct coverage (D3).

## Implemented correction

`identity-discriminator-v2` adds reusable, normalized record-local semantics:

- `rim` canonicalizes to the existing `wheel` class;
- bounded physical classes cover table, nail, clutch disk/disc, dust cap, and
  coil spring, with explicit pairwise incompatibilities;
- condition and discount are distinct commercial construct classes only when
  expressed in part-number fields; descriptions alone cannot invent them;
- two explicit incompatible single-class part numbers produce
  `EXPLICIT_TWO_SIDED_PART_NUMBER_CLASS`, so a copied description cannot erase
  the contradiction;
- physical conflicts remain `IDENTITY_OBJECT_CLASS`; commercial conflicts use
  `IDENTITY_CONSTRUCT_CLASS`.

Unknown-versus-known remains unknown. Same-class pairs remain non-conflicting.
Generic text, shared dimensions, UOM differences, and description disagreement
alone do not create cannot-links. Production has no scan ID, group suffix,
source row, filename, exact real part number, or membership exception. GF4 uses
the existing signed evidence payload and `canonical-identity-evaluator-v3`; no
schema or migration was required.

## Deterministic fixtures and controls

Focused R9/R7/GF4/GF5 tests pass 119 cases. The negative suite covers alias
versus incompatible class, different mechanical components, copied
descriptions, shared generic text, three-component mixtures, commercial
constructs, protected A-B/B-C/A-C bridges, known/unknown, generic nouns, and
dimensions. Required N1-N7 are blocked where explicit contradictions exist;
N8-N10 do not invent conflicts.

All P1-P12 controls remain non-conflicting, including spelling/punctuation,
different part numbers for the same item, cross-site eligibility, missing or
ambiguous UOM, Contact Cleaner, Francis Turbine Lower Bearing, Fan Blade, B38,
F30, same-class qualifiers, and accounting/governance differences. R7 C5 tyre
variants, C6 wheel/tyre, C7 carbon-stick/pencil, C8 F30, and C9 B38 remain safe.
The multi-member bridge fixture cannot merge across the protected endpoint.

## C-watchlist and changed groups

Of the 22 R8 weak-review watchlist groups, 19 retain exact membership. Three
changed because ordinary deterministic discovery produced a different bounded
graph, not because the R9 discriminator fired. Zero watchlist groups received
a new R9 conflict. No broad weak-group suppression or overcorrection occurred.

Across scan 29 and scan 30, 188 group memberships are common and all retain
their prior status. Scan 29 has 18 old-only memberships and scan 30 has 8
new-only memberships. The accepted-group/member aggregate changes from
206/437 to 196/414. D1-D4 and groups touched by explicit new contradictions
were inspected; unrelated graph variation is not attributed to R9 semantics.

## Fresh authoritative real run

Fresh scan 30 used the ordinary browser-equivalent current-product request,
threshold 75, same-site mode, `CONTRACT` and `UNIT_MEAS`, policy v2,
`group_first_primary`, and visible `G2_V2`. It completed with
`visible_product_ready=true`, no provider, and no secret/config-file access.
Wall runtime was 696.028868 seconds.

| Stage/result | Count or runtime |
|---|---:|
| GF1 canonical catalog | 5,327 records; 7.478438 s |
| GF2 proposals | 20,395; discovery stage 150.940303 s |
| GF3 neighborhoods | 1,278 |
| GF4 signed edges | 20,395; 45.204147 s |
| GF4 strong / review / cannot / non-groupable | 263 / 945 / 139 / 19,048 |
| GF5 work units / partitions | 235 / 212,267; 455.058211 s |
| GF5 groups likely / review | 113 / 83 |
| GF5 conflicts / deferred / unassigned | 30 / 31 / 4,913 |
| GF5 targeted requested/completed | 26 / 26 |
| GF6 projection | 196 groups, 414 members; 19.978186 s |

Resolution fingerprint:
`b937fce6dfc0d598f5aa3b45379d7d6326953ec672a4365a2237c996c827d5ae`.
G2-v2 manifest fingerprint:
`a76e254ee38a57c97cb2249f1f54fb5ff8fa28ef5a7fb2dc38dc8df16098ea77`.

The R9 mechanisms create 21 protected real edges: six rim/tyre, three
table/nail, nine condition/discount, and three clutch-disk/dust-cap/coil-spring
edges. D1, D2, and D4 no longer survive; D3's mixed three-member identity no
longer survives, while its same-class condition pair remains legitimately
reviewable. All four are `SAFELY_SEPARATED` from their proven incompatible
members.

The broad sweep considered 148 current GF4, targeted, and constraint
cannot-link pairs. Accepted groups containing their endpoints: zero. Accepted
groups containing an identity-discriminator contradiction: zero. G2-v2
internal cannot-links: zero, as required by projection validation.

## Repeated semantic audit

The deterministic stratified sample contains 45 unique groups: 10 likely
size-2, 10 review size-2, all 18 size-3-or-more groups, and 10 evenly spaced
groups, with overlap removed.

```text
A_STRONG_DUPLICATE_HYPOTHESIS: 6
B_PLAUSIBLE_REVIEW: 11
C_WEAK_REVIEW_CANDIDATE: 26
D_LIKELY_FALSE_GROUP: 1
E_INSUFFICIENT_DATA: 1
```

The remaining D group has suffix `25353d2b0aac`: source row 4132 is
`FRONT L/S SHOCK` / Front L/S Shock and row 4635 is `FRONT R/S SHOCK` with a
copied Front L/S Shock description. The persisted edge is 99.17
`STRONG_SUPPORT`. Current technical extraction sees only shared `front` and
does not recognize L/S versus R/S as mutually exclusive directional variants.
This is a new variant-extraction family, not incomplete vocabulary from D1-D4.

## Export and performance evidence

Scan 30 IdentityRead, System Group CSV, and XLSX have exact parity: `G2_V2`,
196 group keys, 414 stable member references, and matching statuses. The
155,335-byte in-memory workbook has a valid OOXML archive, one table-owned
filter, no worksheet filter, 1,176 non-overlapping merged ranges, and zero
package corruption.

A bounded 1,800-evaluation microbenchmark measured 1.387536 seconds for raw
scoring/classification and 2.999736 seconds through the full evaluator, a
1.612200-second delta (about 895.667 microseconds per edge, including evaluator
serialization/fingerprinting). The authoritative GF4 stage was 45.204147
seconds and the full real wall runtime was 696.028868 seconds. R9 adds no
all-pairs scan, ontology traversal, service, or provider call.

## Boundaries and next blocker

R9 changes no global threshold, GF5 cap, group-size limit, status, candidate
retrieval, review/export authority, schema, migration, dependency, frontend,
provider, or deployment behavior. It does not claim human-reviewed accuracy.
GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`. GF-11 remains `IN PROGRESS`,
its waiver remains `ACTIVE`, `GF11-PERF-100K-COLD-FULL` remains `OPEN`, and the
300-second target remains not met. Deployment and integration remain deferred.

The only next recommendation is:

`ONE DISTINCT QUALITY FAMILY REMAINS -> correct only that proven family in the next bounded task`
