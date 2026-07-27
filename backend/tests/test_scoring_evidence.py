from dataclasses import FrozenInstanceError

import pytest

from app.contracts.evidence import (
    SCORING_EVIDENCE_FIELDS,
    ScoringEvidence,
)
from app.contracts.results import CandidateScoringResult
from app.engine.scoring import score_candidate


SCORE_FIELDS = SCORING_EVIDENCE_FIELDS[:5]
SEQUENCE_FIELDS = (
    'matched_fields',
    'mismatched_fields',
    'application_context_a',
    'application_context_b',
)
BOOL_FIELDS = (
    'generic_description_warning',
    'application_context_warning',
)
STRING_FIELDS = SCORING_EVIDENCE_FIELDS[-4:]


def _record(part_no, description, unit='PCS'):
    return {
        'PART_NO': part_no,
        'DESCRIPTION': description,
        'CONTRACT': 'S1',
        'UNIT_MEAS': unit,
        'HSN_SAC_CODE': '1000',
    }


def _result(record_a, record_b):
    return score_candidate(
        record_a,
        record_b,
        ['CONTRACT', 'UNIT_MEAS'],
    )


def _allowed_result():
    return _result(
        _record('MCB30A-1', 'MCB30A'),
        _record('MCB30A-2', 'MCB 30 Amp'),
    )


ACTUAL_RESULT_CASES = [
    (
        'allow',
        _record('MCB30A-1', 'MCB30A'),
        _record('MCB30A-2', 'MCB 30 Amp'),
    ),
    (
        'critical-mismatch',
        _record('FILTER-1', 'Generator Oil Filter'),
        _record('FILTER-2', 'Generator Air Filter'),
    ),
    (
        'generic-description',
        _record('TR LABELS', 'Labels'),
        _record('TR WARNING LABELS', 'Warning labels'),
    ),
    (
        'application-context',
        _record('SP-GEN-AIR-FLT', 'Generator Air Filter'),
        _record('HVAC-FILTER-01', 'Air Filter'),
    ),
    (
        'structural-role',
        _record('SJ COMP PART1', 'SJ COMP PART1'),
        _record('SJ TOP PART1', 'SJ TOP PART1'),
    ),
]


@pytest.mark.parametrize(
    ('_name', 'record_a', 'record_b'),
    ACTUAL_RESULT_CASES,
    ids=[case[0] for case in ACTUAL_RESULT_CASES],
)
def test_actual_paths_construct_complete_exact_ordered_evidence(
    _name,
    record_a,
    record_b,
):
    source = _result(record_a, record_b)
    before = dict(source)

    typed_result = CandidateScoringResult.from_legacy_mapping(source)
    converted = typed_result.evidence.to_legacy_fields()

    assert typed_result.to_legacy_dict() == source
    assert list(typed_result.to_legacy_dict()) == list(source)
    assert list(converted) == list(SCORING_EVIDENCE_FIELDS)
    assert converted == {
        field: source[field] for field in SCORING_EVIDENCE_FIELDS
    }
    assert all(type(converted[field]) is float for field in SCORE_FIELDS)
    assert all(type(converted[field]) is bool for field in BOOL_FIELDS)
    assert all(type(converted[field]) is str for field in STRING_FIELDS)
    assert all(
        all(type(item) is str for item in converted[field])
        for field in SEQUENCE_FIELDS
    )
    assert all(
        type(mismatch) is dict
        for mismatch in converted['critical_mismatches']
    )
    assert source == before


def test_preserves_order_duplicates_and_extra_mapping_keys():
    source = _allowed_result()
    source['matched_fields'] = ['CONTRACT', 'CONTRACT']
    source['mismatched_fields'] = ['CLIENT_FIELD', 'CLIENT_FIELD']
    source['application_context_a'] = ['generator', 'generator']
    source['application_context_b'] = ['hvac', 'hvac']
    source['critical_mismatches'] = [{
        'group': 'CUSTOM',
        'label': 'custom',
        'values_a': ['one', 'one'],
        'values_b': ['two'],
        'extra': 'preserved',
    }]
    source['variant_attributes_a']['EXTRA'] = ['one', 'one']
    source['variant_attributes_b']['EXTRA'] = ['two']

    converted = ScoringEvidence.from_legacy_result(
        source
    ).to_legacy_fields()

    assert converted['matched_fields'] == ['CONTRACT', 'CONTRACT']
    assert converted['mismatched_fields'] == [
        'CLIENT_FIELD',
        'CLIENT_FIELD',
    ]
    assert converted['application_context_a'] == [
        'generator',
        'generator',
    ]
    assert converted['application_context_b'] == ['hvac', 'hvac']
    assert converted['critical_mismatches'] == source['critical_mismatches']
    assert converted['variant_attributes_a'] == source[
        'variant_attributes_a'
    ]
    assert converted['variant_attributes_b'] == source[
        'variant_attributes_b'
    ]


@pytest.mark.parametrize('invalid', [None, [], object(), 'not a mapping'])
def test_rejects_non_mapping_input(invalid):
    with pytest.raises(TypeError, match='scoring result must be a mapping'):
        ScoringEvidence.from_legacy_result(invalid)


@pytest.mark.parametrize('missing_field', SCORING_EVIDENCE_FIELDS)
def test_rejects_each_missing_required_evidence_field(missing_field):
    source = _allowed_result()
    del source[missing_field]

    with pytest.raises(
        ValueError,
        match=f'missing required evidence field: {missing_field}',
    ):
        ScoringEvidence.from_legacy_result(source)


@pytest.mark.parametrize(
    ('field', 'invalid', 'expected_type'),
    [
        *[(field, 1, 'float') for field in SCORE_FIELDS],
        *[(field, 1, 'bool') for field in BOOL_FIELDS],
        *[(field, None, 'str') for field in STRING_FIELDS],
    ],
)
def test_rejects_invalid_scalar_types(field, invalid, expected_type):
    source = _allowed_result()
    source[field] = invalid

    with pytest.raises(TypeError, match=f'{field} must be {expected_type}'):
        ScoringEvidence.from_legacy_result(source)


@pytest.mark.parametrize('field', SEQUENCE_FIELDS)
@pytest.mark.parametrize('invalid', ['plain string', b'plain bytes'])
def test_rejects_string_and_bytes_sequence_fields(field, invalid):
    source = _allowed_result()
    source[field] = invalid

    with pytest.raises(TypeError, match=f'{field} must be a sequence'):
        ScoringEvidence.from_legacy_result(source)


@pytest.mark.parametrize('field', SEQUENCE_FIELDS)
def test_rejects_non_string_sequence_entries(field):
    source = _allowed_result()
    source[field] = ['valid', 1]

    with pytest.raises(TypeError, match=f'{field} entries must be strings'):
        ScoringEvidence.from_legacy_result(source)


def test_rejects_non_mapping_critical_mismatch_entry():
    source = _allowed_result()
    source['critical_mismatches'] = [{'group': 'valid'}, 'invalid']

    with pytest.raises(
        TypeError,
        match='critical_mismatches entries must be mappings',
    ):
        ScoringEvidence.from_legacy_result(source)


def test_rejects_non_string_critical_mismatch_keys():
    source = _allowed_result()
    source['critical_mismatches'] = [{1: 'invalid'}]

    with pytest.raises(
        TypeError,
        match='critical_mismatches entry keys must be strings',
    ):
        ScoringEvidence.from_legacy_result(source)


@pytest.mark.parametrize('invalid', ['plain string', b'plain bytes'])
def test_rejects_string_and_bytes_critical_mismatches(invalid):
    source = _allowed_result()
    source['critical_mismatches'] = invalid

    with pytest.raises(
        TypeError,
        match='critical_mismatches must be a sequence',
    ):
        ScoringEvidence.from_legacy_result(source)


@pytest.mark.parametrize(
    'field',
    ['variant_attributes_a', 'variant_attributes_b'],
)
def test_rejects_non_mapping_variant_attributes(field):
    source = _allowed_result()
    source[field] = []

    with pytest.raises(TypeError, match=f'{field} must be a mapping'):
        ScoringEvidence.from_legacy_result(source)


@pytest.mark.parametrize(
    'field',
    ['variant_attributes_a', 'variant_attributes_b'],
)
def test_rejects_non_string_variant_attribute_keys(field):
    source = _allowed_result()
    source[field] = {1: ['invalid']}

    with pytest.raises(TypeError, match=f'{field} keys must be strings'):
        ScoringEvidence.from_legacy_result(source)


def test_snapshots_top_level_containers_and_exposes_them_read_only():
    source = _allowed_result()
    source['mismatched_fields'] = ['CLIENT_FIELD']
    source['application_context_a'] = ['generator']
    source['application_context_b'] = ['hvac']
    source_mismatch = {
        'group': 'CUSTOM',
        'values_a': ['one'],
        'values_b': ['two'],
    }
    source['critical_mismatches'] = [source_mismatch]
    source['variant_attributes_a'] = {'CUSTOM': ['one']}
    source['variant_attributes_b'] = {'CUSTOM': ['two']}
    evidence = ScoringEvidence.from_legacy_result(source)

    source['matched_fields'].append('NEW')
    source['mismatched_fields'].clear()
    source['application_context_a'].append('pump')
    source['application_context_b'].clear()
    source['critical_mismatches'].append({'group': 'NEW'})
    source_mismatch['group'] = 'REPLACED'
    source['critical_mismatches'][0] = {'group': 'REPLACED_AGAIN'}
    source['variant_attributes_a']['NEW'] = []
    source['variant_attributes_b'].clear()

    assert evidence.matched_fields == ('CONTRACT', 'UNIT_MEAS')
    assert evidence.mismatched_fields == ('CLIENT_FIELD',)
    assert evidence.application_context_a == ('generator',)
    assert evidence.application_context_b == ('hvac',)
    assert len(evidence.critical_mismatches) == 1
    assert evidence.critical_mismatches[0]['group'] == 'CUSTOM'
    assert list(evidence.variant_attributes_a) == ['CUSTOM']
    assert list(evidence.variant_attributes_b) == ['CUSTOM']
    with pytest.raises(TypeError):
        evidence.matched_fields[0] = 'BLOCKED'
    with pytest.raises(TypeError):
        evidence.variant_attributes_a['CUSTOM'] = []
    with pytest.raises(TypeError):
        evidence.critical_mismatches[0]['group'] = 'BLOCKED'
    with pytest.raises(FrozenInstanceError):
        evidence.final_score = 1.0


def test_known_mappings_preserve_shallow_nested_references():
    source = _allowed_result()
    mismatch_nested = ['one']
    variant_a_nested = ['two']
    variant_b_nested = {'three': 3}
    source['critical_mismatches'] = [{
        'group': 'CUSTOM',
        'nested': mismatch_nested,
    }]
    source['variant_attributes_a'] = {'CUSTOM': variant_a_nested}
    source['variant_attributes_b'] = {'CUSTOM': variant_b_nested}

    evidence = ScoringEvidence.from_legacy_result(source)

    assert evidence.critical_mismatches[0]['nested'] is mismatch_nested
    assert evidence.variant_attributes_a['CUSTOM'] is variant_a_nested
    assert evidence.variant_attributes_b['CUSTOM'] is variant_b_nested
    mismatch_nested.append('changed')
    variant_a_nested.append('changed')
    variant_b_nested['changed'] = 4
    assert evidence.critical_mismatches[0]['nested'] == ['one', 'changed']
    assert evidence.variant_attributes_a['CUSTOM'] == ['two', 'changed']
    assert evidence.variant_attributes_b['CUSTOM']['changed'] == 4


def test_legacy_conversion_returns_fresh_mutable_top_level_containers():
    source = _allowed_result()
    nested = ['shared']
    source['matched_fields'] = ['CONTRACT', 'CONTRACT']
    source['critical_mismatches'] = [{
        'group': 'CUSTOM',
        'nested': nested,
    }]
    source['variant_attributes_a'] = {'CUSTOM': nested}
    source['variant_attributes_b'] = {'CUSTOM': nested}
    evidence = ScoringEvidence.from_legacy_result(source)

    first = evidence.to_legacy_fields()
    second = evidence.to_legacy_fields()

    assert type(first) is dict
    assert first == second
    assert list(first) == list(SCORING_EVIDENCE_FIELDS)
    for field in SEQUENCE_FIELDS:
        assert type(first[field]) is list
        assert first[field] is not second[field]
    assert first['critical_mismatches'] is not second[
        'critical_mismatches'
    ]
    assert first['critical_mismatches'][0] is not second[
        'critical_mismatches'
    ][0]
    assert first['variant_attributes_a'] is not second[
        'variant_attributes_a'
    ]
    assert first['variant_attributes_b'] is not second[
        'variant_attributes_b'
    ]
    assert first['critical_mismatches'][0]['nested'] is nested
    assert first['variant_attributes_a']['CUSTOM'] is nested

    first['matched_fields'].append('CHANGED')
    first['critical_mismatches'][0]['group'] = 'CHANGED'
    first['variant_attributes_a']['NEW'] = []
    assert evidence.matched_fields == ('CONTRACT', 'CONTRACT')
    assert evidence.critical_mismatches[0]['group'] == 'CUSTOM'
    assert 'NEW' not in evidence.variant_attributes_a
    assert second == evidence.to_legacy_fields()
