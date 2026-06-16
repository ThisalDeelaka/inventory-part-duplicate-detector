# Data Security and Privacy

Inventory Part Master exports can contain commercially sensitive ERP data: site codes, accounting groups, product families, safety classifications, supplier hints, material strategies, and operational footprint. Treat uploaded CSV files as sensitive customer data.

## Sensitive Data Mode

The demo includes a practical Sensitive Data Mode for customer workshops and controlled pilots.

When enabled:

- The raw CSV is processed locally by the backend.
- The raw uploaded CSV file is not persisted.
- No external AI, LLM, or paid model API is called.
- A SHA-256 fingerprint is calculated so the scanned file can be identified without storing it.
- Validation checks for possible sensitive patterns such as email-like values, phone-like values, project/work-order references, and supplier/vendor/manufacturer references.
- Scan results persist only candidate pairs, scores, explanations, warnings, and review feedback.

## What Is Stored

- Scan summary
- Selected fields and threshold
- Candidate pairs above threshold
- Similarity scores and explanations
- Data-quality and sensitive-pattern warnings
- Human review feedback

## What Is Not Stored

- The uploaded raw CSV file
- External AI prompts or responses
- Full raw file copies in logs

## Production Recommendation

For real IFS ERP environments, deploy inside the customer's controlled network or private Kubernetes environment. Add SSO/OIDC, authorization, audit logging, PostgreSQL, encrypted storage, network policies, retention/deletion workflows, and monitoring.

This demo is intentionally local-first and explainable. It avoids external AI data transfer by design.
