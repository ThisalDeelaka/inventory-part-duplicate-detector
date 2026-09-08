# GF-12C1-R17 trusted identity coverage gap study

## Trigger, scope, and outcome

R16 produced trusted identity on only 12 of 252 accepted-group edges and left
seven established positive controls lexical-only. R17 reconstructs those exact
real records, evaluates six bounded offline strategies, and changes no runtime
source or detector behavior.

The selected outcome is `R17-G_NO_SAFE_GENERALIZATION_PROVEN`. Strategies C
and E are narrower but do not cover the controls. Strategy F covers all seven
and avoids the four named R12 pairs, yet its 55 real-edge promotions include 12
explicit numeric-variant risks and 37 cases that remain plausible or
insufficient rather than trusted. A production representation correction is
therefore not authorized without human-labelled identity evidence.

## Exact real-control reconstruction

All rows are zero-based CSV source-row indexes from the immutable protected
file. Stable references are the R12 scan-1 canonical record references. Type
designation and dimension/quality are empty for every row; description and
master description normalize identically, so R15 records copied-description
provenance on every description observation.

| Control | Exact rows, stable refs, and source values | Existing signature and R16 cause | Current context |
|---|---|---|---|
| Contact Cleaner | 5194 `CB-CC`, 5195 `AP-CONTACT-CLEANER`; refs `abfe139e...82ea`, `03bfe588...e71a`; `Contact Cleaner (can)`, PCS/Purchased/site 10 | No recognized object/model/role; phrase and PN abbreviation remain unresolved; 6 lexical facts | current edge `REVIEW_SUPPORT`; family capped/deferred with one malformed-UOM row unassigned |
| Turbine Lubricating Oil | 5246 `AP-LUBE-OIL-ISO068`, 5263 `SP-LUBE-OIL-ISO068`; refs `a66d3f8c...b6a1`, `85f6c30b...7cc2`; exact oil description, litre/Purchased/site 10 | `iso068` model and typed oil function are extracted; structural model is lexical under R16 and copied sources cannot independently establish identity; 1 attribute + 9 lexical | current edge `STRONG_SUPPORT`; family capped/deferred; a separate PCS record is protected |
| Francis Turbine Lower Bearing | 5262 `AP-BRG-FR-22`, 5283 `CB-BRG-FR-22`; refs `879ed8c6...b456`, `ed70f060...4707`; exact phrase, PCS/Purchased/site 10 | Phrase/role is unresolved; suffix 22 is attribute only; 1 attribute + 10 lexical | current edge `STRONG_SUPPORT`; family capped/deferred |
| Pump X500 | 5294/5295 `X500`; refs `609c0b1c...50be`, `c9528c8e...18aa`; `Pump Model X500`, PCS/Purchased, sites 10/AG-10 | `x500` is extracted from PN and copied descriptions, but structural-model equality is deliberately lexical; 8 lexical | current edge `NON_GROUPABLE`; family split across deferred units |
| Fan Blade | 2306 `KM-FB`, 2385 `KM/FANBLADE`; refs `6a5f5447...6b73`, `fefd8403...4f55`; exact phrase, PCS/Manufactured/K-MRO | Compound head and FB alias remain unresolved; 5 lexical | current `STRONG_SUPPORT`; R12 likely group DG-000176 |
| F30 | 2526 `AS-COM-ROT`, 3045 `KA/ASCOMROT1`; refs `75d5bf1a...677d`, `e4c701eb...c16`; `F30 Engine Compressor Rotor`, PCS/Manufactured/MRO | `f30` model and rotor role are extracted from copied descriptions; R16 does not trust that source combination; 9 lexical | current `STRONG_SUPPORT`; R12 likely group DG-000128 |
| B38 | 5126 `AS-B38-H`, 5131 `ES/AS-B38-H`; refs `ecb2d4e7...1cc3`, `d63afacb...22f`; `B38 Engine Head`, PCS/Manufactured/MRO | `b38` has trusted PN provenance and head role is extracted from copied text, but R16 has no safe tuple rule; 9 lexical | current `STRONG_SUPPORT`; R12 likely group DG-000049 |

The human-visible signal is exact item phrase plus corroborating PN
abbreviation/stem for Contact Cleaner, Francis Bearing, and Fan Blade; exact
structured model/function or role tuples for the other four. The first three
signals are not represented semantically. The latter four are represented but
R16 correctly refuses the unproven trust composition.

## Failure classifications and shared patterns

| Code | Count | Controls |
|---|---:|---|
| C1 object phrase not represented | 3 | Contact Cleaner, Francis Bearing, Fan Blade |
| C2 model/type not represented | 0 | none; relevant models are represented where present |
| C3 PN structure not represented | 3 | Contact Cleaner, Francis Bearing, Fan Blade |
| C4 recognized fact marked non-trusted | 4 | Oil, Pump X500, F30, B38 |
| C5 alias equivalence not represented | 1 | Fan Blade |
| C6 compound head not represented | 3 | Contact Cleaner, Francis Bearing, Fan Blade |
| C7 source reliability too conservative | 7 | all descriptions equal master descriptions |
| C8 signed-evidence match rule too narrow | 4 | Oil, Pump X500, F30, B38 |
| C9 control not safe as trusted identity | 0 | established controls remain plausible, but are not human ground truth |
| C10 other | 0 | none |

All seven have exact bounded multi-token descriptions. Six have a reusable
compound head; four already have a structural model/typed corroborator; three
have equal structured PN stems; three need phrase/abbreviation representation.
Thus H (fact exists but comparator refuses it) covers four and I (fact never
captured) covers three. There is no single safe common rule: exact text is also
the failure mechanism in R12.

## Candidate strategies and guard results

| Strategy | Seven gained | R12 pairs incorrectly gained | Real promotions | Result |
|---|---:|---:|---:|---|
| A bounded identity phrase | 7 | 1 (coil/staplers) | 86 | rejected: 31 numeric-variant risks |
| B source-qualified exact span | 7 | 4 | 151 | rejected: copied exact text repeats the R12 defect |
| C structured PN semantic stem | 3 | 0 | 24 | insufficient coverage; 19 promotions lack enough evidence |
| D compound head | 6 | 1 (coil/staplers) | 84 | rejected: 32 numeric-variant risks |
| E comparator trust refinement | 4 | 0 | 8 | insufficient coverage; two numeric-variant risks |
| F combined bounded representation | 7 | 0 | 55 | rejected: 12 unsafe, 13 plausible-only, 24 insufficient |

H1-H9 protected historical contradictions remain unchanged because the study
does not construct runtime evidence. R16 H10-H13 and all four exact R12 guards
remain without trusted identity under F. Existing aliases, cross-site identity,
different-part-number aliases, missing descriptions, copied-description cases,
and attribute-difference controls remain unchanged and non-contradictory.

## Real-edge promotion audit

The audit reuses all 252 complete-pair edges inside the 205 accepted R12 groups.
Baseline is 12 trusted and 240 lexical-only. F would produce 67 trusted and 185
lexical-only, adding 55 promotions. Because 55 is at most 100, every promotion
was inspected deterministically:

| Inspection label | Count |
|---|---:|
| `SAFE_TRUSTED_IDENTITY` | 6 |
| `PLAUSIBLE_BUT_NOT_TRUSTED` | 13 |
| `UNSAFE_PROMOTION` | 12 |
| `INSUFFICIENT_DATA` | 24 |

Unsafe examples include `DUWE PART 1`/`PART 3`, `RDEW-COM-3`/`-4`, three
`RDEW-COM1/2/3` combinations, `NAS-REPL1`/`REPL2`, three `AM INV COM1/2/3`
combinations, dated MLR variants, and two model-number pairs whose shared
typed/copy evidence does not justify ignoring their different numeric identity.
These are architecture counterexamples, not measured false-positive rates.

Repeated runs produced identical counts. Observed audit wall times were
3.629094 and 3.735686 seconds; the earlier complete labelled run was 6.579908
seconds. Provider/network calls were zero, no global all-pairs set was created,
and no normal G2-v2 scan ran.

## Decision, risks, and next boundary

Phrase/span strategies have unacceptable false-positive risk from copied text
and lost qualifiers. Stem/model strategies leave false-negative risk for
abbreviations and phrases and still cannot establish trust without labels.
Combining them increases coverage but does not establish safety.

The smallest next action is not a code seam. Obtain a representative,
independently human-labelled identity/non-identity edge set covering phrase,
abbreviation, structured-model, copied-description, and explicit-variant cases;
then repeat A-F offline. R17 authorizes no R15/R16 change and no GF4 shadow or
runtime integration. The detector remains unfrozen, the R12 freeze remains a
quality failure, and CEO-demo readiness is not claimed.
