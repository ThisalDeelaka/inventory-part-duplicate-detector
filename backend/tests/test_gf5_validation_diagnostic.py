"""GF-11D-GF5-PRE focused diagnostic contracts V1-V16."""

from __future__ import annotations

import inspect

from app.benchmarks import gf5_validation_diagnostic as diagnostic
from app.benchmarks.group_first_scale import benchmark_configuration
from app.resolution.validation import validate_resolution_result


def test_v1_v4_exact_throw_site_and_rule_are_explicit():
    source = inspect.getsource(validate_resolution_result)
    assert "targeted evidence request budget exceeded for a work unit" in source
    assert "len(result.targeted_evidence_requests)" in source
    assert "max_targeted_checks_per_work_unit" in source
    assert "request_counts_by_work_unit" in source


def test_v2_v11_minimal_selection_is_deterministic_and_exceeds_global_limit():
    units = [
        {"unit": object(), "size": 3, "planned": 20, "scheduled": 20},
        {"unit": object(), "size": 4, "planned": 21, "scheduled": 21},
        {"unit": object(), "size": 8, "planned": 40, "scheduled": 40},
    ]
    first = diagnostic._minimal_unit_selection(units, 40)
    second = diagnostic._minimal_unit_selection(units, 40)
    assert first == second == (units[0], units[1])
    assert sum(item["scheduled"] for item in first) == 41


def test_v3_diagnostic_output_contract_excludes_raw_identity_fields():
    source = inspect.getsource(diagnostic).casefold()
    for forbidden in (
        "description_raw", "part_no_raw", "record_ref_key\"", "sql_values",
        "authorization", "credential", "api_key",
    ):
        assert forbidden not in source


def test_v5_v6_aggregate_and_work_unit_counts_are_explicit():
    source = inspect.getsource(diagnostic.diagnose_canonical_scale)
    assert '"work_units"' in source
    assert '"observed_scan_wide_requests"' in source
    assert '"maximum_requests_in_one_work_unit"' in source


def test_v7_v8_v9_safety_counters_are_derived_from_output():
    source = inspect.getsource(diagnostic._output_counts)
    assert '"cannot_link_violations"' in source
    assert '"duplicate_assigned_members"' in source
    assert '"overlapping_accepted_memberships"' in source
    assert '"singleton_accepted_groups"' in source


def test_v10_reducer_uses_immutable_in_memory_replace_only():
    source = inspect.getsource(diagnostic._subset_input)
    assert "replace(" in source
    assert "commit" not in source and "delete" not in source and "update" not in source


def test_v12_pure_and_persistence_boundaries_are_distinct():
    source = inspect.getsource(diagnostic.diagnose_canonical_scale)
    assert '"PURE_OUTPUT_VALIDATION"' in source
    assert '"persistence_started"' in source
    assert '"reconstruction_started"' in source


def test_v13_historical_comparison_has_stable_rule_surface():
    assert diagnostic.PER_WORK_UNIT_BUDGET_MESSAGE == (
        "targeted evidence request budget exceeded"
    )


def test_v14_provider_none_is_explicit():
    configuration = benchmark_configuration()
    assert configuration.llm_provider == configuration.group_llm_provider == "none"


def test_v15_disposable_database_and_no_default_database_access():
    source = inspect.getsource(diagnostic.diagnose_canonical_scale)
    assert "TemporaryDirectory" in source
    assert "database_url" not in source
    assert "inventory_detector.db" not in source


def test_v16_no_schema_migration_or_dependency_hook():
    source = inspect.getsource(diagnostic).casefold()
    assert "alembic" not in source
    assert "pip install" not in source
    assert "subprocess" not in source


def test_classification_requires_global_scope_mismatch_before_persistence():
    assert diagnostic.classify_budget_failure(
        message=diagnostic.PER_WORK_UNIT_BUDGET_MESSAGE,
        boundary="PURE_OUTPUT_VALIDATION",
        observed=80,
        expected=40,
        maximum_unit=40,
    ) == "IMPLEMENTATION_DEFECT"
    assert diagnostic.classify_budget_failure(
        message=diagnostic.PER_WORK_UNIT_BUDGET_MESSAGE,
        boundary="RECONSTRUCTION_VALIDATION",
        observed=80,
        expected=40,
        maximum_unit=40,
    ) == "BLOCKED"


def test_instrumentation_does_not_edit_or_replace_resolver_semantics():
    source = inspect.getsource(diagnostic)
    assert "original_resolve(" in source
    assert "validate_resolution_result" in source
    assert "IdentityResolutionResult(" not in source
    assert "DeferredIdentityWorkUnit(" not in source
    assert "IdentityConflict(" not in source
    assert "IdentityGroupHypothesis(" not in source


def test_all_non_overlapping_timing_keys_are_declared():
    assert diagnostic.TIMING_KEYS == (
        "WORK_UNIT_BUILD", "SUPPORT_GRAPH_BUILD", "CANNOT_LINK_GRAPH_BUILD",
        "BASE_CELL_BUILD", "BRIDGE_ANALYSIS", "ATTRIBUTE_CONFLICT_INDEX",
        "TARGETED_CROSS_BRANCH_EVALUATION", "PARTITION_SEARCH",
        "SAFE_SUBGROUP_SALVAGE", "OUTPUT_ASSEMBLY", "VALIDATION",
        "PERSISTENCE", "RECONSTRUCTION_VALIDATION", "OTHER_UNATTRIBUTED",
    )
