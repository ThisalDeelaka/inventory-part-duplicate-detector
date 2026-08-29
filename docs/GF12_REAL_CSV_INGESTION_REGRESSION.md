# GF-12C1-R1 real CSV ingestion regression evidence

## Decision

The historical input contract is restored without reverting group-first product
authority. The unchanged real CSV validates through the exact multipart contract
used by New Scan. A separate downstream character-retrieval failure prevents an
end-to-end real-data product claim and is not disguised as an ingestion failure.

The regression was **not introduced by the group-first migration itself**. The
best-evidence boundary predates group-first: `f6889ef3b05cee89369af232a8344aff12f969a7`
accepted and committed the byte-identical file, and
`42fa7ba3e7b2a8190179030e001deb07c65ee023` reverted that mapper. Commit
`957762a2a2abcf2a2df341e49393df0865fabe90` restored flexible mapping but omitted
the historical `Part Description in Use` fallback. Later synthetic-demo
acceptance also supplied a mapping that the browser-default request did not,
creating an `R7_DEMO_HARNESS_BYPASSES_BROWSER_VALIDATION` parity gap.

## Immutable real-file evidence

- Path: `C:\Users\ThisalDeelaka\Downloads\List_20260709_093045.csv`
- Size: 3,265,800 bytes
- SHA-256: `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`
- Encoding: UTF-8 (strict decode); delimiter: comma
- Data rows: 5,327; columns: 133
- Header length: 2,908 bytes/characters
- Header SHA-256: `02679af51603d8fa053f63d64346277bf6428c08e2676b1da22a38935393b779`
- Git evidence: the blob at `f6889ef:data/List_20260709_093045.csv` has the
  same byte size and SHA-256 and is byte-for-byte identical.

Exact serialized header row:

```csv
Part No,Part Description in Use,Part Description,Site,Site Description,Part Type,Planner,Inventory UoM,Catch UoM,Input UoM Group,Input UoM Group Description,Commodity Group 1,Commodity Group 1 Description,Commodity Group 2,Commodity Group 2 Description,Asset Class,Asset Class Description,Part Status,Part Status Description,ABC Class,ABC Class Description,Abc Class Locked Until,Frequency Class,Frequency Class Locked Until,Lifecycle Stage,Lifecycle Stage Locked Until,Safety Code,Safety Code Description,Accounting Group,Accounting Group Description,Product Code,Product Code Description,Product Family,Product Family Description,Type Designation,Dimension/ Quality,Net Weight,Weight UoM,Net Volume,Volume UoM,Exclude from Shipment Packing Proposal,On Hand Qty,On Hand Catch Qty,Created,Modified,Document Text,Notes,Lead Time Code,Purchasing Lead Time,Earliest Unlimited Supply Date,Manufacturing Lead Time,Expected Lead Time,Supersedes Part,Superseded By Part,Shelf Life in Days,Minimum Remaining Days at CO Delivery,Minimum Remaining Days for Planning,Mandatory Expiration Date,Country of Origin,Country of Origin Description,Region Code,Region Code Description,Customs Statistics No,Customs Statistics No Description,Intrastat Conv Factor,Customs UoM,Supply Chain Part Group,Supply Chain Part Group Description,Default Mtrl Req Supply,Dop Connection,Dop Netting,Tech Coordinator,Qty Calc Rounding,Configurable,Inventory Valuation Method,Inventory Part Cost Level,Supplier Invoice Consideration,Zero Cost,Part Cost Group,Part Cost Group Description,External Service Cost Method,Cycle Counting Interval,Cum Count Diff,Cycle Counting,Reserve at order entry,Automatic Capability Check,Negative On Hand,Availability Check,Availability Check at CO Reserve,Online Consumption,Shortage Notification,Stock Management,Refill Putaway Zones,Refill Putaway Zones Operative Value,Refill Putaway Zones Source,Std Putaway Qty,Inventory Part Standard Name,Inventory Part Standard Name Description,Part Catalog Standard Name,Part Catalog Standard Name Description,GTIN,GTIN Series,Alternate Parts Exist,Characteristic Template,Operative Storage Width Requirement,Storage Width Requirement Source,Operative Storage Height Requirement,Storage Height Requirement Source,Operative Storage Depth Requirement,Storage Depth Requirement Source,UoM for Length,Qty per Volume,Operative Qty per Volume,Qty per Volume Source,UoM for Volume,Operative Storage Weight Requirement,Storage Weight Requirement Source,UoM for Weight,Operative Min Storage Temperature,Min Storage Temperature Source,Operative Max Storage Temperature,Max Storage Temperature Source,UoM for Temperature,Operative Min Storage Humidity (%),Min Storage Humidity (%) Source,Operative Max Storage Humidity (%),Max Storage Humidity (%) Source,HSN/SAC Code,HSN/SAC Code Description,Product Category,Product Category Description,Consumption Tax,Master Part Description
```

No inventory rows are copied into repository tests or documentation.

## Historical and current contract

The historical mapper normalized punctuation/case, recognized multiple source
aliases, and populated canonical columns. The current mapper deliberately fails
closed on ambiguous aliases. The correction adds a contextual fallback: `Part
Description in Use` maps to `DESCRIPTION` only when a primary description source
is absent. Thus a real export containing both description columns remains
unambiguous, while the older single-description variant is accepted again.

| Meaning | Real/historical header | Historical canonical | Corrected current canonical | Frontend condition | Required? |
|---|---|---|---|---|---|
| part identifier | Part No | PART_NO | PART_NO | implicit | yes |
| description | Part Description in Use / Part Description | DESCRIPTION | DESCRIPTION (primary plus fallback) | implicit | yes |
| site | Site | CONTRACT | CONTRACT | CONTRACT | no |
| inventory UOM | Inventory UoM | UNIT_MEAS | UNIT_MEAS | UNIT_MEAS | no |
| part type | Part Type | TYPE_CODE | TYPE_CODE | TYPE_CODE | no |
| commodity 1 | Commodity Group 1 | PRIME_COMMODITY | PRIME_COMMODITY | PRIME_COMMODITY | no |
| commodity 2 | Commodity Group 2 | SECOND_COMMODITY | SECOND_COMMODITY | SECOND_COMMODITY | no |
| safety | Safety Code | HAZARD_CODE | HAZARD_CODE | HAZARD_CODE | no |
| accounting | Accounting Group | ACCOUNTING_GROUP | ACCOUNTING_GROUP | ACCOUNTING_GROUP | no |
| product code | Product Code | PART_PRODUCT_CODE | PART_PRODUCT_CODE | PART_PRODUCT_CODE | no |
| product family | Product Family | PART_PRODUCT_FAMILY | PART_PRODUCT_FAMILY | PART_PRODUCT_FAMILY | no |
| product category | Product Category | PRODUCT_CATEGORY_ID | PRODUCT_CATEGORY_ID | PRODUCT_CATEGORY_ID | no |
| HSN/SAC | HSN/SAC Code | HSN_SAC_CODE | HSN_SAC_CODE | HSN_SAC_CODE | no |

Required-column calculation remains exactly `PART_NO` plus `DESCRIPTION`.
Selected optional conditions remain warnings when absent. Same-site and
cross-site modes use the same canonical intake and preserve current site
semantics.

## Reproduction and root cause

At starting HEAD `5fa036c`, the exact real file produced HTTP 200, 5,327 records,
`valid=true`, and no missing required/selected fields through the browser-equivalent
multipart request. Therefore the reported real-file missing-column response was
not reproducible in the current clean code and cannot honestly be attributed to
group-first. Historical inspection nevertheless proves an incomplete compatibility
restoration: `R3_HEADER_ALIAS_MAPPING_REMOVED` for exports having only `Part
Description in Use`.

The synthetic fixture reproduced the visible problem at starting HEAD: HTTP 200
with `valid=false` and missing `PART_NO`/`DESCRIPTION`. The automated demo helper
silently supplied `Stock Ref` and `Item Narrative` mappings while New Scan sent
`column_mapping={}`. This is `R7_DEMO_HARNESS_BYPASSES_BROWSER_VALIDATION`.

The correction adds deterministic aliases for those generic demo headers, changes
the demo acceptance helper to use `{}`, and retains explicit mapping plus ambiguity
failure for genuinely custom or conflicting headers. There is one normalization
implementation shared by Validate only and Run scan.

## Validation evidence

- Real Validate only: HTTP 200, `valid=true`, 5,327 records, no missing required
  or selected fields; `Part No -> PART_NO`, `Part Description -> DESCRIPTION`,
  `Site -> CONTRACT`, and `Inventory UoM -> UNIT_MEAS`.
- Synthetic browser-default Validate only after correction: HTTP 200,
  `valid=true`; `Stock Ref -> PART_NO`, `Item Narrative -> DESCRIPTION`.
- Small real-schema browser-parity uploads complete in both same-site and
  cross-site modes with `group_first_primary`, `G2_V2`, no compatibility
  projection, and zero provider requests.
- A genuinely missing description upload remains HTTP 422 with typed missing
  column `DESCRIPTION`; unknown extra columns remain harmless.
- Focused intake/demo tests: 48 passed.
- Full backend regression: 1,400 passed, 15 skipped, one pre-existing pytest
  configuration warning.
- Frontend: no `test` script is configured; the Vite production build passed
  (38 modules transformed).

## Real end-to-end result

Provider-free disposable execution accepted and canonicalized all 5,327 records.
The subsequent group-first run did **not** complete: after approximately 60.136
seconds, character retrieval raised `CharacterRetrievalError: LSH candidate pool
has too few positive-cosine candidates`. The persisted scan/orchestration status
was `FAILED`, safe category `PRIMARY_IDENTITY_FAILED`, and
`visible_product_ready=false`. No GF2-GF6 result counts can be claimed for this
failed run. Provider calls were zero by configuration and no provider code path
was authorized.

This is a separate retrieval/data-shape blocker. It was not fixed by weakening
candidate-pool, similarity, or group semantics because those changes are outside
the ingestion-restoration scope.

## REG1-REG22 disposition

REG1-REG2 are backed by the byte-identical historical blob and commit boundary.
REG3 is not reproducible for the exact real file at clean starting HEAD and is
recorded honestly; the narrower historical alias gap is proven. REG4 reproduced
the synthetic harness/browser mismatch. REG5-REG12 pass through focused mapping,
Validate-only, Run-scan, fail-closed, and extra-column tests. REG13-REG17 pass on
small real-schema same/cross-site group-first integrations with zero providers.
REG18 passes by unchanged real-file SHA-256. REG19-REG20 pass with no schema,
migration, dependency, threshold, or decision change. REG21 passes after removal
of hidden demo mappings. REG22 passes: no `.env` or secret was read or changed.

Group-first remains the sole primary product authority. No pair-first product,
auto-merge/delete/writeback, human-quality graduation, deployment readiness, or
production-scale graduation is claimed.
