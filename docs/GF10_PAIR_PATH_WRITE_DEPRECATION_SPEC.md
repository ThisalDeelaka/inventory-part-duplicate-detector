# GF-10 pair-path write deprecation specification

## Scope and phase boundary

GF-10 remains one phase in the frozen GF-0 through GF-12 roadmap:

- GF-10A defines the residual dependency inventory, post-GF-9 orchestration
  policy v2, write-deprecation policy, diagnostics availability, and historical
  policy-version interpretation.
- GF-10B wires policy v2 into new scans and stops legacy pair/G1/G2-v1 writes
  for `group_first_primary` only.

GF-10A remains the pure contract boundary. GF-10B is now verified as the
runtime consumer of those frozen contracts.

## GF-10B prerequisite: truthful orchestration-audit persistence

GF-10B pre-flight found that the persisted orchestration-run schema allowed
only `G2_V1` as `visible_projection_contract`. That invariant was correct for
policy v1, but it cannot truthfully represent the already-frozen policy-v2
`group_first_primary` contract, whose visible projection is `G2_V2` and whose
compatibility projection is not required. Persisting `G2_V1` for that plan
would create false audit history.

The narrow GF-10B prerequisite therefore expands the non-null allowlist to
exactly `G2_V1 | G2_V2`. It does not permit arbitrary values, `AUTO`, or future
contract names. The SQLite migration rebuilds only `scan_orchestration_run`
from its stored definition, copies every column and row without rewriting any
value, and restores its explicit indexes and triggers. Primary/foreign/unique
keys, unrelated checks, types, nullability, defaults, IDs, timestamps, status,
readiness, and failure fields remain intact. Historical policy-v1 legacy and
group-first rows remain `G2_V1`; there is no backfill.

This prerequisite proved policy-v2 G2-v2 persistence before runtime activation;
the verified runtime behavior is recorded below.

## GF-10B verified runtime behavior

Every new scan now persists `group-first-orchestration-policy-v2` and executes
the frozen plan together with `PairPathWritePolicy`. The default mode remains
`legacy_primary`; neither shadow metrics nor current configuration can promote
a scan automatically.

An explicit `group_first_primary` scan executes canonical catalog, discovery,
signed evidence, constrained resolution, and G2-v2 projection in order. The
legacy pair, G1, G2-v1, and shadow stages are persisted as `NOT_APPLICABLE`.
Their writers/services are not invoked, including when the legacy shadow gate
is enabled. Primary GF-1 through GF-6 success directly makes the v2 product
visible; GF-5/GF-6 failure remains a primary failure with no v1 rescue.

GF-2 neighbor proposals, GF-4 signed `CANNOT_LINK`/`STRONG_SUPPORT`/
`REVIEW_SUPPORT` evidence, GF-5 targeted evidence, and GF-6 evidence provenance
remain intact. Controlled regression input avoids all candidate/rejection,
G1/G2-v1, and shadow rows while retaining nonzero proposal/evidence rows and a
completed resolution/G2-v2 snapshot. Equivalent legacy-mode execution retains
candidate, v1, and gated shadow artifacts.

Pair diagnostics for policy-v2 group-first scans report
`NOT_GENERATED_NOT_APPLICABLE` with no candidate count. Candidate/rejection and
pair-advisory exports fail with a typed not-applicable response rather than an
empty CSV. Advanced diagnostics display that explicit absence. Historical and
policy-v2 legacy scans retain generated-zero versus generated-nonzero semantics,
candidate APIs, pair exports, and legacy numeric v1 routes.

Authority-selected summary/list/detail and System Group, Reviewed Identity,
Conflict, and Deferred exports operate from G2-v2 without v1. Projection-safe
G6 review chains and constraints work without legacy artifacts; G7 complete-
pairwise review eligibility builds its request from v2, while progressive and
likely groups remain ineligible. Review never auto-runs GF-5/GF-6.

Historical policy-v1 audits retain their persisted compatibility semantics and
are neither backfilled nor reinterpreted. GF-10 is complete; GF-11 scale
hardening has not started.

## Dependency-audit conclusion

No authoritative `group_first_primary` product or business flow requires a new
pair, G1, or G2-v1 write after GF-9.

`IdentityReadService` selects authority from the orchestration mode persisted
for the scan. A completed persisted group-first scan requires the exact G2-v2
stage source and never falls back to compatibility v1. Normal APIs and
canonical exports consume that snapshot. Versioned G6 review and G7 eligibility
receive the same projection-safe opaque group key and load v2 membership and
evidence. The group-first product result is therefore complete after GF-1
through GF-6.

Residual dependencies have only these roles:

- policy-v1 and `legacy_primary` computation;
- historical/no-audit and legacy v1 reads;
- advanced pair diagnostics and compatibility exports/routes;
- GF-7 migration comparison when both projections legitimately exist;
- regression fixtures and tests;
- writes scheduled for deprecation by GF-10B.

## Policy generations and historical immutability

`group-first-orchestration-policy-v1` is the persisted GF-8 transitional
contract. Historical group-first policy-v1 plans keep pair, G1, and G2-v1 as
`COMPATIBILITY_REQUIRED`, visible projection `G2_V1`, and the v1 compatibility
readiness gate. Existing rows are never rebuilt from current configuration.

`group-first-orchestration-policy-v2` is the post-GF-9 contract for future
GF-10B scans. Pure plan reconstruction and outcome evaluation dispatch on the
persisted policy version. Unknown versions fail closed. The only modes remain
`legacy_primary` and `group_first_primary`.

## Policy-v2 stage plans

### `GROUP_FIRST_PRIMARY`

| Stage | Authority |
|---|---|
| `CANONICAL_CATALOG` | `PRIMARY_REQUIRED` |
| `DISCOVERY` | `PRIMARY_REQUIRED` |
| `SIGNED_EVIDENCE` | `PRIMARY_REQUIRED` |
| `GROUP_RESOLUTION` | `PRIMARY_REQUIRED` |
| `G2_V2_PROJECTION` | `PRIMARY_REQUIRED` |
| `LEGACY_PAIR_COMPATIBILITY` | `NOT_APPLICABLE` |
| `G1_COMPATIBILITY_PROJECTION` | `NOT_APPLICABLE` |
| `G2_V1_COMPATIBILITY_PROJECTION` | `NOT_APPLICABLE` |
| `SHADOW_COMPARISON` | `NOT_APPLICABLE` |

Its primary pipeline is `GROUP_FIRST_GF1_GF6`, visible projection is `G2_V2`,
and `compatibility_projection_required` is false. When all required GF-1
through GF-6 stages succeed, `primary_identity_ready` directly implies
`visible_product_ready`. Absence of v1 and shadow output is expected, not a
failure.

### `LEGACY_PRIMARY`

The policy-v2 legacy plan preserves current behavior: catalog, discovery,
signed evidence, legacy pair persistence, G1, and G2-v1 are
`PRIMARY_REQUIRED`; GF-5 resolution and GF-6 v2 are optional diagnostics; GF-7
shadow remains optional only when its existing explicit gate is enabled. The
primary pipeline remains `LEGACY_PAIR_G1`, visible projection remains `G2_V1`,
and legacy authoritative output remains the readiness gate.

## Pair-path dependency contract

`PairPathDependency` is immutable and records component, source module,
`PAIR_WRITE`/`PAIR_READ`/`G1_WRITE`/`G1_READ`/`G2_V1_WRITE`/`G2_V1_READ`, one
classification, policy-v2 allowance, reason, and replacement authority.
Allowed classifications are `AUTHORITATIVE_REQUIRED`, `LEGACY_MODE_REQUIRED`,
`HISTORICAL_READ_ONLY`, `DIAGNOSTIC_READ_ONLY`, `MIGRATION_SHADOW_ONLY`,
`TEST_ONLY`, and `DEPRECATED_WRITE`.

The executable validator requires:

- `AUTHORITATIVE_REQUIRED` residual count equals zero;
- allowed `PAIR_WRITE`, `G1_WRITE`, and `G2_V1_WRITE` count equals zero;
- `MIGRATION_SHADOW_ONLY` is not allowed for policy-v2 group-first scans;
- every direct runtime module containing known candidate/G1/v1 markers has at
  least one manifest entry.

## Complete residual dependency inventory

`Allowed` means the residual reference may remain for compatibility; it does
not mean that the component executes for a policy-v2 group-first scan.

| Component / module | Kind | Classification | Allowed | Replacement |
|---|---|---|---:|---|
| `scan_runner.py` candidate transaction | `PAIR_WRITE` | `DEPRECATED_WRITE` | no | GF-4 evidence |
| `scan_runner.py` G1 projection | `G1_WRITE` | `DEPRECATED_WRITE` | no | GF-5 resolver |
| `scan_runner.py` G2-v1 projection | `G2_V1_WRITE` | `DEPRECATED_WRITE` | no | GF-6 G2-v2 |
| `candidate_repository.py` persistence | `PAIR_WRITE` | `DEPRECATED_WRITE` | no | GF-4 evidence |
| `candidate_repository.py` listing | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | authority-selected groups |
| `routes_scans.py` candidate API/export | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | identity-read APIs/exports |
| `routes_diagnostics.py` pair telemetry | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | identity-read summary |
| `routes_llm.py` pair advisory | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | versioned group advisory |
| `feedback_service.py` pair feedback | `PAIR_WRITE` | `DEPRECATED_WRITE` | no | versioned G6 review |
| `llm_enhancement_service.py` input | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | G7 group advisory |
| `llm_enhancement_service.py` candidate creation | `PAIR_WRITE` | `DEPRECATED_WRITE` | no | GF-2/GF-4 |
| `llm_triage_service.py` input | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | G7 group advisory |
| `llm_triage_service.py` snapshot | `PAIR_WRITE` | `DEPRECATED_WRITE` | no | G7 group advisory |
| `recall_rescue_service.py` pair pool | `PAIR_WRITE` | `DEPRECATED_WRITE` | no | GF-2 proposals |
| `recall_rescue_service.py` candidate lookup | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | GF-2 proposal identity |
| `identity_group_projection.py` pure G1 | `G1_WRITE` | `LEGACY_MODE_REQUIRED` | no | GF-5 resolver |
| `identity_group_snapshot_service.py` G1 consumption | `G1_READ` | `LEGACY_MODE_REQUIRED` | no | GF-6 adapter |
| `identity_group_snapshot_service.py` v1 persistence | `G2_V1_WRITE` | `LEGACY_MODE_REQUIRED` | no | GF-6 v2 persistence |
| `identity_group_query_service.py` v1 query | `G2_V1_READ` | `HISTORICAL_READ_ONLY` | yes | IdentityReadService |
| `identity_group_export_service.py` G5 export | `G2_V1_READ` | `LEGACY_MODE_REQUIRED` | yes | canonical System Group Export |
| `identity_group_review_service.py` v1 review | `G2_V1_READ` | `LEGACY_MODE_REQUIRED` | yes | versioned G6 review |
| `identity_group_review_service.py` G1 reprojection | `G1_WRITE` | `LEGACY_MODE_REQUIRED` | no | versioned v2 constraints |
| `scan_orchestration_service.py` v1 audit | `G2_V1_READ` | `HISTORICAL_READ_ONLY` | yes | persisted policy audit |
| `shadow_comparison_service.py` comparison | `G2_V1_READ` | `MIGRATION_SHADOW_ONLY` | no | none after deprecation |
| `identity_read_repository.py` v1 source | `G2_V1_READ` | `HISTORICAL_READ_ONLY` | yes | persisted-mode reader |
| `identity_read_service.py` v1 adapter | `G2_V1_READ` | `HISTORICAL_READ_ONLY` | yes | G2-v2 for group-first |
| `identity_read_export_service.py` v1 branch | `G2_V1_READ` | `HISTORICAL_READ_ONLY` | yes | G2-v2 export branch |
| `group_llm_eligibility.py` v1 advisory | `G2_V1_READ` | `LEGACY_MODE_REQUIRED` | yes | versioned v2 advisory |
| `routes_identity_groups.py` numeric routes | `G2_V1_READ` | `HISTORICAL_READ_ONLY` | yes | opaque identity-read routes |
| `scan_service.py` candidates | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | identity-read groups |
| `export_service.py` candidate CSV | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | member-shaped exports |
| `llm_export_service.py` pair advisory CSV | `PAIR_READ` | `DIAGNOSTIC_READ_ONLY` | yes | canonical identity exports |
| `rejection_repository.py` pair rejection | `PAIR_WRITE` | `DEPRECATED_WRITE` | no | GF-4 cannot-link evidence |
| `backend/tests/` legacy fixture writes | `PAIR_WRITE`, `G1_WRITE`, `G2_V1_WRITE` | `TEST_ONLY` | no | none |
| `backend/tests/` legacy assertions | `PAIR_READ`, `G1_READ`, `G2_V1_READ` | `TEST_ONLY` | yes | none |

Test fixtures are represented once per dependency kind rather than once per
test function. Full regression checks their historical compatibility behavior.

## Write policy

`PairPathWritePolicy` is immutable and fingerprinted over mode, policy version,
all flags, and its bounded reason.

| Flag | Policy-v2 group-first | Policy-v2 legacy |
|---|---:|---:|
| `write_legacy_pairs` | false | true |
| `write_g1_projection` | false | true |
| `write_g2_v1_projection` | false | true |
| `run_shadow_comparison` | false | existing explicit gate |
| `pair_diagnostics_available_for_new_scan` | false | true |
| `legacy_numeric_group_routes_authoritative` | false | true |

GF-10A only defines these values. GF-10B owns enforcement.

## Diagnostics, exports, and shadow lifecycle

Historical and legacy scans retain readable pair diagnostics and legacy pair
exports. A future policy-v2 group-first scan has
`NOT_GENERATED_NOT_APPLICABLE` pair diagnostics with a null candidate count.
It must not be reported as zero pairs, and no fake empty pair export may imply
that the pair engine ran. Canonical GF-9 exports remain authority-selected and
unchanged.

GF-7 is a migration diagnostic only where legitimate v1 and v2 projections
both exist. Historical comparison rows remain immutable/readable, and legacy
mode may continue the current gated comparison. Policy-v2 group-first does not
manufacture v1 merely for comparison, so shadow is `NOT_APPLICABLE` and its
absence is successful expected behavior.

## G6 and G7 isolation proof

For a persisted group-first scan, `IdentityReadService` loads the exact G2-v2
source reference. `VersionedIdentityGroupReviewService` resolves the opaque v2
target and persists append-only projection-scoped G6 rows. The authoritative G7
loader consumes that same identity-read group and its materialized v2 evidence.
These code paths do not load `DuplicateCandidate`, invoke G1, or use the v1
current selector. Existing v1 review/advisory branches remain valid only for
historical and legacy authority.

## GF-10A verification boundary

Golden tests D1-D12 freeze policy-v1 history, both policy-v2 modes, readiness,
write flags, diagnostics semantics, shadow absence, GF-9 persisted-mode read
authority, and policy-version reconstruction. Manifest tests freeze complete
classification and zero-authoritative/write invariants. Full regression must
prove that the unmodified runtime continues the GF-8 compatibility path until
GF-10B.
