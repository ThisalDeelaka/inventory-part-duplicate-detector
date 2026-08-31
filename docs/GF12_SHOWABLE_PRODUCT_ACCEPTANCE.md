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
| Real target CSV end-to-end product | `PASS` | R4 preserves existing GF5 cap semantics and completes the unchanged 5,327-row target through authoritative GF6 with `visible_product_ready=true` |
| Scan completes | `PASS` | Three fresh group-first scans `COMPLETED` |
| Authoritative group result displays | `PASS` | Identity-read summary/list/detail and group-first Scan Results UI |
| 2..N semantics visible | `PASS` | Size-2 groups plus one size-3 motor group |
| Conflict/deferred visibility | `PASS` | 3 conflicts and explicit zero-deferred state |
| Review read path works | `PASS` | Versioned current/history route |
| Review create/update works | `PASS` | Append-only create, Unsure correction, and restored confirm-all current event |
| System Group Export works | `PASS` | 9 member rows plus header; member-shaped, group-first |
| Ordinary New Scan selects current authority | `PASS` | Typed browser/API selection persists policy-v2, group-first primary, and G2-v2 even under legacy configuration default |
| Microsoft Excel table/filter compatibility | `PASS` | Group Data table owns one AutoFilter; package-level and round-trip regressions cover the reported repair defect |
| Fresh real G2-v2 API/CSV/XLSX parity | `PASS` | Scan 27: 207 groups and 440 member rows match across the exact authority-selected snapshot and exports |
| R6 fresh real-output quality canary | `FAIL` | Historical Q2 finding: tyre subtype, wheel/tyre, and dirty carbon-stick/pencil false review groups |
| R7 corrected real-output quality canary | `PASS` | Scan 29 removes all three false groups through protected GF4 contradictions, preserves F30/B38 controls, and has no surviving group with the new contradiction |
| R9 bounded D1-D4 correction | `PASS` | Scan 30 safely separates all four R8 false-group families; R7 controls remain safe and no accepted group contains protected endpoints |
| R9 repeated semantic freeze audit | `FAIL` | A distinct left-side/right-side shock abbreviation group remains under a copied description; classification is `R9_QUALITY_CORRECTION_PARTIAL_NEW_BLOCKER` |
| R10 directional-side target | `PASS` | Scan 31 places the LEFT/RIGHT shock pair in a protected conflict; no accepted group contains a side contradiction |
| R10 repeated semantic freeze audit | `FAIL` | The directional implementation is verified; a distinct BUFFER01/MIRROR01 copied-description false group still blocks overall freeze |
| R12 final freeze-only real audit | `FAIL` | Exact product/export authority and package guards pass, but four likely false groups block freezing the full-real demo candidate |
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
  VERIFIED FOR SYNTHETIC DEMO AND REAL-TARGET END-TO-END EXECUTION

DEMO-READY:
  SYNTHETIC PATH YES; FULL-REAL FREEZE NO

PRODUCTION DEPLOYMENT READY:
  NO CLAIM

FINAL HUMAN-QUALITY SIGNOFF:
  PENDING

GF-11 PERFORMANCE DEBT:
  OPEN
```

This checklist does not mark GF-12 production validation complete.

R6 proves the interactive authority and XLSX repair, but its read-only real
quality canary is `Q2_DEMO_QUALITY_NEEDS_BOUNDED_CORRECTION`. The synthetic demo
acceptance remains verified; the fresh real workbook must not be frozen as the
demo candidate until the three documented deterministic review-group patterns
receive a separate bounded correction. GF-12A2 remains
`HUMAN_REVIEW_DATASET_REQUIRED`.

R7 resolves the three documented R6 deterministic false-group patterns without
changing retrieval, GF5 thresholds/caps, projection, review, or export
authority. Fresh scan 29 is `Q1_DEMO_QUALITY_PLAUSIBLE` and has exact G2-v2
API/CSV/XLSX parity. Product-owner workbook inspection and GF-12A2 human-label
validation remain required before any broader accuracy claim.

Real-target character retrieval remains verified without fabricated neighbors
or an exact large-N fallback. R4 corrects the GF5 runtime blocker by enforcing
the existing candidate-generation exhaustion result before discarded candidate
construction. The real scan completes GF5 and authoritative GF6 with zero
provider calls. No retrieval threshold, candidate budget, resolver bound,
identity semantics, cannot-link rule, or group-first authority was weakened.
This verifies executable product flow, not human-reviewed accuracy, deployment
readiness, GF-11 graduation, or GF-12 completion.

R9 corrects the four R8 detector-quality targets through bounded deterministic
identity semantics and preserves exact scan-30 G2-v2 API/CSV/XLSX membership.
The repeated 45-group audit still contains one likely false group caused by a
separate left-side/right-side shock abbreviation extraction gap. Consequently
the synthetic product remains showable and the real end-to-end path remains
executable, but the fresh real result is not a frozen demo candidate. No Reason
polish is authorized. GF-12A2 human validation, GF-11 performance debt, and
deployment/integration remain open.

R10 safely corrects the directional-side family without broad side inference or
front/rear semantics. Fresh scan 31 remains operationally showable and export-
consistent, but its repeated semantic audit identifies a separate buffer-versus-
mirror false group. The real result is not a frozen demo candidate, but R10A
authorizes committing the independently verified directional implementation.
No Reason or presentation change is authorized.

R11 safely closes the proven buffer/mirror family using two reusable bounded
object classes and one explicit incompatibility relation. The repeated
46-group audit has D=0, provider calls are zero, and exact G2-v2 CSV/XLSX parity
holds. This is `R11_QUALITY_PASS_READY_FOR_FINAL_FREEZE`; it authorizes one
freeze-only audit with no further detector changes. It does not complete
GF-12A2 human validation, GF-11 performance graduation, deployment, tenancy,
IAM, storage, or integration readiness.

R12 performs the authorized freeze-only audit without changing detector
semantics. Its exact current-product G2-v2 product path, API/CSV/XLSX parity,
workbook package, provider-none boundary, and deterministic internal safety
sweep pass. The complete flagged-group inspection nevertheless finds four
likely false identity groups outside the successive bounded vocabularies.
Therefore the synthetic path remains showable and the full-real path remains
executable, but the full-real candidate is not frozen and must not be described
as demo-ready. The architecture/evidence boundary requires reassessment before
further semantic expansion.

R13 completes the architecture reassessment without changing production
semantics. It confirms that the R12 failures arise from broad lexical support
and narrow ontology-dependent contradiction evidence, selects source-aware
identity signatures plus a GF4 identity-support gate, and classifies ontology
as supporting rather than primary. Offline experiments prove the direction but
also show that a crude token gate would overcorrect known-positive groups.
Accordingly only pure seam/contracts and golden cases are authorized next. The
full-real detector remains unfrozen and must not be called demo-ready; synthetic
showability, GF-11 debt, GF-12A2 human validation, and deferred deployment/
integration statuses are unchanged.
