# GF-12C1-R15 deterministic identity-signature derivation

## Authority, scope, and result

R14 verified the pure `IdentitySignature`/`SignedIdentityEvidence` contract
seam. R15 implements only the next bounded unit:

```text
record -> derive_identity_signature(record) -> IdentitySignature
```

The result is `R15_SIGNATURE_DERIVATION_VERIFIED`. The API is pure,
record-local, deterministic, provider-free, and unused by the production scan
path. It does not compare records, build `SignedIdentityEvidence`, classify GF4
edges, change a support gate, persist signatures, or alter detector behavior.

## Version and location

```text
derivation version: identity-signature-derivation-v1
contract version:   identity-signature-contract-v1
module:             app.engine.identity_signature_derivation
offline audit:      app.benchmarks.identity_signature_derivation_audit
```

The module sits beside the R14 contract and the existing engine primitives it
reuses. This keeps derivation independent of services, databases, APIs,
orchestration, GF5, exports, and providers.

## Reused deterministic primitives

R15 reuses without modification:

- `normalize_description` and `normalize_part_no_with_dictionary` for canonical
  spacing, case, token boundaries, abbreviations, and domain expansion;
- `identity-discriminator-v4` record-local object/construct, tyre-variant, and
  directional-side recognition;
- `extract_variant_attributes` for bounded role, variant, type/grade,
  electrical-rating, and dimension evidence;
- `extract_technical_tokens` for typed measurement/dimension observations; and
- `is_generic_description` for metadata-only genericity provenance.

No pairwise evaluator is called.

## Category derivation rules

### Object or construct

Only current bounded discriminator matches become `OBSERVED`
`bounded_object_or_construct` facts. Equal canonical facts from multiple fields
are combined into one immutable observation while retaining every distinct
source observation. No new object vocabulary was added.

### Assembly/component role

Existing structural, end-position, serialization, flow, and engine-component
role groups become source-specific observed role facts. Absence is unknown, not
negative evidence.

### Model/type

Existing explicit `type`/`grade` phrases and structurally alphanumeric tokens
containing both letters and digits are represented as observed model/type
facts. A one-character alphabetic qualifier after explicit `model` or `type`
is deliberately not promoted; it is retained as `UNRESOLVED`. Arbitrary suffix
or residual inequality has no semantic effect.

### Variant

Current bounded side, tyre, filter/function, color, size, sensor, connectivity,
environment, operation, placement, hierarchy, signal, and trailing-variant
observations are retained. This is representation only; no conflict is derived.

### Critical identity attributes

Existing electrical-rating and dimension groups plus typed technical
measurements/dimensions are represented with their source field and normalized
evidence. Raw numbers alone are not promoted as critical attributes.

## Unresolved and unknown semantics

For each populated source, at most four residual normalized tokens of at most
32 characters are retained as source-specific `UNRESOLVED` observations after
recognized tokens and structural stopwords are removed. Single-character raw
residuals are not promoted. Additional model/reliability metadata is drawn from
a finite set of bounded rules and stores only bounded normalized evidence, not
the full raw description.

Unresolved observations produce neither identity support nor contradiction.
Each semantic category with no observed fact appears in `unknown_categories`,
even when unresolved evidence exists. Thus unknown, unresolved, observed, and
contradictory states remain distinct.

## Copied/generic description treatment

Descriptions and master descriptions that normalize identically receive an
explicit `description-master-identical` metadata observation with both source
fields and `DESCRIPTION_MASTER_MATCH` provenance. Existing genericity detection
adds `generic-description` metadata and `GENERIC` provenance. Recognized facts
from those sources remain visible but are not declared trusted. R15 neither
suppresses nor promotes copied/generic evidence.

## Source provenance and fingerprints

Every observation records one of `PART_NUMBER`, `DESCRIPTION`,
`MASTER_DESCRIPTION`, `TYPE_DESIGNATION`, `DIMENSION_QUALITY`, or the existing
bounded-source escape value. Multiple fields may coexist on one fact, and
conflicting/unrecognized evidence is not silently collapsed.

The R14 contract canonicalizes observation/source ordering. The signature
fingerprint includes the contract version, derivation version, record reference,
observed facts, unresolved facts, unknown categories, normalized evidence, and
provenance. It excludes wall time and mutable/runtime state. Repeated derivation
and reordered input mappings are stable.

## Golden and metamorphic tests

Historical golden cases cover carbon-stick/pencil, rim/tyre, table/nail,
condition/discount, clutch-disk/dust-cap/coil-spring, left/right shock,
buffer/mirror, brush/paint, Model S/Model X, wood/steel-frame, and
coil-spring/staplers. They assert only representation, provenance, and unknown/
unresolved preservation.

Positive controls cover Contact Cleaner, Turbine Lubricating Oil, Francis
Turbine Lower Bearing, Pump X500, Fan Blade, F30, B38, different part numbers,
cross-site identity, aliases, missing identity fields, and generic copied text.

M1-M10 prove field-order invariance, canonical observation ordering,
case/spacing normalization, site independence, safe missing optional fields,
unknown noun preservation, non-adjudication of residual differences, copied
provenance visibility, repeated-evidence canonicalization, and repeated
fingerprint stability. Additional tests prove bounded unresolved evidence,
required stable record references, single-record API shape, and audit coverage.

## Read-only 5,327-row audit

The protected CSV was read once through the pure offline audit. No normal scan,
database write, persistence, provider, or pair evaluation occurred.

| Metric | Result |
|---|---:|
| Records derived | 5,327 |
| Unique signature fingerprints | 5,327 |
| Records with recognized object/construct | 200 |
| Records with model/type | 1,902 |
| Records with variant | 1,957 |
| Records with critical attribute | 29 |
| Total unresolved observations | 40,816 |
| Records with unresolved observations | 5,327 |
| All four major identity categories unknown | 1,681 |
| Failures | 0 |
| Wall time | 23.488907 seconds |

Fingerprints are unique because each source row receives its own deterministic
`csv-row-N` record reference; this does not claim semantic uniqueness.

## R12 eight-record audit

| Part number | Recognized | Unresolved identity-bearing evidence | Reliability/source provenance |
|---|---|---|---|
| `XX-BRUSH` | trailing variant `3` | PN `xx`, `brush`; description `exercise` | description/master normalized match retained |
| `XX-PAINT` | trailing variant `3` | PN `xx`, `paint`; description `exercise` | description/master normalized match retained |
| `NE01-MODEL-S` | structural model `ne01` | PN/description/master `model s`; PN `ne`, `01` | single-character model explicitly unresolved; copied metadata retained |
| `NE01-MODEL-X` | structural model `ne01` | PN `model x`; description/master `model s`; PN `ne`, `01` | both source observations coexist; copied metadata retained |
| `NS-WOOD` | none | PN `ns`, `wood`; description/master `nsudlk`, `test` | all major identity categories unknown; copied metadata retained |
| `NS-STEELFRAME` | none | PN `ns`, `steelframe`; description/master `nsudlk`, `test` | all major identity categories unknown; copied metadata retained |
| `AUTO01 COILSPRING` | model `auto01`; coil-spring from PN/description/master | PN `auto`, `01` | three source observations retained; copied metadata retained |
| `AUTO01 STAPLERS` | model `auto01`; coil-spring from description/master only | PN `auto`, `01`, `staplers` | description does not override the unresolved PN evidence |

No pair was evaluated and no duplicate/non-duplicate conclusion was produced.

## Runtime isolation and performance

Import/call-site inspection finds the derivation API only in its tests and the
offline audit module. It is unreachable from GF1-GF6 orchestration, the current
GF4 evaluator, GF5, APIs, persistence, exports, and frontend code.

Work is O(fields × tokens) per record over five bounded source fields. There is
no global O(N²) pass, network access, external inference, ontology traversal,
or per-record database query.

## Deferred work and next unit

R15 explicitly defers pairwise signed-evidence construction, trust/adjudication,
support gating, GF4 behavior, persistence/shadow runs, and fresh real scanning.
The smallest next unit is non-authoritative pairwise `SignedIdentityEvidence`
derivation in tests/offline shadow mode, consuming two derived signatures while
leaving current GF4 support classification unchanged.
