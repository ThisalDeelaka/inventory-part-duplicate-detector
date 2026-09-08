"""Read-only offline coverage audit for the unused R15 signature deriver."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from time import perf_counter

from app.engine.identity_signature import IdentitySemanticCategory
from app.engine.identity_signature_derivation import derive_identity_signature


_MAJOR_IDENTITY_CATEGORIES = frozenset({
    IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
    IdentitySemanticCategory.ASSEMBLY_COMPONENT_ROLE,
    IdentitySemanticCategory.MODEL_TYPE_IDENTITY,
    IdentitySemanticCategory.VARIANT_IDENTITY,
})


def _observation_payload(item) -> dict:
    return {
        "semantic_key": item.semantic_key,
        "normalized_value": item.normalized_value,
        "state": item.state.value,
        "sources": [
            {
                "source_field": source.source_field.value,
                "normalized_evidence": list(source.normalized_evidence),
                "provenance_code": source.provenance_code,
            }
            for source in item.sources
        ],
        "reason_code": item.reason_code,
    }


def signature_summary(signature) -> dict:
    return {
        "record_reference": signature.record_reference,
        "signature_fingerprint": signature.signature_fingerprint,
        "object_construct": [
            _observation_payload(item)
            for item in signature.object_construct_observations
        ],
        "assembly_component_role": [
            _observation_payload(item)
            for item in signature.assembly_component_role_observations
        ],
        "model_type": [
            _observation_payload(item) for item in signature.model_type_observations
        ],
        "variant": [
            _observation_payload(item) for item in signature.variant_observations
        ],
        "critical_attribute": [
            _observation_payload(item)
            for item in signature.critical_attribute_observations
        ],
        "unresolved": [
            _observation_payload(item) for item in signature.unresolved_observations
        ],
        "unknown_categories": [item.value for item in signature.unknown_categories],
    }


def audit_identity_signatures(records, *, target_part_numbers=()) -> dict:
    started = perf_counter()
    targets = {str(value) for value in target_part_numbers}
    fingerprints = set()
    coverage = {
        "recognized_object_construct_record_count": 0,
        "model_type_record_count": 0,
        "variant_record_count": 0,
        "critical_attribute_record_count": 0,
        "unresolved_observation_count": 0,
        "records_with_unresolved_observations": 0,
        "all_major_identity_categories_unknown_count": 0,
    }
    failures = []
    target_summaries = {}
    record_count = 0
    for source_index, record in enumerate(records):
        record_count += 1
        reference = f"csv-row-{source_index}"
        try:
            signature = derive_identity_signature(record, record_reference=reference)
        except (TypeError, ValueError) as exc:
            failures.append({
                "record_reference": reference,
                "failure_type": type(exc).__name__,
                "message": str(exc),
            })
            continue
        fingerprints.add(signature.signature_fingerprint)
        coverage["recognized_object_construct_record_count"] += bool(
            signature.object_construct_observations
        )
        coverage["model_type_record_count"] += bool(signature.model_type_observations)
        coverage["variant_record_count"] += bool(signature.variant_observations)
        coverage["critical_attribute_record_count"] += bool(
            signature.critical_attribute_observations
        )
        coverage["unresolved_observation_count"] += len(
            signature.unresolved_observations
        )
        coverage["records_with_unresolved_observations"] += bool(
            signature.unresolved_observations
        )
        coverage["all_major_identity_categories_unknown_count"] += (
            _MAJOR_IDENTITY_CATEGORIES <= set(signature.unknown_categories)
        )
        part_number = str(
            record.get("PART_NO", record.get("Part No", ""))
        ).strip()
        if part_number in targets:
            target_summaries[part_number] = signature_summary(signature)
    return {
        "records_derived": record_count - len(failures),
        "unique_signature_fingerprints": len(fingerprints),
        **coverage,
        "failure_count": len(failures),
        "failures": failures,
        "target_signatures": target_summaries,
        "wall_time_seconds": perf_counter() - started,
    }


def audit_csv(path: Path, *, target_part_numbers=()) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return audit_identity_signatures(
            csv.DictReader(handle), target_part_numbers=target_part_numbers
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--target-part-number", action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(
        audit_csv(
            args.csv_path,
            target_part_numbers=tuple(args.target_part_number),
        ),
        ensure_ascii=True,
        sort_keys=True,
        indent=2,
    ))


if __name__ == "__main__":
    main()
