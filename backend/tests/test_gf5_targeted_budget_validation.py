"""GF-11D-GF5-FIX focused per-work-unit budget contracts C1-C10."""

from dataclasses import replace
from itertools import combinations
import inspect

import pytest

from app.resolution import validation
from app.resolution.contracts import (
    IdentityResolutionNeighborhood,
    TargetedEvidenceReason,
    TargetedEvidenceRequest,
)
from app.resolution.validation import (
    IdentityResolutionValidationError,
    validate_resolution_result,
    with_resolution_result_fingerprint,
    with_targeted_request_fingerprint,
)
from test_identity_resolution_contracts import record, resolution_input, result


def _fixture(unit_sizes, request_counts, *, budget=40):
    records = tuple(record(index) for index in range(1, sum(unit_sizes) + 1))
    neighborhoods = []
    units = []
    offset = 0
    for index, size in enumerate(unit_sizes, start=1):
        members = tuple(range(offset + 1, offset + size + 1))
        reference = f"unit-{index}"
        units.append((reference, members))
        neighborhoods.append(IdentityResolutionNeighborhood(
            neighborhood_reference=reference,
            scan_id=1,
            discovery_run_id=20,
            member_record_ids=members,
            truncated=False,
            degraded=False,
        ))
        offset += size
    value = resolution_input(
        len(records),
        neighborhoods=tuple(neighborhoods),
        records=records,
    )
    value = replace(
        value,
        resolver_configuration=replace(
            value.resolver_configuration,
            max_targeted_checks_per_work_unit=budget,
        ),
    )
    references = {item.record_id: item.record_ref_key for item in records}
    requests = []
    for (owner, members), count in zip(units, request_counts):
        pairs = tuple(combinations(members, 2))
        assert count <= len(pairs)
        for left, right in pairs[:count]:
            requests.append(with_targeted_request_fingerprint(TargetedEvidenceRequest(
                scan_id=1,
                record_id_1=left,
                record_id_2=right,
                reason=TargetedEvidenceReason.PARTITION_CROSS_CHECK,
                requesting_work_unit_reference=owner,
                request_fingerprint="",
                record_reference_1=references[left],
                record_reference_2=references[right],
            )))
    requests = tuple(sorted(
        requests,
        key=lambda item: (item.record_id_1, item.record_id_2, item.reason.value),
    ))
    return value, result(
        value,
        unassigned=tuple(range(1, len(records) + 1)),
        requests=requests,
    )


def test_c1_c2_validator_encodes_per_work_unit_semantics_without_global_cap():
    source = inspect.getsource(validation.validate_resolution_result)
    assert "request_counts_by_work_unit" in source
    assert "for count in request_counts_by_work_unit.values()" in source
    assert "sum(request_counts_by_work_unit.values())" in source
    assert not (
        "len(result.targeted_evidence_requests)\n"
        "        <= resolution_input.resolver_configuration."
        "max_targeted_checks_per_work_unit"
    ) in source


def test_c3_former_two_unit_41_total_false_failure_is_valid():
    value, output = _fixture((10, 10), (20, 21))
    validate_resolution_result(output, value)


def test_c4_exact_40_per_unit_80_total_boundary_is_valid():
    value, output = _fixture((10, 10), (40, 40))
    validate_resolution_result(output, value)


def test_c5_true_41_request_single_unit_violation_fails_closed():
    value, output = _fixture((10,), (41,))
    with pytest.raises(
        IdentityResolutionValidationError,
        match="budget exceeded for a work unit",
    ):
        validate_resolution_result(output, value)


def test_c6_large_safe_aggregate_is_valid():
    value, output = _fixture((10, 10, 10, 10, 10), (40, 40, 40, 40, 40))
    validate_resolution_result(output, value)


def test_c7_request_metric_count_still_reconciles():
    value, output = _fixture((10, 10), (20, 21))
    tampered = replace(
        output,
        metrics=replace(output.metrics, targeted_evidence_request_count=40),
        resolution_fingerprint="",
    )
    tampered = with_resolution_result_fingerprint(tampered)
    with pytest.raises(IdentityResolutionValidationError, match="metrics do not reconcile"):
        validate_resolution_result(tampered, value)


def test_c8_c9_unknown_work_unit_ownership_fails_closed():
    value, output = _fixture((10,), (1,))
    request = with_targeted_request_fingerprint(replace(
        output.targeted_evidence_requests[0],
        requesting_work_unit_reference="unknown-unit",
        request_fingerprint="",
    ))
    tampered = result(
        value,
        unassigned=tuple(range(1, 11)),
        requests=(request,),
    )
    with pytest.raises(IdentityResolutionValidationError, match="unknown work-unit"):
        validate_resolution_result(tampered, value)


def test_c10_mismatched_owner_endpoints_fail_closed():
    value, output = _fixture((10, 10), (1, 0))
    request = with_targeted_request_fingerprint(replace(
        output.targeted_evidence_requests[0],
        requesting_work_unit_reference="unit-2",
        request_fingerprint="",
    ))
    tampered = result(
        value,
        unassigned=tuple(range(1, 21)),
        requests=(request,),
    )
    with pytest.raises(IdentityResolutionValidationError, match="declared work unit"):
        validate_resolution_result(tampered, value)
