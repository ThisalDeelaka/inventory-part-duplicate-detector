# GF-12 Corrected Canonical Quality Baseline

> **SYNTHETIC/CANONICAL OFFLINE QUALITY BASELINE**
>
> **NOT FINAL HUMAN-REVIEWED PRODUCTION QUALITY SIGNOFF**

## Baseline identity

All runs used corpus `group-first-scale-corpus-v1`, corrected truth
`group-first-scale-truth-v2`, evaluation `gf12-group-quality-v1`, seed 1101,
provider none, policy-v2 `group_first_primary`, and a unique disposable SQLite
database. Every production run completed, every truth-integrity gate passed,
and provider calls were zero.

The historical 50k truth-v1 annotation `cross-site-3755308: (31249,)` is not
used. Truth v2 retains the production record and S5 label but omits that
incomplete positive family, as documented in
`GF12_CANONICAL_TRUTH_INTEGRITY_CORRECTION.md`.

No GQ acceptance threshold exists:

```text
THRESHOLD NOT YET AUTHORIZED
```

The measured quality values are evidence for later human-reviewed validation,
not a synthetic-data production-quality graduation.

## Result identity and primary group metrics

`N/A` denotes an undefined zero-denominator ratio.

| Records | Product fingerprint | Evaluation fingerprint | Predicted / truth groups | GQ1 exact precision | GQ2 exact recall | GQ3 F1 | GQ4 member coverage | GQ5 split | GQ6 merge | GQ7 missed | GQ8 spurious |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | `4de337f7b65f219a5d60178d1df966e3da83374382ce37c432e5290264d60713` | `8082dd8f67a39283a7a27f711ace6548f16f54774d358508cf61b4a53e2e549c` | 0 / 60 | N/A (0/0) | 0 (0/60) | N/A | 0 (0/167) | 0 | 0 | 60 | 0 |
| 5,000 | `55f3845d19b3ec4867169c2a50fe881c663a2ab439f2ef2a54eb71b56a161c63` | `f7a8ac64111d938a4b4996fdc5c889c2c9e00c65acde98d81eeca970baa86521` | 169 / 591 | 0.603550295858 (102/169) | 0.172588832487 (102/591) | 0.268421052631 | 0.122448979592 (204/1,666) | 0 | 0 | 422 | 67 |
| 20,000 | `f16f2fa5dca7ee441630ce955a5829c96a9012b4d6ce0cdef3ef8c7ebcc406ea` | `04ed03aeb27e540c09664a78770c38fb8cfd7bff2c00d11d321ba26824bf52d2` | 299 / 2,421 | 0.779264214047 (233/299) | 0.096241222635 (233/2,421) | 0.171323529411 | 0.069906990699 (466/6,666) | 0 | 0 | 2,126 | 66 |
| 50,000 | `51ea34b939809e3b916210d475411b5a087d761c37fcb196a41f30b01d32630f` | `8b4de97f238326ad2c155c423497a1f242b2c2885bfd88371736fd8b377f56f3` | 304 / 5,960 | 0.871710526316 (265/304) | 0.044463087248 (265/5,960) | 0.084610472541 | 0.031863186319 (531/16,665) | 0 | 0 | 5,660 | 39 |

Exact recall and member coverage decline with scale, and nearly all exact
recoveries are size-2 groups. This is material quality evidence for the next
human-reviewed unit. It is not hidden, and it is not compared with an invented
pass threshold.

## Pair diagnostics

These values are **DIAGNOSTIC ONLY — NOT PRIMARY PRODUCT QUALITY**.

| Records | Pair precision | Pair recall | Pair F1 |
| ---: | ---: | ---: | ---: |
| 500 | N/A (0/0) | 0 (0/178) | N/A |
| 5,000 | 0.557755775578 (169/303) | 0.092653508772 (169/1,824) | 0.158909261871 |
| 20,000 | 0.697399527187 (295/423) | 0.042287844037 (295/6,976) | 0.079740505474 |
| 50,000 | 0.803191489362 (302/376) | 0.016868681227 (302/17,903) | 0.033043383118 |

## Status-aware results

| Records | Likely predictions | Review predictions | Conflict outcomes | Deferred outcomes | Truth recovered likely | Truth recovered review | Truth conflict-only | Truth deferred-only | Completely missed | Unassigned records |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | 0 | 0 | 5 | 6 | 0 | 0 | 41 | 19 | 0 | 500 |
| 5,000 | 0 | 169 | 1 | 3 | 0 | 102 | 0 | 180 | 309 | 4,595 |
| 20,000 | 0 | 299 | 1 | 5 | 0 | 233 | 0 | 742 | 1,446 | 19,340 |
| 50,000 | 0 | 304 | 2 | 2 | 0 | 265 | 0 | 1,795 | 3,900 | 49,356 |

Conflict and deferred representation remains distinct from accepted-group
recovery. GQ7 includes every truth group without accepted/review recovery,
including cautious conflict/deferred representation.

## Group-size breakdown

Each cell is `exact / truth (exact recall); split; merge involvement`.

| Records | Size 2 | Size 3 | Size 4–5 | Size 6–10 | Size >10 |
| ---: | --- | --- | --- | --- | --- |
| 500 | 0/34 (0); 0; 0 | 0/8 (0); 0; 0 | 0/18 (0); 0; 0 | N/A | N/A |
| 5,000 | 102/322 (0.316770186335); 0; 0 | 0/104 (0); 0; 0 | 0/165 (0); 0; 0 | N/A | N/A |
| 20,000 | 233/1,347 (0.172976985895); 0; 0 | 0/481 (0); 0; 0 | 0/593 (0); 0; 0 | N/A | N/A |
| 50,000 | 264/3,224 (0.081885856079); 0; 0 | 1/1,171 (0.000853970965); 0; 0 | 0/1,565 (0); 0; 0 | N/A | N/A |

## Scenario breakdown

The generator's authoritative labels are S1 unique, S2 positive duplicate,
S3 generic description, S4 protected cannot-link, S5 cross-site duplicate,
S6 missing-value, S7 bridge/chained, and S8 repeated-family stress. Each cell
below is `records / positive truth / exact / conflict-or-deferred / completely
missed / protected cases / bridge cases`.

| Records | S1 | S2 | S3 | S4 |
| ---: | --- | --- | --- | --- |
| 500 | 63/0/0/0/0/0/0 | 63/19/0/19/0/0/0 | 63/0/0/0/0/0/0 | 63/0/0/0/0/31/0 |
| 5,000 | 625/0/0/0/0/0/0 | 625/179/0/179/0/0/0 | 625/0/0/0/0/0/0 | 625/0/0/0/0/312/0 |
| 20,000 | 2,500/0/0/0/0/0/0 | 2,500/738/0/738/0/0/0 | 2,500/0/0/0/0/0/0 | 2,500/0/0/0/0/1,250/0 |
| 50,000 | 6,250/0/0/0/0/0/0 | 6,250/1,794/0/1,794/0/0/0 | 6,250/0/0/0/0/0/0 | 6,250/0/0/0/0/3,125/0 |

| Records | S5 | S6 | S7 | S8 |
| ---: | --- | --- | --- | --- |
| 500 | 62/20/0/20/0/0/0 | 62/0/0/0/0/0/0 | 62/21/0/21/0/0/20 | 62/0/0/0/0/0/0 |
| 5,000 | 625/204/61/1/142/0/0 | 625/0/0/0/0/0/0 | 625/208/41/0/167/0/208 | 625/0/0/0/0/0/0 |
| 20,000 | 2,500/850/177/3/670/0/0 | 2,500/0/0/0/0/0/0 | 2,500/833/56/1/776/0/833 | 2,500/0/0/0/0/0/0 |
| 50,000 | 6,250/2,083/169/1/1,913/0/0 | 6,250/0/0/0/0/0/0 | 6,250/2,083/96/0/1,987/0/2,083 | 6,250/0/0/0/0/0/0 |

## Safety and truth integrity

| Records | Cannot-link accepted | Duplicate membership | Singleton accepted | Overlap membership | Cross-scan | Source mutation | Truth integrity |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 500 | 0 | 0 | 0 | 0 | 0 | N/A | PASS |
| 5,000 | 0 | 0 | 0 | 0 | 0 | N/A | PASS |
| 20,000 | 0 | 0 | 0 | 0 | 0 | N/A | PASS |
| 50,000 | 0 | 0 | 0 | 0 | 0 | N/A | PASS |

At every scale truth contained zero empty/singleton groups, unknown references,
duplicate IDs, illegal overlaps, and positive/cannot-link contradictions. Truth
group counts and size distributions reconcile with the correction evidence.

## 5k deterministic repeat

Three fresh production/evaluation runs produced byte-identical JSON with SHA-256
`14977b4e4c2f56d9a163c77cfaf3b100bbdc21ffc6303a2ad9b23fa6cca598c5`,
identical product fingerprint
`55f3845d19b3ec4867169c2a50fe881c663a2ab439f2ef2a54eb71b56a161c63`,
and identical evaluation fingerprint
`f7a8ac64111d938a4b4996fdc5c889c2c9e00c65acde98d81eeca970baa86521`.

## Decision boundary

GF-12A1 establishes trustworthy evaluation machinery and a corrected canonical
baseline. The safety, isolation, truth-integrity, determinism, and regression
gates pass. Numerically weak exact recall and member coverage remain explicit
evidence for a later authorized human-reviewed validation unit.

GF-11 remains IN PROGRESS, its bounded performance waiver remains ACTIVE,
`GF11-PERF-100K-COLD-FULL` remains OPEN, and the 300-second criterion remains
unchanged and unmet. GF-12 is STARTED; GF-12A1 is VERIFIED. GF-12 is not
complete, and final human-reviewed production-quality signoff is still pending.
