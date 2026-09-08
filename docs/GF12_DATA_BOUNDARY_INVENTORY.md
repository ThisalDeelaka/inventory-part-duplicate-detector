# GF-12B1 current data-boundary and retention inventory

This is a current-code inventory, not a new retention policy. `UNSPECIFIED`
means the reviewed repository does not define a retention/deletion period or
procedure for that state. Secrets must never be stored in any listed state.

| Data state | Stored/emitted where | Production/offline | Raw description? | IDs/references? | Provider output? | Secrets? | Retention/deletion policy |
|---|---|---|---|---|---|---|---|
| Source upload bytes | Request memory in `read_csv_upload_with_metadata`; only SHA-256 and size metadata are derived | Production, transient | Yes, while parsing | Yes, while parsing | Not applicable | No | `UNSPECIFIED`; raw upload file is not stored as a file by this path |
| Canonical source records | `scan_record_snapshot` plus scan metadata in the application database | Production | Yes | Yes | No | No | `UNSPECIFIED` |
| Normalized features and pair compatibility data | Normalized catalog columns; current compatibility candidate/exclusion/semantic-profile tables where enabled | Production | Normalized description may be present; candidate rows also retain raw descriptions | Yes | Pair LLM compatibility snapshots may contain validated advisory content when separately enabled; not used by group-first deterministic decisions | No | `UNSPECIFIED` |
| Local embedding/character-vector cache | `local_embedding_cache`: record fingerprint, model version, vector JSON, state, timestamp | Production support | No raw description field | Fingerprint only | No; local deterministic vector | No | `UNSPECIFIED` |
| GF2 discovery proposals | `identity_discovery_run` and `identity_neighbor_proposal` | Production | No direct raw description field | Scan/record/proposal IDs and channel evidence | No; database constraint requires zero provider requests | No | `UNSPECIFIED` |
| GF3 neighborhoods | `identity_neighborhood_snapshot` and `identity_neighborhood_member` | Production | No direct raw description field | Yes | No | No | `UNSPECIFIED` |
| GF4 signed evidence | `identity_evidence_run` and `identity_evidence_edge_snapshot` | Production | Evidence JSON may contain derived description/technical evidence, not a dedicated raw-description column | Yes | No | No | `UNSPECIFIED` |
| GF5 resolution | `identity_resolution_*` run/group/member/conflict/deferred/targeted-evidence/constraint tables | Production | Summaries may contain bounded derived evidence; raw descriptions remain joined from the catalog | Yes | No; database constraint requires zero provider requests | No | `UNSPECIFIED` |
| GF6 projections | G2-v1 `identity_group_*` snapshots and G2-v2 `g2_v2_*` projection/group/evidence/conflict/deferred/unassigned tables | Production | Group tables use references/derived evidence; business reads join catalog descriptions | Yes | No | No | `UNSPECIFIED` |
| Review state | Append-only v1/v2 group-review event, partition, member, and human-constraint tables | Production | Review comments may contain reviewer-entered text; record descriptions remain in catalog | Yes, including reviewer identity/code and group/member refs | No | No | `UNSPECIFIED` |
| Business API/CSV exports | In-memory response payloads for System Group, Reviewed Identity, Conflict, Deferred, and compatibility diagnostics exports | Production emission | Yes for explicit business export fields | Yes | No provider credentials/config; some separate compatibility LLM exports may contain validated advisory metadata | No | `UNSPECIFIED`; response destination is caller-controlled |
| Benchmark results | Explicit operator-selected JSON/Markdown output paths from offline benchmark CLIs | Offline | Usually no raw description; varies by bounded diagnostic contract | Corpus/run IDs and fingerprints | Provider call count only for deterministic GF-12 quality baseline; no raw provider output | No | `UNSPECIFIED` |
| Benchmark truth | Synthetic generator/evaluator memory and explicit benchmark result artifacts | Offline only | Synthetic descriptions may exist in generated corpus | Synthetic row/truth group IDs | No | No | `UNSPECIFIED`; never imported by production modules |
| Blinded human-review pack | Typed in-memory/serialized `BlindedReviewPack`; no built-in writer | Offline only | Yes, allowlisted description | Stable/source-row references and dataset/review-unit IDs | No | No | `UNSPECIFIED`; no authorized non-synthetic pack exists |
| Private evaluation manifest | Typed in-memory/serialized `PrivateEvaluationManifest`; no built-in writer | Offline only, kept separate from blinded pack | No raw description field | Review/source/record refs, fingerprints, strata, bounded internal evidence | No | No | `UNSPECIFIED`; no authorized non-synthetic manifest exists |
| Human review labels/evaluation | Typed in-memory/serialized labels and `HumanPilotEvaluationResult`; no built-in writer | Offline only | No record description field | Review-unit/dataset/reviewer codes and group partitions | No | No | `UNSPECIFIED`; no real labels or human metrics exist |
| Provider credentials | Typed `SecretStr` settings and transport header construction only | Optional runtime boundary | No | Not applicable | Not applicable | Must not persist or emit | Environment/secret lifecycle is outside current repository policy; application retention is none |

## Boundary conclusions

- The database intentionally persists raw catalog descriptions and business
  identifiers needed for scan-local identity review and exports.
- Deterministic GF2/GF5 runs persist provider-request count zero; group-first
  production decisions do not persist provider output.
- Offline truth and human-label states have no production reverse-import path.
- Current export and human-review contracts are allowlisted and contain no
  credential fields.
- No automatic raw authorized-dataset commit or artifact write exists.
- Retention/deletion governance is broadly `UNSPECIFIED`; GF-12B1 records that
  gap without choosing a policy.
