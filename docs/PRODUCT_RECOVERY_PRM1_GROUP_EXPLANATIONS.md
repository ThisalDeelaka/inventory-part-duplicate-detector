# PRM-1 Plain-Language Group Explanations

## Authority and boundary

PRM-0 (`PRM0_PRODUCT_RECOVERY_AUDIT_COMPLETE`) identified count-only evidence as
the smallest user-visible blocker. PRM-1 adds a deterministic presentation/read
model only. It does not change normalization, discovery, scoring, thresholds,
cannot-link behavior, membership, machine status, provider behavior, review
authority, persistence schema, migrations, dependencies, or exports.

## Persisted evidence used

The mapper reads persisted group status, immutable member projections,
validation-coverage counts, group evidence summary, genericity risk, bridge risk,
and missing-evidence summary. Conflict explanations read persisted conflict type,
summary, and involved record references. Deferred explanations read persisted
reason, unfinished-evidence summary, and record references. It performs no
detector computation and no database write.

## Explanation model and status language

`SystemExplanation` contains `headline`, `summary`, up to three
`supporting_points`, up to two `caution_points`, `review_guidance`, and
`evidence_basis`. A likely group is a stronger system-generated duplicate
hypothesis that still requires human confirmation. A review group is a possible
duplicate identity requiring human review. Conflict means persisted evidence
prevented safe automatic grouping and is not a duplicate group. Deferred means no
duplicate conclusion was reached because persisted evidence or bounded resources
were insufficient.

Human review remains a separate display and authority. Existing Confirmed, Keep
separate, Unsure/deferred, and Superseded states do not rewrite the historical
system explanation.

## Selection, aggregation, and fallback

The mapper selects a bounded deterministic set: group-wide normalized part number,
one common persisted technical classification, relationship support counts, and a
non-generic group-wide normalized description. Generic/copied descriptions,
insufficient independent evidence, incomplete coverage, bridge ambiguity,
review-only support, neutral relationships, and differing part numbers are
cautions. Duplicate wording is removed.

A member field is called group-wide only when every member has the same nonblank
persisted value. Relationship evidence remains a count, never a claim that every
member pair shares it. Mixed and partial evidence becomes a caution. With no
specific group-wide reason, the explanation honestly says the persisted result
supports review without establishing a more specific fact. No score is presented
as a calibrated probability.

## UI placement and review separation

The group list shows a short preview. Group detail shows the complete System
explanation before existing advanced evidence. Conflict and deferred cards use
status-specific explanations. The existing Human decision panel remains separate,
and raw technical evidence remains available under Advanced.

## Historical-case verification

Persisted-fixture tests cover a strong plausible hypothesis, weak review-only
evidence, generic/copied descriptions, explicit object/construct and variant
conflicts, left/right conflict text, three-plus-member mixed evidence,
confirmed/rejected/deferred human states, deterministic historical rendering, and
R12-style overclaim guards. They verify pair evidence is not generalized to the
whole group and machine hypotheses never say confirmed duplicate, same physical
item, or a confidence percentage.

## Verification

- Backend explanation tests: 12 passed.
- Backend explanation/API inversion tests: 32 passed.
- Full frontend component/contract suite: 102 passed.
- Frontend production build: passed.
- Full backend suite: 1,709 passed, 15 skipped, one existing pytest-configuration
  warning.
- Provider calls: zero by construction and test guard.

A browser session was not started. Component tests, API integration tests, and the
production frontend build provide equivalent local verification without Docker,
secrets, or rerunning the 5,327-row detector.

## Deferred work and unchanged governance

System Group XLSX could later reuse an explanation mapper, but PRM-1 does not alter
export shape or authority; export work is deferred to PRM-3. PRM-2 is next and is
limited to making Confirm / Reject / Defer unmistakable and polishing saved-review
interaction without changing review authority.

Detector semantics remain unchanged and remain unfrozen from the R12 quality
perspective. R18 is `R18_HUMAN_REVIEW_DATASET_PREPARED`; human-label execution
remains deferred, so GF-12A2 is not complete. GF-11 remains in progress, its
waiver is active, `GF11-PERF-100K-COLD-FULL` is open, and deployment remains
deferred.
