# LLM-assisted MVP demo guide

This demo runs on branch `llm-assisted-mvp` after the approved Prompt 2 commit `db8336ffef3d9d62800863e6d2b46bc98435ef5f`. The deterministic baseline remains protected by `deterministic-demo-v1`.

## Start in default-off mode

LLM assistance is optional and off by default. Its status is informational; the browser cannot change server configuration. The relevant environment variable names are:

- `LLM_DEMO_ENABLED`
- `LLM_PROVIDER`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_CACHE_ENABLED`
- `LLM_CACHE_MAX_ENTRIES`
- `LLM_CACHE_TTL_SECONDS`
- `LLM_AUDIT_ENABLED`
- `LLM_AUDIT_MAX_ENTRIES`

No values belong in this guide or the frontend.

Start the backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Start the frontend in another terminal:

```powershell
cd frontend
npm.cmd run dev
```

## Run the bounded demo

1. Open **New Scan** and upload `data/llm_assisted_mvp_demo.csv`.
2. Select **Validate only**. The identity headers are intentionally unresolved.
3. Optionally request a suggestion for **Stock Ref** or **Item Narrative**. The request is explicit and includes only the source header and up to five bounded nonblank samples.
4. Review the reason and confidence, then explicitly choose **Use suggestion** if correct. A suggestion never applies itself.
5. Ensure the mappings are **Stock Ref → PART_NO** and **Item Narrative → DESCRIPTION**, then validate again.
6. Run the deterministic scan. No LLM call occurs during upload, validation, mapping, scan execution, or result retrieval.
7. Expand a persisted candidate. Request a candidate advisory explicitly; only its positive candidate ID is sent by the browser, and the server builds bounded evidence.
8. Optionally interpret one visible part number or description. The raw value remains unchanged and the interpretation is not persisted.

The results view keeps **Deterministic result — authoritative** separate from **LLM advisory — non-authoritative**. Advisory output cannot change a score, confidence, business status, rule decision, review, feedback, or export.

## Expected states and safety boundary

- **Off / unconfigured:** the action reports that LLM assistance is disabled or unavailable; deterministic controls continue working.
- **Timeout:** a bounded timeout message appears and the action can be retried.
- **Provider failure or invalid output:** a safe category message appears, never a provider body or exception.
- **Cache hit:** the advisory is successful and labeled as cached; no provider call is required for that response.
- **Ineligible candidate:** the backend reason is shown as a normal deterministic bypass and confirms no LLM advisory was used.

There is no automatic merge, deletion, source rewrite, candidate update, review update, or IFS writeback. Cache and audit storage are process-local and non-durable. Only bounded headers, values, and server-built candidate evidence may reach the configured provider; the complete CSV and complete rows are never sent. All rows in the demo CSV are synthetic and identify no real company, customer, or person.
