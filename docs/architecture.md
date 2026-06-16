# Architecture

## Problem and scope

The system identifies possible duplicate Inventory Part master records from CSV exports. It is advisory and explainable: no records are merged automatically. Direct IFS Cloud, Projection, OAuth, table, lobby, and event-action integrations are out of scope.

## System view

```text
Browser -> React/Vite UI -> FastAPI routes -> scan/validation services
                                      |-> hybrid NLP scoring engine
                                      |-> SQLAlchemy -> SQLite
CSV upload ---------------------------+
```

The backend separates transport, orchestration, scoring, repositories, and persistence. The frontend provides Dashboard, New Scan, Results, Warnings, Load Test, Data Security, and Future IFS pages.

## Data flow

The API validates required columns and hands scan execution to `ScanRunner`. `ScanRunner` records warnings, removes unusable empty-description rows, blocks records using selected business fields or description tokens, scores unique pairs, and persists candidates above the threshold through repository classes. Review feedback updates the candidate and appends an immutable feedback record.

## Reliability and uncertainty

Bad files return structured errors. Missing optional fields and high-null columns become visible warnings rather than crashes. Confidence bands, component scores, explanations, and human decisions expose uncertainty. Health and readiness endpoints separate process health from dependency readiness.

Sensitive Data Mode keeps processing local, avoids raw CSV persistence, calculates a SHA-256 file fingerprint, and warns about possible sensitive values in uploaded exports.

## Scalability

Grouping avoids unrestricted all-pairs comparison when business fields are selected. The API is stateless apart from database persistence. Larger deployments should use PostgreSQL, shared storage, a background worker, and measured block-size limits.
