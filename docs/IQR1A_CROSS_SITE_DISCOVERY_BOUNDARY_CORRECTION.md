# IQR-1A Cross-Site Discovery Boundary Correction

## IQR-1B preservation result

IQR-1B preserved this result exactly at the discovery/evidence boundary: Scan
33 still has 1,124 proposals, 21 cross-site proposals, and all 21 Bicycle
relationships reach GF5 as `REVIEW_SUPPORT`; the family remains deferred.
IQR-1B independently corrected Head/Tail functional/location evidence. See
`docs/IQR1B_FUNCTIONAL_LOCATION_IDENTITY_EVIDENCE_CORRECTION.md`.

## Classification

`IQR1A_CROSS_SITE_DISCOVERY_VERIFIED`

The current-product Group-First path can now discover bounded cross-site
physical-identity candidates. Historical legacy scan-mode behavior remains
unchanged. IQR-1A does not change Head/Tail semantics, evidence thresholds,
GF5 partition policy, review authority, confidence, LLM, or exports.

## Baseline and safety

- Branch: `llm-assisted-mvp`.
- Starting HEAD: `0c76e478b73015288469dba31d05cb86e5be37fb`.
- Protected tag `deterministic-demo-v1` remained at
  `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- Initial status contained only `?? List_20260709_093045.xlsx`; nothing was
  staged.
- The XLSX was not inspected, modified, staged, hashed, or deleted.
- No `.env`, credential, token, authorization header, or secret was inspected.
- Provider requests were 0. Docker was not used; backend and frontend remained
  stopped.

## IQR-0 causal finding

IQR-0 proved that all 21 relationships among the seven Scan-33 Bicycle records
were rejected before identity evidence because the saved scan scope was
`SAME_SITE_DUPLICATE` and every record had a different site. A site-neutral
counterfactual retrieved all 21 through existing exact-description and
part-number-family channels.

The two exact causal checks were in
`backend/app/services/hybrid_retrieval.py::_allowed_pair`:

1. the direct site-mismatch rejection for `SAME_SITE_DUPLICATE`; and
2. `evaluate_hard_business_rules`, which classified the same mismatch as
   `CONTRACT_MISMATCH_IN_SAME_SITE_MODE`.

The later evidence evaluator also used the saved scan mode, so merely removing
the first check would not have been sufficient.

## Authority boundary and correction

The repository already has an authoritative separation:

- request authority `current_product` maps to `group_first_primary` and G2-v2;
- request authority `legacy_compatibility` maps to `legacy_primary` and the
  historical pair/G1/G2-v1 path.

`identity_discovery_scan_mode_for_orchestration` now expresses the missing
contract:

- `group_first_primary` uses `DISCOVERY` for GF2 discovery through GF4 evidence;
- `legacy_primary` retains the normalized requested scan mode unchanged.

The saved `DuplicateScan.scan_mode` is not rewritten. Site remains present on
every canonical record and in retrieval blocking/context signals, APIs,
explanations, site-spread summaries, audit, and exports.

`ScanRunner` uses the effective Group-First discovery mode consistently for:

- the immutable discovery configuration/fingerprint;
- hybrid eligibility;
- deterministic scoring of hybrid additions; and
- the GF4 deterministic evidence context.

The legacy standard-pair scoring and persistence path continues to use its
requested scan mode.

## Bounded cross-site anchor policy

An initial unrestricted site-neutral probe exposed a real safety regression:
weak lexical/character cross-site Review edges could bridge otherwise valid
same-site demo groups. The final correction therefore enables cross-site
identity discovery only when an existing bounded identity-retrieval anchor is
present:

- `EXACT_DESCRIPTION`; or
- `PART_NUMBER_FAMILY`.

Once anchored, lexical, character, and technical channels may enrich the same
pair's deterministic provenance. Weak channels cannot independently create a
new cross-site proposal. This is a general signal contract, not a Bicycle or
dataset rule.

All existing limits remain unchanged: channel top-k values, per-record final
top-k, global cap, family cap, tier caps, neighborhood member limit,
deterministic ordering, genericity penalties, conflict penalties, and explicit
truncation/degradation. No all-pairs fallback or site Cartesian product was
added.

## Exact bounded Scan-33 before/after

The persisted Scan-33 canonical catalog of 118 records was loaded from the
SQLite database in read-only mode and rerun in a temporary test database with
the persisted retrieval configuration. The protected XLSX was not used.

| Metric | Before | After |
|---|---:|---:|
| Total proposals | 1,103 | 1,124 |
| Cross-site proposals | 0 | 21 |
| Candidate/evidence edges | 1,103 | 1,124 |
| GF5 work units | 10 | 9 |
| Accepted groups | 3 | 3 |
| Likely groups | 0 | 0 |
| Review groups | 3 | 3 |
| Conflicts | 3 | 3 |
| Deferred work units | 2 | 3 |
| Unassigned records | 111 | 111 |
| Provider requests | 0 | 0 |

The increase is exactly 21 proposals/edges (1.9%), not an unexplained proposal
explosion. All previously grouped pairs remained discoverable. The finalized
temporary runs completed in 5.286 and 7.687 seconds; the variation is reported
only as a bounded 118-record observation, not a general performance result.
The existing harness did not report memory, so memory was not estimated.

## Bicycle 7 x 7 relationship matrix

Before IQR-1A every row below was: not retrieved, no candidate edge, rejected by
site, no evidence, not considered by GF5, and separated/unassigned.

After IQR-1A every row below is: retrieved, candidate edge present, no site
rejection, `REVIEW_SUPPORT`, considered by GF5, and separated in the system
projection.

| Relationship | Retrieved | Edge | Site rejection | Evidence | Resolver | Final |
|---|---|---|---|---|---|---|
| AB-BICYCLE / SD-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| AB-BICYCLE / JS-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| AB-BICYCLE / TD BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| AB-BICYCLE / HM-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| AB-BICYCLE / SJ-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| AB-BICYCLE / UH-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| SD-BICYCLE / JS-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| SD-BICYCLE / TD BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| SD-BICYCLE / HM-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| SD-BICYCLE / SJ-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| SD-BICYCLE / UH-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| JS-BICYCLE / TD BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| JS-BICYCLE / HM-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| JS-BICYCLE / SJ-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| JS-BICYCLE / UH-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| TD BICYCLE / HM-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| TD BICYCLE / SJ-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| TD BICYCLE / UH-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| HM-BICYCLE / SJ-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| HM-BICYCLE / UH-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |
| SJ-BICYCLE / UH-BICYCLE | yes | yes | no | REVIEW_SUPPORT | considered | separated |

All seven canonical records and site values are preserved. GF5 places the seven
records in one new deferred work unit; it does not force a group. That is the
truthful outcome for a discovery-only correction: the recall blocker is gone,
while confidence/support policy was not weakened.

## Regression controls

- **Same-site behavior:** same-site exact identity remains retrievable, and the
  existing synthetic showable-product groups and review workflow remain intact.
- **Cross-site is not support:** a Pump-X500 / Valve-Z900 cross-site pair remains
  `NON_GROUPABLE`; site-neutral context creates no support.
- **Technical contradiction:** cross-site `PUMP L/S` / `PUMP R/S` remains
  `CANNOT_LINK`.
- **Same part number:** equal normalized part numbers remain ineligible across
  sites, preserving normal IFS record semantics.
- **Weak bridge safety:** cross-site 10 kW / 5 kW motor records with only
  lexical/character/technical retrieval signals cannot create a proposal
  without an exact-description or part-family anchor.
- **Historical semantics:** legacy-primary `SAME_SITE_DUPLICATE` and
  `CROSS_SITE_STANDARDIZATION` modes are returned unchanged by the new contract.
- **Quality controls:** left/right, rim/tyre, buffer/mirror, structural role,
  trailing variant, generic/copied description, whole-set GF5, reviewed-set
  exclusivity, and signed evidence suites remain passing.

## IQR-0 xfails

```text
IQR-0 xfails before: 3
cross-site xfails converted: 1
remaining strict xfails: 2
```

The Head/Tail functional/location xfail remains. The copied/generic-description
trust xfail also remains. Neither behavior was changed by IQR-1A.

## Verification

- IQR-0/IQR-1A focused contracts: `11 passed, 2 xfailed` after the final weak
  bridge and part-family-anchor regressions were added.
- Discovery/retrieval/evidence/resolver/Group-First bounded set before the final
  anchor refinement: `282 passed, 2 xfailed`.
- Final showable-product and historical GF12 controls: `134 passed, 2 xfailed`.
- Exact final Scan-33 temporary rerun: passed; 0 provider requests.
- Full backend suite after the final correction: `1,720 passed, 15 skipped,
  2 xfailed` in 280.02 seconds. The only warning was the repository's existing
  unknown `asyncio_default_fixture_loop_scope` pytest configuration option.
- Frontend testing was not required because no frontend file changed.

## Remaining risks and next task

The cross-site discovery boundary is corrected, but Bicycle evidence remains
Review-only and deferred. Head/Tail remains an open, independent typed-evidence
defect. External demo readiness therefore remains
`BLOCKED_BY_IDENTITY_OUTPUT_QUALITY`.

Exact next task:

> IQR-1A VERIFIED -> execute IQR-1B only: implement a general source-aware
> functional/location identity attribute so mutually exclusive placement/role
> evidence such as Head vs Tail can create deterministic identity contradiction
> or bounded downgrade without noun-specific rules; preserve all IQR-1A
> cross-site recall behavior.

Do not start R18, confidence, LLM advisory, XLSX vNext, deployment, or GF11 until
both IQR-1A and IQR-1B pass bounded pre-demo identity-quality acceptance.
