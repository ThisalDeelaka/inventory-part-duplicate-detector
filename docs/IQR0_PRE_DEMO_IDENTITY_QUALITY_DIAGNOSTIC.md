# IQR-0 Pre-Demo Identity Quality Diagnostic

## IQR-1A disposition of the discovery finding

The site-boundary finding is now corrected and verified for the current-product
Group-First path by IQR-1A. Scan 33 produces all 21 Bicycle relationships as
bounded `REVIEW_SUPPORT` evidence and sends the seven records to one deferred
GF5 work unit. Legacy scan modes remain unchanged. Head/Tail and copied/generic
text findings remain open. See
`docs/IQR1A_CROSS_SITE_DISCOVERY_BOUNDARY_CORRECTION.md`.

## Classification

`IQR0_MULTILAYER_DEFECT`

Scan 33 proves two independent first causal layers:

1. The Bicycle family is removed by a **discovery site boundary before candidate
   evidence exists**.
2. Head/Tail survives because the **identity-evidence vocabulary does not extract
   the functional/location distinction**, leaving similarity to become review
   support.

Neither outcome is caused by GF5 partitioning, G2 adaptation, API selection, or
XLSX visibility. No runtime behavior was changed in IQR-0.

## Baseline and corrected demo status

- Branch: `llm-assisted-mvp`.
- Starting HEAD: `4be9b7c5030fdf8cfa8f078eb221ae3aed18f839`.
- Protected tag: `deterministic-demo-v1` at
  `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Initial status: only `?? List_20260709_093045.xlsx`; nothing staged.
- The protected XLSX was not inspected, modified, or staged.
- Provider calls: 0. No `.env`, credential, token, or secret was accessed.
- PRM-5 remains historical workflow/presentation verification. External demo
  readiness is `BLOCKED_BY_IDENTITY_OUTPUT_QUALITY`; the showable-product
  baseline is preserved; pre-demo quality recovery is active; post-proof work is
  deferred.

## Scan 33 authority and metadata

The local persisted evidence is available and was read in SQLite read-only mode.

| Property | Persisted value |
|---|---|
| Scan | 33, `Inventory duplicate scan` |
| Scan status | `COMPLETED` |
| Records | 118 |
| Scan mode | `SAME_SITE_DUPLICATE` |
| Selected fields | `CONTRACT`, `UNIT_MEAS` |
| Orchestration | Run 10, `group_first_primary`, `COMPLETED` |
| Primary pipeline | `GROUP_FIRST_GF1_GF6` |
| Visible authority | `G2_V2`, visible-product-ready |
| Discovery | Run 10, `COMPLETED`, 1,103 proposals, 104 covered, 14 without proposals |
| Discovery degradation | `HYBRID_CAP_REACHED`; 64 truncated neighborhoods |
| Evidence | Run 9, 1,103 edges: 1 strong, 37 review, 20 cannot-link, 1,045 non-groupable |
| Resolution | Run 9, `COMPLETED`, provider requests 0 |
| G2-v2 | Run 9, `COMPLETED`, snapshot contract 2 |
| Product result | 3 Review groups, 0 Likely, 3 Conflicts, 2 Deferred, 111 unassigned |

The canonical identity reader independently selected `G2_V2` and returned the
same counts. There is no G2-v1 fallback.

## Bicycle canonical source records

The persisted canonical contract does not retain Master Description, Type
Designation, or Dimension/Quality. Those values are therefore recorded as
`UNAVAILABLE_IN_CANONICAL_SNAPSHOT`, not inferred. All seven records have no
persisted commodity, product-family/code, category, HSN/SAC, accounting-group,
or hazard identity value.

| Source row / record | Stable record reference | Part / description | Site | UOM / type | Normalized identity input |
|---|---|---|---|---|---|
| 72 / 53343 | `9cea077191548ba19b57ee7d47e9359051429d74753771d37b665c7183e7d1a3` | `AB-BICYCLE` / `Bicycle` | `AB-SA` | `PCS` / Purchased | `ab bicycle` / `bicycle` |
| 84 / 53355 | `f6b8e7d375de0250b7f841df967dd36a2c7025ca940978fb2805252e94c10351` | `SD-BICYCLE` / `Bicycle` | `SD-SA` | `PCS` / Purchased | `sd bicycle` / `bicycle` |
| 100 / 53371 | `7d1dcc156e860deb2d556dfe557a4fa35e5060e6f3f43095eb3a359869966faf` | `JS-BICYCLE` / `Bicycle` | `JS-SA` | `PCS` / Purchased | `js bicycle` / `bicycle` |
| 101 / 53372 | `7ac53dc1cc28a82f11019040b8fda783cdceef3075bdc6f4aa1dc330931ab016` | `TD BICYCLE` / `Bicycle` | `TD-SA` | `PCS` / Purchased | `td bicycle` / `bicycle` |
| 109 / 53380 | `29783c5419dd262c8f5fa61a8625332b39bd7ca5bd6258be5e19a394032c8ebd` | `HM-BICYCLE` / `Bicycle` | `HM-SA` | `PCS` / Purchased | `hm bicycle` / `bicycle` |
| 110 / 53381 | `321b07f80f5f7124f778ea65899f29cd5fcd7658dd2849c27161687776b39f86` | `SJ-BICYCLE` / `Bicycle` | `SJ-SA` | `PCS` / Purchased | `sj bicycle` / `bicycle` |
| 112 / 53383 | `ec3b6ee0f5d36d28c0d17c6054a3feb3a0454f725b56201ed425419fe0e7a1a9` | `UH-BICYCLE` / `Bicycle` | `UH-SA` | `PCS` / Purchased | `uh bicycle` / `bicycle` |

Pure current signature derivation exposes no recognized object, component role,
model, variant, or critical attribute for these records. `bicycle` and each site
prefix remain unresolved tokens; description reliability is marked generic.
That limitation affects later evidence strength but is not what prevents these
pairs from reaching evidence in Scan 33.

## Discovery-channel trace and first causal layer

All 118 canonical records are indexed. Every Bicycle-to-Bicycle pair is rejected
by pair eligibility before any proposal is persisted:

- Standard blocking groups by the selected `CONTRACT` and `UNIT_MEAS`, so records
  from the seven sites cannot share a standard block.
- Hybrid `_allowed_pair` rejects a nonblank contract mismatch whenever scan mode
  is `SAME_SITE_DUPLICATE`; exact-description, part-family, lexical, character,
  and technical channels all call that eligibility gate.
- The same mode is also passed to the hard business rule that returns
  `CONTRACT_MISMATCH_IN_SAME_SITE_MODE`.
- Site therefore prevents discovery; it is not merely a rank reduction or soft
  evidence signal in this run.

Persisted proposals confirm that no Bicycle pair exists. AB-BICYCLE received two
unrelated same-site standard-blocking proposals to the AB Head/Tail records;
SD-BICYCLE received one unrelated same-site proposal to `DEMO-INTERSITE`; all
three became `NON_GROUPABLE`. JS-, TD-, HM-, SJ-, and UH-BICYCLE received no
proposal. None of the seven entered an accepted group, conflict, or deferred
family; all seven are unassigned.

The overall run did reach the hybrid global cap, but it is not causal for this
family. A bounded in-memory replay over the same 118 persisted records and exact
persisted caps selected 0 Bicycle pairs in `SAME_SITE_DUPLICATE`. Changing only
the mode to site-neutral `DISCOVERY` selected all 21 Bicycle pairs, despite the
same caps and generic penalty. Every pair used exact-description and part-family;
20 also used lexical and character retrieval. Thus neither cap exhaustion nor
generic-family deferral explains the miss.

Per-record answers are identical except for the unrelated standard proposals:
each record was eligible for indexing, but every cross-site Bicycle pair was
ineligible before channel output; no Bicycle pair reached channel/per-record or
family-cap selection; no candidate budget or neighborhood truncation affected
its pair outcome.

### Authoritative 7x7 relationship matrix

For each pair below: `retrieved` means a persisted neighbor proposal exists;
`evidence` is the persisted GF4 edge; and `resolver considered` is pair-specific
consideration through persisted proposal/targeted evidence. No absent edge is
inferred as neutral or contradiction.

| Pair | Retrieved | Candidate edge | Evidence state | Cannot-link | Neutral | Support | Resolver considered | Final co-membership |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| AB / SD | No | No | Not evaluated | No | No | No | No | No |
| AB / JS | No | No | Not evaluated | No | No | No | No | No |
| AB / TD | No | No | Not evaluated | No | No | No | No | No |
| AB / HM | No | No | Not evaluated | No | No | No | No | No |
| AB / SJ | No | No | Not evaluated | No | No | No | No | No |
| AB / UH | No | No | Not evaluated | No | No | No | No | No |
| SD / JS | No | No | Not evaluated | No | No | No | No | No |
| SD / TD | No | No | Not evaluated | No | No | No | No | No |
| SD / HM | No | No | Not evaluated | No | No | No | No | No |
| SD / SJ | No | No | Not evaluated | No | No | No | No | No |
| SD / UH | No | No | Not evaluated | No | No | No | No | No |
| JS / TD | No | No | Not evaluated | No | No | No | No | No |
| JS / HM | No | No | Not evaluated | No | No | No | No | No |
| JS / SJ | No | No | Not evaluated | No | No | No | No | No |
| JS / UH | No | No | Not evaluated | No | No | No | No | No |
| TD / HM | No | No | Not evaluated | No | No | No | No | No |
| TD / SJ | No | No | Not evaluated | No | No | No | No | No |
| TD / UH | No | No | Not evaluated | No | No | No | No | No |
| HM / SJ | No | No | Not evaluated | No | No | No | No | No |
| HM / UH | No | No | Not evaluated | No | No | No | No | No |
| SJ / UH | No | No | Not evaluated | No | No | No | No | No |

Primary Bicycle cause: `SITE_BOUNDARY`. Architectural layer:
`IQR0_DISCOVERY_RECALL_DEFECT`. There is secondary weak/generic identity evidence,
but it occurs downstream of the first causal layer.

## Head Light versus Tail Light trace

The accepted Review hypothesis is
`gf5b-dc1cf73d74a4bc764b961a68600e0880cea820e1e2337b6141ae081d341f5250`,
projected as
`g2v2-group-4fb5771bc2d5daf1f197bf7a812b71c4f9a2dd3b04782dfc5ac1f3f0b3c57784`.

| Record | Persisted values |
|---|---|
| Head | row 114 / record 53385; `AB-LIGHT`; `LED Head Light`; site `AB-SA`; `PCS`; Purchased |
| Tail | row 115 / record 53386; `AB-TAIL LIGHT`; `LED Tail Light`; site `AB-SA`; `PCS`; Purchased |

Discovery proposed the pair through reciprocal `CHAR_VECTOR` and `LEXICAL` plus
`STANDARD_BLOCKING`, priority 13.1932. GF4 persisted one `REVIEW_SUPPORT` edge:

- deterministic score 69.74;
- description 61.61, TF-IDF 50.31, fuzzy 78.57, part number 77.78,
  technical token 50.0;
- rule `ALLOW`;
- no protected conflict;
- no generic-description warning;
- all runtime variant groups empty;
- discriminator object, side, and tyre fields empty/unknown.

Pure current signature derivation likewise produces no object, component-role,
model, variant, or critical-attribute observation. `head` and `tail` remain
separate unresolved identity tokens. The shadow signed comparison therefore sees
only shared unresolved lexical tokens (`ab`, `led`, `light`) and no typed
contradiction. The signature/signed-evidence layer is shadow-only and did not
change the persisted GF4 edge or GF5 decision.

GF5 correctly consumes the edge it receives: a two-member `COMPLETE_PAIRWISE`
Review group with one review edge, zero strong/neutral/cannot-link edges,
review-only support, no missing pair, and no unresolved bridge. G2 copies it
without semantic recomputation. The API explanation truthfully says possible
duplicate identity and human review required, and cautions that part numbers
differ. System CSV/XLSX include both members; all seven Bicycle records are absent
because they are unassigned. Export visibility is therefore faithful, not causal.

An additional exact Head record, row 113 / record 53384 (`AB-LIGHT`, `LED Head
Light`, site `AB SD`), is unassigned because the same site hard boundary prevents
it from being proposed with record 53385. This independently corroborates the
discovery defect.

Primary Head/Tail cause: `ATTRIBUTE_NOT_EXTRACTED`. Secondary cause:
`EVIDENCE_WEIGHTING`, because unresolved lexical/part-number similarity is still
sufficient for review support without a typed functional/location caution. The
resolver is not the first causal layer.

## Bounded historical controls

Direct current evaluator checks, without a full scan, show the broader pattern:

| Control | Current edge result |
|---|---|
| Brush / Paint under copied `Exercise 3` | `STRONG_SUPPORT` — unsafe gap remains |
| Model S / Model X under copied `Model S` | `STRONG_SUPPORT` — unsafe gap remains |
| Wood / Steel Frame under copied test text | `REVIEW_SUPPORT` — caution gap remains |
| Coil Spring / Staplers under copied `Coil Spring` | `STRONG_SUPPORT` — unsafe gap remains |
| Left / Right | `CANNOT_LINK` |
| Rim / Tyre | `CANNOT_LINK` |
| Buffer / Mirror | `CANNOT_LINK` |
| Contact Cleaner | `REVIEW_SUPPORT`, not rejected |
| Turbine Lubricating Oil | `STRONG_SUPPORT` |
| Francis Turbine Lower Bearing | `STRONG_SUPPORT` |
| Pump X500 | `STRONG_SUPPORT` |
| Fan Blade | `STRONG_SUPPORT` |
| F30 aliases | `STRONG_SUPPORT` |
| B38 aliases | `STRONG_SUPPORT` |

Existing bounded tests also protect the implemented cannot-link categories and
positive-control compatibility. The non-authoritative R17 counterfactual covers
the four R12 false pairs but was deliberately never promoted into runtime. The
Head/Tail miss is therefore part of a broader sparse semantic-coverage and
copied-text trust gap, while existing general side/object protections still work.
No accuracy metric or general quality claim is inferred from these controls.

## Architecture decision and smallest safe correction layers

The exact classification is `IQR0_MULTILAYER_DEFECT`:

1. **Retrieval/discovery policy:** remove site/contract as an independent hard
   eligibility boundary for the current Group-First physical-identity discovery
   path while preserving it as context, scope only when explicitly requested,
   and a visible provenance signal. Preserve all bounds and legacy compatibility.
2. **General role/location/variant extraction and signed evidence:** represent
   bounded functional/location roles such as head/tail as typed observations and
   compare incompatible roles only when a compatible shared component/object
   base is established. Do not add a Head-Light/Tail-Light item rule.
3. **Generic/copied-text trust:** prevent copied/generic text from independently
   creating strong identity support; require independent identity-specific
   evidence. This is proven by the bounded historical controls and must be
   protected alongside the Head/Tail correction.

The first correction phase should address these proven general seams in that
order and rerun only the bounded Scan-33 acceptance/control set. It must not
change exports, human authority, confidence, LLM, or XLSX-vNext behavior.

## Confidence and LLM implications

A whole-group confidence index cannot compensate for Bicycle records that never
reach the resolver. A group-first LLM cannot review a group discovery never
creates. For Head/Tail, neither confidence nor LLM should be used to hide missing
deterministic typed evidence. Both initiatives remain downstream of the IQR
correction and later R18/R18-G measurement.

## Diagnostic regression contracts

`backend/tests/test_iqr0_pre_demo_identity_quality_diagnostic.py` adds no runtime
behavior. Passing characterization tests freeze the current causal evidence;
strict xfails make these next-phase requirements explicit:

- site alone cannot block physical-identity discovery;
- Head/Tail functional/location distinction reaches typed evidence;
- copied generic description cannot independently create strong support.

Existing general cannot-link safety remains a passing control. All tests make
zero provider requests.

Focused verification passed 181 discovery, evidence, resolver-safety,
authority/API, XLSX, and historical-control tests. The three explicitly named
future contracts remain strict expected failures, which is the intended IQR-0
diagnostic state. The full 5,327-row detector was not run.

## Exact next task

Implement the smallest general architecture correction for the proven IQR-0
failure layers, protect the positive and negative regression controls, rerun the
bounded Scan-33 acceptance case, and make no LLM/confidence/XLSX-vNext changes.

Only after bounded correction acceptance may work proceed to R18/R18-G,
deterministic quality measurement, whole-group confidence, group-first LLM
shadow evaluation, and the primary client XLSX vNext.
