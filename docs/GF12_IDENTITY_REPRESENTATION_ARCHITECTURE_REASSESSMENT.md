# GF-12C1-R13 identity representation architecture reassessment

## Decision summary

R12 failed the full-real demo freeze after four likely false groups survived the
unchanged R11 detector. R13 confirms that these are not four isolated missing
nouns. The recurring defect is an asymmetric evidence boundary: broad lexical
and business-context similarity can create positive GF4 support, while negative
identity evidence exists only when a bounded extractor already recognizes an
explicit incompatibility. An unrecognized or source-conflicted identity remains
permissive even when a copied description supplies nearly all of the score.

The selected target is:

```text
R13-E_COMBINE_SIGNATURE_AND_SUPPORT_GATE
ONTOLOGY_SUPPORTING
```

The correction belongs first in deterministic per-record identity-signature
extraction/enrichment and then in GF4 signed-evidence classification. Discovery
must remain recall-oriented and GF5 must remain a constrained whole-group
resolver, not become an ad-hoc semantic classifier. R13 changes no production
semantics. The current detector remains unfrozen.

## R12 trigger and method

The authoritative R12 scan completed with 5,327 records, 205 groups, 431 grouped
members, 114 likely groups, 91 review groups, 31 conflicts, 30 deferred units,
4,896 unassigned records, zero provider calls, and a runtime of 893.978466
seconds. All 205 groups were screened and 204 were inspected. The labels were
A=52, B=35, C=111, D=4, and E=2.

R13 used a read-only offline harness over the R12 Group Data export and the
hash-verified source CSV. It rebuilt current pair features, discriminator
evidence, GF4 edge classes, and six counterfactual classifications. It neither
wrote a database nor changed production code. Group-impact counts are
conservative edge-screening estimates, not claims that the GF5 resolver was
rerun under changed semantics.

## Exact reconstruction of the four D groups

All four groups contain exactly two members. Consequently each has one internal
edge, no bridge record, and the group-resolution path is the same: one support
edge forms a complete-pairwise accepted group.

### D1 `d56bb1400644`: brush / paint

Canonical group:
`g2v2-group-09e675eb0862874bcdef344c1e938109bd8ef3e68dcdedfa885fd56bb1400644`.

| Field | Brush record | Paint record |
|---|---|---|
| Source row / stable ref | 1434 / `76bb99a49dabcd106b6c57546eaa81b92a56e1d061dca7c3a2750ed2dac66247` | 1433 / `b7e850dc0497dbd384b63f2ea3fababee5a7a61b45eaffaf982534435018a5bb` |
| Part number | `XX-BRUSH` | `XX-PAINT` |
| Description / master description | `Exercise 3` / `Exercise 3` | `exercise 3` / `exercise 3` |
| Type designation / dimension-quality | empty / empty | empty / empty |
| UOM / part type | `pcs` / `Purchased` | `pcs` / `Purchased` |
| Normalized part number | `xx brush` | `xx paint` |
| Normalized description | `exercise 3` | `exercise 3` |
| Object / construct / variant / side | none / none / none / none | none / none / none / none |

Pair scores are final 92.86, description 100, TF-IDF 100, fuzzy 100,
part-number 28.57, and technical-token 100. The business result is
`LIKELY_DUPLICATE`, the rule is `ALLOW`, and GF4 emits `STRONG_SUPPORT` with
`DETERMINISTIC_LIKELY_DUPLICATE`. Description reliability is
`IDENTICAL_NON_OBJECT_BEARING_TEXT`; genericity flags are false despite the
obviously non-identifying text. There is no current contradiction. The
part-number signature shares `xx` and has unresolved residuals `brush` versus
`paint`; there is no trusted identity agreement. Copied lexical evidence plus
matching site/UOM dominates the unrecognized identity disagreement.

### D2 `b93ad06c716b`: Model S / Model X

Canonical group:
`g2v2-group-14866a589a989960270239c6768ce256f247477f4a672f34c874b93ad06c716b`.

| Field | Model S record | Model X record |
|---|---|---|
| Source row / stable ref | 4991 / `3286f903299caf2f7ef5dd68dcbc9e585587cdc6a0a511394b7b612bb112abc6` | 4925 / `c34279d587e929606175f82fbb35c976c2df3d31e613e14b80a4b2961b980539` |
| Part number | `NE01-MODEL-S` | `NE01-MODEL-X` |
| Description / master description | `Model S` / `Model S` | `Model S` / `Model S` |
| Type designation / dimension-quality | empty / empty | empty / empty |
| UOM / part type | `PCS` / `Purchased` | `PCS` / `Purchased` |
| Normalized part number | `ne 01 model s` | `ne 01 model x` |
| Normalized description | `model s` | `model s` |
| Object / construct / variant / side | none / none / none / none | none / none / none / none |

Pair scores are final 94.0, description 100, TF-IDF 100, fuzzy 100,
part-number 90, and technical-token 50. The result is `LIKELY_DUPLICATE` /
`ALLOW`; GF4 emits `STRONG_SUPPORT` with
`DETERMINISTIC_LIKELY_DUPLICATE`. Reliability is
`IDENTICAL_NON_OBJECT_BEARING_TEXT`, and no contradiction exists. The
part-number signature shares `ne`, `01`, and `model`, but has residual model
qualifiers `s` versus `x`. A crude 90-percent part-number similarity test calls
this trusted agreement, proving that fuzzy similarity is not itself trusted
identity evidence when explicit residual qualifiers disagree.

### D3 `879cdd84a580`: wood / steel-frame

Canonical group:
`g2v2-group-6edf19886970013f3716b9de3226f764447b17c3f9907bbd82af879cdd84a580`.

| Field | Wood record | Steel-frame record |
|---|---|---|
| Source row / stable ref | 5135 / `18477b5eecb035329b95a9ad6727d8105e53ca19c21f47c0e7b0d219ad93cc1b` | 5012 / `9a5fd1ff5c0e8735bf7002851480ae27ec3990294a08cc8ca80a4b2961b980539` |
| Part number | `NS-WOOD` | `NS-STEELFRAME` |
| Description / master description | `NSUDLK TEST` / `NSUDLK TEST` | `NSUDLK TEST` / `NSUDLK TEST` |
| Type designation / dimension-quality | empty / empty | empty / empty |
| UOM / part type | `PCS` / `Purchased` | `PCS` / `Manufactured` |
| Normalized part number | `ns wood` | `ns steelframe` |
| Normalized description | `nsudlk test` | `nsudlk test` |
| Object / construct / variant / side | none / none / none / none | none / none / none / none |

Pair scores are final 87.22, description 100, TF-IDF 100, fuzzy 100,
part-number 22.22, and technical-token 50. The result is
`POSSIBLE_DUPLICATE_REVIEW` / `ALLOW`; GF4 emits `REVIEW_SUPPORT` with
`DETERMINISTIC_REVIEW_CANDIDATE`. Reliability is
`IDENTICAL_NON_OBJECT_BEARING_TEXT`; no contradiction or trusted identity
agreement exists. The signature shares `ns` and has residuals `wood` versus
`steelframe`. The single review edge is sufficient for a review group.

### D4 `8c5f9962410d`: coil-spring / staplers

Canonical group:
`g2v2-group-cca445ef47445485d99ed7bf2c97a2b785211e10c45c93cae8ca8c5f9962410d`.

| Field | Coil-spring record | Staplers record |
|---|---|---|
| Source row / stable ref | 3983 / `4764a45dd99da3952f65d937d0fb5f938793afe805aaa00c8a107598203acc77` | 3941 / `b5766902113f79adb643332b229d41646edc0cf5fbd6282b10c277e76c682ea1` |
| Part number | `AUTO01 COILSPRING` | `AUTO01 STAPLERS` |
| Description / master description | `Coil Spring` / `Coil Spring` | `Coil Spring` / `Coil Spring` |
| Type designation / dimension-quality | empty / empty | empty / empty |
| UOM / part type | `PCS` / `Purchased` | `PCS` / `Purchased` |
| Normalized part number | `auto 01 coilspring` | `auto 01 staplers` |
| Normalized description | `coil spring` | `coil spring` |
| Object / construct / variant / side | coil-spring / none / none / none | coil-spring from description only / none / none / none |

Pair scores are final 91.0, description 100, TF-IDF 100, fuzzy 100,
part-number 60, and technical-token 50. The result is `LIKELY_DUPLICATE` /
`ALLOW`; GF4 emits `STRONG_SUPPORT` with
`DETERMINISTIC_LIKELY_DUPLICATE`. Reliability is
`IDENTICAL_OBJECT_BEARING_TEXT`. The coil record is corroborated by part number
and description; the staplers record inherits coil-spring solely from the
copied description because `staplers` is unknown. No contradiction results.
The signature shares `auto` and `01` but has residuals `coilspring` versus
`staplers`, with no trusted agreement. This is direct evidence that even a
recognized object-bearing description is not reliable when record-local source
fields disagree.

## Historical false-group matrix

| Family | Support and description state | Identity-bearing source / recognition before correction | Miss and correction | Reusable? |
|---|---|---|---|---|
| carbon-stick / pencil | copied carbon-stick text | part-number noun; incomplete recognition | no pre-patch contradiction; R7 bounded classes/composite | bounded only |
| rim / tyre | high lexical/size similarity | part-number noun; rim alias absent | relation invisible; R9 classes/incompatibility | yes, within wheel domain |
| table / nail | copied test text | part-number noun; absent | unknown stayed permissive; R9 classes | bounded only |
| condition / discount | copied commercial text | part-number construct; absent | object ontology was the wrong signal; R9 construct class | yes, commercial constructs |
| clutch-disk / dust-cap / coil-spring | copied dust-cap text | part-number nouns; absent | description dominated; R9 classes/incompatibilities | bounded only |
| left / right shock | copied left text | part-number side abbreviations; extractor absent | same object but mutually exclusive side; R10 side/base extractor | yes, directional variants |
| buffer / mirror | copied condition text | part-number nouns; absent | unknown stayed permissive; R11 classes/incompatibility | bounded only |
| brush / paint | copied `Exercise 3` | part-number residual nouns; absent | 100 lexical score plus context outweighed identity | uncorrected |
| Model S / Model X | copied `Model S` | part-number model qualifier; absent | fuzzy part-number similarity hid residual qualifier conflict | uncorrected |
| wood / steel-frame | copied test text | part-number residual identity; absent | review support needed no identity agreement | uncorrected |
| coil-spring / staplers | copied recognized coil text | first part number recognized; second unknown | description-only class overrode source conflict | uncorrected |

The recurring pattern is not merely missing vocabulary. Positive support is
available from an exact copied description and contextual fields before any
identity-bearing agreement is proved. Contradiction is available only after a
specialized extractor maps both sides into a protected relation. Unknown and
source-conflicted identities therefore behave as though nothing is wrong.
Each noun patch fixes its fixture, but unrelated residual identity tokens keep
crossing the same permissive evidence boundary.

## Positive-control matrix

| Control | Identity evidence that must remain usable | Architectural implication |
|---|---|---|
| Contact Cleaner | specific object phrase plus compatible attributes | trusted phrase can support identity; lexical similarity alone cannot define it |
| Turbine Lubricating Oil | object/role phrase and grade/application attributes | distinguish identity from compatible attributes |
| Francis Turbine Lower Bearing | assembly, component role, location | structured role tokens are identity-bearing |
| Pump X500 | object plus model | model agreement is trusted only when qualifiers are compatible |
| Fan Blade | aliases and object/component role across varying part numbers | canonical alias/signature equivalence must survive; the crude gate harmed one group |
| F30 / B38 | explicit model tokens and corresponding component descriptions | shared model/role can be trusted; crude residual disagreement harmed six F30 groups and copied-description caps harmed F30/B38 |
| Same physical item, different part numbers | corroborating object/model/role/critical attributes | different part number is never automatically contradiction |
| Same item across sites | physical signature agreement | site is context, not identity disagreement |
| Same object, different aliases | canonical alias equivalence or compatible signature | ontology supports normalization but is not the sole authority |
| Same object, model/size suffix differences | structured qualifier compatibility or unknown | difference is not automatically cannot-link; unresolved cases remain review/deferred |
| Review-only naming similarity | lexical candidate support without identity quorum | retain for discovery, but do not promote to accepted identity group |
| Generic copied text with unknown identity | no trusted identity support | remain discoverable and auditable as unknown/non-groupable evidence |

The separating signal is a trusted, record-local identity agreement assembled
from source-aware object/model/role/variant/critical-attribute evidence, not a
complete universal noun list. Missing evidence is `UNKNOWN`, not contradiction.
Explicit recognized incompatibility remains the only route to cannot-link.

## Current architecture diagnosis

The deterministic score weights description similarity at 60 percent, selected
business fields at 20 percent, part number at 10 percent, and technical tokens
at 10 percent. Exact copied descriptions plus same site/UOM can therefore reach
likely or review status despite very weak part-number similarity. The generic
guard catches only narrow forms, so `Exercise 3`, `Model S`, `NSUDLK TEST`, and
`Coil Spring` are not sufficient safeguards. GF4 then promotes a permitted
likely result to strong support without requiring identity-bearing agreement.

The discriminator is source-aware where it has vocabulary, but its positive
and negative sides are not symmetric. Broad scores create support; protected
conflicts require exact known classes, variants, constructs, or sides. Known
versus unknown and source disagreement do not create contradiction, correctly,
but they also do not stop copied lexical evidence from becoming identity
support. GF5 consumes the resulting signed edges correctly; it is not the root
defect.

The contributing causes are A, B, C, D, E, F, G, and H from the R13 question.
The ontology is structurally useful but cannot be the primary identity model.
The additional proven cause J is source trust: a description-derived class can
mask contradictory or unresolved part-number structure on the same record.

## Positive-versus-negative asymmetry

The hypothesis is confirmed. All four D groups had exact 100-point lexical
description support. Three had no recognized object class on either record; the
fourth had a description-derived class on both records but part-number
corroboration on only one. All four had zero protected contradictions. A simple
strong-support identity-agreement rule downgraded three strong D edges but did
not eliminate any accepted two-record group; a signed non-groupable gate
eliminated two. The residual-signature prototype eliminated all four, but its
positive-control damage proves that the prototype is not production-safe.

## Offline counterfactual experiments

| CF | Rule | D groups prevented | Accepted groups affected | Likely groups without strong support | Review groups affected | No longer supportable | Named positive-control impacts |
|---|---|---:|---:|---:|---:|---:|---|
| CF1 | current behavior | 0 | 0 | 0 | 0 | 0 | none |
| CF2 | unreliable description cannot alone create strong support, except crude strong-PN escape | 0 | 82 | 79 | 2 | 0 | B38 5, F30 6, Fan Blade 1 |
| CF3 | strong support requires prototype trusted agreement | 0 | 59 | 57 | 1 | 0 | Fan Blade 1 |
| CF4 | unknown object plus unreliable copied text capped at review | 0 | 113 | 110 | 3 | 0 | B38 5, F30 6, Fan Blade 1 |
| CF5 | unreliable and no prototype identity agreement becomes non-groupable | 2 | 87 | 55 | 31 | 83 | Fan Blade 1 |
| CF6 | CF5 plus unresolved residual part-number disagreement under identical text | 4 | 124 | 91 | 32 | 119 | F30 6, Fan Blade 1 |

CF2 downgrades D1 and D4 but D2 escapes through 90-percent fuzzy part-number
similarity; D3 was already review. CF3 downgrades D1 and D4, while the same
crude fuzzy test lets D2 escape. CF4 downgrades D1 and D2 but misses D4 because
the copied description supplies a known class. CF5 prevents D1 and D3 but
misses D2 and D4. CF6 prevents all four.

These experiments reject every raw counterfactual as production semantics.
CF6 demonstrates that cross-source residual disagreement is necessary evidence,
but its 124-group impact and harm to F30/Fan Blade demonstrate that raw token
inequality is not a safe signature. The design must first represent aliases,
models, component roles, and critical attributes and freeze those rules against
historical and positive-control golden cases.

## Architecture candidates and rejected alternatives

### A. Continue bounded ontology expansion — rejected

It is deterministic and auditable, but coverage scales with encountered nouns,
maintenance is open-ended, domain portability is poor, and each missing class
creates a false-negative in contradiction detection. Broad incompatibility
expansion also increases false cannot-links. R7-R11 are valid bounded evidence,
but their repetition demonstrates that this cannot be the primary architecture.

### B. Trusted object-signature representation — necessary but insufficient alone

A source-aware signature can separate object/construct, assembly/component role,
model/type, directional/other variant, and identity-critical attributes from
generic/commercial text. It addresses part-number structure without requiring
every noun pair. On its own, however, it does not state how unknown or
source-conflicted signatures constrain broad lexical support.

### C. Positive-support gating under unreliable descriptions — necessary but insufficient alone

It directly fixes the promotion asymmetry, but CF2/CF4 show that reliability and
unknown-class tests are too coarse. Legitimate F30/B38/Fan Blade groups can be
downgraded, while description-derived false agreement such as D4 can escape.

### D. Identity-evidence quorum / signed evidence — necessary but insufficient without representation

Separating identity, attribute, lexical, and contradictory evidence makes GF4
semantics explicit and auditable. Without a richer record signature, however,
the quorum inherits the same incomplete ontology and fuzzy-part-number errors.

### E. Combine signature and support gate — selected

Derive a deterministic source-aware identity signature per record, compare it
per candidate edge, and require at least one trusted identity-bearing agreement
plus no protected contradiction for `STRONG_SUPPORT`. Lexical and attribute
agreement remain visible but cannot masquerade as identity. Unknown evidence
does not become cannot-link. This combines B, C, and D at the existing GF4
boundary and preserves GF5 responsibility.

Rejected overcorrections include unknown-class rejection, arbitrary different-
noun or different-part-number cannot-links, generic-description rejection, and
no-ontology-match rejection. Each would suppress legitimate dirty-data,
cross-site, alias, or different-part-number duplicates.

## Formal semantic contract

### Inputs and representation

For each record, produce an immutable, versioned `IdentitySignature` from only
allowlisted normalized fields:

```text
object_or_construct: value + source + confidence/provenance
assembly_component_role: values + provenance
model_type_identity: base + qualifiers + provenance
variants: directional and other identity-critical qualifiers + provenance
critical_attributes: typed values/units + provenance
generic_commercial_tokens: values, never identity-bearing by themselves
unknowns_and_source_conflicts: explicit reason codes
```

For an edge, emit four independent evidence channels:

```text
IDENTITY_SUPPORT       trusted canonical agreement in object/construct,
                       role, model/type, variant, or critical identity tuple
ATTRIBUTE_SUPPORT      compatible non-identity properties and context
LEXICAL_SUPPORT        description/part-number similarity, including generic text
IDENTITY_CONTRADICTION explicit recognized incompatible signatures/qualifiers
```

Trusted identity evidence must be record-local, source-aware, and explainable.
Description-only identity is not trusted when the same record has unresolved
part-number identity residuals. Fuzzy part-number similarity is lexical support,
not trusted identity agreement. Ontology aliases may canonicalize evidence, but
absence of an alias is `UNKNOWN`.

### State table

| Evidence state | GF4 behavior |
|---|---|
| protected identity contradiction | `CANNOT_LINK` regardless of positive scores |
| trusted identity support + no contradiction + current likely criteria | `STRONG_SUPPORT` |
| trusted identity support + no contradiction + current review criteria | `REVIEW_SUPPORT` |
| no trusted identity support, but useful lexical/attribute evidence | discovery remains; edge is `REVIEW_SUPPORT` only if policy explicitly treats it as non-accepting evidence, otherwise `NON_GROUPABLE/DEFERRED`; it cannot form an accepted identity group by itself |
| signature unknown or source-conflicted | `UNKNOWN`, never automatic contradiction; retain provenance and do not promote lexical evidence to strong |
| no meaningful evidence | `NON_GROUPABLE/DEFERRED` with reason |

Normative pseudocode:

```text
signature_a = extract_identity_signature(record_a)
signature_b = extract_identity_signature(record_b)
evidence = compare_signed(signature_a, signature_b, lexical, attributes)

if evidence.protected_identity_contradiction:
    return CANNOT_LINK
if evidence.trusted_identity_agreement and current_policy_is_likely:
    return STRONG_SUPPORT
if evidence.trusted_identity_agreement and current_policy_is_review:
    return REVIEW_SUPPORT
if evidence.lexical_or_attribute_support:
    return NON_GROUPABLE_OR_DEFERRED_WITH_REVIEW_PROVENANCE
return NON_GROUPABLE_OR_DEFERRED
```

The exact non-accepting representation (`NON_GROUPABLE` versus a separately
named deferred-review evidence state) must be frozen in Phase 1 before code is
integrated; current review/export/status authority must not be silently changed.

### Whole-group and provenance implications

GF5 continues to require complete-pairwise admissibility, respect every
cannot-link, enforce existing bounds, and rank deterministic candidate groups.
Lexical-only bridge edges cannot provide the identity quorum needed for group
membership. Every edge persists signature version, field sources, normalized
matches, channel-specific support, unknown/conflict reasons, protected
contradictions, and final GF4 reason codes. Human review remains final authority.

## Abstraction layer, ontology role, and performance

The earliest correct seam is enrichment/identity-signature extraction, with
the resulting signed evidence consumed by GF4 support classification. It is not
normalization alone because token roles and source trust are semantic; not
discovery because recall must remain broad; and not GF5 because whole-group
resolution must not infer record semantics.

Ontology role is exactly `ONTOLOGY_SUPPORTING`. It supplies canonical aliases,
known constructs, protected incompatible relations, and typed attribute rules.
The primary safety rule is the evidence contract and source-aware signature,
while ontology misses remain unknown. Reducing ontology would discard proven
R7-R11 safeguards; making it primary repeats the patching cycle.

Signature extraction is O(records × bounded fields/tokens); edge comparison is
O(candidate edges × bounded signature size). It requires no external inference,
global ontology traversal, or new all-record O(N²) pass. Existing candidate
edges remain the comparison boundary. The R12 893.978466-second performance
debt is not addressed here.

## Smallest safe migration

1. **Representation/evidence seam:** add versioned pure contracts and golden
   fixtures only—no runtime integration—for signature fields, source trust,
   signed channels, unknown/conflict states, and provenance. Include all
   historical failures and every named positive control.
2. **Signature derivation:** implement pure record-local extraction behind the
   unused seam; prove aliases, model qualifiers, role, side, typed attributes,
   copied-source conflict, and missing data behavior.
3. **GF4 shadow comparison:** compute old and proposed classes offline/persisted
   non-authoritatively; do not change current writes or visible authority.
4. **Regression decision:** require all historical false groups to be withheld,
   R7/R9/R10/R11 cannot-links preserved, and positive controls preserved. Reject
   any CF6-like broad damage.
5. **Bounded GF4 integration:** only after reviewed fixtures and shadow evidence,
   switch the evidence classifier without changing retrieval, GF5 caps,
   statuses, schema authority, review, or export behavior.
6. **Fresh real G2-v2 scan and final freeze audit:** repeat complete risk review,
   parity/package/safety gates, zero-provider boundary, and human inspection.

Each phase is independently commit-eligible. The exact smallest next
implementation unit is Phase 1 only: pure identity-signature and signed-evidence
contracts plus golden cases, with no production call-site integration.

## Demo implication and remaining risks

The four R12 D labels are substantiated, not overturned. The current full-real
detector must not be frozen or presented as CEO-demo-ready, and false groups
must not be hidden or excluded from demo data. The synthetic showable path and
real executable path remain distinct from a frozen real demo candidate.

Remaining risks are alias/model/role ambiguity, incomplete trusted-source rules,
single-character qualifier handling, typed attribute normalization, legitimate
different-part-number duplicates, review-state compatibility, and the large
blast radius demonstrated by CF6. GF-12A2 human labels are still required to
measure precision/recall. GF-11 remains in progress under its active waiver,
`GF11-PERF-100K-COLD-FULL` remains open, the 300-second target remains unmet,
and deployment/integration remains deferred.
