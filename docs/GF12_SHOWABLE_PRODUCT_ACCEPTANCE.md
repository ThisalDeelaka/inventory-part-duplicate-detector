# GF-12C1 showable product acceptance checklist

Allowed statuses: `PASS`, `FAIL`, `NOT_APPLICABLE`, `DEFERRED_POST_DEMO`,
`EXTERNAL_EVIDENCE_REQUIRED`.

| Acceptance item | Status | Evidence |
|---|---|---|
| Backend starts | `PASS` | Local provider-none Uvicorn startup and `/health`/`/ready` smoke |
| Frontend starts | `PASS` | Vite local startup smoke and production build |
| Demo dataset loads | `PASS` | 17-row explicitly synthetic CSV through validate/upload API |
| Synthetic demo browser-default mapping | `PASS` | New Scan multipart defaults; no hidden explicit mapping in acceptance helper |
| Real target CSV intake | `PASS` | Unchanged 5,327-row historical file validates through browser/API contract |
| Real target character retrieval | `PASS` | Three deterministic runs; 5,324 full-K anchors, 3 legitimate zero-neighbor anchors, zero failures |
| Real target CSV end-to-end product | `FAIL` | Corrected scan crossed character retrieval but remained nonterminal beyond 900 seconds |
| Scan completes | `PASS` | Three fresh group-first scans `COMPLETED` |
| Authoritative group result displays | `PASS` | Identity-read summary/list/detail and group-first Scan Results UI |
| 2..N semantics visible | `PASS` | Size-2 groups plus one size-3 motor group |
| Conflict/deferred visibility | `PASS` | 3 conflicts and explicit zero-deferred state |
| Review read path works | `PASS` | Versioned current/history route |
| Review create/update works | `PASS` | Append-only create, Unsure correction, and restored confirm-all current event |
| System Group Export works | `PASS` | 9 member rows plus header; member-shaped, group-first |
| Reviewed Identity Export authority | `PASS` | Header-only before/Unsure; 3 member rows only after current confirmed review |
| Failure boundary safe | `PASS` | Controlled synthetic failed scan is non-authoritative; final read/export return 409 |
| Pair provider none | `PASS` | `LLM_DEMO_ENABLED=false`, `LLM_PROVIDER=none` |
| Group provider none | `PASS` | `GROUP_LLM_PROVIDER=none` |
| Provider calls zero | `PASS` | GF2/GF5 persisted zero-provider constraints across all three runs |
| No secret/config leakage | `PASS` | Synthetic sentinel absent from health/readiness/status/results/exports |
| No automatic merge/delete/writeback | `PASS` | Product contract and implementation boundary |
| Three-run deterministic demo | `PASS` | Equal offline production-semantic fingerprint, membership/status signature, and normalized export identity |
| Demo operator runbook | `PASS` | `docs/GF12_DEMO_RUNBOOK.md` |
| Presenter script | `PASS` | `docs/GF12_DEMO_PRESENTER_SCRIPT.md` |
| Cross-site duplicate in selected fixture | `NOT_APPLICABLE` | `NOT_AVAILABLE_IN_CURRENT_DEMO_FIXTURE` |
| Deployment/IAM/tenancy/storage/integration | `DEFERRED_POST_DEMO` | Product-owner sequencing decision; not marked complete |
| Representative human-quality validation | `EXTERNAL_EVIDENCE_REQUIRED` | GF-12A2 `HUMAN_REVIEW_DATASET_REQUIRED` |
| GF-11 300-second debt | `EXTERNAL_EVIDENCE_REQUIRED` | Waiver active, debt open, target not met |

## Milestone wording

```text
SHOWABLE WORKING PRODUCT:
  VERIFIED FOR SYNTHETIC DEMO; REAL TARGET E2E BLOCKED

DEMO-READY:
  YES

PRODUCTION DEPLOYMENT READY:
  NO CLAIM

FINAL HUMAN-QUALITY SIGNOFF:
  PENDING

GF-11 PERFORMANCE DEBT:
  OPEN
```

This checklist does not mark GF-12 production validation complete.

Real-target character retrieval is verified without fabricated neighbors or an
exact large-N fallback. The end-to-end real scan remains blocked by a separate
nonterminal runtime beyond 900 seconds. No retrieval threshold, candidate budget,
identity semantics, or group-first authority was weakened to hide it.
