# GF-12C1-R6 interactive G2-v2 XLSX and real-output audit

## Decision and scope

The ordinary current-product **New Scan** flow now selects the existing
group-first-primary orchestration explicitly. Same-site/cross-site remains a
business-scope choice and is not used as an orchestration selector. Explicit
legacy compatibility and historical scan interpretation remain unchanged.
This correction does not change discovery, evidence, resolution, projection,
threshold, UOM, cannot-link, review, or provider semantics.

The real-output audit is an offline engineering canary, not ground-truth or
human-quality certification. Its result is
`Q2_DEMO_QUALITY_NEEDS_BOUNDED_CORRECTION`. No audit finding was written into
product state and no detector correction is part of R6.

## Scan 26 forensic cause

Before R6, the browser sent `file`, `scan_name`, `threshold`,
`selected_fields`, `column_mapping`, `sensitive_mode`, and the same-site scan
mode. It sent no product-orchestration authority. The upload route forwarded
the application `Settings`; `ScanRunner` selected
`identity_orchestration_mode`; and the configured default was
`legacy_primary`. Scan 26 therefore persisted policy v2 with pipeline
`LEGACY_PAIR_G1`, visible projection `G2_V1`, and compatibility projection
required. The cause is exactly:

- `A_FRONTEND_DID_NOT_REQUEST_GROUP_FIRST`
- `B_BACKEND_DEFAULTED_TO_LEGACY_PRIMARY`
- `C_CONFIG_DEFAULT_LEGACY_PRIMARY_REACHED_NORMAL_PRODUCT_FLOW`

The result page and export used scan 26 and its persisted authority correctly;
they did not select a wrong scan or projection. Historical scan 26 remains
G2-v1 and was not reinterpreted.

## Current-product correction and compatibility

The public multipart contract now accepts the allowlisted typed values
`current_product` and `legacy_compatibility`, separate from internal pipeline
names. The browser sends `product_authority=current_product`. The upload route
maps it to the existing `GROUP_FIRST_PRIMARY` enum and passes that per-scan
selection through the scan service and runner. Arbitrary values fail request
validation with HTTP 422. Non-product callers that omit a runner-level override
retain the prior configuration/default behavior.

Focused tests prove that the route default and browser request select the
current product even when configuration is deliberately legacy, while an
explicit `legacy_compatibility` request still persists legacy pair/G1/G2-v1
authority. Existing persisted-authority tests prove historical G2-v1 reads and
the group-first no-G2-v1-fallback boundary.

## Microsoft Excel repair

Package inspection of the pre-correction scan-25 workbook proved that
`xl/worksheets/sheet3.xml` declared an AutoFilter over `A1:T712` while
`xl/tables/table1.xml` declared a Table over the same range with its own
AutoFilter. The relationship from the worksheet to `table1.xml` was otherwise
valid. This exact overlapping worksheet/table filter conflict matches Excel's
reported removal of the table and AutoFilter.

The corrected `Group Data` sheet lets its Excel Table own the single
AutoFilter. The table, frozen header, flat member rows, values, and CSV parity
remain. Package-level regression tests verify ZIP readability, `table1.xml`,
the exact populated table range, one table AutoFilter, no worksheet AutoFilter,
the worksheet/table relationship, stable legal `SystemGroupData` name, 20
unique sequential table columns matching 20 headers, valid non-overlapping
merged ranges, openpyxl reopen, and round-trip table/filter retention. Existing
tests retain formula-injection protection.

## Fresh browser-equivalent real run

The immutable 3,265,800-byte `List_20260709_093045.csv` had SHA-256
`8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`
before and after the run. The request matched the browser: threshold 75,
selected fields `CONTRACT` and `UNIT_MEAS`, empty explicit column mapping,
sensitive mode enabled, same-site business scope, and
`product_authority=current_product`. Configuration was deliberately legacy to
prove request-level precedence. Providers were disabled and provider calls
were zero.

Scan 27 completed in 315.779825 seconds with 5,327 canonical records. It
persisted policy `group-first-orchestration-policy-v2`, mode
`group_first_primary`, pipeline `GROUP_FIRST_GF1_GF6`, visible projection
`G2_V2`, compatibility projection false, and both primary and visible readiness
true. Orchestration runtime was 313.042321 seconds:

| Stage | Count | Runtime seconds |
|---|---:|---:|
| GF1 catalog | 5,327 records | 1.141966 |
| GF2 discovery | 20,396 proposals; 1,285 records with proposals; 4,042 without | 48.017719 run / 50.040965 stage |
| GF3 neighborhoods | 1,285 | included in discovery stage |
| GF4 signed evidence | 20,396 edges: 269 strong, 954 review, 103 cannot-link, 19,070 non-groupable | 15.885954 run / 20.870259 stage |
| GF5 resolution | 240 work units; 207 groups; 19 conflicts; 31 deferred; 4,887 unassigned | 215.594044 run / 230.323226 stage |
| GF6 G2-v2 | 207 groups: 113 likely, 94 review | 1.367147 run / 10.498592 stage |

GF5 recorded 32 targeted requests/results and 212,544 candidate partitions
explored. Legacy pair, G1, G2-v1, and shadow stages were all
`NOT_APPLICABLE`, with zero rows. The earlier R4 diagnostic used threshold 60,
no selected fields, and sensitive mode false; its different aggregate counts
are therefore not evidence of an R6 semantic regression.

## Exact-scan read and export parity

The scan-27 IdentityRead snapshot is ready and has source projection run 3,
orchestration run 4, resolution run 3, 5,327 canonical records, 207 groups,
113 likely groups, 94 review groups, 19 conflicts, 31 deferred units, and 4,887
unassigned records. Its fingerprint is
`181b2f78a24aca00ea10cf7bb3d25f6b197c197e39802403886fbf858748227c`.

The paginated API group list, System Group CSV, and XLSX have identical 207
canonical group keys, statuses, stable member references, and 440 member rows.
The XLSX Summary identifies scan 27 and `G2_V2`. The disposable workbook is:

`C:\Users\THISAL~1\AppData\Local\Temp\scan-27-system-groups-G2V2.xlsx`

It is 164,648 bytes and contains exactly `Summary`, `Duplicate Groups`, and
`Group Data`; 185 groups have two members and 22 have three or more; friendly
labels run deterministically from `DG-000001` to `DG-000207`; and the grouped
sheet contains 1,242 valid merged ranges. `Group Data` has table range
`A1:T441`, zero worksheet AutoFilters, and one table AutoFilter. Repeated export
has identical semantic cell values and merged ranges. Reason and Review State
remain non-authoritative presentation fields.

## Read-only quality canaries

Only source part number, description, UOM, available type/scope fields, and
persisted deterministic outcome/evidence summaries were used. No unavailable
technical attribute was inferred.

- **C1 Contact Cleaner — INSUFFICIENT_DATA.** Six matching records were found.
  Five belong to the same 115-record deferred work unit
  (`RESOLUTION_MEMBER_CAP_REACHED`) and one malformed-UOM record is unassigned.
  No accepted/review group makes an identity claim.
- **C2 Turbine Lubricating Oil — INSUFFICIENT_DATA.** Five ISO68-named records
  were found with litre, liquid-quart, and PCS UOMs. Four are in the same
  capped deferred work unit; the PCS record is in a protected-cannot-link
  conflict. The persisted result does not assert one group.
- **C3 Francis Turbine Lower Bearing — INSUFFICIENT_DATA.** Six same-description
  records were found, mostly PCS with one malformed UOM, all in the capped
  115-record deferred unit. No group identity was decided.
- **C4 Pump X500 versus bearing/component records — INSUFFICIENT_DATA.** Three
  Pump Model X500 records are split across capped deferred work units (115 and
  46 records). They are not accepted with lower-bearing/component records, but
  deferral prevents a positive separation judgment.
- **C5 205/70/15 tyre family — LIKELY_FALSE_GROUP.** AT tyre, slick tyre, and
  snow tyre are combined in one three-member review group. All have the same
  size and PCS UOM, but the explicit subtype words identify materially
  different tyre variants. Coverage is complete pairwise (one strong and two
  review edges) with no recorded technical consensus or cannot-link.
- **C6 wheel versus tyre — LIKELY_FALSE_GROUP.** `MLR-TIRE17-03.10.2023` and
  `MLR-WHEEL-03.10.2023` are combined in one two-member review group. Both use
  EA and share scope, but their explicit physical-item nouns differ. Evidence
  is one review edge, zero strong edges, and review-only support.
- **C7 carbon-stick versus pencil — LIKELY_FALSE_GROUP.** A carbon-stick part
  and pencil part share the dirty carbon-stick description but have G versus
  PCS UOMs. They form a two-member review group with one review edge, zero
  strong edges, and review-only support. Four other carbon-stick matches are
  unassigned.
- **C8 F30 component family — SAFELY_SEPARATED.** Engine, combustion chamber,
  compressor, rotor, stator, and fuel injector remain six separate likely
  groups; each contains only the corresponding two like-described records.
  Each pair has one strong edge and complete pairwise coverage.
- **C9 B38 component family — SAFELY_SEPARATED.** Engine, head, block, fuel
  pump, and pistons remain five separate likely groups; each contains its two
  like-described variants with one strong edge and complete pairwise coverage.
- **C10 MLR/circuit-board transitivity — LIKELY_FALSE_GROUP.** The MLR top and
  component pair is safely held as a protected-cannot-link conflict. The MLR
  wheel/tyre pair is the C6 false review group. Two generic Circuit Board
  records form a likely pair with one strong edge, while model-numbered and
  other generic board records are deferred or unassigned; available fields do
  not justify a broader board conclusion.

The repeatable bounded failure categories for a later task are: explicit
technical subtype words not preventing tyre-variant review grouping; distinct
whole-item nouns (`wheel` versus `tyre`) receiving review-only group support;
and dirty shared descriptions overpowering conflicting part-number nouns and
UOM context (`carbon stick` versus `pencil`). GF-12A2 remains
`HUMAN_REVIEW_DATASET_REQUIRED` regardless of this canary result.

## Boundaries retained

R6 adds no schema, migration, dependency, deployment, IAM, tenancy, provider,
or secret change. It does not reinterpret historical scans, add G2-v1 fallback,
or change human review authority. GF-11 remains in progress under its active
waiver, `GF11-PERF-100K-COLD-FULL` remains open, and the 300-second target is
not met. The real scan proves current-product authority and export consistency;
the Q2 canaries prevent freezing this real workbook as the demo candidate until
a separate bounded identity correction is authorized and verified.
