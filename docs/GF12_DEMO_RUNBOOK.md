# GF-12 showable product demo runbook

This is a local, non-Docker, provider-free demonstration using synthetic data.
It is not a production deployment procedure.

## Prerequisites

- Windows PowerShell
- Python 3.11 virtual environment already installed at `backend/.venv`
- frontend dependencies already installed under `frontend/node_modules`
- repository branch `llm-assisted-mvp`
- ports 8000 and 5173 available

Do not load `.env` for this demo. Do not paste or inspect any provider key.

## 1. Start the backend

From a fresh PowerShell terminal:

```powershell
cd "C:\Users\ThisalDeelaka\OneDrive - SEBSA World\Desktop\SEBSA External Proj\inventory-part-duplicate-detector\backend"
$env:IDENTITY_ORCHESTRATION_MODE = "group_first_primary"
$env:GROUP_LLM_PROVIDER = "none"
$env:LLM_DEMO_ENABLED = "false"
$env:LLM_PROVIDER = "none"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Confirm:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/api/llm/status
```

The LLM status must report `enabled=false` and `provider=none`. Do not continue
if it does not.

## 2. Start the frontend

From a second PowerShell terminal:

```powershell
cd "C:\Users\ThisalDeelaka\OneDrive - SEBSA World\Desktop\SEBSA External Proj\inventory-part-duplicate-detector\frontend"
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

## 3. Validate and submit the synthetic demo

1. Open **New Scan**.
2. Choose `data/llm_assisted_mvp_demo.csv`.
3. Leave **Same-site duplicate scan**, threshold **75**, Sensitive Data Mode on,
   and the selected Site/Contract plus Inventory UOM conditions.
4. Choose **Validate only**.
5. Map `Stock Ref` to `PART_NO`, `Item Narrative` to `DESCRIPTION`, `Site Code`
   to `CONTRACT`, `Inventory UOM` to `UNIT_MEAS`, and `HSN Code` to
   `HSN_SAC_CODE` if not already resolved. Validate again.
6. Confirm **17 records**, then choose **Run scan**.

The request is synchronous. On success the browser navigates to the completed
scan result; there is no background scan polling or resume action to present.

## 4. Navigate the result

1. Confirm the authoritative projection is `G2_V2`.
2. Confirm 4 potential identities: 1 likely and 3 needing review.
3. Open the three-member motor identity and show all members plus validation
   coverage/evidence.
4. Open **Conflicts & Deferred** and show 3 conflicts, zero deferred work, and 8
   not-safely-assigned records. Never describe unassigned as confirmed unique.
5. Keep legacy pair evidence under **Advanced diagnostics**; it is not the
   product result.

## 5. Perform a synthetic demo review

1. In the three-member motor group choose **Review this identity group**.
2. Use presenter name `GF12C1_DEMO_PRESENTER`.
3. Choose **Confirm all as one item** and save.
4. Show the append-only current review and review history.

This is a live product action on synthetic data, not an expert label or
human-quality validation result. A correction may be submitted through the same
panel; it supersedes rather than overwrites the prior event.

## 6. Export

1. Choose **Export System Groups**. The CSV is member-shaped and contains all
   current system identity hypotheses.
2. Choose **Export Reviewed Identities** after the confirmed review. It contains
   only the current confirmed reviewed set; before review (or while the current
   decision is Unsure) it is header-only.
3. Optionally export conflicts. Deferred export is not shown for this
   zero-deferred fixture.

Exports contain no benchmark truth, provider key, or automatic writeback.

## 7. Optional safe failure demonstration

Use a disposable automated test, not a manual database edit or a deliberate
crash of the live demo:

```powershell
cd "C:\Users\ThisalDeelaka\OneDrive - SEBSA World\Desktop\SEBSA External Proj\inventory-part-duplicate-detector\backend"
.\.venv\Scripts\python.exe -m pytest tests/test_gf12_showable_product_demo.py -k demo18 -q
```

The controlled synthetic fault produces a persisted `FAILED` scan,
`visible_product_ready=false`, and HTTP 409 for final result/export. Safe next
action is to preserve evidence, correct the cause, and submit a new scan. Resume
is not implemented.

## 8. Shutdown and cleanup

Press `Ctrl+C` once in the frontend terminal and once in the backend terminal.
The raw uploaded CSV is not persisted by the application. Completed scans,
derived evidence, and reviews remain in the configured local SQLite database;
do not delete or edit that database during a presentation. Any cleanup or
retention action is outside this demo milestone and must be separately approved.
