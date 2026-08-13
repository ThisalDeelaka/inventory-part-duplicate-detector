"""Explicit opt-in command for the synthetic G7C Groq benchmark corpus."""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.llm.groq_group_provider import create_group_advisory_provider
from app.llm.group_benchmark import (
    GroupAdvisoryBenchmarkRunner,
    curated_group_benchmark_cases,
    live_group_benchmark_enabled,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--corpus", choices=("curated-v1",), required=True)
    parser.add_argument("--max-calls", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    configuration = Settings()
    if not live_group_benchmark_enabled(
        configuration, explicit_live=args.live, corpus_selected=bool(args.corpus)
    ):
        print("LIVE_BENCHMARK_NOT_RUN: explicit group benchmark enablement unavailable")
        return 2
    cases = curated_group_benchmark_cases()
    provider = create_group_advisory_provider(configuration)
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        provider, max_calls=args.max_calls
    ).run(cases[:args.max_calls]))
    args.output.write_text(
        json.dumps(report.model_dump(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"Cases attempted: {report.total_cases_attempted}; "
        f"transport successes: {report.successful_transport_responses}"
    )
    failures = {
        category: count for category, count in report.failure_counts.items()
        if count
    }
    if failures:
        print("Failure categories:")
        for category, count in sorted(failures.items()):
            print(f"  {category}: {count}")
    print(f"Benchmark report written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
