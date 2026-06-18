# Part Master Duplication Identifier

A production-oriented demo for identifying possible duplicate Inventory Part master records from ERP CSV exports. It uses configurable business conditions, local hybrid NLP similarity, confidence scoring, explanations, data-quality warnings, and human review feedback.

The current version uses IFS-compatible CSV field names. It has **no direct IFS integration**, no paid AI API, no deep learning, no authentication, and no automatic merging.

## Features

- CSV upload and validation-only workflow
- Supports real ERP export files like the workspace `data set.csv`; aliases such as `PART_TYPE`, `INVENTORY_UOM`, `COMMODITY_GROUP_1`, `COMMODITY_GROUP_2`, and `SAFETY_CODE` are mapped automatically
- Sensitive Data Mode: no raw CSV persistence, no external AI API usage, SHA-256 file fingerprint, and sensitive-pattern warnings
- Configurable business-field blocking and threshold
- TF-IDF character n-grams, RapidFuzz, part-number, technical-token, and business-rule scoring
- Confidence, explanations, matched/mismatched fields, and recommended action
- Persistent review feedback and comments
- Result export, diagnostics, warnings, and synthetic load tests
- Docker Compose and Kubernetes-ready examples

## Local run

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` before the frontend build when the API is not at `http://127.0.0.1:8000`. On Windows, `127.0.0.1` is more reliable than `localhost` when Docker or other local proxies are also listening.

Open the Vite URL shown in the terminal, usually `http://localhost:5173`. API documentation is at `http://127.0.0.1:8000/docs`.

## Docker Compose

```bash
docker compose up --build
```

Frontend: `http://localhost:5173`; backend: `http://127.0.0.1:8000`.

## Tests and evaluation

```bash
cd backend
pytest
python -m app.services.evaluate_model
```

## Limitations

Scores are candidate-ranking signals, not proof. SQLite and synchronous scans suit a demo; production scale must use PostgreSQL, background workers, bounded upload sizes, tenant-aware security, observability, and organization-specific evaluation data. Kubernetes manifests are realistic starting points, not turnkey production infrastructure.

For sensitive ERP exports, see `docs/data_security_and_privacy.md`.
For the redesigned deterministic backend engine and `USE_REDESIGNED_ENGINE` switch, see `backend/docs/redesigned_engine.md`.

## Troubleshooting

- Missing required fields: provide `PART_NO` and `DESCRIPTION`.
- Optional aliases in the original workspace dataset are accepted for `PART_TYPE`, `INVENTORY_UOM`, `COMMODITY_GROUP_1`, `COMMODITY_GROUP_2`, and `SAFETY_CODE`.
- If PowerShell blocks `npm.ps1`, run `npm.cmd install` and `npm.cmd run dev`.
- If CORS is blocked during local development, use `http://127.0.0.1:8000` for the backend or set `CORS_ORIGINS` / `CORS_ORIGIN_REGEX`.

## Positioning

This demo is a production-oriented duplicate intelligence engine for Inventory Part master data. It safely identifies possible duplicates while preserving uncertainty, explanation, and human control. Future IFS Cloud integration remains a documented adapter boundary after the detection engine is validated.
