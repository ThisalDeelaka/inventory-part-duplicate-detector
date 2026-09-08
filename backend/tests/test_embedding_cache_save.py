"""GF-11D-CACHE1 deterministic cache-save contracts K1-K20."""

from __future__ import annotations

import inspect
import json
import random

import numpy as np
import pytest
from sqlalchemy import event

from app.db.models import LocalEmbeddingCache, utcnow
from app.services import hybrid_retrieval
from app.services.hybrid_retrieval import SqlAlchemyEmbeddingVectorCache


def _vector(seed: int) -> np.ndarray:
    return np.asarray(
        [((seed + index * 17) % 101) / 100 for index in range(384)],
        dtype=np.float32,
    )


def _payload(count: int, *, offset: int = 0):
    return {f"fingerprint-{index:05d}": _vector(index + offset) for index in range(count)}


def _reference_save(db, vectors, model_version):
    for fingerprint, vector in vectors.items():
        row = db.query(LocalEmbeddingCache).filter_by(
            record_fingerprint=fingerprint,
            embedding_model_version=model_version,
        ).first()
        if row is None:
            row = LocalEmbeddingCache(
                record_fingerprint=fingerprint,
                embedding_model_version=model_version,
            )
            db.add(row)
        row.vector_json = json.dumps(
            [round(float(value), 7) for value in vector], separators=(",", ":")
        )
        row.state = "AVAILABLE"
        row.generated_at = utcnow()
    db.flush()


def _snapshot(db, model_version):
    return tuple(
        (row.record_fingerprint, row.vector_json, row.state)
        for row in db.query(LocalEmbeddingCache).filter_by(
            embedding_model_version=model_version
        ).order_by(LocalEmbeddingCache.record_fingerprint)
    )


@pytest.mark.parametrize(
    ("case", "initial", "requested"),
    (
        ("empty", {}, {}),
        ("one", {}, _payload(1)),
        ("many", {}, _payload(23)),
        ("all-existing", _payload(23), _payload(23, offset=100)),
        ("mixed", _payload(12), _payload(23, offset=200)),
    ),
)
def test_k1_k7_reference_and_batched_semantics_are_equal(
    db, case, initial, requested
):
    reference_model = f"reference-{case}"
    optimized_model = f"optimized-{case}"
    _reference_save(db, initial, reference_model)
    _reference_save(db, initial, optimized_model)
    _reference_save(db, requested, reference_model)
    SqlAlchemyEmbeddingVectorCache(db).save(requested, optimized_model)
    assert _snapshot(db, reference_model) == _snapshot(db, optimized_model)


def test_k8_duplicate_dictionary_key_retains_last_requested_vector(db):
    first, second = _vector(1), _vector(2)
    vectors = dict((("same", first), ("same", second)))
    SqlAlchemyEmbeddingVectorCache(db).save(vectors, "duplicate-model")
    loaded = SqlAlchemyEmbeddingVectorCache(db).load(["same"], "duplicate-model")
    assert np.array_equal(loaded["same"], np.round(second, 7))


def test_k9_same_fingerprint_remains_isolated_by_model_scope(db):
    cache = SqlAlchemyEmbeddingVectorCache(db)
    cache.save({"same": _vector(1)}, "model-a")
    cache.save({"same": _vector(2)}, "model-b")
    assert not np.array_equal(
        cache.load(["same"], "model-a")["same"],
        cache.load(["same"], "model-b")["same"],
    )


@pytest.mark.parametrize("seed", (7, 19, 1101))
def test_k10_reverse_and_seeded_shuffle_have_equal_contents(db, seed):
    vectors = _payload(37)
    keys = list(vectors)
    random.Random(seed).shuffle(keys)
    shuffled = {key: vectors[key] for key in keys}
    reversed_values = dict(reversed(tuple(vectors.items())))
    first, second = f"shuffle-{seed}", f"reverse-{seed}"
    SqlAlchemyEmbeddingVectorCache(db).save(shuffled, first)
    SqlAlchemyEmbeddingVectorCache(db).save(reversed_values, second)
    assert _snapshot(db, first) == _snapshot(db, second)


def test_k11_serialization_and_float32_reload_match_reference(db):
    vectors = _payload(9)
    _reference_save(db, vectors, "reference-serialization")
    SqlAlchemyEmbeddingVectorCache(db).save(vectors, "optimized-serialization")
    cache = SqlAlchemyEmbeddingVectorCache(db)
    reference = cache.load(list(vectors), "reference-serialization")
    optimized = cache.load(list(vectors), "optimized-serialization")
    assert reference.keys() == optimized.keys()
    assert all(np.array_equal(reference[key], optimized[key]) for key in reference)
    assert all(value.dtype == np.float32 and value.shape == (384,)
               for value in optimized.values())


def test_k11_vectorized_serialization_matches_frozen_scalar_reference():
    generator = np.random.default_rng(1101)
    for _index in range(1_000):
        vector = generator.random(384, dtype=np.float32)
        reference = json.dumps(
            [round(float(value), 7) for value in vector], separators=(",", ":")
        )
        optimized = json.dumps(
            np.round(np.asarray(vector, dtype=np.float64), 7).tolist(),
            separators=(",", ":"),
        )
        assert optimized == reference


def test_k12_k15_lookup_and_insert_batches_are_fixed_bounded_and_not_per_row(db):
    counts = {"SELECT": [], "INSERT": []}

    def capture(_connection, _cursor, statement, parameters, _context, executemany):
        operation = statement.lstrip().split(None, 1)[0].upper()
        if operation in counts and "local_embedding_cache" in statement.casefold():
            counts[operation].append((len(parameters), executemany))

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        SqlAlchemyEmbeddingVectorCache(db).save(_payload(2_501), "bounded-work")
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert hybrid_retrieval._EMBEDDING_CACHE_SAVE_LOOKUP_CHUNK_SIZE == 900
    assert hybrid_retrieval._EMBEDDING_CACHE_SAVE_INSERT_BATCH_SIZE == 1_000
    assert [parameters for parameters, _many in counts["SELECT"]] == [901, 901, 702]
    assert counts["INSERT"] == [(1_000, True), (1_000, True), (501, True)]


def test_k16_save_never_commits(db, monkeypatch):
    monkeypatch.setattr(db, "commit", lambda: pytest.fail("cache save committed"))
    SqlAlchemyEmbeddingVectorCache(db).save(_payload(3), "no-local-commit")


def test_k17_insert_failure_rolls_back_existing_overwrite_with_outer_transaction(db):
    cache = SqlAlchemyEmbeddingVectorCache(db)
    cache.save({"existing": _vector(1)}, "failure-model")
    db.commit()
    original = _snapshot(db, "failure-model")

    def fail_insert(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("INSERT"):
            raise RuntimeError("injected cache insert failure")

    event.listen(db.bind, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="injected cache insert failure"):
            cache.save(
                {"existing": _vector(2), "missing": _vector(3)},
                "failure-model",
            )
    finally:
        event.remove(db.bind, "before_cursor_execute", fail_insert)
    db.rollback()
    assert _snapshot(db, "failure-model") == original


def test_k18_k20_scope_has_no_provider_schema_migration_or_dependency_hook():
    source = inspect.getsource(hybrid_retrieval.SqlAlchemyEmbeddingVectorCache)
    assert "provider" not in source.casefold()
    assert ".commit(" not in source
    assert "alembic" not in source.casefold()
    assert "create_all" not in source.casefold()
    assert "pip install" not in source.casefold()
