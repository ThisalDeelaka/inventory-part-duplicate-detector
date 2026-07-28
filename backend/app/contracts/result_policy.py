from dataclasses import dataclass
from enum import StrEnum

from app.contracts.statuses import TargetBusinessStatus


class RedesignedResultMode(StrEnum):
    REVIEW = 'review'
    ALL = 'all'


_REVIEW_STATUSES = (
    TargetBusinessStatus.DUPLICATE_CANDIDATE,
    TargetBusinessStatus.POSSIBLE_DUPLICATE_REVIEW,
    TargetBusinessStatus.DATA_CONFLICT_REVIEW,
    TargetBusinessStatus.CROSS_SITE_STANDARDIZATION_CANDIDATE,
    TargetBusinessStatus.INSUFFICIENT_DATA,
)

_ALL_STATUSES = tuple(TargetBusinessStatus)


@dataclass(frozen=True, init=False)
class ResultPolicy:
    '''Immutable target-status inclusion policy for redesigned result modes.

    This contract is not wired into the legacy deterministic path. ``review``
    is the approved architectural default, while runtime configuration belongs
    to a later implementation unit.
    '''

    mode: RedesignedResultMode
    included_statuses: tuple[TargetBusinessStatus, ...]

    def __init__(self):
        raise TypeError('use ResultPolicy.for_mode()')

    @classmethod
    def for_mode(cls, mode: RedesignedResultMode) -> 'ResultPolicy':
        if type(mode) is not RedesignedResultMode:
            raise TypeError('mode must be a RedesignedResultMode')

        included_statuses = (
            _REVIEW_STATUSES
            if mode is RedesignedResultMode.REVIEW
            else _ALL_STATUSES
        )
        policy = cls.__new__(cls)
        object.__setattr__(policy, 'mode', mode)
        object.__setattr__(
            policy,
            'included_statuses',
            included_statuses,
        )
        return policy

    def includes(self, status: TargetBusinessStatus) -> bool:
        if type(status) is not TargetBusinessStatus:
            raise TypeError('status must be a TargetBusinessStatus')
        return status in self.included_statuses
