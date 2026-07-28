from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path
import subprocess
import sys

import pytest

from app.contracts import (
    CandidatePair,
    CandidateScoringResult,
    CanonicalRecord,
    LegacyBusinessStatus,
    LegacyStatusTranslation,
    RedesignedResultMode,
    ResultPolicy,
    ScoringEvidence,
    TargetBusinessStatus,
    translate_legacy_business_status,
)
from app.contracts import status_compatibility as status_compatibility_module
from app.engine.scoring import score_candidate


LEGACY_STATUS_VALUES = (
    'LIKELY_DUPLICATE',
    'POSSIBLE_DUPLICATE_REVIEW',
    'RELATED_BUT_NOT_DUPLICATE',
    'REJECTED_BY_BUSINESS_RULE',
    'DATA_CONFLICT_REVIEW',
    'CROSS_SITE_STANDARDIZATION_CANDIDATE',
    'INSUFFICIENT_DATA',
)

EXPECTED_MAPPINGS = (
    ('LIKELY_DUPLICATE', 'DUPLICATE_CANDIDATE'),
    ('POSSIBLE_DUPLICATE_REVIEW', 'POSSIBLE_DUPLICATE_REVIEW'),
    ('RELATED_BUT_NOT_DUPLICATE', 'RELATED_BUT_NOT_DUPLICATE'),
    ('REJECTED_BY_BUSINESS_RULE', 'DATA_CONFLICT_REVIEW'),
    ('DATA_CONFLICT_REVIEW', 'DATA_CONFLICT_REVIEW'),
    (
        'CROSS_SITE_STANDARDIZATION_CANDIDATE',
        'CROSS_SITE_STANDARDIZATION_CANDIDATE',
    ),
    ('INSUFFICIENT_DATA', 'INSUFFICIENT_DATA'),
)

EXPECTED_RESULT_KEYS = (
    'final_score',
    'confidence_level',
    'description_similarity',
    'tfidf_score',
    'fuzzy_score',
    'part_no_similarity',
    'technical_token_score',
    'matched_fields',
    'mismatched_fields',
    'explanation',
    'recommended_action',
    'business_status',
    'rule_decision',
    'rejection_reason',
    'scan_mode',
    'critical_mismatches',
    'variant_attributes_a',
    'variant_attributes_b',
    'generic_description_warning',
    'application_context_a',
    'application_context_b',
    'application_context_warning',
    'normalized_description_a',
    'normalized_description_b',
    'normalized_part_no_a',
    'normalized_part_no_b',
)


def _record(
    part_no: str,
    description: str,
    *,
    site: str = 'S1',
    unit: str = 'PCS',
    hsn: str = '1000',
) -> dict[str, str]:
    return {
        'PART_NO': part_no,
        'DESCRIPTION': description,
        'CONTRACT': site,
        'UNIT_MEAS': unit,
        'HSN_SAC_CODE': hsn,
    }


def _likely_duplicate_result() -> dict:
    return score_candidate(
        _record('MCB30A-1', 'MCB30A'),
        _record('MCB30A-2', 'MCB 30 Amp'),
        ['CONTRACT', 'UNIT_MEAS'],
    )


def _typed_result(source: dict) -> CandidateScoringResult:
    return CandidateScoringResult.from_legacy_mapping(source)


def _approved_typed_mapping() -> dict:
    return {
        LegacyBusinessStatus(source): TargetBusinessStatus(target)
        for source, target in EXPECTED_MAPPINGS
    }


def test_legacy_status_vocabulary_is_exact_ordered_and_has_no_aliases():
    members = list(LegacyBusinessStatus)

    assert len(members) == 7
    assert tuple(member.name for member in members) == LEGACY_STATUS_VALUES
    assert tuple(member.value for member in members) == LEGACY_STATUS_VALUES
    assert tuple(LegacyBusinessStatus.__members__) == LEGACY_STATUS_VALUES
    assert len(LegacyBusinessStatus.__members__) == len(members)
    assert tuple(str(member) for member in members) == LEGACY_STATUS_VALUES
    assert 'UNIQUE_NO_MATCH' not in LegacyBusinessStatus.__members__


def test_legacy_status_constructs_only_from_exact_legacy_values():
    for value in LEGACY_STATUS_VALUES:
        assert LegacyBusinessStatus(value).value == value

    invalid_values = (
        '',
        'likely_duplicate',
        ' LIKELY_DUPLICATE',
        'LIKELY_DUPLICATE ',
        'DUPLICATE_CANDIDATE',
        'UNIQUE_NO_MATCH',
    )
    for value in invalid_values:
        with pytest.raises(ValueError):
            LegacyBusinessStatus(value)


def test_exact_complete_mapping_uses_independent_literal_oracle():
    actual = tuple(
        (
            status.value,
            translate_legacy_business_status(status).value,
        )
        for status in LegacyBusinessStatus
    )

    assert actual == EXPECTED_MAPPINGS
    assert len(actual) == len(set(source for source, _target in actual)) == 7
    assert all(
        type(translate_legacy_business_status(status))
        is TargetBusinessStatus
        for status in LegacyBusinessStatus
    )
    assert 'UNIQUE_NO_MATCH' not in {
        target for _source, target in actual
    }


def test_mapping_validator_rejects_matching_raw_string_keys():
    raw_string_mapping = {
        source: TargetBusinessStatus(target)
        for source, target in EXPECTED_MAPPINGS
    }

    with pytest.raises(
        RuntimeError,
        match='keys must be LegacyBusinessStatus',
    ):
        status_compatibility_module._validate_legacy_to_target_mapping(
            raw_string_mapping
        )


def test_mapping_validator_rejects_plain_string_target_value():
    mapping = _approved_typed_mapping()
    mapping[LegacyBusinessStatus.LIKELY_DUPLICATE] = 'DUPLICATE_CANDIDATE'

    with pytest.raises(
        RuntimeError,
        match='values must be TargetBusinessStatus',
    ):
        status_compatibility_module._validate_legacy_to_target_mapping(
            mapping
        )


@pytest.mark.parametrize(
    ('mutation', 'message'),
    [
        ('missing-key', 'keys must exactly match'),
        ('extra-key', 'keys must be LegacyBusinessStatus'),
    ],
)
def test_mapping_validator_rejects_missing_and_extra_keys(
    mutation,
    message,
):
    mapping = _approved_typed_mapping()
    if mutation == 'missing-key':
        del mapping[LegacyBusinessStatus.INSUFFICIENT_DATA]
    else:
        mapping['FUTURE_STATUS'] = TargetBusinessStatus.INSUFFICIENT_DATA

    with pytest.raises(RuntimeError, match=message):
        status_compatibility_module._validate_legacy_to_target_mapping(
            mapping
        )


def test_mapping_validator_rejects_unique_no_match_target():
    mapping = _approved_typed_mapping()
    mapping[LegacyBusinessStatus.INSUFFICIENT_DATA] = (
        TargetBusinessStatus.UNIQUE_NO_MATCH
    )

    with pytest.raises(
        RuntimeError,
        match='UNIQUE_NO_MATCH cannot have a legacy source mapping',
    ):
        status_compatibility_module._validate_legacy_to_target_mapping(
            mapping
        )


def test_translator_rejects_untyped_target_unrelated_and_missing_inputs():
    class UnrelatedStatus(Enum):
        LIKELY_DUPLICATE = 'LIKELY_DUPLICATE'

    invalid = (
        'LIKELY_DUPLICATE',
        TargetBusinessStatus.DUPLICATE_CANDIDATE,
        UnrelatedStatus.LIKELY_DUPLICATE,
        None,
    )
    for status in invalid:
        with pytest.raises(TypeError, match='LegacyBusinessStatus'):
            translate_legacy_business_status(status)


def test_translation_is_frozen_factory_only_exact_and_repeatable():
    source = _likely_duplicate_result()
    result = _typed_result(source)

    first = LegacyStatusTranslation.from_scoring_result(result)
    second = LegacyStatusTranslation.from_scoring_result(result)

    assert type(first) is LegacyStatusTranslation
    assert type(first.legacy_business_status) is LegacyBusinessStatus
    assert type(first.target_business_status) is TargetBusinessStatus
    assert type(first.rule_decision) is str
    assert type(first.rejection_reason) is str
    assert first.legacy_business_status is LegacyBusinessStatus.LIKELY_DUPLICATE
    assert (
        first.target_business_status
        is TargetBusinessStatus.DUPLICATE_CANDIDATE
    )
    assert first.rule_decision == source['rule_decision']
    assert first.rejection_reason == source['rejection_reason']
    assert first == second
    assert first is not second

    with pytest.raises(FrozenInstanceError):
        first.rule_decision = 'CHANGED'
    with pytest.raises(TypeError):
        LegacyStatusTranslation()
    with pytest.raises(TypeError):
        LegacyStatusTranslation(
            LegacyBusinessStatus.LIKELY_DUPLICATE,
            TargetBusinessStatus.DUPLICATE_CANDIDATE,
            'ALLOW',
            '',
        )


def test_translation_factory_accepts_scoring_result_subclasses():
    class SpecializedResult(CandidateScoringResult):
        pass

    result = SpecializedResult.from_legacy_mapping(
        _likely_duplicate_result()
    )

    translation = LegacyStatusTranslation.from_scoring_result(result)

    assert (
        translation.legacy_business_status
        is LegacyBusinessStatus.LIKELY_DUPLICATE
    )


@pytest.mark.parametrize(
    ('legacy_value', 'target_value'),
    EXPECTED_MAPPINGS,
)
def test_all_seven_statuses_translate_through_result_contract_without_mutation(
    legacy_value,
    target_value,
):
    source = _likely_duplicate_result()
    source['business_status'] = legacy_value
    original = dict(source)
    original_order = tuple(source)
    result = _typed_result(source)

    translation = LegacyStatusTranslation.from_scoring_result(result)

    assert translation.legacy_business_status.value == legacy_value
    assert translation.target_business_status.value == target_value
    assert translation.rule_decision == original['rule_decision']
    assert translation.rejection_reason == original['rejection_reason']
    assert source == original
    assert tuple(source) == original_order
    assert result.to_legacy_dict() == original
    assert tuple(result.to_legacy_dict()) == original_order


def test_unsupported_status_fails_explicitly_without_fallback():
    source = _likely_duplicate_result()
    source['business_status'] = 'FUTURE_UNSUPPORTED_STATUS'
    result = _typed_result(source)

    with pytest.raises(
        ValueError,
        match='unsupported legacy business_status.*FUTURE_UNSUPPORTED_STATUS',
    ) as error:
        LegacyStatusTranslation.from_scoring_result(result)

    assert type(error.value.__cause__) is ValueError
    assert (
        "'FUTURE_UNSUPPORTED_STATUS' is not a valid LegacyBusinessStatus"
        in str(error.value.__cause__)
    )


@pytest.mark.parametrize(
    'rejection_reason',
    [
        'SAME_PART_NO',
        'UNIT_MEAS_MISMATCH',
        'PRODUCT_CATEGORY_ID_MISMATCH',
    ],
)
def test_rejected_business_rule_mapping_is_reason_independent(
    rejection_reason,
):
    source = _likely_duplicate_result()
    source['business_status'] = 'REJECTED_BY_BUSINESS_RULE'
    source['rule_decision'] = 'REJECT'
    source['rejection_reason'] = rejection_reason
    original = dict(source)
    result = _typed_result(source)

    translation = LegacyStatusTranslation.from_scoring_result(result)
    legacy_output = result.to_legacy_dict()

    assert (
        translation.legacy_business_status
        is LegacyBusinessStatus.REJECTED_BY_BUSINESS_RULE
    )
    assert (
        translation.target_business_status
        is TargetBusinessStatus.DATA_CONFLICT_REVIEW
    )
    assert translation.rule_decision == 'REJECT'
    assert translation.rejection_reason == rejection_reason
    assert source == original
    assert legacy_output == original
    for leaked_key in (
        'target_business_status',
        'legacy_business_status',
        'translation',
    ):
        assert leaked_key not in legacy_output


@pytest.mark.parametrize('invalid', [{}, object(), 'LIKELY_DUPLICATE'])
def test_translation_factory_rejects_non_scoring_results(invalid):
    with pytest.raises(TypeError, match='CandidateScoringResult'):
        LegacyStatusTranslation.from_scoring_result(invalid)


@pytest.mark.parametrize(
    ('business_status', 'error_type', 'message'),
    [
        (None, TypeError, 'business_status must be str'),
        (17, TypeError, 'business_status must be str'),
    ],
)
def test_result_contract_owns_malformed_business_status_validation(
    business_status,
    error_type,
    message,
):
    source = _likely_duplicate_result()
    source['business_status'] = business_status

    with pytest.raises(error_type, match=message):
        CandidateScoringResult.from_legacy_mapping(source)


def test_result_contract_owns_missing_business_status_validation():
    source = _likely_duplicate_result()
    del source['business_status']

    with pytest.raises(
        ValueError,
        match='missing required field: business_status',
    ):
        CandidateScoringResult.from_legacy_mapping(source)


def test_translation_does_not_mutate_or_leak_into_legacy_output():
    source = score_candidate(
        _record('FILTER-1', 'Generator Oil Filter'),
        _record('FILTER-2', 'Generator Air Filter'),
        ['CONTRACT', 'UNIT_MEAS'],
    )
    original = dict(source)
    result = _typed_result(source)
    raw_before = result.raw_result
    raw_order = tuple(raw_before)
    nested_before = {
        key: raw_before[key]
        for key in (
            'matched_fields',
            'critical_mismatches',
            'variant_attributes_a',
            'variant_attributes_b',
        )
    }

    first = LegacyStatusTranslation.from_scoring_result(result)
    second = LegacyStatusTranslation.from_scoring_result(result)
    converted = result.to_legacy_dict()

    assert first == second
    assert source == original
    assert result.raw_result is raw_before
    assert dict(raw_before) == original
    assert tuple(raw_before) == raw_order == EXPECTED_RESULT_KEYS
    assert converted == original
    assert tuple(converted) == EXPECTED_RESULT_KEYS
    for key, nested in nested_before.items():
        assert raw_before[key] is nested
        assert converted[key] is nested
    for leaked_key in (
        'target_business_status',
        'legacy_business_status',
        'translation',
    ):
        assert leaked_key not in source
        assert leaked_key not in raw_before
        assert leaked_key not in converted


ACTUAL_PATH_CASES = (
    (
        'likely-duplicate',
        _record('MCB30A-1', 'MCB30A'),
        _record('MCB30A-2', 'MCB 30 Amp'),
        'LIKELY_DUPLICATE',
        'DUPLICATE_CANDIDATE',
    ),
    (
        'business-rule-rejection',
        _record('SAME-PART', 'Pump'),
        _record('SAME-PART', 'Pump'),
        'REJECTED_BY_BUSINESS_RULE',
        'DATA_CONFLICT_REVIEW',
    ),
    (
        'data-conflict',
        _record('PIPE-1', 'SS Pipe', hsn='7306'),
        _record('PIPE-2', 'Stainless Steel Pipe', hsn='3917'),
        'DATA_CONFLICT_REVIEW',
        'DATA_CONFLICT_REVIEW',
    ),
    (
        'cross-site',
        _record('PIPE-1', 'SS Pipe', site='S1'),
        _record('PIPE-2', 'Stainless Steel Pipe', site='S2'),
        'CROSS_SITE_STANDARDIZATION_CANDIDATE',
        'CROSS_SITE_STANDARDIZATION_CANDIDATE',
    ),
    (
        'related-but-not-duplicate',
        _record('FILTER-1', 'Generator Oil Filter'),
        _record('FILTER-2', 'Generator Air Filter'),
        'RELATED_BUT_NOT_DUPLICATE',
        'RELATED_BUT_NOT_DUPLICATE',
    ),
    (
        'possible-review',
        _record('SP-GEN-AIR-FLT', 'Generator Air Filter'),
        _record('HVAC-FILTER-01', 'Air Filter'),
        'POSSIBLE_DUPLICATE_REVIEW',
        'POSSIBLE_DUPLICATE_REVIEW',
    ),
    (
        'insufficient-data',
        _record('TR-LABELS', 'Labels'),
        _record('TR-WARNING-LABELS', 'Warning labels'),
        'INSUFFICIENT_DATA',
        'INSUFFICIENT_DATA',
    ),
)


@pytest.mark.parametrize(
    (
        '_case_name',
        'record_a',
        'record_b',
        'legacy_value',
        'target_value',
    ),
    ACTUAL_PATH_CASES,
)
def test_actual_reachable_deterministic_paths_translate_with_exact_parity(
    _case_name,
    record_a,
    record_b,
    legacy_value,
    target_value,
):
    source = score_candidate(
        record_a,
        record_b,
        ['CONTRACT', 'UNIT_MEAS'],
    )
    original = dict(source)
    original_order = tuple(source)
    result = _typed_result(source)

    translation = LegacyStatusTranslation.from_scoring_result(result)

    assert source['business_status'] == legacy_value
    assert translation.legacy_business_status.value == legacy_value
    assert translation.target_business_status.value == target_value
    assert translation.rule_decision == source['rule_decision']
    assert translation.rejection_reason == source['rejection_reason']
    assert source == original
    assert tuple(source) == original_order == EXPECTED_RESULT_KEYS
    assert result.to_legacy_dict() == original
    assert tuple(result.to_legacy_dict()) == original_order


def test_package_exports_new_and_existing_contracts():
    assert LegacyBusinessStatus.__name__ == 'LegacyBusinessStatus'
    assert LegacyStatusTranslation.__name__ == 'LegacyStatusTranslation'
    assert callable(translate_legacy_business_status)
    assert TargetBusinessStatus.__name__ == 'TargetBusinessStatus'
    assert RedesignedResultMode.__name__ == 'RedesignedResultMode'
    assert ResultPolicy.__name__ == 'ResultPolicy'
    assert CandidatePair.__name__ == 'CandidatePair'
    assert CandidateScoringResult.__name__ == 'CandidateScoringResult'
    assert CanonicalRecord.__name__ == 'CanonicalRecord'
    assert ScoringEvidence.__name__ == 'ScoringEvidence'


def test_status_compatibility_import_has_no_runtime_layer_dependencies():
    backend_root = Path(__file__).resolve().parents[1]
    script = (
        'import sys\n'
        'import app.contracts.status_compatibility\n'
        "forbidden = ('pandas', 'fastapi', 'sqlalchemy', "
        "'app.repositories', 'app.services', "
        "'app.engine.engine_selection')\n"
        'assert not any(name == prefix or name.startswith(prefix + \".\") '
        'for name in sys.modules for prefix in forbidden)\n'
    )

    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=backend_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
