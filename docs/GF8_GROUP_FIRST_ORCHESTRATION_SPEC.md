# GF-8 group-first scan-orchestration specification

## Scope and phase boundary

GF-8 remains one phase in the frozen GF-0 through GF-12 roadmap:

- GF-8A defines pure orchestration mode, stage-authority, readiness, failure,
  compatibility, and explicit-selection contracts.
- GF-8B may later wire controlled group-first-primary execution into normal
  scans.

GF-8A changes no scan execution, persistence, current-result selection, API,
UI, export, review, advisory, pair write, provider, or source-data behavior.

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
