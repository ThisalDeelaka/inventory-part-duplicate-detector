from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from app.contracts.candidates import CandidatePair
from app.contracts.evidence import ScoringEvidence
from app.contracts import results as results_module
from app.contracts.results import CandidateScoringResult
from app.engine import engine_selection
from app.engine.engine_selection import LegacyDeterministicScoringEngine
from app.engine.scoring import score_candidate
from app.services import scan_runner as scan_runner_module
from app.services.scan_runner import ScanRunner


EXPECTED_RESULT_KEYS = [
    'final_score',
    'confidence_level',
    'description_similarity',
    'tfidf_score',
    'fuzzy_score',
    'part_no_similarity',
    'technical_token_score',
    'matched_fields',
    'mismatched_fields',
    'explanation',
    'recommended_action',
    'business_status',
    'rule_decision',
    'rejection_reason',
    'scan_mode',
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
]

TYPED_FIELDS = [
    'final_score',
    'confidence_level',
    'business_status',
    'rule_decision',
    'rejection_reason',
    'scan_mode',
    'explanation',
    'recommended_action',
]


def _record(part_no, description, unit='PCS'):
    return {
        'PART_NO': part_no,
        'DESCRIPTION': description,
        'CONTRACT': 'S1',
        'UNIT_MEAS': unit,
        'HSN_SAC_CODE': '1000',
        'CLIENT_SPECIFIC_FIELD': 'preserved extra value',
    }


def _pair(record_a, record_b):
    return {
        'record_a': record_a,
        'record_b': record_b,
        'matched_fields': ['CONTRACT'],
        'mismatched_fields': [],
        'warnings': [],
    }


def _allowed_result():
    return score_candidate(
        _record('MCB30A-1', 'MCB30A'),
        _record('MCB30A-2', 'MCB 30 Amp'),
        ['CONTRACT', 'UNIT_MEAS'],
    )


def _non_allow_result():
    return score_candidate(
        _record('FILTER-1', 'Generator Oil Filter'),
        _record('FILTER-2', 'Generator Air Filter'),
        ['CONTRACT', 'UNIT_MEAS'],
    )


def _structured_result():
    return score_candidate(
        _record('SP-GEN-AIR-FLT', 'Generator Air Filter'),
        _record('HVAC-FILTER-01', 'Air Filter'),
        ['CONTRACT', 'UNIT_MEAS'],
    )


def test_complete_actual_result_snapshot_preserves_fields_order_and_unknown_keys():
    source = _allowed_result()
    source['CURRENT_EXTRA_RESULT'] = {'value': 'preserved'}
    before = dict(source)

    result = CandidateScoringResult.from_legacy_mapping(source)

    assert result.final_score == source['final_score']
    assert result.confidence_level == source['confidence_level']
    assert result.business_status == source['business_status']
    assert result.rule_decision == source['rule_decision']
    assert result.rejection_reason == source['rejection_reason']
    assert result.scan_mode == source['scan_mode']
    assert result.explanation == source['explanation']
    assert result.recommended_action == source['recommended_action']
    assert isinstance(result.evidence, ScoringEvidence)
    assert list(result.raw_result) == EXPECTED_RESULT_KEYS + [
        'CURRENT_EXTRA_RESULT'
    ]
    assert dict(result.raw_result) == source
    assert result.raw_result['CURRENT_EXTRA_RESULT'] == {'value': 'preserved'}
    assert 'CURRENT_EXTRA_RESULT' not in result.evidence.to_legacy_fields()
    assert 'evidence' not in result.raw_result
    assert 'evidence' not in result.to_legacy_dict()
    assert source == before


def test_constructs_evidence_once_from_the_same_result_snapshot(monkeypatch):
    source = _allowed_result()
    calls = []
    original_factory = ScoringEvidence.from_legacy_result.__func__

    def factory_spy(cls, result):
        calls.append(result)
        return original_factory(cls, result)

    monkeypatch.setattr(
        results_module.ScoringEvidence,
        'from_legacy_result',
        classmethod(factory_spy),
    )

    result = CandidateScoringResult.from_legacy_mapping(source)

    assert len(calls) == 1
    assert calls[0] == source
    assert calls[0] is not source
    assert result.evidence.to_legacy_fields() == {
        key: source[key]
        for key in result.evidence.to_legacy_fields()
    }


@pytest.mark.parametrize('invalid', [None, [], object(), 'not a mapping'])
def test_rejects_non_mapping_result_input(invalid):
    with pytest.raises(TypeError, match='scoring result must be a mapping'):
        CandidateScoringResult.from_legacy_mapping(invalid)


@pytest.mark.parametrize('missing_field', TYPED_FIELDS)
def test_rejects_each_missing_typed_field(missing_field):
    source = _allowed_result()
    del source[missing_field]

    with pytest.raises(ValueError, match=f'missing required field: {missing_field}'):
        CandidateScoringResult.from_legacy_mapping(source)


@pytest.mark.parametrize(
    ('field', 'invalid', 'expected_type'),
    [
        ('final_score', 75, 'float'),
        ('confidence_level', None, 'str'),
        ('business_status', None, 'str'),
        ('rule_decision', None, 'str'),
        ('rejection_reason', None, 'str'),
        ('scan_mode', None, 'str'),
        ('explanation', None, 'str'),
        ('recommended_action', None, 'str'),
    ],
)
def test_rejects_invalid_typed_field_types(field, invalid, expected_type):
    source = _allowed_result()
    source[field] = invalid

    with pytest.raises(TypeError, match=f'{field} must be {expected_type}'):
        CandidateScoringResult.from_legacy_mapping(source)


def test_snapshots_top_level_and_preserves_shallow_nested_values():
    source = _non_allow_result()
    nested_evidence = source['critical_mismatches']
    matched_evidence = source['matched_fields']
    variant_evidence = source['variant_attributes_a']
    original_score = source['final_score']
    original_rule = source['rule_decision']
    result = CandidateScoringResult.from_legacy_mapping(source)

    source['final_score'] = 999.0
    source['rule_decision'] = 'CHANGED'
    source['NEW_TOP_LEVEL_KEY'] = 'not captured'

    assert result.final_score == original_score
    assert result.rule_decision == original_rule
    assert result.raw_result['final_score'] == original_score
    assert result.raw_result['rule_decision'] == original_rule
    assert 'NEW_TOP_LEVEL_KEY' not in result.raw_result
    with pytest.raises(TypeError):
        result.raw_result['final_score'] = 1.0
    with pytest.raises(FrozenInstanceError):
        result.final_score = 1.0

    nested_evidence.append({'group': 'SHALLOW_REFERENCE'})
    matched_evidence.append('SHALLOW_REFERENCE')
    variant_evidence['SHALLOW_REFERENCE'] = []
    assert result.raw_result['critical_mismatches'] is nested_evidence
    assert result.raw_result['matched_fields'] is matched_evidence
    assert result.raw_result['variant_attributes_a'] is variant_evidence
    assert result.raw_result['critical_mismatches'][-1] == {
        'group': 'SHALLOW_REFERENCE'
    }
    assert all(
        mismatch.get('group') != 'SHALLOW_REFERENCE'
        for mismatch in result.evidence.critical_mismatches
    )
    assert 'SHALLOW_REFERENCE' not in result.evidence.matched_fields
    assert 'SHALLOW_REFERENCE' not in result.evidence.variant_attributes_a


def test_legacy_conversion_is_complete_ordered_fresh_and_isolated():
    source = _structured_result()
    source['CURRENT_EXTRA_RESULT'] = ['preserved']
    result = CandidateScoringResult.from_legacy_mapping(source)

    first = result.to_legacy_dict()
    second = result.to_legacy_dict()

    assert type(first) is dict
    assert first == source
    assert second == source
    assert list(first) == list(source)
    assert first is not second
    assert first['critical_mismatches'] is second['critical_mismatches']
    first['final_score'] = -1.0
    first['NEW_TOP_LEVEL_KEY'] = 'changed'
    del first['CURRENT_EXTRA_RESULT']
    assert second == source
    assert result.to_legacy_dict() == source


@pytest.mark.parametrize(
    'result_factory',
    [_allowed_result, _non_allow_result, _structured_result],
    ids=['allowed', 'non-allow', 'structured-evidence'],
)
def test_actual_result_paths_round_trip_exactly(result_factory):
    original = result_factory()

    converted = CandidateScoringResult.from_legacy_mapping(
        original
    ).to_legacy_dict()

    assert converted == original
    assert list(converted) == list(original) == EXPECTED_RESULT_KEYS


@pytest.mark.parametrize(
    ('record_a', 'record_b'),
    [
        (
            _record('MCB30A-1', 'MCB30A'),
            _record('MCB30A-2', 'MCB 30 Amp'),
        ),
        (
            _record('FILTER-1', 'Generator Oil Filter'),
            _record('FILTER-2', 'Generator Air Filter'),
        ),
    ],
    ids=['allowed', 'non-allow'],
)
def test_legacy_adapter_returns_typed_exact_parity_and_calls_scorer_once(
    record_a,
    record_b,
    monkeypatch,
):
    selected_fields = ['CONTRACT', 'UNIT_MEAS']
    direct_result = score_candidate(record_a, record_b, selected_fields)
    calls = []

    def scoring_spy(actual_a, actual_b, actual_fields, actual_mode):
        calls.append((actual_a, actual_b, actual_fields, actual_mode))
        return direct_result

    monkeypatch.setattr(engine_selection, 'score_candidate', scoring_spy)
    candidate = CandidatePair.from_legacy_mapping(_pair(record_a, record_b))

    typed_result = LegacyDeterministicScoringEngine().score_candidate(
        candidate,
        selected_fields,
    )

    assert isinstance(typed_result, CandidateScoringResult)
    assert typed_result.to_legacy_dict() == direct_result
    assert list(typed_result.raw_result) == list(direct_result)
    assert len(calls) == 1
    assert calls[0][0] == record_a
    assert calls[0][1] == record_b
    assert calls[0][2] is selected_fields
    assert calls[0][3] == 'SAME_SITE_DUPLICATE'


def test_scan_uses_typed_fields_and_one_legacy_conversion_per_pair(
    db,
    monkeypatch,
):
    pair_allowed = _pair(
        _record('MCB30A-1', 'MCB30A'),
        _record('MCB30A-2', 'MCB 30 Amp'),
    )
    pair_excluded = _pair(
        _record('FILTER-1', 'Generator Oil Filter'),
        _record('FILTER-2', 'Generator Air Filter'),
    )
    legacy_results = [_allowed_result(), _non_allow_result()]
    conversions = []

    class CountingResult(CandidateScoringResult):
        def to_legacy_dict(self):
            conversions.append(self)
            return super().to_legacy_dict()

    class SpyEngine:
        def __init__(self):
            self.candidates = []

        def score_candidate(self, candidate, selected_fields, scan_mode):
            self.candidates.append(candidate)
            return CountingResult.from_legacy_mapping(
                legacy_results[len(self.candidates) - 1]
            )

    spy = SpyEngine()
    selections = []

    def select_spy():
        selections.append(True)
        return spy

    monkeypatch.setattr(
        scan_runner_module,
        'select_candidate_scoring_engine',
        select_spy,
    )
    monkeypatch.setattr(
        scan_runner_module,
        'generate_candidate_pairs',
        lambda _frame, _fields: [pair_allowed, pair_excluded],
    )

    runner = ScanRunner(db)
    candidate_saves = []
    rejection_saves = []
    original_candidate_save = runner.candidates.save
    original_rejection_save = runner.rejections.save

    def capture_candidate_save(scan_id, record_a, record_b, result):
        candidate_saves.append((record_a, record_b, result))
        return original_candidate_save(scan_id, record_a, record_b, result)

    def capture_rejection_save(scan_id, record_a, record_b, result):
        rejection_saves.append((record_a, record_b, result))
        return original_rejection_save(scan_id, record_a, record_b, result)

    monkeypatch.setattr(runner.candidates, 'save', capture_candidate_save)
    monkeypatch.setattr(runner.rejections, 'save', capture_rejection_save)
    frame = pd.DataFrame([
        _record('FRAME-A', 'Frame record A'),
        _record('FRAME-B', 'Frame record B'),
    ])

    scan, pair_count = runner.run(
        frame,
        'Typed result scan',
        ['CONTRACT', 'UNIT_MEAS'],
        75,
    )

    assert scan.status == 'COMPLETED'
    assert pair_count == 2
    assert len(selections) == 1
    assert len(spy.candidates) == pair_count
    assert all(
        isinstance(candidate, CandidatePair)
        for candidate in spy.candidates
    )
    assert len(conversions) == pair_count
    assert len(candidate_saves) == 1
    assert len(rejection_saves) == 1
    assert candidate_saves[0][0] is pair_allowed['record_a']
    assert candidate_saves[0][1] is pair_allowed['record_b']
    assert rejection_saves[0][0] is pair_excluded['record_a']
    assert rejection_saves[0][1] is pair_excluded['record_b']
    assert type(candidate_saves[0][2]) is dict
    assert type(rejection_saves[0][2]) is dict
    assert candidate_saves[0][2] == legacy_results[0]
    assert rejection_saves[0][2] == legacy_results[1]
