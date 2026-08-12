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

The API validates required columns and hands scan execution to `ScanRunner`. `ScanRunner` records warnings, removes unusable empty-description rows, blocks records using selected business fields or description tokens, and scores unique pairs. Candidates above the threshold are persisted as review results. Below-threshold pairs deliberately excluded by a deterministic business rule are persisted separately as rule-exclusion audit evidence; ordinary low-similarity pairs are discarded. Review feedback updates the candidate and appends an immutable feedback record.

## Reliability and uncertainty

Bad files return structured errors. Missing optional fields and high-null columns become visible warnings rather than crashes. Confidence bands, component scores, explanations, and human decisions expose uncertainty. Health and readiness endpoints separate process health from dependency readiness.

Sensitive Data Mode keeps processing local, avoids raw CSV persistence, calculates a SHA-256 file fingerprint, and warns about possible sensitive values in uploaded exports.

## Scalability

Grouping avoids unrestricted all-pairs comparison when business fields are selected. The API is stateless apart from database persistence. Larger deployments should use PostgreSQL, shared storage, a background worker, and measured block-size limits.

## Identity edge safety foundation

A persisted pair candidate is internal edge evidence, not a durable identity group. The canonical internal edge contract classifies existing deterministic and human evidence as `STRONG_SUPPORT`, `REVIEW_SUPPORT`, `CANNOT_LINK`, or `NON_GROUPABLE`. Future groups will be constrained identity hypotheses built from those edges.

Connectedness alone is not sufficient for group identity. Any internal `CANNOT_LINK` edge prevents an automatic likely-duplicate group containing both records, even when an intermediate generic record supports each endpoint separately.

Explicit affirmative opposite roles such as rotor/stator, drive-end/non-drive-end, serial/non-serial, inlet/outlet, left/right, top/component, and distinct explicitly named engine components are deterministic conflict evidence. A role present on only one record is not an opposite-role conflict. UOM differences remain separate mapping-quality evidence, LLM results remain advisory, and an explicit human non-duplicate decision remains authoritative.

## Constrained group projection

G0 supplies deterministic edge safety and classification. G1 consumes that contract to compute read-only constrained identity-group hypotheses in memory. Pairwise evidence remains internal. Group hypotheses are the emerging product-level identity abstraction.

A connected support graph is necessary but not sufficient. Every bounded internal relationship is validated, and any `CANNOT_LINK` vetoes the group. Missing internal relationships are rescored locally without persistence or provider work; absence of conflict does not become positive identity evidence.

G1 hypotheses and their stable keys are computed, scan-local, and non-persisted. Durable record and group snapshots arrive in G2. Provisional families above the 20-member validation bound are deferred, never silently truncated.

The existing `grouping_service.build_duplicate_groups` connected-component projection remains transitional and conflict-unaware. It is retained only for backward compatibility and is not an input to G1.
