from dataclasses import MISSING, FrozenInstanceError, fields, is_dataclass
from pathlib import Path
import subprocess
import sys
from typing import get_type_hints

import pytest

from app.contracts import (
    CandidatePair,
    CandidateScoringResult,
    CanonicalRecord,
    EngineVersionMetadata,
    LegacyBusinessStatus,
    LegacyStatusTranslation,
    RedesignedResultMode,
    ResultPolicy,
    ScoringEvidence,
    TargetBusinessStatus,
    translate_legacy_business_status,
)
from app.core.constants import MODEL_VERSION
from app.engine.engine_selection import (
    CandidateScoringEngine,
    LegacyDeterministicScoringEngine,
    RedesignedEngineUnavailableError,
    select_candidate_scoring_engine,
)
from app.engine.scoring import score_candidate


EXPECTED_LEGACY_RESULT_KEYS = [
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
]


def _record(part_no: str, description: str) -> dict[str, str]:
    return {
        'PART_NO': part_no,
        'DESCRIPTION': description,
        'CONTRACT': 'S1',
        'UNIT_MEAS': 'PCS',
        'HSN_SAC_CODE': '1000',
    }


def _candidate(record_a: dict[str, str], record_b: dict[str, str]) -> CandidatePair:
    return CandidatePair.from_legacy_mapping({
        'record_a': record_a,
        'record_b': record_b,
        'matched_fields': ['CONTRACT', 'UNIT_MEAS'],
        'mismatched_fields': [],
        'warnings': [],
    })


def test_contract_has_exact_frozen_slotted_shape_without_defaults():
    contract_fields = fields(EngineVersionMetadata)

    assert is_dataclass(EngineVersionMetadata)
    assert EngineVersionMetadata.__dataclass_params__.frozen is True
    assert EngineVersionMetadata.__slots__ == ('engine_id', 'engine_version')
    assert [field.name for field in contract_fields] == [
        'engine_id',
        'engine_version',
    ]
    assert get_type_hints(EngineVersionMetadata) == {
        'engine_id': str,
        'engine_version': str,
    }
    assert all(field.default is MISSING for field in contract_fields)
    assert all(field.default_factory is MISSING for field in contract_fields)
    assert not hasattr(EngineVersionMetadata('engine-a', 'version-a'), '__dict__')


@pytest.mark.parametrize(
    'field_name',
    ['engine_id', 'engine_version'],
)
@pytest.mark.parametrize(
    'invalid_value',
    [None, 1, True, b'value', object()],
    ids=['none', 'integer', 'boolean', 'bytes', 'object'],
)
def test_contract_rejects_non_string_values(field_name, invalid_value):
    values = {'engine_id': 'engine-a', 'engine_version': 'version-a'}
    values[field_name] = invalid_value

    with pytest.raises(TypeError, match=rf'^{field_name} must be str$'):
        EngineVersionMetadata(**values)


@pytest.mark.parametrize(
    ('invalid_value', 'message'),
    [
        ('', 'must not be empty'),
        ('   ', 'must not be whitespace-only'),
        (' engine-a', 'must not have leading or trailing whitespace'),
        ('engine-a ', 'must not have leading or trailing whitespace'),
    ],
)
@pytest.mark.parametrize('field_name', ['engine_id', 'engine_version'])
def test_contract_rejects_invalid_strings(field_name, invalid_value, message):
    values = {'engine_id': 'engine-a', 'engine_version': 'version-a'}
    values[field_name] = invalid_value

    with pytest.raises(ValueError, match=rf'^{field_name} {message}$'):
        EngineVersionMetadata(**values)


def test_contract_is_immutable_and_has_value_equality():
    metadata = EngineVersionMetadata('engine-a', 'version-a')

    assert metadata == EngineVersionMetadata('engine-a', 'version-a')
    assert metadata is not EngineVersionMetadata('engine-a', 'version-a')
    with pytest.raises(FrozenInstanceError):
        metadata.engine_version = 'version-b'


def test_package_exports_metadata_without_regressing_existing_exports():
    assert EngineVersionMetadata('engine-a', 'version-a').engine_id == 'engine-a'
    assert CandidatePair
    assert CandidateScoringResult
    assert CanonicalRecord
    assert LegacyBusinessStatus
    assert LegacyStatusTranslation
    assert RedesignedResultMode
    assert ResultPolicy
    assert ScoringEvidence
    assert TargetBusinessStatus
    assert translate_legacy_business_status


def test_contract_import_has_no_runtime_framework_dependencies():
    script = '''
import sys
from app.contracts.version_metadata import EngineVersionMetadata

metadata = EngineVersionMetadata("engine-a", "version-a")
forbidden = (
    "app.core.config",
    "app.engine.engine_selection",
    "app.repositories",
    "app.services",
    "fastapi",
    "pandas",
    "sqlalchemy",
)
loaded = sorted(
    name for name in sys.modules
    if any(name == item or name.startswith(item + ".") for item in forbidden)
)
if loaded:
    raise AssertionError(loaded)
'''
    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_legacy_engine_owns_one_exact_immutable_metadata_instance():
    engine = LegacyDeterministicScoringEngine()
    descriptor = LegacyDeterministicScoringEngine.__dict__['version_metadata']

    assert isinstance(descriptor, property)
    assert descriptor.fset is None
    assert engine.version_metadata is engine.version_metadata
    assert engine.version_metadata == EngineVersionMetadata(
        engine_id='legacy-deterministic',
        engine_version=MODEL_VERSION,
    )
    with pytest.raises(FrozenInstanceError):
        engine.version_metadata.engine_id = 'other-engine'


def test_protocol_declares_typed_read_only_metadata_property():
    descriptor = CandidateScoringEngine.__dict__['version_metadata']

    assert isinstance(descriptor, property)
    assert descriptor.fset is None
    assert get_type_hints(descriptor.fget)['return'] is EngineVersionMetadata
    assert CandidateScoringEngine._is_runtime_protocol is False


def test_selector_preserves_false_default_and_true_fail_closed_behavior(
    monkeypatch,
):
    false_engine = select_candidate_scoring_engine(False)
    monkeypatch.setattr(
        'app.engine.engine_selection.settings.use_redesigned_engine',
        False,
    )
    default_engine = select_candidate_scoring_engine()

    assert isinstance(false_engine, LegacyDeterministicScoringEngine)
    assert isinstance(default_engine, LegacyDeterministicScoringEngine)
    assert false_engine.version_metadata is default_engine.version_metadata
    with pytest.raises(RedesignedEngineUnavailableError) as error:
        select_candidate_scoring_engine(True)
    assert str(error.value) == (
        'USE_REDESIGNED_ENGINE=true requested the Production Identity Engine, '
        'but that engine is not implemented'
    )


def test_metadata_access_does_not_change_legacy_scoring_result():
    record_a = _record('MCB30A-1', 'MCB30A')
    record_b = _record('MCB30A-2', 'MCB 30 Amp')
    selected_fields = ['CONTRACT', 'UNIT_MEAS']
    direct_result = score_candidate(record_a, record_b, selected_fields)
    engine = LegacyDeterministicScoringEngine()

    metadata_before = engine.version_metadata
    adapted_result = engine.score_candidate(
        _candidate(record_a, record_b),
        selected_fields,
    ).to_legacy_dict()
    metadata_after = engine.version_metadata

    assert adapted_result == direct_result
    assert list(adapted_result) == EXPECTED_LEGACY_RESULT_KEYS
    assert len(adapted_result) == 26
    assert 'engine_id' not in adapted_result
    assert 'engine_version' not in adapted_result
    assert 'version_metadata' not in adapted_result
    assert metadata_before is metadata_after


def test_metadata_has_no_current_runtime_integration_leakage():
    app_root = Path(__file__).resolve().parents[1] / 'app'
    relative_sources = {
        path.relative_to(app_root).as_posix()
        for path in app_root.rglob('*.py')
        if 'EngineVersionMetadata' in path.read_text(encoding='utf-8')
    }

    assert relative_sources == {
        'contracts/__init__.py',
        'contracts/version_metadata.py',
        'engine/engine_selection.py',
    }
