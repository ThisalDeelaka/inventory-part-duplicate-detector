# GF-12C1-R14 identity-signature contract seam

## Authority and classification

R13 selected `R13-E_COMBINE_SIGNATURE_AND_SUPPORT_GATE` and authorized only a
pure representation/evidence seam as the next bounded unit. R14 implements that
unit. Its target classification is `R14_CONTRACT_SEAM_VERIFIED`.

R14 does not extract signatures, evaluate pairs, classify GF4 edges, change a
support gate, persist data, or alter visible/runtime authority. The new module
is imported only by its tests. Provider calls remain zero.

## Location and scope

The contracts live in `app.engine.identity_signature`, beside the existing
record-local candidate features, identity discriminator, edge contract, and
identity evidence evaluator. This is the narrowest existing domain boundary:
the values describe engine evidence but are independent of services,
persistence, APIs, GF5 resolution, and providers. A new subsystem or dependency
would add no value.

The module defines two versioned top-level contracts:

```text
IdentitySignature             identity-signature-contract-v1
SignedIdentityEvidence        signed-identity-evidence-contract-v1
```

Supporting immutable values are `SourceObservation`, `IdentityObservation`,
and `SignedEvidenceFact`. Supporting string enums are `IdentitySourceField`,
`IdentitySemanticCategory`, `IdentityObservationState`, and
`SignedEvidenceChannel`.

## IdentitySignature

Exact fields:

```text
contract_version
derivation_version
record_reference
object_construct_observations
assembly_component_role_observations
model_type_observations
variant_observations
critical_attribute_observations
unresolved_observations
unknown_categories
signature_fingerprint
```

Each semantic observation contains its category, semantic key, normalized
value, `OBSERVED`/`UNKNOWN`/`UNRESOLVED` state, one or more source observations,
and an explicit reason code. Each source observation contains its source field,
normalized evidence, and provenance code. Separate tuples prevent object,
role, model, variant, and critical-attribute evidence from being conflated.

Multiple source observations coexist. The contract does not choose between a
part-number value and a conflicting description value. Future derivation may
record both and mark the semantic observation `UNRESOLVED`.

## Unknown semantics

Unknown is explicit through `unknown_categories` and, where detail exists,
`IdentityObservationState.UNKNOWN`. Unresolved source evidence is independently
explicit through `unresolved_observations`. Neither state is a contradiction.
Different raw tokens, different part numbers, missing fields, generic text, and
no ontology match have no implicit negative meaning in this seam.

Contradiction exists only as a deliberately constructed
`IDENTITY_CONTRADICTION` signed fact. R14 contains no rule that constructs one.

## Source provenance

`IdentitySourceField` preserves these bounded source identities:

```text
PART_NUMBER
DESCRIPTION
MASTER_DESCRIPTION
TYPE_DESIGNATION
DIMENSION_QUALITY
OTHER_EXISTING_BOUNDED_SOURCE
```

The last value represents an already existing bounded context without creating
an open-ended source registry. No universal trust ranking is encoded. Future
derivation can distinguish description-only, part-number-only, corroborated,
copied, generic, or source-conflicted evidence using the preserved facts and
reason codes.

## SignedIdentityEvidence

Exact fields:

```text
contract_version
record_reference_1
record_reference_2
signature_version_1
signature_version_2
signature_fingerprint_1
signature_fingerprint_2
facts
evidence_fingerprint
```

Each `SignedEvidenceFact` independently records:

```text
channel
semantic_category
semantic_key
observed_fact
source_observations_1
source_observations_2
normalized_matches
reason_code
```

The four channels are `IDENTITY_SUPPORT`, `ATTRIBUTE_SUPPORT`,
`LEXICAL_SUPPORT`, and `IDENTITY_CONTRADICTION`. They are an unordered canonical
set of explainable facts, never a combined score. The contract can represent a
future trusted-identity quorum but contains no threshold, edge class, gate
result, or runtime status.

## Determinism and immutability

Every contract is a frozen dataclass. Collection inputs are deduplicated and
canonically ordered. Pair endpoints are canonicalized by record reference, with
endpoint provenance swapped consistently. Serialization recursively converts
dataclasses and string enums into sorted, compact, ASCII JSON. Fingerprints are
SHA-256 over contract version, artifact kind, and all non-fingerprint semantic
fields.

There are no clocks, random identifiers, mutable registries, database IDs,
provider data, or unordered mutable containers. Reordered observations,
sources, categories, facts, and pair orientation produce equal contracts,
serialization, and fingerprints.

## Golden representation cases

The new tests encode G1-G11: carbon-stick/pencil, rim/tyre, table/nail,
condition/discount, clutch-disk/dust-cap/coil-spring, left/right shock,
buffer/mirror, brush/paint, Model S/Model X, wood/steel-frame, and
coil-spring/staplers. Each preserves separate identity facts, copied lexical
provenance, and the absence of an invented R14 contradiction. The fixtures
demonstrate representational capacity; they do not claim extraction or repair.

P1-P12 cover Contact Cleaner, Turbine Lubricating Oil, Francis Turbine Lower
Bearing, Pump X500, Fan Blade, F30, B38, different part numbers, cross-site
identity, aliases, missing identity fields, and generic copied text with unknown
identity. They preserve identity support where explicitly supplied and retain
unknown/non-contradictory variation elsewhere.

Invariant tests prove:

```text
unknown != unresolved != contradiction
different raw token != contradiction
different part number != contradiction
generic lexical evidence != identity support
identity, attribute, lexical, and contradiction channels remain distinct
source provenance and multiple observations are preserved
collection order and pair orientation do not affect equality or fingerprints
contracts are immutable and contain no runtime decision fields
```

## Compatibility evidence

The new contract module has no production importer. Existing identity
evidence/evaluator, GF4 edge, and R7/R9/R10/R11 regression suites pass unchanged.
The complete backend suite is required and recorded with the R14 closeout. No
real 5,327-row scan is required because no runtime path can construct or consume
the new values.

## Explicitly deferred work

R14 deliberately defers:

```text
record-local extraction
source trust/adjudication policy
canonical alias/model/role derivation
signature comparison
GF4 signed-evidence construction
strong-support gating
shadow execution or persistence
runtime integration
fresh real scan and freeze audit
```

The smallest next unit is a pure deterministic per-record `IdentitySignature`
deriver behind this still-unused contract. It must add extraction and golden
tests only, preserve all source observations and unknown states, and make no GF4
behavior change.
