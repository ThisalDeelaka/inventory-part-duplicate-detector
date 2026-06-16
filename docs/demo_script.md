# Demo Script

1. Open the Dashboard and confirm health, readiness, model version, and advisory warning.
2. Open New Scan and choose `data/sample_inventory_parts.csv`.
3. Select Site (`CONTRACT`) and Inventory UOM (`UNIT_MEAS`). Description is always used automatically.
4. Run Validate Only and discuss empty descriptions and optional-field warnings.
5. Run the scan and open candidate results.
6. Expand an MCB or desiccated-coconut candidate to explain TF-IDF, fuzzy, part-number, technical-token, matched-field, and mismatch scores.
7. Contrast Generator Oil Filter vs Generator Air Filter and Bolt 10MM vs Bolt 12MM.
8. Open Warnings, then return and record Duplicate, Not Duplicate, or Unsure feedback with a comment.
9. Export candidates as CSV.
10. Run a synthetic load test and compare records with generated pair count and processing time.
11. Open Future IFS Integration and state clearly that no direct IFS integration exists today.
