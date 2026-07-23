# Saved LLM advisory exports

## Export endpoints

The deterministic exports remain unchanged in schema, column order, filename, and behavior:

```text
GET /api/scans/{scan_id}/export
scan-{scan_id}-candidates.csv

GET /api/scans/{scan_id}/rejections/export
scan-{scan_id}-rule-exclusions.csv
```

The optional enhanced exports read deterministic records and saved snapshots from the database:

```text
GET /api/scans/{scan_id}/export-with-llm
scan-{scan_id}-candidates-with-llm.csv

GET /api/scans/{scan_id}/rejections/export-with-llm
scan-{scan_id}-rule-exclusions-with-llm.csv
```

They preserve every deterministic column first and retain these existing LLM columns:

```text
llm_state
llm_used
llm_cache_hit
llm_provider
llm_model
llm_prompt_version
llm_assessment
llm_confidence
llm_recommended_action
llm_supporting_evidence
llm_conflicting_evidence
llm_bypass_reason
llm_safe_error_category
llm_generated_at
deterministic_result_authoritative
```

The enhanced candidate export then appends:

```text
effective_status
effective_recommended_action
llm_triage_run_state
```

## Persistence and state semantics

Manual advisory remains an explicit bodyless `POST /api/llm/candidates/{candidate_id}/advisory`. Automatic scan triage persists the distinct `candidate_triage` capability after the deterministic scan commits. Column suggestions and difficult-value interpretations are not persisted. A later request replaces the current outcome for its candidate and capability instead of creating an unbounded history.

Candidate exports use `NOT_REQUESTED`, `AVAILABLE`, `INELIGIBLE`, and `FAILED`. Rule exclusions use `NOT_APPLICABLE_HARD_RULE` for terminal deterministic rejection and `NOT_REQUESTED` for downgraded, reviewable, or unknown decisions. The deterministic result always remains authoritative.

`generated_at` is the generation time of the latest saved outcome and is replaced by a repeated explicit request. `updated_at` is the time the current snapshot row was last updated. Exported `llm_generated_at` values are normalized to UTC ISO-8601 and end in `Z`, including timestamps loaded from SQLite without timezone information.

The enhanced candidate export prefers a saved automatic `candidate_triage` snapshot. For backward compatibility it uses the manual `candidate_advisory` snapshot only when no automatic snapshot exists. Export never generates advisories. Eligible automatic candidates without a completed snapshot are represented by the assisted `LLM_PENDING` status; ineligible candidates use `NOT_APPLICABLE`.

## Database lifecycle and bounded concurrency

The repository initializes ORM tables with `Base.metadata.create_all()`. This feature adds one table, `llm_advisory_snapshot`; an existing database receives that missing table during application startup. No migration framework was added. `create_all()` does not migrate future column or constraint changes into a snapshot table that already exists.

The unique `candidate_id + capability` constraint prevents duplicate current snapshot rows. Two simultaneous first requests may both observe no row; one can receive a safe persistence failure when the unique constraint resolves the conflict. The implementation does not automatically retry that race, but a later explicit user retry is safe.

The persistence helper owns the commit for its route-scoped SQLAlchemy session. Its session must contain no unrelated pending mutations when called and the helper must not be reused where that precondition is false.

## Security and availability

Enhanced exports never call Groq or any other provider and work when LLM assistance is disabled, unavailable, unconfigured, or missing an API key. New LLM-derived text is neutralized against spreadsheet formula execution while preserving reversible source text.

Snapshot storage and exports exclude API keys, secrets, prompts, raw provider responses, request headers, raw exceptions, complete CSVs, and additional complete source rows. Only bounded structured advisory fields, safe metadata, stable categories, and timestamps are saved. Cache and audit remain process-local and non-durable.
