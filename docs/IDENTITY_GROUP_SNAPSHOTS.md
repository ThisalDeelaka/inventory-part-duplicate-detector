# Immutable identity-group snapshots

The identity-group architecture is deliberately layered:

- G0 classifies deterministic pair edges and enforces cannot-link safety.
- G1 computes a bounded constrained group projection in memory.
- G2 persists an immutable scan-time snapshot of that projection.
- G3 exposes those persisted snapshots through a typed, read-only API.

Persisted G2 groups are scan-time hypotheses, not permanent identity truth. They
do not merge inventory, select a canonical item, or create an identity that spans
scans. Cross-scan durable identity entities are deferred until later phases.

## Snapshot contract

One `IdentityGroupProjectionRun` records the scan, projection algorithm,
classifier identifier, deterministic engine version, evidence fingerprint,
validation bound, and G1 metrics. Its accepted groups and diagnostic families
reference scan-local `ScanRecordSnapshot` rows through ordered member rows.
Accepted groups retain the exact G1 status, pair counts, evidence completeness,
reason codes, and a separate UOM/mapping summary. Conflicting, oversized, and
ambiguous families are diagnostic snapshots and never accepted groups.

Each bounded internal edge records its class, reasons, ordered endpoints, and one
of these provenance sources:

- `PERSISTED_CANDIDATE`
- `PERSISTED_EXCLUSION`
- `HUMAN_FEEDBACK`
- `G1_LOCAL_RESCORING`

G1 locally rescored internal relationships are persisted only as group-snapshot
provenance and do not become ordinary candidate rows. LLM advisory data is not
an identity-edge authority.

## Immutability, idempotency, and transactions

The idempotency identity is `(scan_id, projection_algorithm_version,
evidence_fingerprint)`. Repeating an identical projection returns the existing
run and graph. A changed deterministic evidence manifest receives a new run;
existing snapshots are never updated or overwritten.

Record, run, group, diagnostic, member, and edge rows are written in one database
transaction. Validation rejects inconsistent counts, non-canonical membership,
incomplete internal-pair evidence, or a cannot-link inside an accepted group
before commit. Any persistence failure rolls back the complete graph.

G2 is invoked through the internal snapshot service. Normal scans call that
service once after committing their deterministic evidence and before becoming
`COMPLETED`. The additive migration creates empty snapshot tables for historical
databases and does not fabricate or backfill groups for older scans.

## Normal scan orchestration

A normal completed scan now creates its initial immutable G2 identity-group
projection automatically after deterministic evidence persistence. This initial
projection is required for the group-centric UI, API, export, and review
workflow. Human review does not automatically mutate or recompute historical G2
projections; a future projection remains an explicit operation.

`snapshot_available=false` means that no projection exists. A valid projection
with zero accepted groups is different: its projection run exists and
`snapshot_available=true`.

## G3 read-only API

G3 exposes persisted scan-time hypotheses; it does not calculate, recompute, or
modify identity. Accepted groups are not confirmed duplicates, and likely status
is not a human confirmation. Conflicting, oversized, and ambiguous diagnostic
families remain separate from accepted groups. Existing pair APIs and the legacy
connected-component route remain available unchanged for compatibility and
pair-level diagnostics.

The snapshot endpoints are:

- `GET /api/scans/{scan_id}/identity-group-projections`
- `GET /api/scans/{scan_id}/identity-groups/summary`
- `GET /api/scans/{scan_id}/identity-groups`
- `GET /api/scans/{scan_id}/identity-groups/{group_snapshot_id}`
- `GET /api/scans/{scan_id}/identity-group-diagnostics`
- `GET /api/scans/{scan_id}/identity-group-diagnostics/{diagnostic_snapshot_id}`

List and detail endpoints use the latest completed projection by default. An
explicit `projection_run_id` selects only that immutable completed run; runs from
another scan are not accepted and failed runs are never substituted. Group lists
use `limit`/`offset` pagination (maximum 100), optional accepted-status and size
filters, and deterministic status/size/key ordering. Diagnostics have their own
bounded list and detail responses. Historical scans without a snapshot return a
typed empty summary/list and never trigger projection.

Group detail exposes ordered persisted members and bounded internal-edge evidence.
The UOM/mapping summary is a separate structure and is not an identity decision.
`G1_LOCAL_RESCORING` remains an explicit evidence source with no implied candidate
row. G3 provides no write, review, merge, export, UI, or LLM operation.

## G4 group-centric Scan Results

The Scan Results page now treats a persisted 2..N identity-group hypothesis as
the primary business result. Pairwise evidence remains available for diagnostics,
but users do not reconstruct groups from pair rows. The primary views are Groups,
Conflicting families, and Pair diagnostics. The older conflict-unaware connected
component view is no longer reachable from the normal workflow; its backend route
remains unchanged for transition compatibility.

The summary and first bounded group page load from G3. Group details load only on
expansion, diagnostic lists load only when their view opens, and diagnostic detail
also loads on demand. Pair candidates load only after Pair diagnostics is selected.
Filters use the G3 accepted-status and minimum/maximum-size parameters, and page
navigation preserves server ordering.

Conflicting families are separate and never presented as duplicate groups. UOM
and mapping observations are displayed separately from identity status. Historical
scans show an explicit no-snapshot state with Pair diagnostics still available;
a valid snapshot containing no groups has a distinct empty state. G4 is read-only;
group human review comes later.

## G5 group-centric CSV export

The canonical group CSV uses one row per group member, repeats group metadata,
and keeps all members adjacent. Accepted groups are ordered by likely-before-review
status, descending group size, and hypothesis key; members are ordered by their
persisted member index. The export never expands a group into N-choose-2 pair rows.

Accepted identity hypotheses and diagnostic families have separate exports:

- `GET /api/scans/{scan_id}/identity-groups/export.csv`
- `GET /api/scans/{scan_id}/identity-group-diagnostics/export.csv`

Both select the latest completed snapshot by default and accept an exact completed
`projection_run_id` belonging to the scan. They read only G2 snapshot tables and
do not project, score, retrieve, enrich, or call an AI provider. Existing pair and
saved-advisory exports remain unchanged under Pair diagnostics.

CSV does not support merged cells. Group metadata is therefore repeated explicitly
for every machine-readable member row. A later XLSX presentation may visually merge
group-level headings while preserving row-per-member data. XLSX visual grouping is
deferred to G5B because the project declares no XLSX-capable dependency.

## G6A append-only group review foundation

G6A stores human decisions against the exact immutable G2 group snapshot that
was reviewed. A decision records the scan, projection run, group snapshot,
hypothesis key, reviewer, and normalized member partitions. It never edits the
G2 snapshot, candidate pairs, exclusions, scan records, or inventory data.

The supported internal decision vocabulary is:

- `CONFIRM_ALL_AS_ONE`: one partition containing the complete group; derives a
  must-link constraint for every internal pair.
- `CONFIRM_SELECTED`: one selected partition of at least two members; derives
  must-links only within that selection and makes no claim about unselected
  members.
- `SPLIT_PARTITIONS`: an explicit, complete partition of every group member;
  derives must-links within partitions and cannot-links across partitions.
- `KEEP_ALL_SEPARATE`: singleton partitions for every member; derives a
  cannot-link for every internal pair.
- `UNSURE`: preserves the review event without deriving identity constraints.

Partition membership is validated against the immutable snapshot and bounded to
20 members (at most 190 derived pairs). Pair keys and partitions are canonical,
so derivation is independent of submitted ordering. Review rows, partitions,
members, and derived constraints are append-only. A correction creates a new
event that explicitly supersedes the current event; history is retained and only
the unsuperseded event's constraints are effective.

Human cannot-link is authoritative in a future projection and prevents
regrouping. Human must-link is strong positive evidence only when no terminal
deterministic conflict exists; it cannot override a deterministic cannot-link.
When multiple current group reviews disagree about a scan-local pair, resolution
fails explicitly instead of choosing by timestamp. The G6A adapter bulk-loads
effective constraints for an explicitly requested, in-memory future projection.
It does not run automatically, persist a replacement G2 snapshot, call an LLM,
or expose a public API or UI; those orchestration surfaces remain deferred.

## G6B typed review API and human-review UI

G6B exposes the G6A domain through typed, group-scoped history, current-state,
and create endpoints. Accepted group cards show human review separately from the
immutable system group status. Opening or saving a review does not call an AI
provider, run grouping, create another projection snapshot, update inventory, or
change the reviewed snapshot's membership.

The review UI presents all 2..N members together. `CONFIRM_SELECTED` confirms
only the chosen subset and does not classify unselected records as
non-duplicates. `SPLIT_PARTITIONS` is the canonical representation for 4+1,
2+2+1, and other group decisions: every member is assigned exactly once to one
of at least two nonempty identity sets. A split is not represented by repeated
pair clicks. The preview displays relationship counts for clarity, while the
server revalidates membership and derives the authoritative constraints.

Corrections create a new append-only event and submit the current event ID as an
optimistic-concurrency token. A stale token returns conflict and requires the UI
to reload without automatic resubmission. Historical events remain visible.
Saving a review does not automatically rerun grouping; effective constraints are
consumed only by a future explicit projection. Existing pair feedback and G5
snapshot exports remain separate and unchanged.

## G6C human-reviewed identity-decision export

The system grouped export and reviewed-decision export answer different questions.
The G5 CSV remains the immutable scan-time projection. The separate G6C CSV
overlays only the current effective human review on the selected exact G2
snapshot; it does not modify that snapshot or include superseded decisions as
current operational output.

Every accepted-group member is included and marked `NOT_REVIEWED`,
`FULLY_RESOLVED`, `PARTIALLY_RESOLVED`, or `UNSURE`. Reviewed identity-set keys
are deterministic and scoped to the scan, projection, group snapshot, review
event, and canonical partition. They are not durable cross-scan item identities.
Original group identifiers and mapping/UOM observations remain separate audit
provenance.

`CONFIRM_SELECTED` creates a reviewed set only for the selected members;
unselected records export as `UNRESOLVED_MEMBER`, never as confirmed singleton
sets. A split such as 4+1 exports as two adjacent reviewed identity sets while
preserving the original five-member group snapshot identifiers. Superseded
review events remain available through review history but do not drive this
current-state export. Exporting performs no scoring, retrieval, projection,
provider call, inventory writeback, or automatic regrouping.

## G7A group LLM safety boundary and contracts

G7A defines the central, provider-independent safety boundary for future
whole-group advisory. Only unresolved accepted
`POSSIBLE_DUPLICATE_GROUP_REVIEW` snapshots with complete evidence, real
identity ambiguity, no cannot-link or terminal identity conflict, and no current
human review may enter automatic group LLM advisory. Likely groups, diagnostic
families, mapping-only uncertainty, and scope or administrative uncertainty are
ineligible. Provider choice occurs strictly downstream of this gate.

An eligible snapshot produces one bounded `group-advisory-request-v1` contract
for the complete 2..N group, not N-choose-2 provider calls. The request contains
only canonical persisted member identity fields, every checked internal edge,
separate identity and UOM/mapping summaries, and bounded unresolved identity
questions. UOM and mapping differences are contextual evidence and never have
identity authority. Canonical JSON and SHA-256 provide an order-independent
request fingerprint without provider, credential, timestamp, retry, or random
runtime data.

`group-advisory-result-v1` permits only `SUPPORTS_SINGLE_IDENTITY`,
`PROPOSES_PARTITION`, or `INCONCLUSIVE`. A resolved proposal must cover every
immutable member exactly once; an inconclusive result must contain no partition.
Untrusted output is strictly parsed and checked against the exact group and
request fingerprint. Unknown, duplicate, missing, or empty members, invalid
outcome structure, extra authority fields, or a partition that crosses a
protected cannot-link normalize to a clean `INCONCLUSIVE` result. Every result
keeps deterministic evidence authoritative and requires human review; it never
merges, deletes, writes back, or changes G2/G6 state.

G7A performs no provider invocation and adds no advisory persistence, API, or
UI. Existing pair-level LLM code remains transitional advisory infrastructure
and is unchanged while whole-group execution is deferred to a provider-neutral
future phase.

## G7B provider-neutral group execution

G7A decides whether a group may reach AI. G7B only executes an already-approved,
bounded request. Production orchestration builds the request through the G7A
gate, fingerprints it, rechecks eligibility and the immutable fingerprint
immediately before invocation, and then passes the whole request to a
group-capable provider adapter. Provider selection is downstream of eligibility
and cannot alter deterministic evidence or human authority.

One 2..N group is one provider inference unit. Internal edge summaries remain
evidence inside that one request; they are never expanded into N-choose-2
provider calls. The provider-neutral message and structured-output contracts use
only the G7A-minimized fields. Semantic result validation remains central and
cannot be replaced by an adapter.

Runtime execution distinguishes provider-disabled, rate-limited, timed-out,
retryable failure, terminal failure, circuit-open, invalid output, model
inconclusive, and successful validated advisory states. None is identity truth.
Only centrally validated results may enter the process-local group cache, whose
key includes the immutable request fingerprint, provider, model, and prompt
contract version. Pair candidate cache and persistence are not reused.

G7B includes only a disabled provider and test providers. It performs no real
network request and adds no group advisory persistence, API, or UI. Those remain
deferred until a real group-capable provider is independently benchmarked.

## G7C experimental Groq group benchmark adapter

G7C adds Groq only as an experimental whole-group benchmark adapter. The
default `GROUP_LLM_PROVIDER` remains `none`, independently of pair-level LLM
configuration. Existing Groq transport was chosen first to reduce integration
uncertainty—not because Groq has been selected as the best model or provider.
The adapter composes the existing tested JSON transport without changing its
pair behavior, while eligibility, retries, fingerprint guards, and semantic
validation remain in G7A/G7B.

The benchmark uses 30 fixed, fingerprinted, explicitly curated synthetic cases:
12 single-identity cases, 8 ordinary partition cases, 4 safe-abstention cases,
and 6 validator safety challenges. Sizes 2, 3, 4, 5, and 7 are represented,
including 4+1 and 2+2+1 partitions. Safety challenges cover rotor/stator,
top/component, DE/NDE, inlet/outlet, serial/non-serial, and Circuit Board
01/02. Their labels are benchmark truth separate from production snapshots and
are never inferred from model output or G1 review status.

Live execution is available only through the explicit command
`python -m app.llm.group_benchmark_cli --live --corpus curated-v1 --max-calls 30
--output <ephemeral-report.json>` while group-specific runtime configuration is
explicitly `groq`. Ordinary startup and tests never import that command or call
the provider. Reports contain case IDs, fingerprints, expected and validated
outcomes, validity/usefulness classes, timing, attempts, byte counts, and token
usage when returned; they contain no credentials and do not invent cost.

Group advisory persistence, API, UI, automatic triage, and default provider
selection remain deferred. A future Cerebras adapter must be evaluated against
the same cases, fingerprints, contracts, and safety metrics before any provider
choice is considered.

### Benchmark failure observability

A benchmark with zero successful transport responses is not a semantic model
benchmark. Every case that enters the runner remains a first-class report record
even when authentication, permission, invalid-request, model, rate-limit,
timeout, network, server, malformed-response, or other provider execution fails.
Diagnostics retain only bounded safe categories, HTTP status where available,
exception type, fixed sanitized messages, attempts, timing, and byte counts.
They never retain headers, credentials, raw exception text, or arbitrary provider
response bodies.

Request bytes are measured before transport from the secret-free serialized
provider payload. Failed responses may legitimately have no response-byte or
token measurements. The existing shared Groq transport exposes safe HTTP status
but intentionally discards provider response bodies, so provider error-body
type/code/message fields remain unavailable rather than being guessed. A 404 is
treated as model-unavailable; an otherwise undifferentiated 400 remains an
invalid request.

Provider-call count and benchmark-case count are different: a bounded retry is
another transport call attached to the same case and may consume the call cap
before every corpus case begins. For example, 30 calls can represent 29 cases
and one retry. The existing hard maximum remains 35 so a later explicit run can
cover the fixed 30-case corpus with a small retry allowance. Benchmark
diagnostics do not change any provider default.

### G7C-D3 contract alignment and controlled evaluation

The first live Groq run confirmed transport reachability but exposed strict
result-contract mismatches and material rate limiting. All eleven returned JSON
objects failed the authoritative result schema and therefore normalized safely;
the sanitized D2 artifact did not retain raw provider prose or field-level
Pydantic detail, so no narrower historical schema error is inferred. G7C-D3
aligns the provider-facing output instructions with the exact G7A result fields,
immutable identifier echoes, outcome-specific partition rules, human-review
requirement, and deterministic-authority requirement without weakening central
validation.

Invalid benchmark responses retain only bounded G7A validation reason codes.
Raw model prose and validation inputs are not diagnostic fields. Wrong request
fingerprints or group identifiers, missing, unknown, or duplicate members,
invalid partition shapes, extra fields, field bounds, and protected cannot-link
violations remain invalid and normalize to inconclusive.

The explicit benchmark CLI accepts `--case-delay-ms` (default `0`, bounded from
0 through 300000) to pause between logical whole-group cases. It also accepts
`--max-cases` to select a deterministic prefix of the fixed corpus; by default
the whole selected corpus remains eligible. Subsetting never changes case truth,
labels, requests, or fingerprints, and `--max-calls` remains the hard transport
cap. Retry counts remain bounded, and safe provider Retry-After delays share the
benchmark sleeper with logical-case pacing.

Benchmark pacing and subsetting exist only to make controlled provider
evaluation reliable; they do not alter production group execution or pair LLM
execution. Groq remains a reference provider. Claude and future providers must
use the same G7A/G7B contracts, central validation, and benchmark semantics.

### G7C-D5 safe schema diagnostics

G7C-D5 adds field-name-only schema diagnostics for rejected provider JSON while
intentionally withholding provider values and raw response bodies. The broad
`SCHEMA_MISMATCH` outcome remains stable, while supplemental bounded categories
identify missing, unexpected, wrong-type, invalid-literal, invalid-length,
invalid-format, and otherwise unclassified schema paths. Paths are sanitized,
deduplicated, sorted, and capped; parser messages and rejected values are never
stored in case records, aggregate reports, logs, or CLI summaries.

The diagnostic layer is derived from the authoritative G7A
`GroupAdvisoryResult` parser and is provider-neutral, so it will also support
future Claude and Cerebras integration. A generated provider-facing JSON
skeleton and consistency tests keep the prompt-visible required fields aligned
with that result model. This does not coerce rejected values or relax identifier,
partition, authority, or cannot-link validation.

Groq remains a reference provider; G7C-D5 does not attempt broad Groq
optimization or change any provider default, production execution, persistence,
API, or UI behavior.
