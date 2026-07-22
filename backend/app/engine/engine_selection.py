from typing import Protocol

from app.contracts.candidates import CandidatePair
from app.contracts.results import CandidateScoringResult
from app.core.config import settings
from app.engine.scoring import score_candidate


class CandidateScoringEngine(Protocol):
    def score_candidate(
        self,
        candidate: CandidatePair,
        selected_fields: list[str],
        scan_mode: str = 'SAME_SITE_DUPLICATE',
    ) -> CandidateScoringResult: ...


class LegacyDeterministicScoringEngine:
    def score_candidate(
        self,
        candidate: CandidatePair,
        selected_fields: list[str],
        scan_mode: str = 'SAME_SITE_DUPLICATE',
    ) -> CandidateScoringResult:
        legacy_result = score_candidate(
            candidate.record_a.to_legacy_dict(),
            candidate.record_b.to_legacy_dict(),
            selected_fields,
            scan_mode,
        )
        return CandidateScoringResult.from_legacy_mapping(
            legacy_result
        )


class RedesignedEngineUnavailableError(RuntimeError):
    '''The explicitly requested Production Identity Engine is unavailable.'''


def select_candidate_scoring_engine(
    use_redesigned_engine: bool | None = None,
) -> CandidateScoringEngine:
    redesigned_requested = (
        settings.use_redesigned_engine
        if use_redesigned_engine is None
        else use_redesigned_engine
    )
    if redesigned_requested:
        raise RedesignedEngineUnavailableError(
            'USE_REDESIGNED_ENGINE=true requested the Production Identity Engine, '
            'but that engine is not implemented'
        )
    return LegacyDeterministicScoringEngine()
