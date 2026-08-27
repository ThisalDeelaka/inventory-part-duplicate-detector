"""GF-11D-GF5-PRE aggregate-only resolution validation diagnosis.

This helper instruments the committed pure resolver in-process. It never
changes resolver semantics, persists diagnostic payloads, or exposes record
content/identity. The production validator remains the failure authority.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from app.benchmarks.group_first_scale import run_scale_benchmark
from app.benchmarks.group_first_scale_generator import CANONICAL_SCENARIO
from app.engine.identity_edge import IdentityEdgeClass
from app.resolution import resolver
from app.resolution.validation import IdentityResolutionValidationError
from app.services import identity_resolution_service as resolution_service


DIAGNOSTIC_CONTRACT_VERSION = "gf11d-gf5-validation-diagnostic-v1"
CANONICAL_SEED = 1101
PER_WORK_UNIT_BUDGET_MESSAGE = "targeted evidence request budget exceeded"
TIMING_KEYS = (
    "WORK_UNIT_BUILD",
    "SUPPORT_GRAPH_BUILD",
    "CANNOT_LINK_GRAPH_BUILD",
    "BASE_CELL_BUILD",
    "BRIDGE_ANALYSIS",
    "ATTRIBUTE_CONFLICT_INDEX",
    "TARGETED_CROSS_BRANCH_EVALUATION",
    "PARTITION_SEARCH",
    "SAFE_SUBGROUP_SALVAGE",
    "OUTPUT_ASSEMBLY",
    "VALIDATION",
    "PERSISTENCE",
    "RECONSTRUCTION_VALIDATION",
    "OTHER_UNATTRIBUTED",
)


class _ExclusiveTimer:
    def __init__(self):
        self.elapsed = Counter()
        self._stack = []
        self._last = None

    @contextmanager
    def measure(self, category):
        now = time.perf_counter()
        if self._stack:
            self.elapsed[self._stack[-1]] += now - self._last
        self._stack.append(category)
        self._last = now
        try:
            yield
        finally:
            now = time.perf_counter()
            self.elapsed[self._stack.pop()] += now - self._last
            self._last = now


def _edge_counts(value):
    counts = Counter(edge.edge_class.value for edge in value.machine_evidence_edges)
    return {
        "support": counts[IdentityEdgeClass.STRONG_SUPPORT.value],
        "review": counts[IdentityEdgeClass.REVIEW_SUPPORT.value],
        "neutral": counts[IdentityEdgeClass.NON_GROUPABLE.value],
        "cannot_link": counts[IdentityEdgeClass.CANNOT_LINK.value],
    }


def _output_counts(result, value):
    assignments = Counter(
        member for group in result.accepted_groups for member in group.member_record_ids
    )
    accepted = set(assignments)
    unassigned = set(result.unassigned_record_ids)
    known = {record.record_id for record in value.canonical_records}
    cannot_pairs = {
        (edge.record_id_1, edge.record_id_2)
        for edge in value.machine_evidence_edges
        if edge.edge_class == IdentityEdgeClass.CANNOT_LINK
    }
    violations = 0
    for group in result.accepted_groups:
        members = set(group.member_record_ids)
        violations += sum(left in members and right in members for left, right in cannot_pairs)
    overlapping_memberships = sum(count > 1 for count in assignments.values())
    return {
        "likely_groups": sum(group.status.value == "LIKELY_DUPLICATE_GROUP"
                             for group in result.accepted_groups),
        "review_groups": sum(
            group.status.value == "POSSIBLE_DUPLICATE_GROUP_REVIEW"
            for group in result.accepted_groups
        ),
        "conflicts": len(result.conflicts),
        "deferred": len(result.deferred_work_units),
        "unassigned": len(result.unassigned_record_ids),
        "covered_members": len(accepted),
        "duplicate_assigned_members": overlapping_memberships,
        "overlapping_accepted_memberships": overlapping_memberships,
        "missing_members": len(known - accepted - unassigned),
        "cannot_link_violations": violations,
        "singleton_accepted_groups": sum(
            len(group.member_record_ids) < 2 for group in result.accepted_groups
        ),
        "targeted_requests": len(result.targeted_evidence_requests),
        "targeted_results": len(result.targeted_evidence_results),
        "candidate_partitions_explored": result.metrics.candidate_partitions_explored,
    }


def classify_budget_failure(*, message, boundary, observed, expected, maximum_unit):
    if (
        message == PER_WORK_UNIT_BUDGET_MESSAGE
        and boundary == "PURE_OUTPUT_VALIDATION"
        and observed > expected
        and maximum_unit <= expected
    ):
        return "IMPLEMENTATION_DEFECT"
    return "BLOCKED"


def _minimal_unit_selection(unit_diagnostics, budget):
    """Choose the fewest-record actual work units whose requests exceed budget."""
    target = budget + 1
    candidates = [item for item in unit_diagnostics if item["scheduled"]]
    states = {0: (0, ())}
    for index, item in enumerate(candidates):
        previous = tuple(states.items())
        for total, (record_count, selected) in previous:
            updated = min(target, total + item["scheduled"])
            proposal = (record_count + item["size"], selected + (index,))
            current = states.get(updated)
            if current is None or (proposal[0], len(proposal[1]), proposal[1]) < (
                current[0], len(current[1]), current[1]
            ):
                states[updated] = proposal
    return tuple(candidates[index] for index in states.get(target, (0, ()))[1])


def _subset_input(value, selected_units):
    selected_ids = {
        member for item in selected_units for member in item["unit"].member_ids
    }
    return replace(
        value,
        canonical_records=tuple(
            record for record in value.canonical_records if record.record_id in selected_ids
        ),
        identity_neighborhoods=tuple(
            item for item in value.identity_neighborhoods
            if set(item.member_record_ids) <= selected_ids
        ),
        machine_evidence_edges=tuple(
            edge for edge in value.machine_evidence_edges
            if edge.record_id_1 in selected_ids and edge.record_id_2 in selected_ids
        ),
        human_constraints=tuple(
            item for item in value.human_constraints
            if item.record_id_1 in selected_ids and item.record_id_2 in selected_ids
        ),
    )


def _fixture_shape(value, request_count, work_units):
    sizes = tuple(len(item.member_ids) for item in work_units)
    return {
        "records": len(value.canonical_records),
        "neighborhoods": len(value.identity_neighborhoods),
        "neighborhood_member_occurrences": sum(
            len(item.member_record_ids) for item in value.identity_neighborhoods
        ),
        "machine_edges": len(value.machine_evidence_edges),
        "edge_classes": _edge_counts(value),
        "work_units": len(work_units),
        "max_work_unit_size": max(sizes, default=0),
        "targeted_requests": request_count,
    }


def diagnose_canonical_scale(records=5_000, seed=CANONICAL_SEED):
    timer = _ExclusiveTimer()
    captured = {
        "failure_message": None,
        "failure_boundary": None,
        "value": None,
        "provider": None,
        "result": None,
        "units": (),
        "unit_requests": [],
        "candidate_subgroups": 0,
        "pure_validated": False,
        "persistence_started": False,
        "reconstruction_started": False,
    }
    restores = []

    def patch(module, name, replacement):
        restores.append((module, name, getattr(module, name)))
        setattr(module, name, replacement)

    def timed(module, name, category, after=None):
        original = getattr(module, name)

        def wrapped(*args, **kwargs):
            with timer.measure(category):
                result = original(*args, **kwargs)
            if after:
                after(args, result)
            return result

        patch(module, name, wrapped)

    original_resolve = resolution_service.resolve_identity_groups
    original_validate = resolver.validate_resolution_result
    original_service_validate = resolution_service.validate_resolution_result
    original_targeted = resolver.CanonicalEvaluatorTargetedEvidenceProvider.evaluate
    original_persist = resolution_service._persist_result
    original_reload = resolution_service.load_persisted_resolution_result

    def work_units_after(_args, result):
        captured["units"] = result

    def targeted_after(args, result):
        unit = args[1]
        budget = args[0].resolver_configuration.max_targeted_checks_per_work_unit
        captured["unit_requests"].append({
            "unit": unit,
            "size": len(unit.member_ids),
            "planned": len(result),
            "scheduled": min(len(result), budget),
        })

    def candidates_after(_args, result):
        captured["candidate_subgroups"] += len(result[0])

    def diagnostic_validate(result, value):
        captured["result"] = result
        with timer.measure("VALIDATION"):
            try:
                original_validate(result, value)
                captured["pure_validated"] = True
            except IdentityResolutionValidationError as error:
                captured["failure_message"] = str(error)
                captured["failure_boundary"] = "PURE_OUTPUT_VALIDATION"
                raise

    def diagnostic_service_validate(result, value):
        with timer.measure("RECONSTRUCTION_VALIDATION"):
            return original_service_validate(result, value)

    def diagnostic_resolve(value, provider):
        captured["value"] = value
        captured["provider"] = provider
        with timer.measure("OTHER_UNATTRIBUTED"):
            return original_resolve(value, provider)

    def targeted_evaluate(instance, request):
        with timer.measure("TARGETED_CROSS_BRANCH_EVALUATION"):
            return original_targeted(instance, request)

    def persist(*args, **kwargs):
        captured["persistence_started"] = True
        with timer.measure("PERSISTENCE"):
            return original_persist(*args, **kwargs)

    def reload(*args, **kwargs):
        captured["reconstruction_started"] = True
        return original_reload(*args, **kwargs)

    patch(resolution_service, "resolve_identity_groups", diagnostic_resolve)
    patch(resolver, "validate_resolution_result", diagnostic_validate)
    patch(resolution_service, "validate_resolution_result", diagnostic_service_validate)
    patch(resolver.CanonicalEvaluatorTargetedEvidenceProvider, "evaluate", targeted_evaluate)
    patch(resolution_service, "_persist_result", persist)
    patch(resolution_service, "load_persisted_resolution_result", reload)
    timed(resolver, "_work_units", "WORK_UNIT_BUILD", work_units_after)
    timed(resolver, "_positive_adjacency", "SUPPORT_GRAPH_BUILD")
    timed(resolver, "_protected_conflict", "CANNOT_LINK_GRAPH_BUILD")
    timed(resolver, "_constraint_conflicts", "BASE_CELL_BUILD")
    timed(resolver, "_bridge_summary", "BRIDGE_ANALYSIS")
    timed(resolver, "_targeted_requests", "OTHER_UNATTRIBUTED", targeted_after)
    timed(resolver, "_candidate_groups", "PARTITION_SEARCH", candidates_after)
    timed(resolver, "_select_partition", "SAFE_SUBGROUP_SALVAGE")
    timed(resolver, "with_resolution_result_fingerprint", "OUTPUT_ASSEMBLY")

    try:
        with tempfile.TemporaryDirectory(prefix="gf5-validation-diagnostic-") as directory:
            scale = run_scale_benchmark(
                records=records,
                seed=seed,
                scenario=CANONICAL_SCENARIO,
                db_path=Path(directory) / "diagnostic.sqlite",
            )
    finally:
        for module, name, original in reversed(restores):
            setattr(module, name, original)

    value = captured["value"]
    result = captured["result"]
    if value is None or result is None:
        raise RuntimeError("canonical run did not reach pure GF5 output validation")
    budget = value.resolver_configuration.max_targeted_checks_per_work_unit
    observed = len(result.targeted_evidence_requests)
    maximum_unit = max(
        (item["scheduled"] for item in captured["unit_requests"]), default=0
    )
    selected = _minimal_unit_selection(captured["unit_requests"], budget)
    minimized = _subset_input(value, selected)
    minimized_units = resolver._work_units(minimized)
    minimized_request_count = sum(item["scheduled"] for item in selected)
    minimized_message = None
    try:
        original_resolve(minimized, captured["provider"])
    except IdentityResolutionValidationError as error:
        minimized_message = str(error)

    units = captured["units"]
    unit_sizes = tuple(len(item.member_ids) for item in units)
    output = _output_counts(result, value)
    classification = classify_budget_failure(
        message=captured["failure_message"],
        boundary=captured["failure_boundary"],
        observed=observed,
        expected=budget,
        maximum_unit=maximum_unit,
    )
    timings = {key: round(timer.elapsed[key], 6) for key in TIMING_KEYS}
    return {
        "contract_version": DIAGNOSTIC_CONTRACT_VERSION,
        "canonical_configuration": {
            "scenario": "group-first-scale-corpus-v1",
            "records": records,
            "seed": seed,
            "provider": "none",
            "mode": "group_first_primary",
            "policy": "group-first-orchestration-policy-v2",
            "database_is_disposable": True,
        },
        "scale_terminal_status": scale.run.status.value,
        "failure": {
            "exception_type": "IdentityResolutionValidationError",
            "message": captured["failure_message"],
            "boundary": captured["failure_boundary"],
            "validation_function": "validate_resolution_result",
            "expected_max_per_work_unit": budget,
            "observed_scan_wide_requests": observed,
            "maximum_requests_in_one_work_unit": maximum_unit,
            "persistence_started": captured["persistence_started"],
            "reconstruction_started": captured["reconstruction_started"],
        },
        "aggregate_context": {
            "work_units": len(units),
            "current_work_unit_ordinal": None,
            "current_work_unit_size": None,
            "max_work_unit_size": max(unit_sizes, default=0),
            "input_neighborhoods": len(value.identity_neighborhoods),
            "input_neighborhood_member_occurrences": sum(
                len(item.member_record_ids) for item in value.identity_neighborhoods
            ),
            "input_edges": _edge_counts(value),
            "base_cells": None,
            "base_cells_note": "not materialized as a distinct GF5 artifact",
            "connected_components": len(units),
            "candidate_subgroups": captured["candidate_subgroups"],
            **output,
        },
        "timing_seconds": timings,
        "timing_reconciles_to_gf5_seconds": round(sum(timings.values()), 6),
        "local_or_global": "SCAN_LEVEL_GLOBAL_VALIDATION",
        "work_units_exceeding_their_own_budget": sum(
            item["scheduled"] > budget for item in captured["unit_requests"]
        ),
        "work_units_contributing_targeted_requests": sum(
            bool(item["scheduled"]) for item in captured["unit_requests"]
        ),
        "minimized_fixture": {
            **_fixture_shape(minimized, minimized_request_count, minimized_units),
            "validation_message": minimized_message,
            "same_validation_rule": minimized_message == captured["failure_message"],
            "persisted_data_mutated": False,
        },
        "pure_resolver_pre_persistence_validated": captured["pure_validated"],
        "post_persistence_reconstruction": "NOT_REACHED",
        "violated_invariant_category": "OTHER_GLOBAL_VS_PER_WORK_UNIT_BUDGET_SCOPE",
        "classification": classification,
        "provider_calls": 0,
        "configured_database_accessed": False,
        "raw_record_data_captured": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=CANONICAL_SEED)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = diagnose_canonical_scale(args.records, args.seed)
    args.output.write_text(
        json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if result["classification"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
