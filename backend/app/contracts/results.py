from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


_TYPED_FIELD_TYPES = {
    'final_score': float,
    'confidence_level': str,
    'business_status': str,
    'rule_decision': str,
    'rejection_reason': str,
    'scan_mode': str,
    'explanation': str,
    'recommended_action': str,
}


@dataclass(frozen=True, init=False)
class CandidateScoringResult:
    '''Immutable wrapper around the complete current deterministic result.

    This preserves the legacy boundary and is not the final production evidence
    or decision model.
    '''

    final_score: float
    confidence_level: str
    business_status: str
    rule_decision: str
    rejection_reason: str
    scan_mode: str
    explanation: str
    recommended_action: str
    raw_result: Mapping[str, Any]

    def __init__(self, result: Mapping[str, Any]):
        if not isinstance(result, Mapping):
            raise TypeError('legacy scoring result must be a mapping')

        snapshot = dict(result)
        for field, expected_type in _TYPED_FIELD_TYPES.items():
            if field not in snapshot:
                raise ValueError(
                    f'legacy scoring result is missing required field: {field}'
                )
            if type(snapshot[field]) is not expected_type:
                raise TypeError(
                    f'{field} must be {expected_type.__name__}'
                )

        for field in _TYPED_FIELD_TYPES:
            object.__setattr__(self, field, snapshot[field])
        object.__setattr__(self, 'raw_result', MappingProxyType(snapshot))

    @classmethod
    def from_legacy_mapping(
        cls,
        result: Mapping[str, Any],
    ) -> 'CandidateScoringResult':
        return cls(result)

    def to_legacy_dict(self) -> dict[str, Any]:
        return dict(self.raw_result)
