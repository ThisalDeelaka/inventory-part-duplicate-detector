from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path
import subprocess
import sys

import pytest

from app.contracts import (
    CandidatePair,
    CandidateScoringResult,
    CanonicalRecord,
    RedesignedResultMode,
    ResultPolicy,
    ScoringEvidence,
    TargetBusinessStatus,
)


TARGET_STATUS_VALUES = (
    'DUPLICATE_CANDIDATE',
    'POSSIBLE_DUPLICATE_REVIEW',
    'RELATED_BUT_NOT_DUPLICATE',
    'DATA_CONFLICT_REVIEW',
    'CROSS_SITE_STANDARDIZATION_CANDIDATE',
    'INSUFFICIENT_DATA',
    'UNIQUE_NO_MATCH',
)

REVIEW_STATUS_VALUES = (
    'DUPLICATE_CANDIDATE',
    'POSSIBLE_DUPLICATE_REVIEW',
    'DATA_CONFLICT_REVIEW',
    'CROSS_SITE_STANDARDIZATION_CANDIDATE',
    'INSUFFICIENT_DATA',
)


def test_target_status_vocabulary_is_exact_ordered_and_has_no_aliases():
    members = list(TargetBusinessStatus)

    assert len(members) == 7
    assert tuple(member.name for member in members) == TARGET_STATUS_VALUES
    assert tuple(member.value for member in members) == TARGET_STATUS_VALUES
    assert tuple(TargetBusinessStatus.__members__) == TARGET_STATUS_VALUES
    assert len(TargetBusinessStatus.__members__) == len(members)
    assert tuple(str(member) for member in members) == TARGET_STATUS_VALUES


def test_target_status_constructs_only_from_exact_target_values():
    for value in TARGET_STATUS_VALUES:
        assert TargetBusinessStatus(value).value == value

    invalid_values = (
        '',
        'duplicate_candidate',
        ' DUPLICATE_CANDIDATE',
        'DUPLICATE_CANDIDATE ',
        'LIKELY_DUPLICATE',
        'REJECTED_BY_BUSINESS_RULE',
    )
    for value in invalid_values:
        with pytest.raises(ValueError):
            TargetBusinessStatus(value)


def test_result_mode_vocabulary_is_exact_and_ordered():
    modes = list(RedesignedResultMode)

    assert tuple(mode.name for mode in modes) == ('REVIEW', 'ALL')
    assert tuple(mode.value for mode in modes) == ('review', 'all')
    assert tuple(str(mode) for mode in modes) == ('review', 'all')
    assert len(RedesignedResultMode.__members__) == 2


@pytest.mark.parametrize(
    'value',
    ['', 'REVIEW', ' review', 'review ', 'All', 'unsupported'],
)
def test_result_mode_rejects_non_exact_values(value):
    with pytest.raises(ValueError):
        RedesignedResultMode(value)


def test_review_policy_has_exact_approved_inclusions_and_exclusions():
    policy = ResultPolicy.for_mode(RedesignedResultMode.REVIEW)

    assert policy.mode is RedesignedResultMode.REVIEW
    assert tuple(status.value for status in policy.included_statuses) == (
        REVIEW_STATUS_VALUES
    )
    assert len(set(policy.included_statuses)) == 5
    assert all(
        type(status) is TargetBusinessStatus
        for status in policy.included_statuses
    )
    for status in TargetBusinessStatus:
        assert policy.includes(status) is (status.value in REVIEW_STATUS_VALUES)


def test_all_policy_has_every_target_status_in_ssot_order():
    policy = ResultPolicy.for_mode(RedesignedResultMode.ALL)

    assert policy.mode is RedesignedResultMode.ALL
    assert tuple(policy.included_statuses) == tuple(TargetBusinessStatus)
    assert len(set(policy.included_statuses)) == 7
    assert all(policy.includes(status) for status in TargetBusinessStatus)
    assert policy != ResultPolicy.for_mode(RedesignedResultMode.REVIEW)


def test_policy_factory_rejects_strings_and_unrelated_enums():
    class UnrelatedMode(Enum):
        REVIEW = 'review'

    for invalid in ('review', 'all', UnrelatedMode.REVIEW, None):
        with pytest.raises(TypeError, match='RedesignedResultMode'):
            ResultPolicy.for_mode(invalid)


def test_includes_rejects_strings_legacy_values_and_unrelated_enums():
    class UnrelatedStatus(Enum):
        DUPLICATE_CANDIDATE = 'DUPLICATE_CANDIDATE'

    policy = ResultPolicy.for_mode(RedesignedResultMode.REVIEW)
    invalid = (
        'DUPLICATE_CANDIDATE',
        'LIKELY_DUPLICATE',
        UnrelatedStatus.DUPLICATE_CANDIDATE,
        None,
    )
    for status in invalid:
        with pytest.raises(TypeError, match='TargetBusinessStatus'):
            policy.includes(status)


def test_policy_is_frozen_factory_only_and_repeatable():
    first = ResultPolicy.for_mode(RedesignedResultMode.REVIEW)
    second = ResultPolicy.for_mode(RedesignedResultMode.REVIEW)

    assert first == second
    assert first.included_statuses is second.included_statuses
    assert isinstance(first.included_statuses, tuple)
    with pytest.raises(FrozenInstanceError):
        first.mode = RedesignedResultMode.ALL
    with pytest.raises(TypeError):
        first.included_statuses[0] = TargetBusinessStatus.UNIQUE_NO_MATCH
    with pytest.raises(TypeError):
        ResultPolicy()
    with pytest.raises(TypeError):
        ResultPolicy(
            RedesignedResultMode.REVIEW,
            (),
        )


def test_package_exports_new_and_existing_contracts():
    assert TargetBusinessStatus.__name__ == 'TargetBusinessStatus'
    assert RedesignedResultMode.__name__ == 'RedesignedResultMode'
    assert ResultPolicy.__name__ == 'ResultPolicy'
    assert CandidatePair.__name__ == 'CandidatePair'
    assert CandidateScoringResult.__name__ == 'CandidateScoringResult'
    assert CanonicalRecord.__name__ == 'CanonicalRecord'
    assert ScoringEvidence.__name__ == 'ScoringEvidence'


def test_policy_import_has_no_runtime_layer_dependencies():
    backend_root = Path(__file__).resolve().parents[1]
    script = (
        'import sys\n'
        'import app.contracts.result_policy\n'
        "forbidden = ('pandas', 'fastapi', 'sqlalchemy', "
        "'app.repositories', 'app.engine.engine_selection')\n"
        'assert not any(name == prefix or name.startswith(prefix + \".\") '
        'for name in sys.modules for prefix in forbidden)\n'
    )

    completed = subprocess.run(
        [sys.executable, '-c', script],
        cwd=backend_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
