from enum import StrEnum


class TargetBusinessStatus(StrEnum):
    '''Target production vocabulary, distinct from legacy deterministic statuses.

    These values define the intended business-status contract. The current
    deterministic engine does not yet produce this complete vocabulary.
    '''

    DUPLICATE_CANDIDATE = 'DUPLICATE_CANDIDATE'
    POSSIBLE_DUPLICATE_REVIEW = 'POSSIBLE_DUPLICATE_REVIEW'
    RELATED_BUT_NOT_DUPLICATE = 'RELATED_BUT_NOT_DUPLICATE'
    DATA_CONFLICT_REVIEW = 'DATA_CONFLICT_REVIEW'
    CROSS_SITE_STANDARDIZATION_CANDIDATE = (
        'CROSS_SITE_STANDARDIZATION_CANDIDATE'
    )
    INSUFFICIENT_DATA = 'INSUFFICIENT_DATA'
    UNIQUE_NO_MATCH = 'UNIQUE_NO_MATCH'
