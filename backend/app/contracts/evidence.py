from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


SCORING_EVIDENCE_FIELDS = (
    'description_similarity',
    'tfidf_score',
    'fuzzy_score',
    'part_no_similarity',
    'technical_token_score',
    'matched_fields',
    'mismatched_fields',
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

_SCORE_FIELDS = SCORING_EVIDENCE_FIELDS[:5]
_NORMALIZED_FIELDS = SCORING_EVIDENCE_FIELDS[-4:]


def _require_exact_type(
    result: Mapping[str, Any],
    field: str,
    expected_type: type,
) -> Any:
    value = result[field]
    if type(value) is not expected_type:
        raise TypeError(f'{field} must be {expected_type.__name__}')
    return value


def _snapshot_strings(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f'{field} must be a sequence of strings')
    if any(type(item) is not str for item in value):
        raise TypeError(f'{field} entries must be strings')
    return tuple(value)


def _snapshot_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f'{field} must be a mapping')
    if any(type(key) is not str for key in value):
        raise TypeError(f'{field} keys must be strings')
    return MappingProxyType(dict(value))


def _snapshot_mismatches(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError('critical_mismatches must be a sequence of mappings')

    snapshots = []
    for mismatch in value:
        if not isinstance(mismatch, Mapping):
            raise TypeError('critical_mismatches entries must be mappings')
        if any(type(key) is not str for key in mismatch):
            raise TypeError('critical_mismatches entry keys must be strings')
        snapshots.append(MappingProxyType(dict(mismatch)))
    return tuple(snapshots)


@dataclass(frozen=True, init=False)
class ScoringEvidence:
    '''Immutable top-level snapshot of current deterministic scoring evidence.

    This contract describes the current compatibility boundary, not the final
    production feature or evidence model. Known mappings are copied and exposed
    read-only, but arbitrary values nested inside them remain shallow references.
    '''

    description_similarity: float
    tfidf_score: float
    fuzzy_score: float
    part_no_similarity: float
    technical_token_score: float
    matched_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    critical_mismatches: tuple[Mapping[str, Any], ...]
    variant_attributes_a: Mapping[str, Any]
    variant_attributes_b: Mapping[str, Any]
    generic_description_warning: bool
    application_context_a: tuple[str, ...]
    application_context_b: tuple[str, ...]
    application_context_warning: bool
    normalized_description_a: str
    normalized_description_b: str
    normalized_part_no_a: str
    normalized_part_no_b: str

    def __init__(self, result: Mapping[str, Any]):
        if not isinstance(result, Mapping):
            raise TypeError('legacy scoring result must be a mapping')

        for field in SCORING_EVIDENCE_FIELDS:
            if field not in result:
                raise ValueError(
                    f'legacy scoring result is missing required evidence field: '
                    f'{field}'
                )

        for field in _SCORE_FIELDS:
            object.__setattr__(
                self,
                field,
                _require_exact_type(result, field, float),
            )
        for field in ('matched_fields', 'mismatched_fields'):
            object.__setattr__(
                self,
                field,
                _snapshot_strings(result[field], field),
            )
        object.__setattr__(
            self,
            'critical_mismatches',
            _snapshot_mismatches(result['critical_mismatches']),
        )
        for field in ('variant_attributes_a', 'variant_attributes_b'):
            object.__setattr__(
                self,
                field,
                _snapshot_mapping(result[field], field),
            )
        object.__setattr__(
            self,
            'generic_description_warning',
            _require_exact_type(
                result,
                'generic_description_warning',
                bool,
            ),
        )
        for field in ('application_context_a', 'application_context_b'):
            object.__setattr__(
                self,
                field,
                _snapshot_strings(result[field], field),
            )
        object.__setattr__(
            self,
            'application_context_warning',
            _require_exact_type(
                result,
                'application_context_warning',
                bool,
            ),
        )
        for field in _NORMALIZED_FIELDS:
            object.__setattr__(
                self,
                field,
                _require_exact_type(result, field, str),
            )

    @classmethod
    def from_legacy_result(
        cls,
        result: Mapping[str, Any],
    ) -> 'ScoringEvidence':
        return cls(result)

    def to_legacy_fields(self) -> dict[str, Any]:
        return {
            'description_similarity': self.description_similarity,
            'tfidf_score': self.tfidf_score,
            'fuzzy_score': self.fuzzy_score,
            'part_no_similarity': self.part_no_similarity,
            'technical_token_score': self.technical_token_score,
            'matched_fields': list(self.matched_fields),
            'mismatched_fields': list(self.mismatched_fields),
            'critical_mismatches': [
                dict(mismatch) for mismatch in self.critical_mismatches
            ],
            'variant_attributes_a': dict(self.variant_attributes_a),
            'variant_attributes_b': dict(self.variant_attributes_b),
            'generic_description_warning': self.generic_description_warning,
            'application_context_a': list(self.application_context_a),
            'application_context_b': list(self.application_context_b),
            'application_context_warning': self.application_context_warning,
            'normalized_description_a': self.normalized_description_a,
            'normalized_description_b': self.normalized_description_b,
            'normalized_part_no_a': self.normalized_part_no_a,
            'normalized_part_no_b': self.normalized_part_no_b,
        }
