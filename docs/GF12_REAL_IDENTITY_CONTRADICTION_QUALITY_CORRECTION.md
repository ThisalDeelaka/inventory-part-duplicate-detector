# GF-12C1-R7 deterministic identity-contradiction quality correction

## Scope and decision

R6 proved three deterministic false review groups in the authoritative real
G2-v2 output. R7 corrects only the GF4 signed-evidence boundary that allowed
explicitly different physical object classes or mutually exclusive tyre
variants to remain support edges. Candidate retrieval remains free to retrieve
related items. The existing GF5 resolver consumes the corrected `CANNOT_LINK`
edges without any threshold, status, cap, group-size, or review-authority
change.

The fresh result is `Q1_DEMO_QUALITY_PLAUSIBLE`. This is an offline engineering
canary result, not human-validated accuracy. GF-12A2 remains
`HUMAN_REVIEW_DATASET_REQUIRED`.

## Frozen pre-correction evidence and root cause

Scan 27 was completed current-product G2-v2 authority. Its three false groups
were reproduced through the pre-discriminator scorer and persisted snapshot:

- **C5:** AT, slick, and snow 205/70/15 tyres formed one three-member review
  group. Pair evidence was one `STRONG_SUPPORT` and two `REVIEW_SUPPORT` edges,
  with no cannot-link. Explicit subtype lived in part numbers while the shared
  dimension dominated descriptions. Root causes: F2, F3, F6, F7, and F9.
- **C6:** wheel and tyre formed one two-member review group with one
  `REVIEW_SUPPORT`, zero strong, and zero cannot-link edges. Root causes: F1,
  F3, F7, and F9.
- **C7:** carbon-stick and pencil formed one two-member review group with one
  `REVIEW_SUPPORT`, zero strong, and zero cannot-link edges. Their copied
  carbon-stick description hid the part-number noun conflict, while G versus
  PCS remained non-authoritative UOM context. Root causes: F1, F3, F4, F5, F7,
  and F9.

There was no GF5 propagation defect: GF4 contained no protected contradiction
for these endpoints. Existing GF5 tests already proved that any persisted
cannot-link vetoes a whole group.

## Selected fix and discriminator contract

R7 uses FIX-B, FIX-C, and the bounded composite FIX-D. The versioned
`identity-discriminator-v1` is a pure, record-local and pair-local GF4 input. It
extracts a small controlled vocabulary from normalized part number and
description:

- physical classes: tyre/tire, wheel, carbon stick, and pencil;
- explicit tyre variants: all-terrain/AT, slick, and snow.

The contract is conservative:

1. Known-versus-unknown is never a contradiction.
2. Two known classes conflict only for documented incompatible class pairs.
3. Tyre variants conflict only when both records explicitly identify exactly
   one different mutually exclusive variant.
4. A copied-description composite conflict requires a trusted class on one
   record, an incompatible explicit part-number class on the other, the copied
   trusted class in that other description, and an independently different UOM
   dimension/basis.
5. UOM mismatch alone never creates cannot-link.
6. Different part numbers alone never create cannot-link.

The result is appended to existing GF4 `protected_conflicts_json`; the existing
classifier emits `CRITICAL_MISMATCH_IDENTITY_OBJECT_CLASS` or
`CRITICAL_MISMATCH_MUTUALLY_EXCLUSIVE_TYRE_VARIANT`. Full discriminator inputs,
resolved values, source provenance, UOM relationship, version, and conflict
count are persisted in `technical_evidence_json`. No new schema was required.

This is general semantic vocabulary rather than demo-specific logic.
Production code contains no scan ID, group ID, source row, input filename, or
exact real part number. Literal fixture examples occur only in tests.

## Negative and positive controls

N1–N9 pass: mutually exclusive same-dimension variants; wheel versus tyre;
assembly versus component; rotor versus stator; copied description with
part-number object conflict; copied description plus incompatible UOM context;
generic noun only; generic dimension only at the discriminator boundary; and
an A-B/B-C support bridge with an A-C protected contradiction. The final case
cannot form one three-member group.

P1–P10 pass without cannot-link: spelling/case/punctuation variants; different
part numbers for the same item; permitted cross-site identity; one missing UOM;
legitimate UOM ambiguity; contact-cleaner-like records; Francis-turbine-lower-
bearing-like records; fan-blade-like records; corresponding B38 pairs; and
accounting/governance differences. Tyre/tire spelling and AT/all-terrain
synonyms with the same variant also remain compatible.

Three repeated focused evaluations produce identical GF4 evidence, conflict
decisions, provenance, and fingerprints. Existing GF5 contracts and all status
thresholds remain byte-for-byte unchanged.

## Fresh real current-product scan

The unchanged 3,265,800-byte real CSV retained SHA-256
`8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
The browser-equivalent request used threshold 75, `CONTRACT` and `UNIT_MEAS`,
empty explicit mapping, sensitive mode, same-site scope, and
`product_authority=current_product`. Both provider families were disabled.

Scan 29 completed in 449.346238 seconds. It persisted policy
`group-first-orchestration-policy-v2`, mode `group_first_primary`, pipeline
`GROUP_FIRST_GF1_GF6`, visible projection `G2_V2`, compatibility false, and
both readiness flags true.

| Stage | Fresh evidence | Runtime seconds |
|---|---|---:|
| GF1 | 5,327 records | 2.269152 stage |
| GF2/GF3 | 20,397 proposals; 1,288 neighborhoods; 4,039 records without proposals | 68.909598 run / 70.408900 stage |
| GF4 | 20,397 edges: 268 strong, 951 review, 118 cannot-link, 19,060 non-groupable | 20.076833 run / 24.864959 stage |
| GF5 | 241 work units; 206 groups; 24 conflicts; 31 deferred; 4,890 unassigned | 300.525876 run / 316.463995 stage |
| GF6 | 206 groups: 113 likely and 93 review | 8.060832 run / 23.808396 stage |

GF5 made 38 targeted requests/results, explored 212,060 candidate partitions,
and made zero provider requests. The IdentityRead fingerprint is
`d702163d622f3214044ee3c5c38f8527827f9c836a50c074c0f1b7faf61b9572`.

## Exact canary re-audit

- **C1 — INSUFFICIENT_DATA:** five contact-cleaner records remain in the same
  115-member capped deferred unit; one malformed-UOM record is unassigned.
- **C2 — INSUFFICIENT_DATA:** four turbine-oil records remain capped/deferred;
  the PCS record remains in a protected conflict.
- **C3 — INSUFFICIENT_DATA:** all six Francis lower-bearing records remain in
  the same capped deferred unit.
- **C4 — INSUFFICIENT_DATA:** the three X500 pump records remain split across
  115- and 46-member capped deferred units.
- **C5 — SAFELY_SEPARATED:** AT, slick, and snow variants are now a protected
  conflict and no longer form a group.
- **C6 — SAFELY_SEPARATED:** wheel and tyre are now a protected conflict and no
  longer form a group.
- **C7 — SAFELY_SEPARATED:** carbon-stick and pencil are now a protected
  composite conflict; the other carbon-stick matches remain unassigned.
- **C8 — SAFELY_SEPARATED:** F30 engine, chamber, compressor, rotor, stator,
  and injector remain six corresponding two-record likely groups.
- **C9 — SAFELY_SEPARATED:** B38 engine, head, block, fuel pump, and pistons
  remain five corresponding two-record likely groups.
- **C10 — INSUFFICIENT_DATA:** MLR top/component remains a protected conflict;
  circuit-board records are capped/deferred or unassigned, so no broader board
  identity conclusion is justified.

C1–C4 safety caps were not changed.

## Broader changed-group audit

The new mechanism produced 15 protected GF4 edges: 12 object-class and three
tyre-variant contradictions. A bounded review confirmed they are explicit
wheel/tyre, tyre-variant, or carbon-stick/pencil cases. No scan-29 accepted or
review group contains any new discriminator contradiction.

Relative to scan 27, 200 membership sets and statuses are unchanged, seven old
membership sets are absent, and six new sets appear. Exactly three old groups
contain the new discriminator contradiction: C5, C6, and C7, representing seven
members in those false groups. Aggregate result deltas are one fewer group,
three fewer grouped members, five more conflicts, unchanged deferred count, and
three more unassigned records.

Discovery produced 20,397 proposals and 1,288 rather than 1,285
neighborhoods, even though R7 changed no discovery code. Therefore the complete
seven-old/six-new membership-set delta cannot truthfully be attributed solely
to the new GF4 mechanism. A bounded inspection of all changed sets found no additional
high-confidence physical contradiction; generic tracking, service,
manufacturing, and accounting-like examples remain domain-ambiguous and do not
authorize another rule.

## Export parity and performance

Scan-29 IdentityRead API, System Group CSV, and XLSX contain the same 206 group
keys, statuses, stable references, and 437 member rows. XLSX Summary reports
scan 29 and G2-v2. Group Data retains one table AutoFilter, zero worksheet
AutoFilters, and table range `A1:T438`. The disposable workbook is:

`C:\Users\THISAL~1\AppData\Local\Temp\scan-29-system-groups-G2V2-corrected.xlsx`

Nine thousand focused old-versus-new evaluations measured approximately
307 microseconds of discriminator overhead per edge. On the real scan, GF4 run
time increased from 15.885954 to 20.076833 seconds (+4.190879 seconds), while
total wall time increased from 315.779825 to 449.346238 seconds. Discovery and
GF5 also varied despite being unchanged, so the entire wall delta is not
attributed to R7. The bounded discriminator adds no global O(N^2) pass,
provider call, or unbounded ontology lookup.

Focused verification passed 95 tests. The complete backend suite passed 1,471
tests with 15 skipped and one existing pytest configuration warning.

## Remaining boundaries

R7 adds no schema, migration, dependency, frontend, export, review, provider,
deployment, IAM, tenancy, or integration change. It does not claim precision,
recall, human-validated quality, GF-12 production graduation, 100k readiness,
or deployment readiness. GF-11 remains in progress under its active waiver,
`GF11-PERF-100K-COLD-FULL` remains open, and the 300-second target remains not
met. The fresh workbook requires product-owner manual inspection before it is
frozen as the demo candidate.
