from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from app.contracts.results import CandidateScoringResult
from app.contracts.statuses import TargetBusinessStatus


class LegacyBusinessStatus(StrEnum):
    '''Exact business-status vocabulary of the deterministic engine.'''

    LIKELY_DUPLICATE = 'LIKELY_DUPLICATE'
    POSSIBLE_DUPLICATE_REVIEW = 'POSSIBLE_DUPLICATE_REVIEW'
    RELATED_BUT_NOT_DUPLICATE = 'RELATED_BUT_NOT_DUPLICATE'
    REJECTED_BY_BUSINESS_RULE = 'REJECTED_BY_BUSINESS_RULE'
    DATA_CONFLICT_REVIEW = 'DATA_CONFLICT_REVIEW'
    CROSS_SITE_STANDARDIZATION_CANDIDATE = (
        'CROSS_SITE_STANDARDIZATION_CANDIDATE'
    )
    INSUFFICIENT_DATA = 'INSUFFICIENT_DATA'


_LEGACY_TO_TARGET_STATUS = MappingProxyType({
    LegacyBusinessStatus.LIKELY_DUPLICATE:
        TargetBusinessStatus.DUPLICATE_CANDIDATE,
    LegacyBusinessStatus.POSSIBLE_DUPLICATE_REVIEW:
        TargetBusinessStatus.POSSIBLE_DUPLICATE_REVIEW,
    LegacyBusinessStatus.RELATED_BUT_NOT_DUPLICATE:
        TargetBusinessStatus.RELATED_BUT_NOT_DUPLICATE,
    LegacyBusinessStatus.REJECTED_BY_BUSINESS_RULE:
        TargetBusinessStatus.DATA_CONFLICT_REVIEW,
    LegacyBusinessStatus.DATA_CONFLICT_REVIEW:
        TargetBusinessStatus.DATA_CONFLICT_REVIEW,
    LegacyBusinessStatus.CROSS_SITE_STANDARDIZATION_CANDIDATE:
        TargetBusinessStatus.CROSS_SITE_STANDARDIZATION_CANDIDATE,
    LegacyBusinessStatus.INSUFFICIENT_DATA:
        TargetBusinessStatus.INSUFFICIENT_DATA,
})

def _validate_legacy_to_target_mapping(
    mapping: Mapping[LegacyBusinessStatus, TargetBusinessStatus],
) -> None:
    if any(type(key) is not LegacyBusinessStatus for key in mapping):
        raise RuntimeError(
            'legacy-to-target status mapping keys must be '
            'LegacyBusinessStatus'
        )
    if any(
        type(value) is not TargetBusinessStatus
        for value in mapping.values()
    ):
        raise RuntimeError(
            'legacy-to-target status mapping values must be '
            'TargetBusinessStatus'
        )
    if tuple(mapping) != tuple(LegacyBusinessStatus):
        raise RuntimeError(
            'legacy-to-target status mapping keys must exactly match '
            'LegacyBusinessStatus in declaration order'
        )
    if TargetBusinessStatus.UNIQUE_NO_MATCH in mapping.values():
        raise RuntimeError(
            'UNIQUE_NO_MATCH cannot have a legacy source mapping'
        )


_validate_legacy_to_target_mapping(_LEGACY_TO_TARGET_STATUS)


def translate_legacy_business_status(
    status: LegacyBusinessStatus,
) -> TargetBusinessStatus:
    '''Translate one exact typed legacy status without coercion or fallback.'''

    if type(status) is not LegacyBusinessStatus:
        raise TypeError('status must be a LegacyBusinessStatus')
    return _LEGACY_TO_TARGET_STATUS[status]


@dataclass(frozen=True, init=False)
class LegacyStatusTranslation:
    '''Immutable compatibility view over a validated scoring result.

    Missing or malformed scoring-result fields are rejected by
    ``CandidateScoringResult`` before this factory is called.
    '''

    legacy_business_status: LegacyBusinessStatus
    target_business_status: TargetBusinessStatus
    rule_decision: str
    rejection_reason: str

    def __init__(self):
        raise TypeError('use LegacyStatusTranslation.from_scoring_result()')

    @classmethod
    def from_scoring_result(
        cls,
        result: CandidateScoringResult,
    ) -> 'LegacyStatusTranslation':
        if not isinstance(result, CandidateScoringResult):
            raise TypeError('result must be a CandidateScoringResult')

        try:
            legacy_status = LegacyBusinessStatus(result.business_status)
        except ValueError as exc:
            raise ValueError(
                'unsupported legacy business_status: '
                f'{result.business_status!r}'
            ) from exc

        translation = cls.__new__(cls)
        object.__setattr__(
            translation,
            'legacy_business_status',
            legacy_status,
        )
        object.__setattr__(
            translation,
            'target_business_status',
            translate_legacy_business_status(legacy_status),
        )
        object.__setattr__(
            translation,
            'rule_decision',
            result.rule_decision,
        )
        object.__setattr__(
            translation,
            'rejection_reason',
            result.rejection_reason,
        )
        return translation
