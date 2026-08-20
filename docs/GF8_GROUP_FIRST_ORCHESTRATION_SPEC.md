# GF-8 group-first scan-orchestration specification

## Scope and phase boundary

GF-8 remains one phase in the frozen GF-0 through GF-12 roadmap:

- GF-8A defines pure orchestration mode, stage-authority, readiness, failure,
  compatibility, and explicit-selection contracts.
- GF-8B wires controlled group-first-primary execution and immutable per-scan
  audit into normal scans without changing current product readers.

GF-8B changes runtime authority only when explicitly configured. It changes no
current-result selection, API, UI, export, review, advisory, pair semantics,
provider, or source-data behavior.

## Transitional authority model

The current runtime executes a group-first substrate and a legacy compatibility
path:

```text
GF-1 -> GF-2/GF-3 -> GF-4 -> GF-5C -> GF-6B
legacy pair persistence -> G1 -> current G2-v1
```

During GF-8/GF-9 migration, primary identity authority and visible projection
are deliberately separate concepts. Even when group-first becomes primary in
GF-8B, the visible projection remains G2-v1 until GF-9 migrates G3/G4/G5/G6/G7
readers. Compatibility output therefore cannot be removed or called optional
in group-first-primary pre-GF-9 operation.

## Modes

`LEGACY_PRIMARY` preserves current behavior:

- primary identity pipeline: legacy pair/G1;
- visible projection: G2-v1;
- GF-5C and GF-6B remain internal, non-current, failure-isolated stages;
- controlled shadow comparison remains optional diagnostic work.

`GROUP_FIRST_PRIMARY` is the future GF-8B authority mode:

- primary identity pipeline: GF-1 through GF-6;
- visible projection before GF-9: still G2-v1;
- legacy pair persistence, G1, and G2-v1 remain required compatibility output;
- a successful compatibility path cannot substitute for failed group-first
  primary identity work.

Mode selection is explicit. It is never inferred from shadow comparison
agreement, safety-delta counts, case priority, or any scalar graduation score.

## Policy and configuration

`ScanOrchestrationPolicy` records mode, version, primary pipeline, visible
projection contract, compatibility requirement, every GF/legacy-stage
requirement, and shadow enablement/authority. The only configured mode values
are `legacy_primary` and `group_first_primary`.

`IDENTITY_ORCHESTRATION_MODE` defaults to `legacy_primary`. Invalid values fail
configuration validation and never silently promote to group-first. GF-8A does
not read this setting from `scan_runner.py`; the field reserves the explicit
GF-8B product-owner selection boundary.

The visible projection contract is frozen to `G2_V1` for both modes.

## Stage taxonomy and authority

Stages are ordered:

1. `CANONICAL_CATALOG`;
2. `DISCOVERY`;
3. `SIGNED_EVIDENCE`;
4. `GROUP_RESOLUTION`;
5. `G2_V2_PROJECTION`;
6. `LEGACY_PAIR_COMPATIBILITY`;
7. `G1_COMPATIBILITY_PROJECTION`;
8. `G2_V1_COMPATIBILITY_PROJECTION`;
9. `SHADOW_COMPARISON`.

Each is classified as `PRIMARY_REQUIRED`, `COMPATIBILITY_REQUIRED`,
`OPTIONAL_DIAGNOSTIC`, or `NOT_APPLICABLE`.

In legacy-primary mode, the current required GF-1/GF-2/GF-3/GF-4 stages and
legacy pair/G1/G2-v1 stages remain primary-required. GF-5C and GF-6B retain
their current failure-isolated optional-diagnostic authority. Shadow is
optional when enabled and not applicable when disabled.

In group-first-primary pre-GF-9 mode:

| Stage | Classification |
|---|---|
| Canonical catalog | Primary required |
| Discovery | Primary required |
| Signed evidence | Primary required |
| Group resolution | Primary required |
| G2-v2 projection | Primary required |
| Legacy pair compatibility | Compatibility required |
| G1 compatibility projection | Compatibility required |
| G2-v1 compatibility projection | Compatibility required |
| Shadow comparison | Optional diagnostic or not applicable |

## Readiness and failures

`ScanOrchestrationOutcome` separates:

- `primary_identity_ready`;
- `compatibility_projection_ready`;
- `visible_product_ready`;
- `shadow_diagnostics_ready`;
- failed primary, compatibility, and optional stage sets;
- one safe categorical failure classification.

Before GF-9:

```text
visible_product_ready =
    primary_identity_ready AND compatibility_projection_ready
```

Failure categories are `PRIMARY_IDENTITY_FAILED`,
`COMPATIBILITY_OUTPUT_FAILED`, `CONFIGURATION_INVALID`,
`OPTIONAL_DIAGNOSTIC_FAILED`, and `MULTIPLE_REQUIRED_STAGE_FAILURES`.

A GF-1 through GF-6 failure in group-first-primary mode means primary identity
is not ready even if every legacy stage succeeds. A legacy compatibility
failure may leave primary identity ready, but compatibility and visible product
readiness are false before GF-9. A shadow failure affects only shadow diagnostic
readiness; disabling shadow satisfies the diagnostic obligation without
requiring a result.

## Pure planning APIs and identity

`build_scan_orchestration_plan(policy)` validates the frozen policy and returns
the canonical ordered stage plan. `evaluate_scan_orchestration_outcome(plan,
stage_results)` evaluates only categorical stage completion.

Policy and plan fingerprints are SHA-256 over stable policy version, explicit
mode, primary/visible authority, stage order, and stage classification. They
exclude timestamps, secrets, providers, randomness, database identities, and
all GF-7 metrics/results. The functions perform no I/O and depend on no ORM,
repository, scan runner, current selector, product reader, or provider.

## GF-8A boundary

GF-8A adds contracts and documentation only, plus the validated but unwired
default-legacy configuration field. It adds no schema, migration, execution,
current-selection, API, frontend, export, review, advisory, pair deprecation,
provider, or secret behavior. GF-8B owns controlled execution. GF-9 owns reader
and visible-projection inversion, and GF-10 owns pair-write deprecation.

## GF-8B runtime wiring

At scan start, the runner resolves `IDENTITY_ORCHESTRATION_MODE`, builds the
frozen GF-8A policy and deterministic plan, establishes a durable RUNNING audit
row, and executes the existing narrow services in plan order. Each committed
stage produces one immutable categorical stage result. Terminal readiness is
derived by `evaluate_scan_orchestration_outcome`; the runner does not duplicate
the stage-authority matrix.

The exact `legacy_primary` order is:

```text
GF-1 catalog -> GF-2/GF-3 discovery -> GF-4 evidence
-> failure-isolated GF-5C -> failure-isolated GF-6B
-> legacy pair persistence -> G1 -> current G2-v1
-> optional GF-7B -> visible completion
```

The exact `group_first_primary` order is:

```text
GF-1 catalog -> GF-2/GF-3 discovery -> GF-4 evidence
-> required GF-5C -> required GF-6B
-> required legacy pair compatibility -> required G1 compatibility
-> required current G2-v1 compatibility -> optional GF-7B
-> visible completion
```

GF-1, discovery, evidence, GF-5C, and GF-6B retain their existing committed
immutable checkpoints. Compatibility pair/G1/G2-v1 work retains its current
atomic transaction. Consequently, a compatibility rollback does not erase a
completed resolution or v2 projection. The orchestration audit commits RUNNING
before business stages, checkpoints at most once per stage, and commits its
terminal outcome separately. Failure to establish or persist the audit fails
the scan closed.

## Durable audit contract

`scan_orchestration_run` has one unique row per scan and records mode, policy
version and fingerprint, plan fingerprint, primary pipeline, visible contract,
compatibility requirement, RUNNING/COMPLETED/FAILED lifecycle, timestamps,
four separate readiness flags, and a bounded categorical failure.

`scan_orchestration_stage_result` has one unique row per stage and execution
order within the run. It records the frozen stage identifier and authority,
SUCCEEDED/FAILED/SKIPPED/NOT_APPLICABLE status, timestamps, bounded safe
failure/diagnostic text, and a nullable stable source-run reference. References
are validated against the same scan for discovery, evidence, resolution, v2,
v1, and shadow runs. Pair work has no invented run identity.

Terminal runs and every stage row are immutable. Re-establishing the same plan
for the same scan reuses the existing run; a different plan is rejected.
Historical scans have no row, are not backfilled, and are never reinterpreted
from the current configuration. Process-crash resume is not claimed in GF-8B.

## Failure and visibility behavior

In group-first-primary mode, GF-5C or GF-6B failure leaves primary readiness
false, skips later compatibility work, fails the scan, and cannot be rescued by
G2-v1. After primary success, compatibility failure leaves primary readiness
true and its artifacts immutable, but compatibility and visible readiness are
false before GF-9. Skipped downstream work is not mislabeled as an independent
required-stage failure.

Shadow failure makes only shadow diagnostic readiness false. Shadow-disabled
plans record the stage as not applicable. Neither case changes primary,
compatibility, or visible readiness.

For both modes, `visible_projection_contract` remains `G2_V1`; G2-v2 has no
current flag. Current/latest selection, `snapshot_available`, G3 queries, G5
exports, G6 review, and G7 advisory eligibility remain v1-backed. GF-7
agreement metrics and safety deltas are never read for mode selection. Only the
explicit configured mode can select authority.
