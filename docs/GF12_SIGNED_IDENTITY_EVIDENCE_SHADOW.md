# GF-12C1-R16 signed identity evidence shadow

## Scope and decision

R16 adds pure, non-authoritative comparison from two R15 `IdentitySignature`
values to R14 `SignedIdentityEvidence`, version
`signed-identity-comparison-v1`. It is used only by tests and offline audit
tooling. It does not emit or change GF4/GF5 classes, scores, thresholds,
statuses, persistence, review, exports, or providers.

The result is `R16_SIGNED_EVIDENCE_VERIFIED_BUT_GATE_NOT_READY`. Historical
protected conflicts and the four R12 lexical-only cases are represented safely,
but several legitimate named controls still lack trusted identity facts. A
future support gate would therefore overcorrect.

## Channel and source rules

- `IDENTITY_SUPPORT` requires equal recognized object/construct, identity-role,
  or explicit type/grade facts and a non-generic, non-copied source on each side.
- `ATTRIBUTE_SUPPORT` records equal bounded variant or critical-attribute facts;
  it does not prove physical identity.
- `LEXICAL_SUPPORT` records equal unresolved facts, structural model overlap,
  copied/generic token overlap (bounded to four), and recognized facts supported
  only by copied/generic sources. No fuzzy threshold is used.
- `IDENTITY_CONTRADICTION` reuses the existing bounded object/construct
  incompatibilities, mutually exclusive tyre variants, and opposite directional
  sides with a shared bounded component base.

Structural alphanumeric models are deliberately lexical because they may be a
family prefix. Unknown/unknown, known/unknown, missing categories, different
part numbers, different residuals, and single-character qualifier differences
do not create contradiction. Equal unresolved evidence is lexical only;
different unresolved evidence is not forced into a channel.

Facts preserve source fields, normalized evidence, signature versions and
fingerprints, and reason codes. There is no global trust score. Copied recognized
facts remain visible but cannot independently establish identity support.

## Canonicalization and diagnostic buckets

R14 canonical endpoint, fact, and source ordering makes A/B orientation and
fingerprints stable. Shadow buckets are diagnostic labels only:

```text
SHADOW_TRUSTED_IDENTITY_PRESENT
SHADOW_LEXICAL_ONLY_OR_UNRESOLVED
SHADOW_EXPLICIT_CONTRADICTION
SHADOW_MIXED_EVIDENCE
SHADOW_INSUFFICIENT
```

Contradiction with other evidence is mixed; contradiction alone is explicit;
otherwise trusted identity wins, then lexical-only, then insufficient.

## Historical, positive, and metamorphic tests

H1-H9—carbon-stick/pencil, rim/tyre, table/nail, condition/discount,
clutch-disk/dust-cap, clutch-disk/coil-spring, dust-cap/coil-spring, left/right
shock, and buffer/mirror—emit existing protected contradictions. H10-H13 emit
lexical/attribute evidence without identity support or invented contradiction.

P1-P14 all avoid invented contradiction. Current canonical object aliases,
cross-site aliases, missing-description aliases, and copied-description aliases
retain trusted part-number identity. The false-negative watchlist is:

| Control | Shadow classification |
|---|---|
| Contact Cleaner | `LEXICAL_ONLY_RISK` |
| Turbine Lubricating Oil | `LEXICAL_ONLY_RISK` |
| Francis Turbine Lower Bearing | `LEXICAL_ONLY_RISK` |
| Pump X500 | `LEXICAL_ONLY_RISK` |
| Fan Blade | `LEXICAL_ONLY_RISK` |
| F30 | `LEXICAL_ONLY_RISK` |
| B38 | `LEXICAL_ONLY_RISK` |
| aliases | `SUFFICIENT_TRUSTED_EVIDENCE` |
| cross-site same identity | `SUFFICIENT_TRUSTED_EVIDENCE` |
| bounded aliases with different part numbers | `SUFFICIENT_TRUSTED_EVIDENCE` |
| bounded alias with missing description | `SUFFICIENT_TRUSTED_EVIDENCE` |

The first seven lack a currently trusted canonical object/role or exact model
fact. R16 does not repair that gap. M1-M12 verify orientation, construction
order, signature order, repeatability, reference-independent semantic facts,
unknown and residual safety, copied lexical separation, site independence,
protected conflict preservation, and safe attribute differences.

## Real accepted-edge shadow audit

The pair source was the read-only R12 Group Data workbook: all complete-pair
edges within its 205 accepted groups. Records came from the hash-verified CSV;
signatures were cached by stable reference and current GF4 class was recomputed
offline with the unchanged evaluator. No database, normal scan, provider, or
global all-pairs generation was used.

| Metric | Result |
|---|---:|
| real accepted-group pairs | 252 |
| trusted identity present | 12 |
| lexical only/unresolved | 240 |
| explicit contradiction | 0 |
| mixed evidence | 0 |
| insufficient | 0 |
| current strong shadow lexical-only | 142 |
| current review shadow lexical-only | 98 |
| accepted-group edges shadow lexical-only | 240 |
| cannot-link pairs in accepted source | 0 |

The accepted artifact contains no cannot-link edges. Preservation is established
by H1-H9 plus existing R7/R9/R10/R11 regressions.

## Mandatory R12 pairs

| Pair | Identity | Attribute | Lexical | Contradiction | Bucket |
|---|---:|---:|---:|---:|---|
| brush / paint | 0 | 1 | 4 | 0 | `SHADOW_LEXICAL_ONLY_OR_UNRESOLVED` |
| Model S / Model X | 0 | 0 | 6 | 0 | `SHADOW_LEXICAL_ONLY_OR_UNRESOLVED` |
| wood / steel-frame | 0 | 0 | 5 | 0 | `SHADOW_LEXICAL_ONLY_OR_UNRESOLVED` |
| coil-spring / staplers | 0 | 0 | 6 | 0 | `SHADOW_LEXICAL_ONLY_OR_UNRESOLVED` |

Brush/paint shares copied `Exercise 3`, attribute `3`, and unresolved `xx`.
Model S/X shares copied text, unresolved prefixes, and structural `ne01`, which
stays lexical. Wood/steel-frame shares copied test text and `ns`. Coil/staplers
shares copied coil text, structural `auto01`, and unresolved prefixes; the coil
class is trusted on only one side. None receives misleading identity support.

## Performance, isolation, and next unit

The 252 comparisons consumed 1.081872 seconds of comparator time: 232.930
pairs/second. Total audit wall time was 3.226313 seconds. Work is O(bounded
signature facts) per supplied pair; no O(N²) corpus pass occurred.

Production imports are limited to offline benchmark modules. GF1-GF6, current
GF4, GF5, APIs, persistence, exports, and frontend do not consume shadow facts.

Do not add a GF4 shadow decision gate yet. The smallest next unit is a bounded
representation/evidence study for the seven named legitimate controls in golden
and offline shadow mode, without making copied text or structural family
prefixes authoritative.
