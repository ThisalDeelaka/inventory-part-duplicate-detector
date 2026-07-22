from types import MappingProxyType

import pandas as pd
import pytest

from app.contracts.candidates import CandidatePair
from app.contracts.records import CanonicalRecord
from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.engine_selection import LegacyDeterministicScoringEngine
from app.engine.scoring import score_candidate


def _record(part_no, description, unit='PCS'):
    return {
        'PART_NO': part_no,
        'DESCRIPTION': description,
        'CONTRACT': 'S1',
        'UNIT_MEAS': unit,
        'CLIENT_SPECIFIC_FIELD': 'preserved extra value',
    }


def _legacy_pair():
    return {
        'record_a': _record('A', 'MCB30A'),
        'record_b': _record('B', 'MCB 30 Amp'),
        'matched_fields': ['CONTRACT', 'UNIT_MEAS', 'CONTRACT'],
        'mismatched_fields': ['CLIENT_FIELD', 'CLIENT_FIELD'],
        'warnings': [
            {
                'warning_type': 'FIRST_WARNING',
                'message': 'First',
                'client_detail': 'preserved',
            },
            {'warning_type': 'SECOND_WARNING', 'message': 'Second'},
        ],
    }


def test_constructs_exact_snapshot_without_mutating_source():
    source = _legacy_pair()
    before = {
        'record_a': dict(source['record_a']),
        'record_b': dict(source['record_b']),
        'matched_fields': list(source['matched_fields']),
        'mismatched_fields': list(source['mismatched_fields']),
        'warnings': [dict(warning) for warning in source['warnings']],
    }

    candidate = CandidatePair.from_legacy_mapping(MappingProxyType(source))

    assert isinstance(candidate.record_a, CanonicalRecord)
    assert isinstance(candidate.record_b, CanonicalRecord)
    assert (
        candidate.record_a.raw_attributes['CLIENT_SPECIFIC_FIELD']
        == 'preserved extra value'
    )
    assert (
        candidate.record_b.raw_attributes['CLIENT_SPECIFIC_FIELD']
        == 'preserved extra value'
    )
    assert candidate.matched_fields == ('CONTRACT', 'UNIT_MEAS', 'CONTRACT')
    assert candidate.mismatched_fields == ('CLIENT_FIELD', 'CLIENT_FIELD')
    assert [warning['warning_type'] for warning in candidate.warnings] == [
        'FIRST_WARNING',
        'SECOND_WARNING',
    ]
    assert candidate.warnings[0]['client_detail'] == 'preserved'
    assert source == before


@pytest.mark.parametrize('invalid', [None, [], object(), 'not a mapping'])
def test_rejects_non_mapping_candidate_input(invalid):
    with pytest.raises(TypeError, match='candidate pair must be a mapping'):
        CandidatePair.from_legacy_mapping(invalid)


@pytest.mark.parametrize(
    'missing_key',
    ['record_a', 'record_b', 'matched_fields', 'mismatched_fields', 'warnings'],
)
def test_rejects_missing_required_keys(missing_key):
    source = _legacy_pair()
    del source[missing_key]

    with pytest.raises(ValueError, match=f'missing required key: {missing_key}'):
        CandidatePair.from_legacy_mapping(source)


@pytest.mark.parametrize('record_key', ['record_a', 'record_b'])
def test_rejects_non_mapping_records(record_key):
    source = _legacy_pair()
    source[record_key] = ['not', 'a', 'mapping']

    with pytest.raises(TypeError, match=f'{record_key} must be a mapping'):
        CandidatePair.from_legacy_mapping(source)


@pytest.mark.parametrize(
    'metadata_key',
    ['matched_fields', 'mismatched_fields', 'warnings'],
)
@pytest.mark.parametrize('invalid', ['plain string', b'plain bytes'])
def test_rejects_string_and_bytes_metadata_collections(metadata_key, invalid):
    source = _legacy_pair()
    source[metadata_key] = invalid

    with pytest.raises(TypeError, match=f'{metadata_key} must be a sequence'):
        CandidatePair.from_legacy_mapping(source)


def test_rejects_non_mapping_warning_entries():
    source = _legacy_pair()
    source['warnings'] = [{'warning_type': 'VALID'}, 'invalid warning']

    with pytest.raises(TypeError, match='warning entries must be mappings'):
        CandidatePair.from_legacy_mapping(source)


def test_snapshots_source_collections_and_exposes_read_only_values():
    source = _legacy_pair()
    candidate = CandidatePair.from_legacy_mapping(source)

    source['record_a']['DESCRIPTION'] = 'Changed'
    source['record_b']['CLIENT_SPECIFIC_FIELD'] = 'Changed'
    source['matched_fields'].append('NEW_MATCH')
    source['mismatched_fields'].clear()
    source['warnings'][0]['message'] = 'Changed'
    source['warnings'].append({'warning_type': 'THIRD', 'message': 'Third'})

    assert candidate.record_a.raw_attributes['DESCRIPTION'] == 'MCB30A'
    assert (
        candidate.record_b.raw_attributes['CLIENT_SPECIFIC_FIELD']
        == 'preserved extra value'
    )
    assert candidate.matched_fields == ('CONTRACT', 'UNIT_MEAS', 'CONTRACT')
    assert candidate.mismatched_fields == ('CLIENT_FIELD', 'CLIENT_FIELD')
    assert candidate.warnings[0]['message'] == 'First'
    assert len(candidate.warnings) == 2
    with pytest.raises(TypeError):
        candidate.matched_fields[0] = 'Blocked'
    with pytest.raises(TypeError):
        candidate.mismatched_fields[0] = 'Blocked'
    with pytest.raises(TypeError):
        candidate.warnings[0] = MappingProxyType({})
    with pytest.raises(TypeError):
        candidate.warnings[0]['message'] = 'Blocked'


def test_legacy_conversion_is_complete_fresh_and_isolated():
    candidate = CandidatePair.from_legacy_mapping(_legacy_pair())

    first = candidate.to_legacy_dict()
    second = candidate.to_legacy_dict()

    assert type(first) is dict
    assert list(first) == [
        'record_a',
        'record_b',
        'matched_fields',
        'mismatched_fields',
        'warnings',
    ]
    assert type(first['record_a']) is dict
    assert type(first['record_b']) is dict
    assert type(first['matched_fields']) is list
    assert type(first['mismatched_fields']) is list
    assert type(first['warnings']) is list
    assert all(type(warning) is dict for warning in first['warnings'])
    assert first == second == _legacy_pair()
    assert first is not second
    assert first['record_a'] is not second['record_a']
    assert first['record_b'] is not second['record_b']
    assert first['matched_fields'] is not second['matched_fields']
    assert first['mismatched_fields'] is not second['mismatched_fields']
    assert first['warnings'] is not second['warnings']
    assert all(
        first_warning is not second_warning
        for first_warning, second_warning in zip(
            first['warnings'],
            second['warnings'],
            strict=True,
        )
    )

    first['record_a']['DESCRIPTION'] = 'Changed'
    first['matched_fields'].append('NEW_MATCH')
    first['mismatched_fields'].clear()
    first['warnings'][0]['client_detail'] = 'Changed'
    first['warnings'].append({'warning_type': 'NEW', 'message': 'Changed'})
    assert second == _legacy_pair()
    assert candidate.to_legacy_dict() == _legacy_pair()


@pytest.mark.parametrize(
    ('record_a', 'record_b'),
    [
        (_record('MCB30A-1', 'MCB30A'), _record('MCB30A-2', 'MCB 30 Amp')),
        (
            _record('PIPE-1', 'Stainless Steel Pipe', 'M'),
            _record('PIPE-2', 'SS Pipe', 'PCS'),
        ),
    ],
)
def test_legacy_adapter_matches_complete_direct_scoring_result(record_a, record_b):
    selected_fields = ['CONTRACT', 'UNIT_MEAS']
    source = {
        'record_a': record_a,
        'record_b': record_b,
        'matched_fields': ['metadata is not scoring evidence'],
        'mismatched_fields': ['also not scoring evidence'],
        'warnings': [{'warning_type': 'TEST', 'message': 'Preserved but unused'}],
    }
    candidate = CandidatePair.from_legacy_mapping(source)

    typed_result = LegacyDeterministicScoringEngine().score_candidate(
        candidate,
        selected_fields,
    )
    assert typed_result.to_legacy_dict() == score_candidate(
        record_a,
        record_b,
        selected_fields,
    )


def test_generated_pair_round_trip_preserves_current_shape_and_missing_values():
    frame = pd.DataFrame([
        {
            **_record('A', 'Pump'),
            'CLIENT_NULL': pd.NA,
        },
        {
            **_record('B', 'Pump assembly'),
            'CLIENT_NULL': pd.NA,
        },
    ])
    generated = generate_candidate_pairs(frame, ['CONTRACT', 'UNIT_MEAS'])[0]

    converted = CandidatePair.from_legacy_mapping(generated).to_legacy_dict()

    assert list(converted) == list(generated)
    assert converted['matched_fields'] == generated['matched_fields']
    assert converted['mismatched_fields'] == generated['mismatched_fields']
    assert converted['warnings'] == generated['warnings']
    assert list(converted['record_a']) == list(generated['record_a'])
    assert list(converted['record_b']) == list(generated['record_b'])
    for side in ('record_a', 'record_b'):
        for key, original_value in generated[side].items():
            converted_value = converted[side][key]
            if pd.isna(original_value):
                assert pd.isna(converted_value)
            else:
                assert converted_value == original_value
