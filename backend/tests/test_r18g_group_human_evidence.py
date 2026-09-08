import json

import pytest
from openpyxl import load_workbook

from app.benchmarks.r18g_group_human_evidence import (
    COMMENT_BASES,
    CONFIDENCES,
    LABELS,
    PARTITION_IDS,
    REASON_CODES,
    Edge,
    GroupHypothesis,
    Member,
    _group_hypothesis,
    _partition_challengers,
    deterministic_split,
    fingerprint,
    review_group_id,
    sha256_file,
    validate_workbooks,
    write_manifest,
    write_mapping,
    write_workbook,
)


def member(number, *, site="SITE-A"):
    return Member(
        number, f"REF-{number:03d}", number, f"PART-{number}",
        f"Description in use {number}", f"Description {number}",
        f"Master description {number}", f"Type {number}", f"Dimension {number}",
        "EA", "STOCK", site,
    )


def group(number, *, source="ACCEPTED_REVIEW_GROUP", size=2,
          shadow=False, partition=False):
    members = tuple(member(number * 10 + offset) for offset in range(size))
    return GroupHypothesis(
        fingerprint((item.stable_ref for item in members), source), members, source,
        "SHADOW_ADR_ORDER" if shadow else "CURRENT", f"CURRENT-{number}",
        f"UNIT-{number}", "", "MIXED_EVIDENCE", 1, 1, 0, 0, False,
        partition, source == "DEFERRED_FAMILY_CANDIDATE",
        source == "CONFLICT_CONTEXT_CANDIDATE",
    )


def test_hypothesis_fingerprint_is_stable_and_group_size_fails_closed():
    assert fingerprint(("REF-2", "REF-1"), "SOURCE") == fingerprint(
        ("REF-1", "REF-2"), "SOURCE"
    )
    with pytest.raises(ValueError, match="R18G_GROUP_TOO_SMALL"):
        _group_hypothesis((1,), {1: member(1)}, {}, source_kind="SOURCE")


def test_split_is_deterministic_disjoint_and_keeps_mandatory_cases():
    population = [group(index) for index in range(70)]
    bicycle = group(100, source="GENERIC_BICYCLE_FAMILY", size=7)
    challenger = group(101, source="ADR_PARTITION_CHALLENGER", size=4,
                       shadow=True, partition=True)
    population.extend((bicycle, challenger))
    first = deterministic_split(tuple(population))
    second = deterministic_split(tuple(reversed(population)))
    assert [[review_group_id(item) for item in split] for split in first] == [
        [review_group_id(item) for item in split] for split in second
    ]
    development, holdout = first
    assert len(development) == 48
    assert len(holdout) == 16
    assert {item.fingerprint for item in development}.isdisjoint(
        item.fingerprint for item in holdout
    )
    assert bicycle in development
    assert challenger in development


def test_partition_challenger_is_complete_and_cannot_link_safe():
    # AB is a separate all-Strong pair. CDEF is a complete Review clique.
    # Current ordering partitions CDEF into two pairs to minimize Review,
    # while ADR ordering keeps the four-member clique to maximize Review.
    edges = {}
    edges[(1, 2)] = Edge(1, 2, "STRONG_SUPPORT", "TRUSTED", False, False, "s")
    for left in range(3, 7):
        for right in range(left + 1, 7):
            edges[(left, right)] = Edge(
                left, right, "REVIEW_SUPPORT", "LEXICAL", False, False,
                f"r-{left}-{right}",
            )
    challengers = _partition_challengers((1, 2, 3, 4, 5, 6), edges)
    assert (3, 4, 5, 6) in challengers
    for candidate in challengers:
        assert all(
            edges[tuple(sorted((left, right)))].edge_class != "CANNOT_LINK"
            for index, left in enumerate(candidate) for right in candidate[index + 1:]
        )


def test_blinded_workbooks_mapping_dropdowns_and_hashes_are_stable(tmp_path):
    development = (
        group(1, source="GENERIC_BICYCLE_FAMILY", size=7),
        group(2, source="ADR_PARTITION_CHALLENGER", size=4,
              shadow=True, partition=True),
    )
    holdout = (group(3),)
    dev_path = tmp_path / "development.xlsx"
    holdout_path = tmp_path / "holdout.xlsx"
    mapping_path = tmp_path / "mapping.csv"
    write_workbook(dev_path, development, "DEVELOPMENT")
    write_workbook(holdout_path, holdout, "SEALED HOLDOUT")
    write_mapping(mapping_path, development, holdout)
    original_hashes = tuple(map(sha256_file, (dev_path, holdout_path, mapping_path)))
    write_workbook(dev_path, development, "DEVELOPMENT")
    write_workbook(holdout_path, holdout, "SEALED HOLDOUT")
    write_mapping(mapping_path, development, holdout)
    assert tuple(map(sha256_file, (dev_path, holdout_path, mapping_path))) == original_hashes

    source_refs = {
        item.stable_ref for candidate in development + holdout
        for item in candidate.members
    }
    validation = validate_workbooks(
        dev_path, holdout_path, mapping_path, source_refs
    )
    assert validation["prefilled_human_field_count"] == 0
    assert validation["formula_count_in_human_fields"] == 0
    assert validation["pair_label_or_comment_leakage"] == 0
    assert validation["internal_mapping_reconciles"] is True

    workbook = load_workbook(dev_path, data_only=False)
    review_formulas = {
        item.formula1 for item in workbook["Group Review"].data_validations.dataValidation
    }
    assert review_formulas == {
        '"' + ",".join(values) + '"'
        for values in (LABELS, CONFIDENCES, REASON_CODES, COMMENT_BASES)
    }
    partition_formulas = {
        item.formula1 for item in workbook["Partition"].data_validations.dataValidation
    }
    assert partition_formulas == {'"' + ",".join(PARTITION_IDS) + '"'}


def test_manifest_serialization_hash_is_stable(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    payload = {"z": [3, 2, 1], "a": {"provider_calls": 0}}
    write_manifest(first, payload)
    write_manifest(second, json.loads(json.dumps(payload)))
    assert sha256_file(first) == sha256_file(second)
    assert first.read_text(encoding="utf-8").endswith("\n")
