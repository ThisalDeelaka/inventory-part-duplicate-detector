# GF-12C1-R8 final real G2-v2 demo acceptance and freeze

## Decision

`DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`

The current product path, authority selection, exact-scan exports, workbook
package, and protected-contradiction safety all pass. The broad deterministic
semantic sample does not pass the freeze gate: four sampled groups are likely
false physical-identity groups. R8 makes no detector or product-state change.

## Protected baseline

- Baseline commit: `4dd1da8ea532b6ea76cd3c63000e13890f89b220`.
- Branch: `llm-assisted-mvp`.
- Protected tag: `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Real CSV SHA-256 before and after:
  `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- The unrelated workbook was not opened or changed. Its audit fingerprint is
  1,508,088 bytes and
  `7b4fca921dee032bc6fec6de8c46f41b4092dc42f7bdd68c8128cf70b2ef5cec`.

## Selected authority

Persisted scan 29 was reused; no full scan was rerun. It is `COMPLETED` under
`group-first-orchestration-policy-v2`, `group_first_primary`, pipeline
`GROUP_FIRST_GF1_GF6`, visible projection `G2_V2`, with
`visible_product_ready=true`. The selected G2-v2 projection is completed and
contains 206 groups and 437 grouped members: 113 likely and 93 review, with 24
conflicts, 31 deferred units, 4,890 unassigned records, and zero provider
calls.

## Exact-scan export parity

The IdentityRead snapshot, System Group CSV, XLSX Duplicate Groups, and XLSX
Group Data have identical scan/projection authority, canonical group keys,
normalized statuses, stable record references, membership, 206 groups, and
437 member rows. XLSX Summary reports scan 29, `G2_V2`, 113 likely, 93 review,
24 conflicts, 31 deferred, and 4,890 unassigned. No G2-v1 fallback occurred.

## Workbook package acceptance

The disposable exact-scan workbook is:

`C:\Users\THISAL~1\AppData\Local\Temp\scan-29-final-real-g2v2-018l83s_.xlsx`

It is 163,510 bytes. `openpyxl` load and round-trip save pass. Group Data has
exactly 20 matching unique columns, one valid `SystemGroupData` table with
range `A1:T438`, one table-owned AutoFilter, no worksheet AutoFilter, and a
valid worksheet/table relationship. Merged presentation ranges are valid and
the round trip retains the same table and range. There are zero formula cells;
formula-like source values remain literal through the existing export guard.

## Full protected-contradiction sweep

All 206 groups were checked against current GF4 evidence, targeted evidence,
resolver constraints, and discriminator provenance:

| Safety condition | Groups violating it |
|---|---:|
| Current `CANNOT_LINK` endpoints co-located | 0 |
| Any identity-discriminator contradiction co-located | 0 |
| Mutually exclusive tyre-variant contradiction co-located | 0 |
| Object-class contradiction co-located | 0 |

The sweep covered 127 current cannot-link pairs and 15 discriminator-conflict
pairs. This safety result passes independently of the semantic freeze failure.

## Deterministic broad sample

The sample used snapshot canonical order and the union of: the first 10 likely
size-2 groups, first 10 review size-2 groups, first 20 groups of size at least
3, and 10 evenly spaced canonical-order positions. Overlap was removed. The
result is 49 unique groups. Only physical-identity fields and persisted
GF4/GF5/G2-v2 evidence/risk summaries were assessed. Accounting and governance
fields were not treated as physical identity authority.

| Index | Stable group suffix | Status/size | Label | Bounded rationale |
|---:|---|---|---|---|
| 0 | `963053923758` | Review/3 | C | Related FIFO-coded records, but identity evidence is naming-only. |
| 1 | `878f36a0048f` | Likely/3 | C | Shared process-like description with differing numbered identifiers. |
| 2 | `6b9a14d7127c` | Review/2 | A | Same turbine-blade object with abbreviation variation. |
| 3 | `7851f7e6e227` | Likely/2 | B | Matching manufacturer description; identifiers differ. |
| 4 | `78ecd8262ad1` | Review/2 | C | Very generic shared description. |
| 5 | `1e6202e92be2` | Likely/2 | A | Same Euro-pallet description and compatible context. |
| 6 | `2ce6621d08dc` | Review/2 | B | Same helmet description with near-identical identifiers. |
| 7 | `3fdce16c30aa` | Likely/2 | C | Copied description conflicts with numbered identifier suffixes. |
| 8 | `ad44a7343852` | Review/3 | C | Cost-coded naming gives weak physical identity evidence. |
| 9 | `d2c164352dae` | Likely/2 | C | One copied identifier-description; second identifier is dissimilar. |
| 10 | `ed5fd5a65be6` | Review/2 | A | Same turbine-disc object with abbreviation variation. |
| 11 | `22f757478113` | Review/2 | D | Rim and tyre are different physical object classes despite shared size. |
| 12 | `dd5d3e2501b2` | Likely/2 | A | Same fuel-nozzle object with abbreviation variation. |
| 13 | `8484b2266509` | Review/2 | B | Shared handling identifier; prefixes differ. |
| 14 | `4d7f51559cdc` | Review/2 | B | Same explicit Siemens model; description wording differs. |
| 15 | `2bc3951a105c` | Review/2 | B | Same component suffix with contextual prefixes. |
| 16 | `04f8d5d14492` | Review/2 | B | Near-identical part identifiers. |
| 17 | `7548f948d3d3` | Review/2 | C | Generic manufactured identifiers with distinct prefixes. |
| 18 | `bee12e99ba1f` | Likely/2 | B | Same inventory description with a minor identifier suffix. |
| 19 | `314c78886a27` | Likely/2 | A | Preserved F30 compressor-rotor corresponding pair. |
| 21 | `7f2e50788295` | Review/3 | C | Shared identifier but missing/nonstandard UOM weakens confidence. |
| 23 | `237359b9bce0` | Review/2 | D | Table product and nails are distinct objects under a copied description. |
| 25 | `509cf5ce166c` | Likely/2 | A | Same bicycle description and compatible context. |
| 27 | `94a9356c5155` | Likely/2 | A | Same explicit part identity with formatting variation. |
| 29 | `4ab1e27ee4c8` | Likely/2 | A | Preserved B38 engine-head corresponding pair. |
| 38 | `75cf4d082356` | Review/3 | B | Candle records are plausible but appropriately review-only. |
| 40 | `c5b3bee61892` | Likely/3 | C | Shared scheduling text is process-like and weak for physical identity. |
| 46 | `30acddf671d5` | Review/2 | A | Same combustion-chamber object with abbreviation variation. |
| 52 | `0e9b372563ab` | Likely/3 | C | Cost-oriented shared text is weak physical identity evidence. |
| 64 | `e6a7eb294d6a` | Review/3 | C | Numbered component suffixes remain unresolved. |
| 68 | `9beeb6b2ef37` | Likely/2 | B | Copied identifier-description supports a plausible review. |
| 80 | `e51e53f816b7` | Likely/3 | C | Generic inventory-part text spans distinct numbered identifiers. |
| 88 | `606e731544d2` | Review/3 | C | Transaction-role identifiers provide weak physical identity evidence. |
| 91 | `6380f84a6a69` | Review/2 | B | Same sales-part suffix with contextual prefix variation. |
| 99 | `b2eb0ca9fa6d` | Review/3 | C | Shared by-product description spans differing type roles. |
| 104 | `2fc76089884a` | Review/3 | D | Discount and condition records are semantically different constructs. |
| 114 | `b83785d2d496` | Likely/2 | B | Same part-3G identity with abbreviated identifier variation. |
| 116 | `79b87b28a2a4` | Review/3 | C | Transaction-role identifiers give insufficient physical proof. |
| 119 | `7d4743a304e9` | Review/3 | C | Explicit numbered component suffixes remain unresolved. |
| 120 | `c238a660fa25` | Likely/4 | C | Generic MRP text spans manufactured/purchased numbered records. |
| 137 | `72d431456dae` | Likely/2 | A | Same engine object with abbreviation variation. |
| 145 | `421e777d5f6d` | Review/3 | E | Date-coded generic records lack enough identity-bearing detail. |
| 150 | `8d2435dadfbd` | Likely/5 | C | Shared batch-balance text spans distinct numbered records. |
| 159 | `ef2cccee42b1` | Likely/2 | A | Same turbine-module object with abbreviation variation. |
| 162 | `398549408563` | Review/3 | D | Clutch disk, dust caps, and coil spring are distinct physical objects. |
| 169 | `6a6376a1c068` | Likely/4 | C | Shared day/planning text is weak physical identity evidence. |
| 171 | `c8727ef1117e` | Review/3 | C | Generic handling-unit descriptions require more identity evidence. |
| 182 | `7f9f484b5a4e` | Review/2 | C | Differing numbered CN101 identifiers remain unresolved. |
| 205 | `2adb53baebdc` | Likely/2 | C | Identifier 01/02 disagreement is obscured by a copied description. |

Audit-label totals:

```text
A_STRONG_DUPLICATE_HYPOTHESIS: 11
B_PLAUSIBLE_REVIEW: 11
C_WEAK_REVIEW_CANDIDATE: 22
D_LIKELY_FALSE_GROUP: 4
E_INSUFFICIENT_DATA: 1
```

The four D cases are independent freeze blockers. They identify rim/tyre,
table/nails, discount/condition, and clutch-disk/dust-caps/coil-spring
co-membership. They are audit findings only and were not written to product
state. The C cases are bounded weak candidates, not accuracy errors or a basis
for changing thresholds in R8.

## C1-C10 recheck

- C1 Contact Cleaner: `INSUFFICIENT_DATA`; capped/deferred and one unassigned.
- C2 Turbine Lubricating Oil: `INSUFFICIENT_DATA`; capped/deferred with the
  incompatible-UOM record protected separately.
- C3 Francis Turbine Lower Bearing: `INSUFFICIENT_DATA`; capped/deferred.
- C4 Pump X500: `INSUFFICIENT_DATA`; split across capped deferred units.
- C5 tyre variants: `SAFELY_SEPARATED`.
- C6 wheel versus tyre: `SAFELY_SEPARATED`.
- C7 carbon-stick versus pencil: `SAFELY_SEPARATED`.
- C8 F30: `SAFELY_SEPARATED`; six corresponding pairs remain intact.
- C9 B38: `SAFELY_SEPARATED`; five corresponding pairs remain intact.
- C10 MLR/circuit-board: `INSUFFICIENT_DATA`; the proven MLR contradiction is
  protected while the broader family remains unresolved.

## Reason presentation

The workbook Reason column is `TOO_GENERIC_FOR_DEMO`: it accurately describes
status but repeats status-level boilerplate instead of the group-specific
evidence visible in the audit. It is not misleading. Record
`NEXT_EVIDENCE_BACKED_GROUP_REASON_EXPORT` as a post-freeze presentation
improvement; R8 does not implement a new Reason system.

## Runtime and demo strategy

The current observed scan-29 wall runtime is 449.346238 seconds. No runtime
optimization was attempted. A pre-completed authoritative real scan plus an
optional smaller live scan remains operationally viable, but this particular
real result must not be frozen while the four likely false groups remain.

## Remaining boundaries

R8 changes no detector, resolver, threshold, cap, group semantics, product
state, review authority, export implementation, schema, migration, dependency,
frontend, provider, or deployment behavior. GF-11 remains `IN PROGRESS`, its
waiver remains `ACTIVE`, `GF11-PERF-100K-COLD-FULL` remains `OPEN`, and the
300-second target remains unmet. GF-12A2 remains
`HUMAN_REVIEW_DATASET_REQUIRED`; no accuracy, precision, recall, deployment,
GF-12 graduation, 100k graduation, or 1M-readiness claim is made.
