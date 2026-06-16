# Model Evaluation

Run `python -m app.services.evaluate_model` from `backend/`. The script reads labeled pairs and reports precision, recall, F1-score, false positives, and false negatives at the discovery threshold.

Precision measures how many flagged pairs are relevant. Recall measures how many labeled duplicates are found. F1 balances both. Raising the threshold generally improves precision and reduces recall; lowering it broadens discovery and increases review workload.

This model does not claim perfect duplicate identification. Evaluation data is intentionally small and illustrative. Human review is required, and a representative organization-specific labeled set is necessary before production threshold decisions.
