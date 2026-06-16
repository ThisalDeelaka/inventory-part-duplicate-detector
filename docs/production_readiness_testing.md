# Production Readiness Testing

This project is a production-oriented demo, not a full production IFS deployment. The readiness checks are designed to show what is reliable today and what must change for large-scale ERP operation.

## What The Check Covers

- Security dependency audit: `python -m pip_audit -r backend/requirements.txt`
- Static Python security scan: `python -m bandit -r backend/app -x backend/tests`
- Frontend dependency audit: `npm.cmd audit --audit-level=moderate`
- Backend tests: `python -m pytest -q`
- Exact ERP export upload: root-level `data set.csv`
- Failure handling: empty file, missing required columns, high-null selected fields
- Model failure cases: oil vs air, 10MM vs 12MM, left vs right
- Load simulation: 500, 2,000, and 5,000 synthetic records
- Docker Compose build and runtime smoke tests
- Repository-backed scan runner orchestration with API compatibility tests

Run:

```powershell
cd F:\part-master-duplication-ai\inventory-part-duplicate-detector
python scripts\production_readiness_check.py
```

The script writes `docs/production_readiness_results.json`.

## Current Readiness Position

Ready for:

- Controlled demos
- CSV-based duplicate candidate analysis
- Explainable scoring
- Human review workflows
- Containerized proof-of-concept deployments
- Load simulation and threshold tuning

Not yet ready as-is for direct large-scale IFS production:

- SQLite must be replaced with PostgreSQL or another production database.
- Synchronous scans should move to a background worker for very large files.
- Authentication and authorization are intentionally absent in this demo and must be added for production.
- Upload size, row count, and runtime limits must be tuned with real customer data.
- Observability should include structured logs, metrics, tracing, dashboards, and alerting.
- IFS Cloud integration remains a future adapter, not current functionality.

## Large ERP Recommendation

For actual IFS ERP use at scale, use this detector as the validated scoring engine, then wrap it with:

- IFS Cloud API/Projection adapter
- PostgreSQL
- Background job queue
- Object storage for uploaded files
- Horizontal API scaling
- Worker autoscaling
- Tenant-aware security model
- Full audit logging
- Monitoring and model drift review
