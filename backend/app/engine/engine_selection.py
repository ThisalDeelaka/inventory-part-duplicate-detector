from typing import Any, Protocol

from app.contracts.records import CanonicalRecord
from app.core.config import settings
from app.engine.scoring import score_candidate


class CandidateScoringEngine(Protocol):
    def score_candidate(
        self,
        record_a: CanonicalRecord,
        record_b: CanonicalRecord,
        selected_fields: list[str],
        scan_mode: str = 'SAME_SITE_DUPLICATE',
    ) -> dict[str, Any]: ...


class LegacyDeterministicScoringEngine:
    def score_candidate(
        self,
        record_a: CanonicalRecord,
        record_b: CanonicalRecord,
        selected_fields: list[str],
        scan_mode: str = 'SAME_SITE_DUPLICATE',
    ) -> dict[str, Any]:
        return score_candidate(
            record_a.to_legacy_dict(),
            record_b.to_legacy_dict(),
            selected_fields,
            scan_mode,
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
