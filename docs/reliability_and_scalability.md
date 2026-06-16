# Reliability and Scalability

- Required columns block invalid scans; optional-column gaps generate warnings.
- Empty descriptions are counted and skipped safely.
- Repeated part numbers, unavailable selected fields, and fields with at least 50% nulls are reported.
- Scan states are `RUNNING`, `COMPLETED`, or `FAILED`; database commits preserve consistent summaries.
- Score bands avoid false certainty: HIGH 90+, MEDIUM 75-89, LOW 60-74, IGNORE below 60.
- Business-field grouping reduces pair growth. Without selected fields, first normalized tokens provide loose blocking.
- Candidate generation has a 20,000-pair safety budget and emits a warning when reached, preventing an accidental synchronous scan from exhausting the demo service.
- Synthetic generation and timing expose record count, pair count, processing time, candidates, and warnings.
- `/health` checks the service; `/ready` checks database availability and model readiness.

SQLite is suitable for a single-node demo, not a multi-replica production database. Kubernetes deployments should use PostgreSQL. Long scans should later move behind a background worker with job limits and idempotency; Celery or other queue infrastructure is deliberately excluded now.
