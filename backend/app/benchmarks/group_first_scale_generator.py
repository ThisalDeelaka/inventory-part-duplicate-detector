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
CANONICAL_SCENARIO = "canonical-mixed"
SCENARIO_CODES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")
SUPPORTED_RECORD_COUNTS = (500, 5_000, 20_000, 100_000)


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
    seed: int
    generator_fingerprint: str
    records: pd.DataFrame
    truth: BenchmarkTruth


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


def _scenario_rows(code: str, count: int, rng: random.Random):
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


def generate_scale_corpus(
    record_count: int, *, seed: int = 1101, scenario: str = CANONICAL_SCENARIO
) -> GeneratedScaleCorpus:
    if record_count <= 0 or record_count > 100_000:
        raise ValueError("record_count must be between 1 and 100000")
    if scenario != CANONICAL_SCENARIO and scenario not in SCENARIO_CODES:
        raise ValueError("unknown scale benchmark scenario")
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
            code, count, rng
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
    truth = BenchmarkTruth(
        duplicate_sets=tuple(duplicate_sets),
        protected_conflict_sets=tuple(conflicts),
        bridge_sets=tuple(bridges),
        scenario_by_source_row=tuple(labels),
    )
    payload = {
        "version": GENERATOR_VERSION,
        "scenario": scenario,
        "seed": seed,
        "records": records,
        "truth": truth,
    }
    return GeneratedScaleCorpus(
        scenario_name=scenario,
        version=GENERATOR_VERSION,
        seed=seed,
        generator_fingerprint=stable_fingerprint(payload),
        records=pd.DataFrame.from_records(records),
        truth=truth,
    )
