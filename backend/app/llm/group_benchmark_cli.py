"""Explicit opt-in command for the provider-neutral synthetic group benchmark."""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.llm.group_benchmark import (
    GroupAdvisoryBenchmarkRunner,
    curated_group_benchmark_cases,
    live_group_benchmark_enabled,
)
from app.llm.group_provider_factory import create_group_advisory_provider


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 300_000:
        raise argparse.ArgumentTypeError("value must be between 0 and 300000")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--corpus", choices=("curated-v1",), required=True)
    parser.add_argument("--max-calls", type=int, default=30)
    parser.add_argument("--max-cases", type=_positive_int)
    parser.add_argument("--case-delay-ms", type=_non_negative_int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def select_benchmark_cases(cases, max_cases: int | None):
    """Select a deterministic prefix without changing corpus case objects."""
    return cases if max_cases is None else cases[:max_cases]


def main() -> int:
    args = build_parser().parse_args()
    configuration = Settings()
    if not live_group_benchmark_enabled(
        configuration, explicit_live=args.live, corpus_selected=bool(args.corpus)
    ):
        print("LIVE_BENCHMARK_NOT_RUN: explicit group benchmark enablement unavailable")
        return 2
    cases = curated_group_benchmark_cases()
    cases = select_benchmark_cases(cases, args.max_cases)
    provider = create_group_advisory_provider(configuration)
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        provider, max_calls=args.max_calls, case_delay_ms=args.case_delay_ms,
    ).run(cases))
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
    field_diagnostics = [
        (category, path, count)
        for category, paths in report.schema_mismatch_field_counts.items()
        for path, count in paths.items() if count
    ]
    if field_diagnostics:
        print("Schema field diagnostics:")
        for category, path, count in sorted(
            field_diagnostics, key=lambda item: (-item[2], item[0], item[1])
        ):
            print(f"  {path} {category}: {count}")
    print(f"Benchmark report written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
