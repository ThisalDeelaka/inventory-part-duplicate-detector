from pathlib import Path

import pandas as pd
import pytest

from app.contracts.candidates import CandidatePair
from app.contracts.results import CandidateScoringResult
from app.core.config import Settings, settings
from app.db.models import (
    DuplicateCandidate,
    DuplicateFeedback,
    DuplicateScan,
    RuleExclusionAudit,
    ScanWarning,
)
from app.engine import engine_selection
from app.engine.engine_selection import (
    LegacyDeterministicScoringEngine,
    RedesignedEngineUnavailableError,
    select_candidate_scoring_engine,
)
from app.engine.scoring import score_candidate
from app.services import scan_runner as scan_runner_module
from app.services.scan_runner import ScanRunner


def _record(part_no: str, description: str, unit: str = 'PCS') -> dict[str, str]:
    return {
        'PART_NO': part_no,
        'DESCRIPTION': description,
        'CONTRACT': 'S1',
        'UNIT_MEAS': unit,
        'HSN_SAC_CODE': '1000',
        'CLIENT_SPECIFIC_FIELD': 'preserved extra value',
    }


def test_use_redesigned_engine_defaults_to_false(monkeypatch):
    monkeypatch.delenv('USE_REDESIGNED_ENGINE', raising=False)

    assert Settings().use_redesigned_engine is False


@pytest.mark.parametrize('value', ['0', 'false', 'FALSE', 'no', 'off', '  false  '])
def test_use_redesigned_engine_accepts_false_values(monkeypatch, value):
    monkeypatch.setenv('USE_REDESIGNED_ENGINE', value)

    assert Settings().use_redesigned_engine is False


@pytest.mark.parametrize('value', ['1', 'true', 'TRUE', 'yes', 'on', '  true  '])
def test_use_redesigned_engine_accepts_true_values(monkeypatch, value):
    monkeypatch.setenv('USE_REDESIGNED_ENGINE', value)

    assert Settings().use_redesigned_engine is True


def test_use_redesigned_engine_rejects_malformed_value(monkeypatch):
    monkeypatch.setenv('USE_REDESIGNED_ENGINE', 'sometimes')

    with pytest.raises(ValueError, match='USE_REDESIGNED_ENGINE must be one of'):
        Settings()


def test_selector_false_returns_legacy_adapter():
    assert isinstance(select_candidate_scoring_engine(False), LegacyDeterministicScoringEngine)


def test_selector_true_raises_without_constructing_legacy_adapter(monkeypatch):
    def unexpected_legacy_adapter():
        raise AssertionError('legacy adapter must not be used as a fallback')

    monkeypatch.setattr(
        engine_selection,
        'LegacyDeterministicScoringEngine',
        unexpected_legacy_adapter,
    )

    with pytest.raises(RedesignedEngineUnavailableError, match='not implemented'):
        select_candidate_scoring_engine(True)


@pytest.mark.parametrize(
    ('record_a', 'record_b'),
    [
        (_record('MCB30A-1', 'MCB30A'), _record('MCB30A-2', 'MCB 30 Amp')),
        (_record('PIPE-1', 'Stainless Steel Pipe', 'M'), _record('PIPE-2', 'SS Pipe', 'PCS')),
    ],
)
def test_legacy_adapter_returns_complete_direct_scoring_result(record_a, record_b):
    selected_fields = ['CONTRACT', 'UNIT_MEAS']
    adapter = LegacyDeterministicScoringEngine()
    candidate = CandidatePair.from_legacy_mapping({
        'record_a': record_a,
        'record_b': record_b,
        'matched_fields': ['CONTRACT'],
        'mismatched_fields': [],
        'warnings': [],
    })

    assert adapter.score_candidate(
        candidate,
        selected_fields,
    ).to_legacy_dict() == score_candidate(
        record_a,
        record_b,
        selected_fields,
    )


def test_scan_selects_engine_once_and_scores_every_pair_through_it(db, monkeypatch):
    class SpyEngine:
        def __init__(self):
            self.calls = 0
            self.candidates = []
            self.results = []

        def score_candidate(self, candidate, selected_fields, scan_mode):
            self.calls += 1
            self.candidates.append(candidate)
            result = CandidateScoringResult.from_legacy_mapping(score_candidate(
                candidate.record_a.to_legacy_dict(),
                candidate.record_b.to_legacy_dict(),
                selected_fields,
                scan_mode,
            ))
            self.results.append(result)
            return result

    spy = SpyEngine()
    selection_calls = 0

    def select_spy():
        nonlocal selection_calls
        selection_calls += 1
        return spy

    monkeypatch.setattr(scan_runner_module, 'select_candidate_scoring_engine', select_spy)
    frame = pd.DataFrame(
        [
            _record('A', 'MCB30A'),
            _record('B', 'MCB 30 A'),
            _record('C', 'M.C.B 30 AMP'),
        ]
    )

    _scan, pair_count = ScanRunner(db).run(
        frame,
        'Delegation test',
        ['CONTRACT', 'UNIT_MEAS'],
        75,
    )

    assert pair_count == 3
    assert selection_calls == 1
    assert spy.calls == pair_count
    assert len(spy.candidates) == pair_count
    assert all(isinstance(candidate, CandidatePair) for candidate in spy.candidates)
    assert all(
        isinstance(result, CandidateScoringResult)
        for result in spy.results
    )
    assert all(
        candidate.record_a.raw_attributes['CLIENT_SPECIFIC_FIELD']
        == 'preserved extra value'
        and candidate.record_b.raw_attributes['CLIENT_SPECIFIC_FIELD']
        == 'preserved extra value'
        for candidate in spy.candidates
    )
    assert all(
        candidate.matched_fields == ('CONTRACT', 'UNIT_MEAS')
        for candidate in spy.candidates
    )
    assert all(candidate.mismatched_fields == () for candidate in spy.candidates)
    assert all(candidate.warnings == () for candidate in spy.candidates)


def test_redesigned_engine_request_fails_before_any_scan_side_effect(db, monkeypatch):
    monkeypatch.setattr(settings, 'use_redesigned_engine', True)

    def unexpected_scoring(*_args, **_kwargs):
        raise AssertionError('scoring must not run')

    def unexpected_candidate_generation(*_args, **_kwargs):
        raise AssertionError('candidate generation must not run')

    monkeypatch.setattr(engine_selection, 'score_candidate', unexpected_scoring)
    monkeypatch.setattr(
        scan_runner_module,
        'generate_candidate_pairs',
        unexpected_candidate_generation,
    )
    frame = pd.DataFrame([_record('A', 'MCB30A'), _record('B', 'MCB 30 A')])

    with pytest.raises(RedesignedEngineUnavailableError, match='not implemented'):
        ScanRunner(db).run(frame, 'Unavailable engine', ['CONTRACT', 'UNIT_MEAS'], 75)

    for model in (
        DuplicateScan,
        ScanWarning,
        DuplicateCandidate,
        RuleExclusionAudit,
        DuplicateFeedback,
    ):
        assert db.query(model).count() == 0


def test_default_sample_scan_characterizes_api_and_exports(db, client):
    sample_path = Path(__file__).resolve().parents[2] / 'data' / 'sample_inventory_parts.csv'
    frame = pd.read_csv(sample_path, dtype=str)

    scan, pair_count = ScanRunner(db).run(
        frame,
        'Deterministic sample characterization',
        ['CONTRACT', 'UNIT_MEAS'],
        75,
    )

    assert len(frame) == 20
    assert pair_count == 48
    assert scan.status == 'COMPLETED'
    assert scan.total_records == 20
    assert scan.total_candidates == 10
    assert scan.rejections_count == 38
    assert scan.warnings_count == 1

    candidate_response = client.get(f'/api/scans/{scan.id}/candidates')
    exclusion_response = client.get(f'/api/scans/{scan.id}/rejections')
    candidate_export = client.get(f'/api/scans/{scan.id}/export')
    exclusion_export = client.get(f'/api/scans/{scan.id}/rejections/export')

    assert candidate_response.status_code == 200
    assert exclusion_response.status_code == 200
    candidates = candidate_response.json()
    exclusions = exclusion_response.json()
    assert len(candidates) == 10
    assert len(exclusions) == 38
    assert set(candidates[0]) == {
        'id', 'scan_id', 'contract_a', 'part_no_a', 'description_a', 'contract_b',
        'part_no_b', 'description_b', 'similarity_score', 'confidence_level',
        'description_similarity', 'tfidf_score', 'fuzzy_score', 'part_no_similarity',
        'technical_token_score', 'matched_fields', 'mismatched_fields', 'explanation',
        'recommended_action', 'review_status', 'reviewed_by', 'reviewed_at',
        'business_status', 'rule_decision', 'rejection_reason', 'scan_mode',
        'critical_mismatches', 'variant_attributes_a', 'variant_attributes_b',
        'generic_description_warning', 'application_context_a', 'application_context_b',
        'application_context_warning', 'normalized_description_a',
        'normalized_description_b', 'normalized_part_no_a', 'normalized_part_no_b',
    }
    assert set(exclusions[0]) == {
        'id', 'scan_id', 'contract_a', 'part_no_a', 'description_a', 'contract_b',
        'part_no_b', 'description_b', 'similarity_score', 'confidence_level',
        'business_status', 'rule_decision', 'rejection_reason', 'critical_mismatches',
        'explanation', 'created_at',
    }

    assert candidate_export.status_code == 200
    assert exclusion_export.status_code == 200
    assert f'scan-{scan.id}-candidates.csv' in candidate_export.headers['content-disposition']
    assert f'scan-{scan.id}-rule-exclusions.csv' in exclusion_export.headers['content-disposition']
    assert len(candidate_export.text.splitlines()) == 11
    assert len(exclusion_export.text.splitlines()) == 39
    assert 'business_status' in candidate_export.text.splitlines()[0]
    assert 'rejection_reason' in exclusion_export.text.splitlines()[0]
