from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.contracts.records import CanonicalRecord


def _snapshot_fields(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f'{name} must be a sequence of field names')
    if any(not isinstance(field, str) for field in value):
        raise TypeError(f'{name} entries must be strings')
    return tuple(value)


def _snapshot_warnings(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError('warnings must be a sequence of mappings')

    snapshots = []
    for warning in value:
        if not isinstance(warning, Mapping):
            raise TypeError('warning entries must be mappings')
        snapshots.append(MappingProxyType(dict(warning)))
    return tuple(snapshots)


@dataclass(frozen=True, init=False)
class CandidatePair:
    '''Immutable snapshot of the current generated candidate-pair boundary.'''

    record_a: CanonicalRecord
    record_b: CanonicalRecord
    matched_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    warnings: tuple[Mapping[str, Any], ...]

    def __init__(
        self,
        record_a: CanonicalRecord,
        record_b: CanonicalRecord,
        matched_fields: Sequence[str],
        mismatched_fields: Sequence[str],
        warnings: Sequence[Mapping[str, Any]],
    ):
        if not isinstance(record_a, CanonicalRecord):
            raise TypeError('record_a must be a CanonicalRecord')
        if not isinstance(record_b, CanonicalRecord):
            raise TypeError('record_b must be a CanonicalRecord')

        object.__setattr__(self, 'record_a', record_a)
        object.__setattr__(self, 'record_b', record_b)
        object.__setattr__(
            self,
            'matched_fields',
            _snapshot_fields(matched_fields, 'matched_fields'),
        )
        object.__setattr__(
            self,
            'mismatched_fields',
            _snapshot_fields(mismatched_fields, 'mismatched_fields'),
        )
        object.__setattr__(self, 'warnings', _snapshot_warnings(warnings))

    @classmethod
    def from_legacy_mapping(cls, candidate: Mapping[str, Any]) -> 'CandidatePair':
        if not isinstance(candidate, Mapping):
            raise TypeError('legacy candidate pair must be a mapping')

        required_keys = (
            'record_a',
            'record_b',
            'matched_fields',
            'mismatched_fields',
            'warnings',
        )
        for key in required_keys:
            if key not in candidate:
                raise ValueError(f'legacy candidate pair is missing required key: {key}')

        record_a = candidate['record_a']
        record_b = candidate['record_b']
        if not isinstance(record_a, Mapping):
            raise TypeError('record_a must be a mapping')
        if not isinstance(record_b, Mapping):
            raise TypeError('record_b must be a mapping')

        return cls(
            CanonicalRecord.from_legacy_mapping(record_a),
            CanonicalRecord.from_legacy_mapping(record_b),
            candidate['matched_fields'],
            candidate['mismatched_fields'],
            candidate['warnings'],
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            'record_a': self.record_a.to_legacy_dict(),
            'record_b': self.record_b.to_legacy_dict(),
            'matched_fields': list(self.matched_fields),
            'mismatched_fields': list(self.mismatched_fields),
            'warnings': [dict(warning) for warning in self.warnings],
        }
