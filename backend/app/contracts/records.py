from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.core.constants import FIELD_DEFINITIONS


_CANONICAL_FIELD_NAMES = frozenset(
    definition['field'] for definition in FIELD_DEFINITIONS
)


@dataclass(frozen=True, init=False)
class CanonicalRecord:
    '''Immutable snapshot of the legacy row after existing upload column mapping.

    Raw attributes are the complete mapping available at the scoring seam; they
    are not original CSV header spellings or pre-normalization source bytes.
    '''

    canonical_fields: Mapping[str, Any]
    raw_attributes: Mapping[str, Any]

    def __init__(self, record: Mapping[str, Any]):
        if not isinstance(record, Mapping):
            raise TypeError('legacy record must be a mapping')

        raw_snapshot = dict(record)
        canonical_snapshot = {
            key: value
            for key, value in raw_snapshot.items()
            if key in _CANONICAL_FIELD_NAMES
        }
        object.__setattr__(
            self,
            'canonical_fields',
            MappingProxyType(canonical_snapshot),
        )
        object.__setattr__(
            self,
            'raw_attributes',
            MappingProxyType(raw_snapshot),
        )

    @classmethod
    def from_legacy_mapping(cls, record: Mapping[str, Any]) -> 'CanonicalRecord':
        return cls(record)

    def to_legacy_dict(self) -> dict[str, Any]:
        return dict(self.raw_attributes)
