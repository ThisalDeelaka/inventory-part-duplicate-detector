# PRM-5 CEO Demo Runbook

## Frozen demo baseline

Use branch `llm-assisted-mvp` at the PRM-5 freeze commit. The primary path uses
saved scan **31**, `R10 directional-side corrected real verification`. It is a
completed 5,327-record `group_first_primary` result whose visible authority is
`G2_V2`. Do not describe it as a live full scan and do not rerun it.

The optional live fixture is `data/llm_assisted_mvp_demo.csv` (17 synthetic
records). It is a disposable demonstration path, not a quality benchmark.

## Pre-demo checklist

- [ ] Confirm the frozen branch and commit; confirm `deterministic-demo-v1` is unchanged.
- [ ] Confirm the protected XLSX remains untracked and unchanged.
- [ ] Confirm no secret or `.env` content is displayed or inspected.
- [ ] Stop any stale local backend/frontend processes on ports 8000 and 5173.
- [ ] Start both services with the commands below; provider settings remain disabled.
- [ ] Open `http://127.0.0.1:5173/` and confirm Dashboard, Latest scan, Recent scans, and New Scan render.
- [ ] Confirm scan 31 appears in history and opens without a manually typed result URL.
- [ ] Confirm the summary, System explanation, and Human decision controls render.
- [ ] Confirm System Group Export downloads and Reviewed Identity Export accurately reports that no confirmed sets exist on scan 31.
- [ ] Keep `data/llm_assisted_mvp_demo.csv` ready only if the optional live scene is used.
- [ ] Set browser zoom to 100%; check the demonstrated desktop width for overlap or clipping.
- [ ] Confirm no mojibake, console-breaking error, failed API request, or stale loading state appears on the scripted path.
- [ ] Confirm provider calls remain 0 and provider execution remains disabled.

## Start commands

Backend, in one PowerShell terminal:

```powershell
cd "C:\Users\ThisalDeelaka\OneDrive - SEBSA World\Desktop\SEBSA External Proj\inventory-part-duplicate-detector\backend"
$env:IDENTITY_ORCHESTRATION_MODE="group_first_primary"
$env:GROUP_LLM_PROVIDER="none"
$env:LLM_DEMO_ENABLED="false"
$env:LLM_PROVIDER="none"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend, in a second PowerShell terminal:

```powershell
cd "C:\Users\ThisalDeelaka\OneDrive - SEBSA World\Desktop\SEBSA External Proj\inventory-part-duplicate-detector\frontend"
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Do not open, copy, or display `.env`; the explicit non-secret settings above keep
provider execution disabled.

## Routes and seven-minute sequence

| Time | Scene | Route/action | Expected screen and message |
|---|---|---|---|
| 0:00-0:35 | 1. Dashboard | `/` | Latest scan, Recent scans, and New Scan. Results persist and reopen from history. |
| 0:35-1:45 | 2. Optional live scan | `/scans/new`; choose `data/llm_assisted_mvp_demo.csv` | Map fields, validate until **Validation passed**, Run Scan, show truthful Processing/elapsed state, then normal result navigation. |
| 1:45-2:55 | 3. Full result | Return to `/`; open scan 31 from Recent scans | 5,327 records; 203 groups: 114 Likely, 89 Review, 30 Conflict, 30 Deferred; 4,898 unassigned. These are system-generated review hypotheses. |
| 2:55-4:05 | 4. Group explanation | Open a representative Likely group | Members first, then the plain-language System explanation, supporting points, cautions, and optional advanced evidence. |
| 4:05-5:10 | 5. Human decision | Use a disposable small-fixture result | Demonstrate Confirm; if time permits, use other disposable groups for Reject and Defer. Never change scan 31 for rehearsal. |
| 5:10-5:50 | 6. Human authority | Stay in the Human decision panel | Show Current decision and history. Explain that append-only human review controls reviewed operational results. |
| 5:50-6:35 | 7. Exports | Export authority panel | System Group Export is machine-generated suggestions. Reviewed Identity Export contains only current human-confirmed sets. |
| 6:35-7:00 | 8. Finish | Return to Dashboard/summary | Close with: discover, explain, review, confirm, export. |

The primary, no-live fallback is approximately 5:50. The scripted path with the
optional fixture is 7:00 and stays within the 5-8 minute target.

## Representative saved-result checks

The first five stable Likely group references and first five stable Review group
references in scan 31 were checked deterministically. Their status text remains
hypothesis/review language, their explanations contain support plus cautions,
and none says confirmed duplicate, same physical item, guaranteed, or 100%.
The first Conflict example says records were not grouped automatically; the
first Deferred example says no duplicate conclusion. Choose any of these checked
examples whose member details are comfortable for the audience; do not alter or
hide the global result.

## Fallbacks

- Small-live failure or delay: stop waiting, return to Dashboard, and open saved scan 31. Say that the full result was prepared before the meeting so the audience would not wait for a full-inventory run.
- Zero reviewed sets on scan 31: leave Reviewed Identity Export disabled/empty and say exactly that no human-confirmed sets exist in this preserved result. Demonstrate Confirm and the reviewed export only on the disposable 17-row path.
- Browser/network hiccup: refresh once, use Dashboard history to reopen scan 31, and continue from the saved result. If the frontend cannot recover, restart only the affected local service; never rerun the full detector.
- Layout issue: restore 100% zoom and the tested desktop width. Do not change application code during the presentation.

## What not to claim

Do not claim that every group is a true duplicate, that all inventory identity is
resolved autonomously, that accuracy/precision/recall is validated, that a full
real scan is instant, or that Reviewed Identity Export includes unreviewed
groups. R12 autonomous-quality freeze failed and R18 human labeling remains
deferred. This demo proves a human-in-the-loop discovery, explanation, review,
and authority-separated export workflow.

## After the demo

Make no product or detector changes before the demonstration unless a blocker on
this exact path is reproduced. After product proof, return separately to R18
human-label identity R&D or to deferred production work such as GF11 performance,
background execution, IAM/tenancy, storage, deployment, monitoring, and
integrations.
