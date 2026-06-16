# Model Selection

The selected model is **TF-IDF Character N-Gram + RapidFuzz Fuzzy Matching + Business Rule Scoring**.

Character 3-5 grams tolerate punctuation, spacing, spelling, and abbreviation differences. Cosine similarity is stable and repeatable. RapidFuzz token-set and partial ratios handle reordered and expanded descriptions. Part-number similarity adds a weak identifier signal. Technical tokens protect numbers, units, dimensions, and critical modifiers such as oil/air or left/right. Selected business fields provide domain context.

The final score uses 60% description similarity, 20% business-field agreement, 10% part-number similarity, and 10% technical-token similarity. Numeric and critical-modifier conflicts receive explicit penalties.

Paid LLMs are unnecessary for this deterministic demo and would add cost, latency, privacy, and repeatability concerns. Deep learning is deferred until sufficient labeled review feedback exists. Future supervised calibration should complement, not obscure, the explainable baseline.
