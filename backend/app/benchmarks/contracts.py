"""Immutable GF-11A scale benchmark contracts and stable serialization."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


SCALE_BENCHMARK_CONTRACT_VERSION = "group-first-scale-benchmark-v1"


class ScaleBenchmarkStatus(str, Enum):
    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    FAILED = "FAILED"
    SAFETY_FAILURE = "SAFETY_FAILURE"


@dataclass(frozen=True)
class ScaleBenchmarkScenario:
    name: str
    version: str
    record_count: int
    seed: int
    generator_fingerprint: str


@dataclass(frozen=True)
class ScaleBenchmarkRun:
    orchestration_mode: str
    policy_version: str
    status: ScaleBenchmarkStatus
    last_stage: str | None
    safe_failure_category: str | None


@dataclass(frozen=True)
class ScaleStageMetrics:
    stage: str
    status: str
    wall_time_seconds: float | None
    input_count: int | None
    output_count: int | None
    truncated_count: int | None
    deferred_count: int | None


@dataclass(frozen=True)
class ScaleDatabaseMetrics:
    row_counts: tuple[tuple[str, int], ...]
    sqlite_size_bytes: int | None
    query_count: int | None


@dataclass(frozen=True)
class ScaleSafetyMetrics:
    accepted_cannot_link_violations: int
    duplicate_accepted_memberships: int
    single_member_accepted_groups: int
    cross_scan_contamination: int
    provider_calls: int
    legacy_pair_rows: int
    g1_projection_rows: int
    g2_v1_rows: int
    shadow_rows: int

    @property
    def passed(self) -> bool:
        return all(value == 0 for value in dataclasses.astuple(self))


@dataclass(frozen=True)
class ScaleQualityMetrics:
    true_duplicate_set_count: int
    covered_true_set_count: int
    missed_true_set_count: int
    over_merged_group_count: int
    split_true_set_count: int
    conflict_detection_count: int
    deferred_true_duplicate_set_count: int


@dataclass(frozen=True)
class ScaleResourceMetrics:
    total_wall_time_seconds: float | None
    peak_rss_bytes: int | None
    peak_rss_availability: str


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def canonical_json(value: Any, *, pretty: bool = False) -> str:
    return json.dumps(
        _plain(value), ensure_ascii=True, sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def stable_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScaleBenchmarkResult:
    contract_version: str
    scenario: ScaleBenchmarkScenario
    environment: tuple[tuple[str, str | int | None], ...]
    run: ScaleBenchmarkRun
    stage_metrics: tuple[ScaleStageMetrics, ...]
    database_metrics: ScaleDatabaseMetrics
    safety_metrics: ScaleSafetyMetrics
    quality_metrics: ScaleQualityMetrics
    resource_metrics: ScaleResourceMetrics
    complexity_metrics: tuple[tuple[str, float | int | None], ...]
    bottleneck_observations: tuple[str, ...]
    result_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    def to_json(self, *, pretty: bool = True) -> str:
        return canonical_json(self, pretty=pretty)


def result_fingerprint_payload(
    *, scenario: ScaleBenchmarkScenario, run: ScaleBenchmarkRun,
    stage_metrics: tuple[ScaleStageMetrics, ...],
    database_metrics: ScaleDatabaseMetrics,
    safety_metrics: ScaleSafetyMetrics,
    quality_metrics: ScaleQualityMetrics,
    complexity_metrics: tuple[tuple[str, float | int | None], ...],
) -> dict[str, Any]:
    """Exclude machine/noise-dependent timing, memory, DB bytes, and query totals."""
    return {
        "contract_version": SCALE_BENCHMARK_CONTRACT_VERSION,
        "scenario": scenario,
        "run": run,
        "stage_metrics": tuple(
            dataclasses.replace(item, wall_time_seconds=None) for item in stage_metrics
        ),
        "database_row_counts": database_metrics.row_counts,
        "safety_metrics": safety_metrics,
        "quality_metrics": quality_metrics,
        "complexity_metrics": complexity_metrics,
    }
