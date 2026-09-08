# GF-12C1 showable working product demo contract

Milestone: `SHOWABLE WORKING PRODUCT / DEMO READINESS`

> **DEMO DATA IS SYNTHETIC.**
>
> **NOT HUMAN-QUALITY VALIDATION EVIDENCE.**
>
> **THIS CONTRACT DOES NOT GRANT PRODUCTION DEPLOYMENT APPROVAL.**

## Product-owner sequencing decision

The current goal is a complete local working product that can be shown end to
end. Deployment architecture, tenancy, an IAM/authorization platform, managed
production storage, cloud/platform deployment, external integrations,
production network and retention policy, and reference production hardware are
deferred until after this milestone. They are deferred—not completed or waived.

GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`. The GF-11 performance waiver
remains active, `GF11-PERF-100K-COLD-FULL` remains open, and the 300-second
target remains unmet.

## Acceptance contract

On the supported local frontend/FastAPI execution model, the demo must prove:

1. a user can upload the repository-owned synthetic inventory CSV;
2. the system starts and completes a `group_first_primary` scan;
3. equivalent fresh runs produce the same semantic product result;
4. duplicate identity groups—not pair rows—are the primary result;
5. accepted/review identity groups contain 2..N records;
6. conflict, deferred, and unassigned outcomes remain distinct;
7. legacy pairs remain optional advanced diagnostics only;
8. a user can inspect all group members and persisted validation evidence;
9. a user can create and correct an append-only group review;
10. System Group Export returns authority-selected member-shaped groups;
11. Reviewed Identity Export contains only a current confirmed human review;
12. failed/incomplete scans cannot expose a final identity result or export;
13. pair and group provider modes remain `none`, with provider calls zero; and
14. no automatic merge, deletion, source rewrite, or ERP/IFS writeback occurs.

## Selected fixture and parameters

- Path: `data/llm_assisted_mvp_demo.csv`
- Authorization: `SYNTHETIC_ONLY / AUTHORIZED_FOR_DEMO`
- Human-quality authorization: **not authorized**
- Records: **17**
- Mode: `SAME_SITE_DUPLICATE`
- Selected conditions: `CONTRACT`, `UNIT_MEAS`
- Threshold: `75`
- Orchestration: `group_first_primary`
- Pair provider: `none` and disabled
- Group provider: `none`

The third motor variant is explicit demo/test data used to demonstrate a
three-member identity hypothesis. It changes no production threshold or
algorithm.

## Scenario coverage

| Scenario | Result |
|---|---|
| Clear size-2 duplicate group | Available: mechanical seal identity group |
| Duplicate group size >=3 | Available: three same-site 10 kW motor records |
| Nonduplicate/unique item | Available among records left safely unassigned; unassigned does not mean confirmed unique |
| Cautious/conflict/deferred case | Three conflict outcomes are visible; deferred count is zero and the empty deferred state remains distinct |
| Cross-site duplicate identity | `NOT_AVAILABLE_IN_CURRENT_DEMO_FIXTURE` |
| Review-required group | Available: three review-status groups, including the size-3 motor group |

## End-to-end flow and integration map

| Demo action | Frontend | API | Classification |
|---|---|---|---|
| Start application | Vite root | `/health`, `/ready` | `WORKING` |
| Load/validate inventory | `/new-scan` | `POST /api/scans/validate-only` | `WORKING` |
| Submit group-first scan | `/new-scan` | `POST /api/scans/upload` | `WORKING` — synchronous request returns after completion |
| Open result | `/scans/{scan_id}` | `GET /api/scans/{scan_id}` and `/identity-read/summary` | `WORKING` |
| View groups | primary Identity Groups tab | `/identity-read/groups` | `WORKING` |
| Inspect group details/evidence | expand identity set | `/identity-read/groups/{versioned_group_key}` | `WORKING` |
| View conflicts/deferred | Conflicts & Deferred tab | `/identity-read/outcomes` | `WORKING` |
| Read/create/correct review | Group Review panel | versioned `/reviews`, `/reviews/current` | `WORKING` |
| Export System Groups | header action | `/identity-read/system-groups/export.csv` | `WORKING` |
| Export Reviewed Identities | header action | `/identity-read/reviewed-identities/export.csv` | `WORKING` — empty until a current confirmed review exists |
| Export conflicts/deferred | conditional header actions | `/identity-read/conflicts|deferred/export.csv` | conflicts `WORKING`; deferred `NOT_APPLICABLE` for this zero-deferred run |
| Inspect pair evidence | Advanced diagnostics only | `/candidates` | `NOT_REQUIRED_FOR_DEMO` and not a product fallback |

## Verified result contract

Each of three fresh scans must reconcile to:

| Evidence | Expected |
|---|---:|
| records | 17 |
| scan status | `COMPLETED` |
| `visible_product_ready` | `true` |
| GF2 proposals | 10 |
| GF3 neighborhoods | 17 |
| GF4 status / persisted evidence | `COMPLETED` / 10 |
| GF4 strong / review / cannot-link / non-groupable | 2 / 4 / 3 / 1 |
| GF5 accepted / likely / review | 4 / 1 / 3 |
| GF5 conflict / deferred / unassigned | 3 / 0 / 8 |
| GF6 accepted / likely / review | 4 / 1 / 3 |
| GF6 conflict / deferred / unassigned | 3 / 0 / 8 |
| provider calls | 0 |

Scan IDs, timestamps, database IDs, opaque group keys, and persisted per-scan
fingerprints legitimately differ. DEMO19-DEMO22 compute an offline
production-semantic fingerprint from the authority-selected summary, group
status/validation mode, source row identity, and normalized member evidence;
they also normalize System Group Export to the same scan-independent member
identity. All three must match. This validation fingerprint does not alter or
replace production persistence.

The three verified demo production-semantic fingerprints are identical:

```text
23b062eeb0558152fcac4097b0432b63fc49c19ccb7f414ae844e1f7cd2ae5ec
23b062eeb0558152fcac4097b0432b63fc49c19ccb7f414ae844e1f7cd2ae5ec
23b062eeb0558152fcac4097b0432b63fc49c19ccb7f414ae844e1f7cd2ae5ec
```

## Presentation guard and open boundaries

The primary UI says “Potential duplicate identities,” displays whole 2..N
groups, and explicitly states that a group is not a collection of A/B
decisions. Legacy pair diagnostics are under Advanced diagnostics and cannot be
used as a fallback when authority-selected reads fail.

The old pair-centric `docs/demo_script.md` is superseded for this milestone by
`GF12_DEMO_PRESENTER_SCRIPT.md`. Production deployment, human-quality signoff,
1M readiness, multi-tenancy/IAM, durable resume, production cancellation and
timeout support, and satisfaction of the GF-11 300-second target are not
claimed.
