"""Isolated production-faithful embedding-cache save benchmark."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.models import LocalEmbeddingCache, utcnow
from app.services.hybrid_retrieval import SqlAlchemyEmbeddingVectorCache


MODEL_VERSION = "sklearn-hashing-domain-v1"
CANONICAL_ROW_COUNTS = (14_041, 35_118, 70_235)


def _vectors(count: int) -> dict[str, np.ndarray]:
    vector = np.linspace(0.0, 1.0, 384, dtype=np.float32)
    return {f"cache-{index:06d}": vector for index in range(count)}


def _seed_existing(session, vectors, *, mixed: bool) -> int:
    selected = tuple(vectors.items())[::2] if mixed else tuple(vectors.items())
    payload = [
        {
            "record_fingerprint": fingerprint,
            "embedding_model_version": MODEL_VERSION,
            "vector_json": json.dumps(
                [round(float(value), 7) for value in vector], separators=(",", ":")
            ),
            "state": "AVAILABLE",
            "generated_at": utcnow(),
        }
        for fingerprint, vector in selected
    ]
    for offset in range(0, len(payload), 2_000):
        session.execute(LocalEmbeddingCache.__table__.insert(), payload[offset:offset + 2_000])
    session.commit()
    return len(payload)


def measure_cache_save(count: int, mode: str) -> dict:
    if mode not in {"fresh", "warm", "mixed"}:
        raise ValueError("mode must be fresh, warm, or mixed")
    vectors = _vectors(count)
    with tempfile.TemporaryDirectory(prefix="embedding-cache-save-") as directory:
        path = Path(directory) / "cache.sqlite"
        engine = create_engine(f"sqlite:///{path.as_posix()}")
        LocalEmbeddingCache.__table__.create(engine)
        session = sessionmaker(bind=engine)()
        existing = 0
        if mode != "fresh":
            existing = _seed_existing(session, vectors, mixed=mode == "mixed")
        counts = Counter()

        def capture(_connection, _cursor, statement, parameters, _context, executemany):
            operation = statement.lstrip().split(None, 1)[0].upper()
            counts[operation] += 1
            if executemany:
                counts["EXECUTEMANY"] += 1
                counts["EXECUTEMANY_ROWS"] += len(parameters)

        event.listen(engine, "before_cursor_execute", capture)
        started = time.perf_counter()
        SqlAlchemyEmbeddingVectorCache(session).save(vectors, MODEL_VERSION)
        elapsed = time.perf_counter() - started
        event.remove(engine, "before_cursor_execute", capture)
        final_rows = session.query(LocalEmbeddingCache).count()
        session.rollback()
        session.close()
        engine.dispose()
    return {
        "rows_requested": count,
        "mode": mode,
        "rows_existing_before": existing,
        "rows_missing_before": count - existing,
        "elapsed_seconds": round(elapsed, 6),
        "sql_work": dict(sorted(counts.items())),
        "final_rows": final_rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--counts", type=int, nargs="+", default=CANONICAL_ROW_COUNTS)
    parser.add_argument("--modes", nargs="+", default=("fresh", "warm", "mixed"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    results = [
        measure_cache_save(count, mode)
        for count in args.counts
        for mode in args.modes
    ]
    args.output.write_text(
        json.dumps(results, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
