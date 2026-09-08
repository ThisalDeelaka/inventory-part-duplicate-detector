"""Fixed-seed synthetic inventory generation for GF-11 scale measurement.

Ground truth is returned separately and no benchmark label is placed in the
product DataFrame consumed by the scan engine.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd

from app.benchmarks.contracts import stable_fingerprint


GENERATOR_VERSION = "group-first-scale-corpus-v1"
TRUTH_VERSION_V1 = "group-first-scale-truth-v1"
TRUTH_VERSION_V2 = "group-first-scale-truth-v2"
SUPPORTED_TRUTH_VERSIONS = (TRUTH_VERSION_V1, TRUTH_VERSION_V2)
TRUTH_V2_CORRECTION_CLASSIFICATION = "A. PARTIAL_GROUP_AFTER_CORPUS_BOUNDARY"
TRUTH_V2_ADDITIONAL_CORRECTION_CLASSIFICATION = "E. TRUTH_ASSEMBLY_DEFECT"
TRUTH_V2_BOUNDARY_RULE = (
    "retain requested production records and scenario labels; emit positive "
    "truth only when the complete generated scenario has at least two members"
)
CANONICAL_SCENARIO = "canonical-mixed"
SCENARIO_CODES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")
SUPPORTED_RECORD_COUNTS = (500, 5_000, 20_000, 50_000, 100_000)


@dataclass(frozen=True)
class BenchmarkTruth:
    duplicate_sets: tuple[tuple[str, tuple[int, ...]], ...]
    protected_conflict_sets: tuple[tuple[int, ...], ...]
    bridge_sets: tuple[tuple[int, ...], ...]
    scenario_by_source_row: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedScaleCorpus:
    scenario_name: str
    version: str
    truth_version: str
    seed: int
    generator_fingerprint: str
    truth_fingerprint: str
    records: pd.DataFrame
    truth: BenchmarkTruth


class BenchmarkTruthIntegrityError(ValueError):
    """Typed fail-closed error for malformed offline benchmark truth."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _row(part_no, description, contract, uom="EA", **values):
    return {
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "CONTRACT": contract,
        "UNIT_MEAS": uom,
        "TYPE_CODE": values.get("TYPE_CODE", "INV"),
        "PRIME_COMMODITY": values.get("PRIME_COMMODITY", "MECH"),
        "SECOND_COMMODITY": values.get("SECOND_COMMODITY", "GENERAL"),
        "ACCOUNTING_GROUP": values.get("ACCOUNTING_GROUP", "STOCK"),
        "PART_PRODUCT_CODE": values.get("PART_PRODUCT_CODE", "PPC"),
        "PART_PRODUCT_FAMILY": values.get("PART_PRODUCT_FAMILY", "FAMILY"),
        "PRODUCT_CATEGORY_ID": values.get("PRODUCT_CATEGORY_ID", "CAT"),
        "HSN_SAC_CODE": values.get("HSN_SAC_CODE", "848390"),
        "HAZARD_CODE": values.get("HAZARD_CODE"),
    }


def _scenario_rows(
    code: str, count: int, rng: random.Random, *, truth_version: str
):
    rows: list[dict] = []
    duplicate_sets: list[tuple[str, tuple[int, ...]]] = []
    conflicts: list[tuple[int, ...]] = []
    bridges: list[tuple[int, ...]] = []
    while len(rows) < count:
        start = len(rows)
        family = rng.randrange(10_000_000)
        if code == "S1":
            rows.append(_row(
                f"U-{family:07d}", f"PRECISION SHAFT MODEL {family:07d}",
                f"SITE-{family % 11}",
            ))
        elif code == "S2":
            size = min(count - len(rows), 2 + family % 4)
            for member in range(size):
                # The first two records intentionally have duplicate values;
                # source-row identity, never the values, keeps them distinct.
                suffix = 0 if member < 2 else member
                rows.append(_row(
                    f"D-{family:06d}-{suffix}",
                    f"PRECISION COUPLING SERIES {family:06d} SIZE 20",
                    "SITE-0" if member < 2 else f"SITE-{member % 3}",
                    "EA" if member < 2 or member % 2 == 0 else "PCS",
                ))
            if truth_version == TRUTH_VERSION_V1 or size >= 2:
                duplicate_sets.append((f"dup-{family}", tuple(range(start, start + size))))
        elif code == "S3":
            rows.append(_row(
                f"G-{family:07d}", "INDUSTRIAL COMPONENT",
                f"SITE-{family % 5}", PART_PRODUCT_FAMILY="GENERIC",
            ))
        elif code == "S4":
            size = min(count - len(rows), 2)
            for member in range(size):
                voltage = "110V" if member == 0 else "220V"
                rows.append(_row(
                    f"T-{family:07d}-{member}",
                    f"CONTROL MODULE {voltage} MODEL {family:06d}", "SITE-0",
                ))
            if size == 2:
                conflicts.append(tuple(range(start, start + size)))
        elif code == "S5":
            size = min(count - len(rows), 2 + family % 3)
            for member in range(size):
                rows.append(_row(
                    f"X-{family:06d}-{member}",
                    f"TRANSFER ASSEMBLY MODEL {family:06d}",
                    f"SITE-{member + 1}",
                ))
            # V1 historically annotated a final boundary record as a singleton
            # positive group. V2 retains that production record and S5 label,
            # but emits positive truth only for a complete 2..4 member family.
            if truth_version == TRUTH_VERSION_V1 or size >= 2:
                duplicate_sets.append((f"cross-site-{family}", tuple(range(start, start + size))))
        elif code == "S6":
            rows.append(_row(
                "" if family % 2 else f"M-{family:07d}",
                f"ASSEMBLY REFERENCE {family:07d}", f"SITE-{family % 7}",
                None if family % 3 else "EA",
            ))
        elif code == "S7":
            size = min(count - len(rows), 3)
            descriptions = (
                f"LINKAGE ALPHA MODEL {family:06d}",
                f"LINKAGE ALPHA BETA MODEL {family:06d}",
                f"LINKAGE BETA MODEL {family:06d}",
            )
            for member in range(size):
                rows.append(_row(
                    f"B-{family:06d}-{member}", descriptions[member], "SITE-0"
                ))
            if size >= 2:
                duplicate_sets.append((f"bridge-truth-{family}", (start, start + 1)))
            if size == 3:
                bridges.append(tuple(range(start, start + size)))
        elif code == "S8":
            bucket = family % 12
            rows.append(_row(
                f"R-{bucket:02d}-{family:07d}",
                f"ROTATING EQUIPMENT FAMILY {bucket:02d} ITEM {family:07d}",
                f"SITE-{family % 9}", PART_PRODUCT_FAMILY=f"REPEAT-{bucket:02d}",
            ))
        else:
            raise ValueError(f"unsupported benchmark scenario: {code}")
    return rows, duplicate_sets, conflicts, bridges


def validate_benchmark_truth(truth: BenchmarkTruth, *, record_count: int) -> None:
    """Validate offline truth without importing it into product execution."""
    if len(truth.scenario_by_source_row) != record_count:
        raise BenchmarkTruthIntegrityError("TRUTH_SCENARIO_MEMBERSHIP_INVALID")
    group_ids = [identity for identity, _members in truth.duplicate_sets]
    if len(group_ids) != len(set(group_ids)):
        raise BenchmarkTruthIntegrityError("TRUTH_GROUP_ID_DUPLICATE")
    positive_membership = set()
    positive_sets = []
    for _identity, members in truth.duplicate_sets:
        if not members:
            raise BenchmarkTruthIntegrityError("TRUTH_GROUP_EMPTY")
        if len(members) < 2:
            raise BenchmarkTruthIntegrityError("TRUTH_GROUP_SINGLETON")
        if len(members) != len(set(members)):
            raise BenchmarkTruthIntegrityError("TRUTH_GROUP_MEMBER_DUPLICATE")
        if any(member < 0 or member >= record_count for member in members):
            raise BenchmarkTruthIntegrityError("TRUTH_RECORD_REFERENCE_INVALID")
        if positive_membership.intersection(members):
            raise BenchmarkTruthIntegrityError("TRUTH_RECORD_MULTI_MEMBERSHIP")
        positive_membership.update(members)
        positive_sets.append(set(members))
    for members in (*truth.protected_conflict_sets, *truth.bridge_sets):
        if any(member < 0 or member >= record_count for member in members):
            raise BenchmarkTruthIntegrityError("TRUTH_RECORD_REFERENCE_INVALID")
    for conflict in truth.protected_conflict_sets:
        conflict_set = set(conflict)
        if any(conflict_set <= positive for positive in positive_sets):
            raise BenchmarkTruthIntegrityError(
                "TRUTH_CANNOT_LINK_CONTRADICTS_IDENTITY"
            )


def _versioned_unique_truth_group_ids(
    groups: list[tuple[str, tuple[int, ...]]], *, truth_version: str
) -> list[tuple[str, tuple[int, ...]]]:
    """Disambiguate only colliding v2 truth IDs; v1 remains historical."""
    if truth_version == TRUTH_VERSION_V1:
        return groups
    counts = {}
    for identity, _members in groups:
        counts[identity] = counts.get(identity, 0) + 1
    return [
        (
            f"{identity}@source-{members[0]}"
            if counts[identity] > 1 else identity,
            members,
        )
        for identity, members in groups
    ]


def generate_scale_corpus(
    record_count: int, *, seed: int = 1101, scenario: str = CANONICAL_SCENARIO,
    truth_version: str = TRUTH_VERSION_V1,
) -> GeneratedScaleCorpus:
    if record_count <= 0 or record_count > 100_000:
        raise ValueError("record_count must be between 1 and 100000")
    if scenario != CANONICAL_SCENARIO and scenario not in SCENARIO_CODES:
        raise ValueError("unknown scale benchmark scenario")
    if truth_version not in SUPPORTED_TRUTH_VERSIONS:
        raise ValueError("unknown scale benchmark truth version")
    rng = random.Random(seed)
    codes = SCENARIO_CODES if scenario == CANONICAL_SCENARIO else (scenario,)
    base, remainder = divmod(record_count, len(codes))
    records: list[dict] = []
    duplicate_sets = []
    conflicts = []
    bridges = []
    labels = []
    for position, code in enumerate(codes):
        count = base + (1 if position < remainder else 0)
        local_rows, local_sets, local_conflicts, local_bridges = _scenario_rows(
            code, count, rng, truth_version=truth_version
        )
        offset = len(records)
        records.extend(local_rows)
        labels.extend([code] * len(local_rows))
        duplicate_sets.extend(
            (identity, tuple(offset + index for index in members))
            for identity, members in local_sets
        )
        conflicts.extend(tuple(offset + index for index in members) for members in local_conflicts)
        bridges.extend(tuple(offset + index for index in members) for members in local_bridges)
    duplicate_sets = _versioned_unique_truth_group_ids(
        duplicate_sets, truth_version=truth_version
    )
    truth = BenchmarkTruth(
        duplicate_sets=tuple(duplicate_sets),
        protected_conflict_sets=tuple(conflicts),
        bridge_sets=tuple(bridges),
        scenario_by_source_row=tuple(labels),
    )
    if truth_version == TRUTH_VERSION_V2:
        validate_benchmark_truth(truth, record_count=record_count)
    payload = {
        "version": GENERATOR_VERSION,
        "scenario": scenario,
        "seed": seed,
        "records": records,
        "truth": truth,
    }
    if truth_version != TRUTH_VERSION_V1:
        payload["truth_version"] = truth_version
    return GeneratedScaleCorpus(
        scenario_name=scenario,
        version=GENERATOR_VERSION,
        truth_version=truth_version,
        seed=seed,
        generator_fingerprint=stable_fingerprint(payload),
        truth_fingerprint=stable_fingerprint({
            "truth_version": truth_version,
            "truth": truth,
        }),
        records=pd.DataFrame.from_records(records),
        truth=truth,
    )


def generate_corrected_scale_corpus(
    record_count: int, *, seed: int = 1101, scenario: str = CANONICAL_SCENARIO
) -> GeneratedScaleCorpus:
    """Explicit GF-12 seam selecting corrected offline truth v2."""
    return generate_scale_corpus(
        record_count, seed=seed, scenario=scenario,
        truth_version=TRUTH_VERSION_V2,
    )
