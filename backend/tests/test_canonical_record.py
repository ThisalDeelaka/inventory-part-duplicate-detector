from types import MappingProxyType

import pandas as pd
import pytest

from app.contracts.records import CanonicalRecord
from app.core.constants import FIELD_DEFINITIONS


def test_selects_only_present_recognized_canonical_fields():
    canonical_names = {definition['field'] for definition in FIELD_DEFINITIONS}
    source = {
        'PART_NO': 'A-100',
        'DESCRIPTION': 'Pump',
        'CLIENT_ATTRIBUTE': 'custom',
        'part_no': 'lowercase key remains distinct',
    }

    record = CanonicalRecord.from_legacy_mapping(source)

    assert set(record.canonical_fields) == {'PART_NO', 'DESCRIPTION'}
    assert set(record.canonical_fields).issubset(canonical_names)
    assert 'CLIENT_ATTRIBUTE' not in record.canonical_fields
    assert record.raw_attributes['CLIENT_ATTRIBUTE'] == 'custom'
    assert record.raw_attributes['part_no'] == 'lowercase key remains distinct'
    assert 'CONTRACT' not in record.canonical_fields


def test_preserves_raw_values_without_coercion_or_missing_value_conversion():
    source = {
        'PART_NO': '00123',
        'DESCRIPTION': '',
        'CONTRACT': None,
        'UNIT_MEAS': pd.NA,
        'CLIENT_ATTRIBUTE': '00045',
    }

    record = CanonicalRecord.from_legacy_mapping(source)

    assert record.raw_attributes['PART_NO'] == '00123'
    assert record.raw_attributes['DESCRIPTION'] == ''
    assert record.raw_attributes['CONTRACT'] is None
    assert record.raw_attributes['UNIT_MEAS'] is pd.NA
    assert pd.isna(record.raw_attributes['UNIT_MEAS'])
    assert record.raw_attributes['CLIENT_ATTRIBUTE'] == '00045'


def test_snapshots_source_and_exposes_read_only_mappings():
    source = {
        'PART_NO': 'A',
        'DESCRIPTION': 'Original',
        'CLIENT_ATTRIBUTE': 'before',
    }
    record = CanonicalRecord.from_legacy_mapping(source)

    source['DESCRIPTION'] = 'Changed'
    source['CLIENT_ATTRIBUTE'] = 'after'

    assert record.canonical_fields['DESCRIPTION'] == 'Original'
    assert record.raw_attributes['CLIENT_ATTRIBUTE'] == 'before'
    with pytest.raises(TypeError):
        record.canonical_fields['DESCRIPTION'] = 'Blocked'
    with pytest.raises(TypeError):
        record.raw_attributes['CLIENT_ATTRIBUTE'] = 'Blocked'

    converted = record.to_legacy_dict()
    converted['DESCRIPTION'] = 'Changed conversion'
    assert record.raw_attributes['DESCRIPTION'] == 'Original'


def test_accepts_non_dict_mapping_without_mutating_it():
    source = MappingProxyType({
        'PART_NO': 'A',
        'DESCRIPTION': 'Pump',
        'CLIENT_ATTRIBUTE': 'custom',
    })
    before = dict(source)

    record = CanonicalRecord.from_legacy_mapping(source)

    assert dict(source) == before
    assert record.to_legacy_dict() == before


@pytest.mark.parametrize('invalid', [None, [], object(), 'not a mapping'])
def test_rejects_non_mapping_input(invalid):
    with pytest.raises(TypeError, match='legacy record must be a mapping'):
        CanonicalRecord.from_legacy_mapping(invalid)


def test_direct_construction_uses_the_same_validated_snapshot_path():
    source = {'PART_NO': 'A', 'CLIENT_ATTRIBUTE': 'custom'}

    record = CanonicalRecord(source)

    assert record.to_legacy_dict() == source
    with pytest.raises(TypeError):
        CanonicalRecord()


def test_legacy_conversion_is_complete_fresh_and_deterministic():
    source = {
        'PART_NO': 'A',
        'DESCRIPTION': 'Pump',
        'CLIENT_ATTRIBUTE': 'custom',
        'EMPTY_EXTRA': '',
    }
    record = CanonicalRecord.from_legacy_mapping(source)

    first = record.to_legacy_dict()
    second = record.to_legacy_dict()

    assert type(first) is dict
    assert first == source
    assert second == source
    assert first is not second
    first['CLIENT_ATTRIBUTE'] = 'mutated'
    assert second['CLIENT_ATTRIBUTE'] == 'custom'
    assert record.raw_attributes['CLIENT_ATTRIBUTE'] == 'custom'
    assert record == CanonicalRecord.from_legacy_mapping(source)
