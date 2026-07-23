# Automatic LLM triage for review candidates

## Deterministic-first architecture

Every scan completes and commits its deterministic candidates before automatic LLM work is scheduled. Scores, confidence, business status, rule decisions, rejection reasons, mismatch evidence, normalized values, and human review data remain unchanged and authoritative. Automatic triage exists to remove repetitive advisory clicks for bounded `POSSIBLE_DUPLICATE_REVIEW` candidates, not to replace the duplicate engine.

The runner reuses the existing server-side candidate eligibility, bounded evidence builder, typed candidate-advisory response, Groq provider, cache, audit, and safe exception taxonomy. It never receives a complete CSV or arbitrary complete source row.

## Activation and automatic start

Automatic triage requires all of the following:

```text
LLM_DEMO_ENABLED=true
LLM_PROVIDER=groq
GROQ_API_KEY configured locally
LLM_AUTO_TRIAGE_ENABLED=true
```

`LLM_TRIAGE_CONCURRENCY` defaults to `1` and is bounded from 1 to 8. `LLM_TRIAGE_MAX_CANDIDATES_PER_SCAN` defaults to `250` and is bounded from 1 to 1000. Candidates above the cap are counted as skipped. The scan response does not wait for provider calls: a FastAPI background task opens independent SQLAlchemy sessions after the deterministic transaction has committed.

Only candidates whose deterministic status is `POSSIBLE_DUPLICATE_REVIEW` and which pass the existing candidate-advisory eligibility are queued. Clear high-confidence duplicates, hard-rule exclusions, and every other ineligible result cause no provider work.

## Durable state and restart behavior

`llm_triage_run` stores one current run per scan with a unique indexed `scan_id`. It contains only state, counters, UTC timestamps, and a safe error category. Automatic candidate outcomes use `llm_advisory_snapshot` with the separate `candidate_triage` capability, so manual `candidate_advisory` outcomes remain distinguishable.

Run states are `QUEUED`, `RUNNING`, `COMPLETED`, `COMPLETED_WITH_FAILURES`, and `FAILED`. Candidate snapshots remain `AVAILABLE`, `INELIGIBLE`, or `FAILED`. A successful snapshot is skipped on resume. Failed snapshots are retried only by the explicit retry-failed action, and a later success replaces the current failure.

The queue is deliberately in-process for this local MVP. A server restart can interrupt active work, but committed run and snapshot state allow an explicit Start/Resume request to continue missing candidates. There is no Redis, Celery, external worker, or production durability claim.

## APIs

```text
POST /api/scans/{scan_id}/llm-triage
GET  /api/scans/{scan_id}/llm-triage
POST /api/scans/{scan_id}/llm-triage/retry-failed
```

Start/resume and retry requests are bodyless and return immediately. Status contains only the run state, safe counters, progress percentage, UTC `Z` timestamps, and the last safe error category. Repeated start requests are idempotent while work is active or completed.

Candidate responses retain all deterministic fields and append automatic snapshot metadata, `effective_status`, `effective_recommended_action`, and `deterministic_result_authoritative=true`.

## Effective status mapping

```text
SUPPORTS_DUPLICATE       -> LLM_LIKELY_DUPLICATE
SUPPORTS_NON_DUPLICATE   -> LLM_DOWNGRADED
INCONCLUSIVE             -> HUMAN_REVIEW
eligible, not completed  -> LLM_PENDING
safe failure             -> LLM_FAILED
not eligible             -> NOT_APPLICABLE
```

These values are assisted workflow labels only. They never alter `business_status` or record a human decision.

## UI and exports

The scan page shows run progress and counters, polls only while queued or running, supports Start/Resume and Retry failed, and filters candidates by assisted status. Each candidate separately shows effective assisted status, deterministic result, and automatic triage result. The original manual advisory remains available as **Re-evaluate candidate** when an automatic result exists.

Legacy deterministic exports remain byte-compatible. The enhanced candidate export prefers the automatic `candidate_triage` snapshot, falls back to a manual `candidate_advisory` snapshot only when automatic output is absent, preserves the existing LLM columns, and appends `effective_status`, `effective_recommended_action`, and `llm_triage_run_state`. Export reads database state only and never calls a provider.

## Failure, privacy, and security

One candidate failure does not stop later work. A run with candidate failures ends as `COMPLETED_WITH_FAILURES`; deterministic scan results remain usable. Snapshots and runs exclude API keys, authorization headers, prompts, raw provider bodies, raw exceptions, complete CSVs, and additional complete source rows. Formula neutralization and UTC `Z` formatting apply to enhanced exports.

No automatic merge, deletion, source rewrite, human review decision, IFS writeback, or browser-side provider configuration exists.

## Run and verify without Docker

Start the backend from `backend` with the repository virtual environment and `--env-file .env`, then start Vite from `frontend`. No container is required. Run a synthetic scan, open its results, and watch **LLM triage** progress. Confirm candidate assisted statuses in Pair View and download **Export CSV with saved LLM advisories** to verify the same automatic result and run state.
