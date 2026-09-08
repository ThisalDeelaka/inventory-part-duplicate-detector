# GF-12C1-R12 final freeze-only real G2-v2 audit

## Decision

`DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`

The final freeze-only audit found four `D_LIKELY_FALSE_GROUP` results. This
evidence records the blockers without changing detector semantics. The current
candidate must not be frozen or presented as the accepted full-real demo
result.

## Baseline and inputs

- Branch: `llm-assisted-mvp`.
- Starting detector baseline: `73e3e382f5275ed3c00582ba3ab130a978ca34f7` (`Generalize copied-description identity contradictions`).
- Protected tag `deterministic-demo-v1`: `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- The unrelated `List_20260709_093045.xlsx` remained untracked and untouched:
  1,508,088 bytes, UTC mtime `2026-08-30T05:53:46Z`, SHA-256
  `7b4fca921dee032bc6fec6de8c46f41b4092dc42f7bdd68c8128cf70b2ef5cec`.
- The real CSV remained unchanged: 3,265,800 bytes, UTC mtime
  `2026-07-09T04:41:43.8560240Z`, SHA-256
  `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- No environment file, credential, key, token, or authorization header was
  accessed.

## Selected authoritative scan

The earlier R11 scan 2 was not locally reusable: the locally available scan 2
did not match the R11 5,327-record authority, and the prior disposable R11
database was unavailable. Therefore `SCAN_2_PERSISTED_RESULT = UNAVAILABLE`.

Exactly one fresh browser-equivalent run was made against a disposable
database with `product_authority=current_product`, threshold 75, the normal
selected fields, sensitive mode, and provider-none overrides. It completed in
893.978466 seconds, below the 900-second hard budget.

| Property | Persisted result |
|---|---|
| scan | `1` |
| status | `COMPLETED` |
| records | 5,327 |
| policy | `group-first-orchestration-policy-v2` |
| mode | `group_first_primary` |
| primary pipeline | `GROUP_FIRST_GF1_GF6` |
| visible projection | `G2_V2` |
| primary / visible ready | `true` / `true` |
| groups / members | 205 / 431 |
| likely / review | 114 / 91 |
| conflicts / deferred / unassigned | 31 / 30 / 4,896 |
| provider calls | 0 |
| snapshot fingerprint | `dc3fcdbddac942d0aad27b8b3af5f3c81935376748d7f2f438c4f1a922b90ba6` |

All required group-first stages succeeded. Legacy pair compatibility, G1/G2-v1
compatibility, and shadow comparison were `NOT_APPLICABLE`; there was no
silent G2-v1 fallback.

## API, CSV, and XLSX parity

IdentityRead summary, the three paginated group-list calls, every group-detail
membership, System Group CSV, XLSX `Duplicate Groups`, and XLSX `Group Data`
all selected scan 1 / G2-v2. Every surface matched the same 205 canonical group
keys, statuses, 431 stable member references and memberships, and the same
114/91/31/30/4,896 outcome counts. All HTTP responses were 200.

The disposable human-facing workbook is:

`C:\Users\THISAL~1\AppData\Local\Temp\GF12_R12_scan_1_G2_V2_system_groups.xlsx`

It was not committed and did not overwrite the unrelated input XLSX.

## XLSX package validity

The workbook loaded successfully and contained exactly `Summary`, `Duplicate
Groups`, and `Group Data`. `Group Data` has one `SystemGroupData` table, one
table-owned AutoFilter, zero worksheet AutoFilters, a valid table relationship,
and 20 matching unique columns. Its 1,230 merged ranges are valid and
non-overlapping. There are zero formula cells. An openpyxl round trip retained
the table and retained no worksheet AutoFilter.

## Full deterministic safety sweep

All 205 accepted/review groups were swept. Results were:

- internal current `CANNOT_LINK` endpoint pairs: 0;
- internal persisted `CANNOT_LINK` evidence rows: 0;
- internal identity-discriminator contradictions: 0;
- internal object-class contradictions: 0;
- internal construct-class contradictions: 0;
- internal tyre-variant contradictions: 0;
- internal directional-side contradictions: 0.

This passing mechanical safety sweep does not override the separate offline
semantic blockers below; the current bounded discriminator vocabulary does not
represent those four contradictions.

## Full-group risk screen and inspection construction

All 205 groups were screened and 204 were flagged. Aggregate flags were:

| Risk flag | Groups |
|---|---:|
| copied or generic description | 143 |
| size/model/type ambiguity | 120 |
| review-only support with zero strong edges | 88 |
| high genericity | 21 |
| heterogeneous 3+ member evidence | 17 |
| contextual UOM mismatch | 3 |
| bridge risk | 0 |
| missing evidence | 0 |
| mixed explicit bounded identity tokens | 0 |

The deterministic inspection union contained all 204 flagged groups, including
all 17 groups of size 3+, 107 likely size-2 groups, and 80 review size-2 groups.
Because the flagged set exceeded 60, every flagged group was inspected. No
random sampling was used.

## Offline semantic labels

The labels below are audit-only and were not written into product state. They
are not accuracy, precision, recall, or F1 claims.

| Label | Count |
|---|---:|
| `A_STRONG_DUPLICATE_HYPOTHESIS` | 52 |
| `B_PLAUSIBLE_REVIEW` | 35 |
| `C_WEAK_REVIEW_CANDIDATE` | 111 |
| `D_LIKELY_FALSE_GROUP` | 4 |
| `E_INSUFFICIENT_DATA` | 2 |

Per-group labels use the final 12 hex characters of the canonical persisted
group reference:

- **A (52):** `c3bfa70e1f07`, `5d4671c9c13f`, `961f14af621c`, `9e6b676da16f`, `c03a098f3c40`, `a45c0e863b73`, `9cfb18823134`, `ccb379dd166a`, `ef4f20fb8c4d`, `32bc3288fd53`, `43861a863259`, `b63c51b22e20`, `5abd77e18b6e`, `06236630d9dd`, `91d210056b7a`, `fca3bf592368`, `bcf4063d3ea6`, `4db4eba35734`, `07f0e31fe4be`, `f49408a8102d`, `c5068a76d927`, `2eb822818673`, `bb1aa6f01e37`, `3f1181ee4b08`, `bc21c7fe89f0`, `4f886c7a7f48`, `92a5135fb66f`, `31ac1aea2900`, `a5d53528dce2`, `b6b19fec04c0`, `a4eb4cf491cb`, `b6ac3041e9be`, `c79ba567fe1e`, `a6bc89840c6d`, `796864029efb`, `f7b046397e6a`, `e6494a2c7b18`, `a6d59d768fa0`, `30f6870de5c1`, `3d45f73e1561`, `f8fb93eee0f2`, `ac086005b729`, `42f050dfbc63`, `238c027d889b`, `422de83cc9e2`, `5ae1257ceeeb`, `c5f4d196a694`, `0538833d3a37`, `ca44b6d0cd5b`, `46ac2114a7b1`, `c40486e4a7ff`, `daf894a4a0fb`.
- **B (35):** `59aba9cc0166`, `16077366b8ad`, `be64c35a7b7e`, `481c9fb0fcc0`, `fa912e880805`, `dad4abec725a`, `e0d8bce27cea`, `7ffad7fc7609`, `a589e9bd2ca6`, `53f3e1c55559`, `fec36306696c`, `5e133ed10295`, `45e17340e577`, `70a78cfcbf88`, `9a254205ff52`, `a49f5c02f173`, `61af2a8b486b`, `02a0fa4e842f`, `5034efcd189e`, `42b0a00d4892`, `7f52fd59cac2`, `24f944a38d3b`, `433eac79f7d0`, `ac3ba0e4c88d`, `2d9fc52e99a7`, `e9f1c73a41e7`, `91482a12c4ae`, `004429fc8b6f`, `b569a363026e`, `322a30a3844f`, `e3ead774992f`, `106b3d55977c`, `34789a9eb73b`, `b653915cd494`, `0b3e902cb68a`.
- **D (4):** `d56bb1400644`, `b93ad06c716b`, `879cdd84a580`, `8c5f9962410d`.
- **E (2):** `1550fc226f08`, `dc1793d54e79` (wildcard/missing-context and date-coded multi-record evidence was insufficient).

The 111 C groups are listed below by their short audit rationale; each suffix
appears exactly once:

- **Copied/generic text plus naming, number, model, or type ambiguity (50):** `31a9eab022f0`, `16f2a5d98199`, `91d0d915558e`, `35294ed110ff`, `d35cd09c7c51`, `d6ebe6d36f46`, `79cc2546b6b6`, `c63d43d9b0dd`, `4fa93c61e8c8`, `cc506095b9fd`, `d857bad5713d`, `1b3ffcfa5414`, `051e7948967c`, `89e07bb2fbd0`, `9b1c2722d396`, `593a6f47d978`, `5fd53b6e4dd9`, `f56715c83ca0`, `7050bf700d18`, `7699ff524512`, `b262188be892`, `3c7707733f92`, `6728ded515d8`, `ee5244dbae55`, `00e8189b04c5`, `c1caaa2d3ce7`, `ffaeadd86f6b`, `a3a9ae77585c`, `78f168e68f42`, `fb30190bd406`, `4fa6fdf278ab`, `23f86ad0c290`, `21b8513f7619`, `8ce07ead74e4`, `77ec0427d262`, `091717e6a417`, `522a0c4f9c86`, `3f12a4c2d1b3`, `7b938b8e66db`, `347214e8efb4`, `c5809c909f92`, `b129b8fbb2aa`, `af0d015207d5`, `d106ba8669e6`, `049cea1c2a43`, `883eb5a9bd33`, `4081b0821026`, `20e3e16b2a3b`, `110659dc4e79`, `2284e0178950`.
- **Review-only/naming support lacks strong identity evidence (45):** `6e60273ecd47`, `8c9737173f30`, `b3ac073335d3`, `6a22a0066205`, `0eb9f3b6dab1`, `77aa1753e2a7`, `aa691232d836`, `95367d827646`, `dbf3213b045d`, `c86923e793c5`, `825dd07e9fe6`, `c3d819cbc1ab`, `78a03dae1345`, `c40e646d547b`, `78b155a13116`, `fea7a8493c1b`, `10475f1d2dbd`, `050b40f2177a`, `b929aecaa1c4`, `4703c961e615`, `674c2e973e7b`, `f4edc4dda4e5`, `a327910b0f2d`, `7c24ea9e05a4`, `80e4659ba9bc`, `4a73fa97292f`, `6f166aad0dcc`, `20ecb0d39da0`, `8d0bb46592bf`, `36db8186a662`, `e4fd14c9ba61`, `afd0d7c44698`, `7fed6061027d`, `8665d6b910e9`, `9207517a099e`, `79335d45e7bd`, `e9ad075c65cb`, `c25abc791d46`, `ac08b52ebe3f`, `926c00c5976e`, `1950144f75cd`, `5b6a1e59c068`, `c0128f13bd9e`, `6b388ce93676`, `c8d948d753ed`.
- **Heterogeneous 3+ member evidence remains identity-ambiguous (13):** `aaa1cfc08dcd`, `715fbbfd1771`, `14fff2fcf013`, `b9b56aa44022`, `9369e7f6048c`, `86caf6fa6bed`, `3d46526604b4`, `fd5fed8ee59f`, `785743102c18`, `94da1e98c8e1`, `2419df8f358b`, `29e0f133dc6a`, `e0b750fc57f0`.
- **Contextual UOM mismatch is not physical-identity authority (2):** `28a627f00ae9`, `2ca90f413894`.
- **Bounded naming similarity remains weak identity evidence (1):** `ea5e2770ea7e`.

## Quality blockers

1. `g2v2-group-09e675eb0862874bcdef344c1e938109bd8ef3e68dcdedfa885fd56bb1400644`
   groups `XX-BRUSH` with `XX-PAINT` under copied `Exercise 3` text. The
   explicit unrelated object nouns make this a likely false identity group.
2. `g2v2-group-14866a589a989960270239c6768ce256f247477f4a672f34c874b93ad06c716b`
   groups `NE01-MODEL-S` with `NE01-MODEL-X` while the Model X record carries
   copied `Model S` text. The explicit model variants contradict identity.
3. `g2v2-group-6edf19886970013f3716b9de3226f764447b17c3f9907bbd82af879cdd84a580`
   groups `NS-WOOD` with `NS-STEELFRAME` under copied test text. Explicit
   wood versus steel-frame identity is unrelated and the types also differ.
4. `g2v2-group-cca445ef47445485d99ed7bf2c97a2b785211e10c45c93cae8ca8c5f9962410d`
   groups `AUTO01 COILSPRING` with `AUTO01 STAPLERS` under copied `Coil Spring`
   text. The explicit object nouns are unrelated.

These are independently sufficient to fail the quality gate. No new noun rule
or other semantic correction was made in this freeze-only task.

## Known-control recheck

- C1 Contact Cleaner, C2 Turbine Lubricating Oil, C3 Francis Turbine Lower
  Bearing, and C4 Pump X500 remain capped/deferred/unassigned and therefore
  `INSUFFICIENT_DATA`; no forced group was created.
- C5 tyre variants, C6 wheel versus tyre, and C7 carbon-stick versus pencil
  remain safely separated.
- C8 F30 retains six corresponding pairs and no cross-component group.
- C9 B38 retains five corresponding pairs and no cross-component group.
- C10 MLR/circuit-board remains unresolved/protected rather than transitively
  accepted as one family.
- R8 rim/tyre, table/nails, discount/condition, and
  clutch-disk/dust-cap/coil-spring protected families remain separated. The
  newly reported `STAPLERS`/coil-spring case is outside that frozen bounded
  vocabulary and is recorded as a blocker, not repaired here.
- R10 left/right shock endpoints remain in protected conflict and outside
  accepted groups.
- R11 `LG - MIRROR01`/`LG - BUFFER01` and the independent
  `CS-MIRROR-1`/`CS-BUFFER-1` endpoints remain protected and outside groups.

## Architecture, Reason, runtime, and open work

`ARCHITECTURE_PATCHING_RISK_REMAINS_HIGH`. Multiple new obvious unrelated
noun/model/material pairs survived after successive bounded vocabulary fixes.
Further noun-by-noun semantic expansion should stop pending reassessment of the
general identity-representation and evidence boundary.

The XLSX Reason text is `TOO_GENERIC_FOR_DEMO` but not misleading. Preserve
`NEXT_EVIDENCE_BACKED_GROUP_REASON_EXPORT` as later presentation work; no Reason
implementation changed here.

The 893.978466-second full run is presentation evidence only. If a later
candidate passes, use a pre-completed authoritative full-real result plus an
optional smaller honest live scan. Do not fake completion and do not optimize
runtime in this task.

GF-11 remains `IN PROGRESS`, its waiver remains `ACTIVE`,
`GF11-PERF-100K-COLD-FULL` remains `OPEN`, and the 300-second target remains
unmet. GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`. There is no human
accuracy certification, production graduation, deployment readiness, 100k
graduation, or 1M-readiness claim.

## Verification boundary

The focused R7/R9/R10/R11 and XLSX suites passed: 126 tests, one pre-existing
pytest configuration warning. Full backend rerun was not required because no
production source changed and the same detector baseline already passed its
full R11 suite. Frontend test/build was not required because no frontend file
changed. `git diff --check` and `git diff --cached --check` are required before
the evidence commit.

Final decision: `DEMO_CANDIDATE_FREEZE_FAIL_QUALITY`.
