"""Read-only deterministic Match Strength V2 projection."""

from app.match_strength.contracts import (
    DETERMINISTIC_MATCH_STRENGTH_V2,
    MatchBand,
    MatchStrengthEvidence,
    MatchStrengthResult,
    MatchStrengthStatus,
    MatchStrengthUnscoredReason,
)
from app.match_strength.projection import project_match_strength

__all__ = (
    "DETERMINISTIC_MATCH_STRENGTH_V2",
    "MatchBand",
    "MatchStrengthEvidence",
    "MatchStrengthResult",
    "MatchStrengthStatus",
    "MatchStrengthUnscoredReason",
    "project_match_strength",
)
