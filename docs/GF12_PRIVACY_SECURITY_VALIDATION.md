# GF-12B1 privacy, security, and data-boundary validation

## Scope and authority

GF-12B1 is a bounded validation baseline over the current group-first
implementation. It does not redesign security, select or call a provider,
authorize a dataset, change production decision semantics, or graduate GF-12.
The review followed `PROJECT_SSOT.md`, the group-first ADR/domain contracts and
roadmap, the active GF-11 waiver, the GF-12 validation and human-review
contracts, and the architect workflow.

The roadmap authorizes independent GF-12 work including **"safety, privacy and
security"** and requires **"Security, privacy, tenancy, authorization, and
export review."** This baseline is the smallest independent unit covering those
boundaries while the human-review dataset remains unavailable.

## Boundary map

| Boundary | Data entering | Data leaving | External transmission | Secrets/config in output | Raw descriptions/IDs | Mode |
|---|---|---|---|---|---|---|
| B1 production input -> internal processing | Multipart CSV bytes, selected fields, column mapping, scan options | Validated dataframe, bounded column samples, file fingerprint, persisted scan/catalog records | No | No configuration is derived from record content | Descriptions and business IDs enter and selected catalog fields persist | Production |
| B2 production processing -> provider | Only an eligible, immutable group advisory request after the G7A gate; pair/demo LLM paths are separate compatibility features | Validated advisory or fixed safe failure metadata | Only when an explicitly selected enabled provider is invoked; default group provider `none` transmits nothing | Credentials are transport headers only and are absent from request bodies/results; provider/model identifiers may be operational metadata | Eligible advisory requests contain bounded record identity evidence, including descriptions/identifiers defined by the group contract | Optional provider boundary; deterministic production remains provider-free |
| B3 production result -> review/read/export | Authority-selected G2 snapshot, current review chain, catalog members | Typed API objects and explicit CSV field allowlists | No | No keys, tokens, headers, or environment values | Yes, approved business exports contain record references, part numbers, descriptions, and selected context | Production |
| B4 production result -> offline benchmark | Persisted/reconstructed authority-selected production snapshot | Deterministic quality metrics/fingerprints compared with separate synthetic truth | No | No | Production references and evaluated group membership; truth stays evaluator-side | Offline only |
| B5 production result -> blinded human tooling | Authority-selected snapshot plus separately supplied allowlisted record views | Blinded pack and separate private evaluation manifest | No writer or transmission exists | No | Blinded pack contains the approved minimum identity-review fields; manifest contains references and bounded evaluation metadata | Offline only |
| B6 configuration/log/error -> visible/persisted output | Typed settings, provider exceptions, operational failure categories | Status metadata, fixed safe HTTP errors, safe persisted error categories | No additional transmission | Provider/model identity may be visible; secret values, credential objects, environment dumps, and authorization headers are excluded | Fixed error paths do not dump records; legitimate record references remain permitted by existing diagnostics contracts | Production and offline diagnostics |

## Validation results

### Provider isolation

- `GROUP_LLM_PROVIDER` still defaults to `none`.
- The `none` factory branch returns `DisabledGroupAdvisoryProvider` without
  consulting a key or invoking the supplied HTTP client.
- Discovery and resolution persistence constrain provider request counts to
  zero, and the deterministic scan runner does not dispatch group providers.
- Groq and Claude adapters are downstream of explicit group-provider selection.
  They were inspected but never invoked.
- GF-12 benchmark and human-review modules have no provider factory, provider
  SDK, or network imports.

Provider calls made during GF-12B1: **0**.

### Synthetic secret sentinel

Only the in-test value `SYNTHETIC_TEST_SECRET_DO_NOT_EXPOSE` was used. It was
absent from the LLM status response, safe typed errors, business-export field
sets, blinded pack, private manifest, offline evaluation JSON, and captured
logs. No `.env`, real credential, authorization header, token, or live provider
configuration was read.

### Logging and errors

The application has no general record/config dump logger in the inspected scan
and group paths. LLM exceptions are translated into fixed category/message
payloads; group execution similarly persists fixed safe codes/messages rather
than exception text.

| Field class | Current examples | Boundary decision |
|---|---|---|
| `SAFE_OPERATIONAL` | status, provider/model identity, request ID, counts, durations, safe error category, bounded record reference | Permitted where the existing typed contract requires it |
| `SENSITIVE_DATA` | part number, description, site/contract, UOM, reviewer/comment, source row reference | Present only in explicit input/catalog/review/export contracts; not emitted by generic failure handling |
| `SECRET` | provider key, authorization header, token, full environment/config dump | Not present in reviewed visible, persisted error, export, benchmark, or human-review artifacts |

### Human-review minimization and private manifest

The blinded record allowlist is exactly: stable record reference, source-row
reference, part number, description, product category, HSN/SAC, optional
site/contract, and optional UOM. Pack serialization excludes system status and
score, retrieval/fusion data, GF4/GF5 decisions, benchmark truth/labels,
sampling stratum, internal evidence, provider config, and secrets.

The private manifest is separate and limited to dataset/contract identity,
evidence classification, production fingerprint, fixed seed, review-unit/source
references, source record references, system status/grouping, sampling stratum,
bounded internal evidence, counts/shortages/exclusions, and pack/manifest
fingerprints. It contains no raw record descriptions and no credential fields.

### Export, review, and read boundary

System Group, Reviewed Identity, Conflict, and Deferred exports use explicit
field lists and spreadsheet-formula cell escaping. Benchmark truth/evaluation
and GF-12 offline human-label fields are absent. The Reviewed Identity Export
does include the production operational review chain by design; this is distinct
from the offline GF-12 blinded-pilot labels. Pair diagnostics remain separate
compatibility/diagnostic routes and are not projected as primary group entities.
All reviewed functions consume persisted records without mutating source rows.

### Benchmark isolation

Production modules contain no `app.benchmarks` reverse import. Truth, GF-12
quality evaluation, and human-review evaluation therefore cannot influence
production discovery, evidence, resolution, projection, or exports. Offline
modules consume authoritative production output only after production execution.

### File and output safety

Human-review tooling serializes typed values but has no filesystem writer.
Dataset IDs are constrained to a safe code alphabet and traversal identifiers
fail closed; review-unit IDs are generated as `hru-` plus a fixed hexadecimal
fingerprint. Source unit references and record contents never become output
paths. Existing benchmark CLIs write only to an explicit operator-supplied
destination and do not derive destinations from dataset records. No raw dataset
is automatically written or committed.

### Input-surface sanity

Empty/malformed upload input produces a controlled HTTP 400; a parseable CSV
missing required columns returns a typed invalid validation result. Unexpected
columns remain data/diagnostic samples and do not become settings. A record
column named like the known group-provider selector cannot alter the immutable
settings object, and record/source identifiers cannot alter an output path.
Pack/evaluation operations leave input dataclasses unchanged.

## Findings

No `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` finding was evidenced.

- `OBSERVATION`: retention/deletion policy is `UNSPECIFIED` for current
  persisted production states and emitted offline artifacts.
- `OBSERVATION`: the repository does not define a single approved filesystem
  root for operator-directed benchmark CLI outputs. These paths are explicit
  operator inputs, not record-derived paths; human-review tooling performs no
  write. A future artifact-runner unit should define operational destination
  governance before handling an authorized non-synthetic dataset.
- `OBSERVATION`: tenancy and authorization enforcement are not represented as a
  distinct application policy layer in the current local MVP. This baseline
  makes no deployment-readiness claim.

None of the observations is evidence of secret leakage, provider dispatch under
provider-none, reverse truth/label influence, unauthorized transmission, or
record-controlled path traversal.

## Test evidence

`backend/tests/test_gf12_privacy_security.py` implements PS1-PS24: provider-none
default/call isolation; benchmark and human-tool provider isolation; secret
absence across API, exports, artifacts, evaluation, logs, and errors; no
environment dump; blinded/private allowlists; export exclusions; reverse-import
isolation; safe artifact identifiers/traversal rejection; controlled input
failure; config/path non-influence; source immutability; and repository-diff
guards for schema/dependencies/production semantics.

Focused result: **24 passed**. Full backend result: **1,317 passed, 15 skipped**
(optional sparse-dot coverage), with one existing pytest configuration warning.
The data-retention gaps are inventoried in
`docs/GF12_DATA_BOUNDARY_INVENTORY.md` and remain `UNSPECIFIED`, not invented.
