# Deterministic group and pair explanation V1

## Boundary and contracts

The user-facing explanation layer is a read-only projection of persisted
deterministic evidence. Its contracts are:

- group projection: `deterministic-group-explanation-v1`;
- pair presentation: `deterministic-pair-explanation-read-model-v1`;
- structured authority source: `deterministic-pair-explanation-v1`.

The layer does not generate candidates, score pairs, execute GF4/GF5, rerun the
evaluator, call an LLM/provider, or influence human-review authority. Rendered
prose is presentation, not persisted authority and not duplicate probability.

## Group Summary

The summary reports member count, recorded/possible internal relationships,
Match Strength and band, and the signed evidence tier. Complete coverage is
required before it says that all internal relationships support grouping or
that no internal cannot-link is recorded. Two-member groups use one compact
relationship. Multi-member groups retain every recorded internal relationship.

## Relationship Map and Pair Explanation

Relationship rows are canonically ordered and expose both record identities,
the persisted deterministic pair score, signed relationship, evidence origin,
availability, safe group role, and review/safety presence. Expanded pair detail
contains only nonempty sections: supporting evidence, limiting evidence,
contradictions, classification controls, decision, and provenance.

Every evidence item carries a `source_field`. Component scores, normalized
values, UOM context, protected conflicts, generic-description controls, reason
codes, evaluator version, evidence fingerprint, and pair-explanation fingerprint
come from persisted evidence. A high numeric score remains separate from a
`REVIEW_SUPPORT` classification.

## Reason codes and safe language

The centralized deterministic mapping currently gives bounded wording to:

- `DETERMINISTIC_LIKELY_DUPLICATE`;
- `LEXICAL_SUPPORT_NOT_INDEPENDENT`;
- `CROSS_FIELD_IDENTITY_INCOHERENCE`.

Unknown codes are shown exactly with the statement that they are persisted
classification codes. The renderer does not infer undocumented semantics.
Relationships may “support the final group.” They are never described as the
decisive pair or as causing the final group.

## Availability and historical evidence

`COMPLETE` means the rich persisted structured source passed its evidence
fingerprint validation. `PARTIAL_LEGACY` shows only retained score/state/reason
facts and the explicit notice “Limited historical evidence available.” Missing
facts are not reconstructed and the evaluator is not rerun.

## UI and XLSX

The group list shows “Why this group exists.” Group detail shows a relationship
list with collapsed pair details by default; no network graph or raw JSON is
used. Two-member groups have one row, while the current largest group has ten.

The XLSX remains exactly five sheets with zero formulas. `Review Groups` keeps
the compact group context (`Group`, `Evidence`, `Match Strength`, `Match Band`,
and `Group Sites`) frozen on the left, followed by `Review Consideration`,
`Why This Group Exists`, and wrapped multiline `Relationship Evidence`.
`Group Index` freezes its first four compact context columns. `Detailed Data`
remains record-oriented and does not contain Match Strength or Match Band.

The former `Why Suggested` column repeated the explanation without adding a
distinct reviewer action. It is therefore repurposed as `Review Consideration`
and now contains only persisted reasons that keep a group under human review,
or a bounded reminder that human review remains authoritative. Export-only
`Review Status` columns were removed; `Human Decision` and `Human Comment`
remain unchanged. Exact reason codes stay available in `Relationship Evidence`
technical details. `Technical Reference` documents the contracts, availability
semantics, reason rendering, safe causal language, and no-evaluator/no-LLM
boundary.

## Acceptance

The provider-free 5,327-row shadow gate produced 208/208 Site-selected group
summaries and 251/251 COMPLETE pair explanations (242 proposal, 9 targeted),
including all 190 two-member and 18 multi-member groups and all 35 High-Match /
Review-Evidence crossovers. Site-unselected produced 42/42 summaries and 68/68
COMPLETE explanations, with 14/14 crossovers. All frozen S0-S10 fingerprints
matched and provider calls were zero. Full performance/payload and workbook
figures are recorded by the acceptance harness.

Across the final repeated Site-selected runs, pure projection of all 208 groups
took 0.066–0.247
seconds. The serialized all-group list-item benchmark grew from 988,615 to
1,319,837 bytes because each item now carries its compact relationship map;
expanded pair details remain detail-only. The largest fully expanded group
payload was 64,853 bytes. The fresh XLSX was about 200.6 KB and generated in
6.84–11.09 seconds. No comparable pre-change XLSX timing was captured in the same
run, so the implementation does not claim an exact generation-time delta.

## Future optional LLM boundary

Any future LLM feature must sit after this deterministic read model and may only
paraphrase or advise. It must not replace structured evidence, signed state,
score, safety controls, human authority, or deterministic provenance.
