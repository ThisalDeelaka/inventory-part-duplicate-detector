# GF-12C1-R2 real-data character retrieval correction

## Decision

Real-target character retrieval is VERIFIED. The correction is FIX-A: return
the legitimate 0..K positive-cosine subset instead of treating a desired top-K
count as a data-validity requirement. No candidate is fabricated, no exact
fallback is introduced, and group-first decision semantics are unchanged.

The full real product flow remains BLOCKED by a separate downstream runtime
condition: the single provider-free disposable scan did not reach terminal GF6
within 900 seconds after character retrieval was corrected. It was stopped at
that diagnostic boundary. No downstream behavior was changed in this task.

## Protected inputs

- Real CSV: 3,265,800 bytes, 5,327 data rows, 133 columns.
- Real CSV SHA-256:
  `8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.
- User-owned XLSX: 1,506,370 bytes; contents not inspected.
- XLSX SHA-256:
  `b32b5428169dca504c00fdf6df24efd90887044c666a71c991e10ec1c31b29c6`.

Only aggregate counts, fingerprints, and opaque record references were used.
No raw real descriptions or inventory rows are recorded here or in tests.

## Failure reproduction and classification

The faithful direct character-stage reproduction used the current canonical
5,327-row input, same-site configuration, K=5, provider-none policy, frozen
384-bin character vectors, and production fixed-seed LSH configuration:

| Diagnostic | Result |
|---|---:|
| eligible anchors | 5,327 |
| nonzero vectors | 5,324 |
| zero vectors | 3 |
| LSH tables / bits | 8 / 12 |
| seed / probe radius | 1101 / 2 |
| retained candidate-pool bound | 320 |
| requested positive neighbors | 5 |
| failing anchors | 3 |
| gathered candidates per failing anchor | 946 |
| retained candidates per failing anchor | 320 |
| positive retained candidates per failing anchor | 0 |

The three failing source-row indexes were 4988, 5072, and 5080. Their opaque
canonical references were `03e7d84a...677d4`, `1a2bebe3...83c2e`, and
`a78a8c7e...390dd`. All had zero vector nonzero bins and zero normalized
character-text length.

Root-cause classification is
`A_ZERO_OR_EMPTY_CHARACTER_VECTOR` plus an overstrict full-K postcondition.
Classes B through G were not evidenced for these anchors.

## Exact-reference evidence

Exact cosine against all 5,327 eligible vectors found exactly zero positive
neighbors for each failing anchor. There were no top-positive scores and no
exact top neighbors for LSH to miss. Therefore:

- the desired five-neighbor count was mathematically unsatisfiable;
- LSH did not miss an existing positive neighbor for these records;
- exact fallback or probe expansion cannot create legitimate evidence; and
- filling K would necessarily fabricate similarity.

The existing exact small-N implementation already filters `similarity > 0` and
returns fewer than K entries. The large-N LSH implementation alone required
exactly K positive entries.

## Historical intent

Commit `bd8109c42564055efaf8b2f500ffc47faedc4d8c` introduced fixed-seed LSH and
the `LSH_CANDIDATE_POOL_INSUFFICIENT` failures. Its P16 guard prohibited a
silent unbounded exact fallback, while P17 required orthogonal vectors to fail
when a full positive top-K could not be produced. The protected invariant was
that approximate/native candidates must not become valid neighbors without
exact positive cosine. That invariant is preserved.

P17 conflated “do not invent invalid neighbors” with “a complete K is always
available.” Character retrieval is a bounded discovery channel, and neither
the exact-path contract nor group-first domain semantics require K fabricated
neighbors. A missing desired neighbor is not positive identity evidence.

## Selected correction: FIX-A

After exact reranking of the same bounded LSH pool, production now:

1. keeps only scores strictly greater than zero;
2. applies the existing score-descending, canonical-reference tie order;
3. returns at most K legitimate entries; and
4. reports zero-, short-, and full-neighbor anchor counts.

Empty pools use the anchor only as a vectorized scratch-array filler outside the
length-delimited result. It can never appear in returned neighbors. Self remains
excluded, encounter duplicates remain deduplicated, and reciprocal reconstruction
is unchanged.

## 100k safety seam

- Activation remains EXACT below 2,000 records and fixed-seed LSH at 2,000+.
- Eight tables, 12 bits, radius two, pool bound 320, and gather bound 1,280 are
  unchanged.
- No `NearestNeighbors`, full dense N-by-N matrix, or unconditional exact
  fallback was added to the LSH function.
- Candidate enumeration, exact rerank work, fusion caps, GF2-GF6, and policy-v2
  selection remain unchanged.
- GF-11 remains IN PROGRESS, the waiver remains ACTIVE,
  `GF11-PERF-100K-COLD-FULL` remains OPEN, and 300 seconds remains NOT MET.

No character semantic/version bump was required: no score, ranking, vector,
candidate-pool, or neighbor identity rule changed. The correction converts an
invalid terminal full-K assumption into the already-established exact-path
0..K result contract.

## Real character-stage acceptance and determinism

Three equivalent runs completed with zero `CharacterRetrievalError`:

| Run | Runtime | Undirected proposals | Directed entries | 0 neighbors | 1..4 | 5 | Fingerprint |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 8.531 s | 20,167 | 26,620 | 3 | 0 | 5,324 | `71f22724...bd38e` |
| 2 | 23.039 s | 20,167 | 26,620 | 3 | 0 | 5,324 | `71f22724...bd38e` |
| 3 | 15.042 s | 20,167 | 26,620 | 3 | 0 | 5,324 | `71f22724...bd38e` |

The full fingerprint is
`71f22724ed9863393542f394a140ead476e1f2840e410cbcd2ba2d41708bd38e`.
Membership, ordering, rounded scores, failure count, proposal counts, and the
contract fingerprint were identical in all three runs.

## Structural and regression evidence

Synthetic fixtures cover zero genuine neighbors, fewer-than-K positives,
an exact positive deliberately missed by a crafted bounded LSH probe, equal
vectors, zero vectors, sparse vectors, normal full-pool behavior, deterministic
ties, self exclusion, deduplication, same/cross-site smoke, zero providers, and
the absence of schema/provider/secret/GF2-GF6 surfaces.

Focused character/retrieval and scope-guard result: 99 passed. Full backend
regression: 1,407 passed, 15 skipped, with one pre-existing pytest configuration
warning.

## Full real scan evidence

The corrected run parsed all 5,327 records and crossed the prior approximately
60-second character failure. It did not emit a new typed exception, but it also
did not reach a terminal GF6 result within 900 seconds. The disposable process
was stopped at that extended diagnostic boundary. Consequently no scan-complete,
visible-product-ready, GF2-GF6 count, or accuracy claim is made.

Authoritative status:

```text
REAL TARGET CHARACTER RETRIEVAL:
  VERIFIED

REAL TARGET END-TO-END PRODUCT:
  STILL BLOCKED BY NONTERMINAL FULL-SCAN RUNTIME BEYOND 900 SECONDS
```

Provider calls were zero. No pair-first fallback, source mutation, automatic
merge/delete/writeback, human-quality signoff, deployment graduation, or
production-scale graduation occurred.
