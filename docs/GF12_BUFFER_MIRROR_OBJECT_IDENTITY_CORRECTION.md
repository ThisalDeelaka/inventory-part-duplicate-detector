# GF-12C1-R11 Buffer/Mirror Object-Identity Correction

## Scope and pre-fix evidence

R11 addresses only the proven copied-description object-identity family. In the
real 5,327-row input, source rows 1511 and 1512 contain `LG - MIRROR01` and
`LG - BUFFER01`. Both have description and master description
`Seria/condition part`, UOM `pcs`, part type `Purchased`, site `IF88`, and no
type designation or dimension/quality. Their normalized part numbers are
`lg mirror 01` and `lg buffer 01`; their normalized descriptions are identical.

A controlled pre-fix run through the normal current-product path reproduced a
90.0 `STRONG_SUPPORT` edge with `DETERMINISTIC_LIKELY_DUPLICATE`, no protected
conflict, and one accepted likely group containing both records. The generic
description guard did not flag the three-token copied text, and the v3
discriminator extracted no object class, construct, or directional variant.

## Root cause and architecture decision

The classified causes are `R11-F1_OBJECT_CLASS_COVERAGE_GAP`,
`R11-F2_TRUSTED_PART_NUMBER_OBJECT_TOKEN_NOT_USED`,
`R11-F3_COPIED_DESCRIPTION_OVERWEIGHTED`. The existing bounded contradiction
contract was sufficient once the missing classes were recognized. Nothing
fired and was lost at GF4, so R11-F7 does not apply. Genericity alone is not
the primary cause: the existing guard reasonably did not classify this phrase
as generic.

R11 selects **Strategy A — bounded class coverage**. Buffer and mirror are
explicit, reusable physical-component nouns that fit the existing bounded
object-class taxonomy. The selected semantic contract is:

```text
both records expose recognized object identities from explicit source evidence
and those identities are an explicitly registered incompatible class pair
=> emit a protected object-class contradiction
```

Different strings or arbitrary part-number tokens are never sufficient.
Known-versus-unknown remains non-conflicting, as do aliases of one class. The
description reliability is recorded as context; copied text cannot erase an
explicit two-sided contradiction, but copied or generic text alone cannot
create one.

## Anti-one-off-patch analysis

Production adds exactly two class entries (`buffer`, `mirror`) and one explicit
bounded incompatibility relation. Each entry uses token-boundary singular/plural
matching and applies independently of prefix, suffix, row, scan, group, or
filename. No `BUFFER01`, `MIRROR01`, row number, scan number, group suffix, or
source filename is present in production. The fresh real scan independently
found the same semantic family at rows 2661/2664 (`CS-MIRROR-1` and
`CS-BUFFER-1`), demonstrating reuse beyond the reported pair. This remains
bounded semantic coverage, not `different token => cannot-link`.

## Implementation and provenance

`identity-discriminator-v4` adds the two bounded classes, their explicit
incompatibility, normalized match capture, source-field capture, and description
reliability context. A resulting protected conflict records canonical class
values, source fields, matched normalized evidence,
`BOUNDED_OBJECT_CLASS_INCOMPATIBILITY`,
`EXPLICIT_TWO_SIDED_OBJECT_CLASS`, and deterministic GF4 evidence. The canonical
evaluator version advances to v5. Existing persistence fields are reused; no
schema or migration changes are required.

## Fixture and regression verification

The 29-test R11 suite covers N1-N4 explicit known incompatibilities and the
three-member bridge as protected. N5-N10 preserve known-versus-unknown,
arbitrary token differences, compatible aliases, prefix/suffix differences,
description typo/copy without a class contradiction, and UOM-only differences.
P1-P12 preserve legitimate different part numbers, compatible aliases,
cross-site/missing-UOM cases, Contact Cleaner, Francis Turbine Lower Bearing,
Fan Blade, F30, B38, same-side controls, legitimate model/token differences,
and accounting-only differences. All R7 tyre, wheel/tyre, and
carbon-stick/pencil controls; all R9 rim/tyre, table/nail,
condition/discount, and mechanical-component controls; and the R10 LEFT/RIGHT
shock control pass. The bridge fixture confirms A-B and B-C support cannot
merge A+B+C when A-C has the protected contradiction.

Focused R7/R9/R10/R11 execution passed 107 tests. The full backend passed
1,553 tests with 15 skipped and no failures; the sole warning is the existing
unknown pytest asyncio configuration option.

## Fresh real current-product verification

Disposable scan 2 used the browser-equivalent upload path with
`product_authority=current_product`, policy v2, `group_first_primary`, and
G2_V2. It completed in 717.115631 seconds with `visible_product_ready=true` and
zero provider requests.

```text
GF2 proposals:                 20,394
GF3 neighborhoods:              1,282
GF4 strong/review/cannot/non: 264 / 940 / 142 / 19,048
GF5 work units:                   238
GF5 candidate partitions:     210,662
GF6 groups:                       201
likely/review:                112 / 89
conflicts/deferred:            31 / 30
unassigned:                      4,904
resolution fingerprint: e433a2ac4d0134113854c4118d1d1ac405758ee83884058e7d592196b2a2e324
manifest fingerprint:   966c40a1db03f7ff3f51dae536c9a3221524613827fac2535461ee6f768c039a
```

The target becomes a 90.0 GF4 `CANNOT_LINK` with reason
`CRITICAL_MISMATCH_IDENTITY_OBJECT_CLASS`, class values/matches
`mirror`/`buffer`, PART_NUMBER provenance on both sides, and description
reliability `IDENTICAL_NON_OBJECT_BEARING_TEXT`. It is absent from accepted
groups and present in a protected conflict: `SAFELY_SEPARATED`.

The complete accepted-group sweep found zero persisted internal cannot-link
pairs and zero direct discriminator contradictions. The R11 mechanism created
two real GF4 protected edges: the target LG pair and the independent CS pair.

## Semantic, watchlist, export, and performance audits

The exact deterministic selection method produced 46 unique groups: 10 likely
size-2, 10 review size-2, up to 20 size-3-or-more, and 10 evenly spaced groups,
deduplicated. Classification was A=4, B=13, C=28, D=0, E=1. No distinct D
family remains; the E case remains insufficient for a false-group conclusion.
This is not a claim of human-validated accuracy.

Canonical membership comparison found 198 common memberships with no status
changes, eight pre-fix-only memberships, and three post-fix-only memberships.
The target membership is the only removed membership directly attributable to
R11. The other differences originate before GF4 (20,396 versus 20,394 proposals
and 1,286 versus 1,282 neighborhoods across scan-local stable identities); the
discovery fingerprint is unchanged, and none contains a new R11 edge. The R11
semantic sweep is therefore bounded to two explicit buffer/mirror edges and
does not overcorrect the weak-review watchlist.

IdentityRead, System Group CSV, and XLSX agree exactly for scan 2: G2_V2, 201
groups, 423 members, identical canonical keys and stable member references.
Both exports return 200. The 158,785-byte XLSX archive is valid, has one
table-owned filter, no worksheet filter, 1,206 non-overlapping merged ranges,
and no corrupt archive member.

A 20,000-evaluation, five-repeat microbenchmark measured 283.821 microseconds
per R11 conflict edge and 213.747 microseconds per comparable unknown-token
edge, an incremental 70.074 microseconds per fired edge. Fresh GF4 took
60.479749 seconds and full wall time was 717.115631 seconds, below the
900-second task budget. No all-pairs semantic pass, ontology traversal,
external NLP, LLM, or provider decision was added.

## Classification and remaining boundaries

The architecture stop condition is not reached: two reusable bounded classes
and one relation corrected two real instances, arbitrary token differences
remain safe, and the repeated audit has D=0. Classification is
`R11_QUALITY_PASS_READY_FOR_FINAL_FREEZE`.

GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`. GF-11 remains `IN PROGRESS`,
its waiver remains `ACTIVE`, `GF11-PERF-100K-COLD-FULL` remains `OPEN`, and the
300-second target remains not met. Deployment/integration remains deferred.
R11 changes no global threshold, retrieval rule, GF5 cap, group-size limit,
status, review authority, export authority, schema, migration, dependency, or
frontend behavior.
