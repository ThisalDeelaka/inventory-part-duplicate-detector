"""Developer CLI for bounded, isolated GF-11A benchmark execution."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import tempfile
import time
from pathlib import Path

from app.benchmarks.contracts import ScaleBenchmarkStatus
from app.benchmarks.group_first_scale import (
    inspect_interrupted_benchmark,
    run_scale_benchmark,
)
from app.benchmarks.group_first_scale_generator import (
    CANONICAL_SCENARIO,
    SCENARIO_CODES,
)


def _worker(arguments, queue):
    result = run_scale_benchmark(**arguments)
    queue.put(result.to_dict())


def execute_bounded_benchmark(
    *, records: int, seed: int, scenario: str, timeout_seconds: float,
    hybrid_enabled: bool = True,
):
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="gf11-scale-") as directory:
        db_path = Path(directory) / "isolated-benchmark.sqlite"
        arguments = {
            "records": records,
            "seed": seed,
            "scenario": scenario,
            "db_path": db_path,
            "hybrid_enabled": hybrid_enabled,
        }
        queue = context.Queue(maxsize=1)
        process = context.Process(target=_worker, args=(arguments, queue))
        started = time.perf_counter()
        process.start()
        process.join(timeout_seconds)
        elapsed = time.perf_counter() - started
        if process.is_alive():
            process.terminate()
            process.join(30)
            return inspect_interrupted_benchmark(
                records=records, seed=seed, scenario=scenario, db_path=db_path,
                elapsed=elapsed, status=ScaleBenchmarkStatus.TIMED_OUT,
            ).to_dict()
        if process.exitcode != 0 or queue.empty():
            return inspect_interrupted_benchmark(
                records=records, seed=seed, scenario=scenario, db_path=db_path,
                elapsed=elapsed, status=ScaleBenchmarkStatus.FAILED,
            ).to_dict()
        return queue.get()


def markdown_summary(result: dict) -> str:
    complexity = dict(result.get("complexity_metrics", ()))
    safety = result["safety_metrics"]
    return "\n".join((
        f"# GF-11A scale result: {result['scenario']['record_count']:,} records",
        "",
        f"- Status: `{result['run']['status']}`",
        f"- Last stage: `{result['run'].get('last_stage') or 'NONE'}`",
        f"- Total wall time: `{result['resource_metrics'].get('total_wall_time_seconds')}` seconds",
        f"- Proposal/record: `{complexity.get('proposal_count_per_record')}`",
        f"- Evidence/record: `{complexity.get('evidence_edges_per_record')}`",
        f"- Max neighborhood: `{complexity.get('max_neighborhood_size')}`",
        f"- Max resolution work unit: `{complexity.get('max_resolution_work_unit_size')}`",
        f"- Safety passed: `{all(value == 0 for value in safety.values())}`",
        f"- Fingerprint: `{result['result_fingerprint']}`",
        "",
    ))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run an isolated group-first scale benchmark")
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=1101)
    parser.add_argument(
        "--scenario", default=CANONICAL_SCENARIO,
        choices=(CANONICAL_SCENARIO, *SCENARIO_CODES),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--disable-hybrid", action="store_true")
    arguments = parser.parse_args(argv)
    result = execute_bounded_benchmark(
        records=arguments.records, seed=arguments.seed,
        scenario=arguments.scenario, timeout_seconds=arguments.timeout_seconds,
        hybrid_enabled=not arguments.disable_hybrid,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if arguments.markdown:
        arguments.markdown.parent.mkdir(parents=True, exist_ok=True)
        arguments.markdown.write_text(markdown_summary(result), encoding="utf-8")
    return 0 if result["run"]["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
