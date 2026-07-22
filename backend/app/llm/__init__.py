"""Optional LLM transport and contracts; deterministic results remain authoritative."""

from app.llm.contracts import (
    AdvisoryAssessment,
    AdvisoryRecommendedAction,
    CandidateAdvisoryRequest,
    CandidateAdvisoryResponse,
    CandidateEvidence,
    ColumnSuggestionRequest,
    ColumnSuggestionResponse,
    CriticalMismatchEvidence,
    DeterministicConfidence,
    DeterministicRuleDecision,
    DeterministicStatus,
    DifficultValueFieldContext,
    DifficultValueRequest,
    DifficultValueResponse,
)
from app.llm.disabled_provider import DisabledLLMProvider
from app.llm.exceptions import (
    LLMProviderConfigurationError,
    LLMProviderDisabledError,
    LLMProviderEmptyResponseError,
    LLMProviderError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderResponseStructureError,
    LLMProviderTimeoutError,
)
from app.llm.factory import create_llm_provider
from app.llm.groq_provider import GroqLLMProvider
from app.llm.provider import LLMProvider, LLMProviderResult, LLMUsageMetadata

__all__ = [
    "AdvisoryAssessment",
    "AdvisoryRecommendedAction",
    "CandidateAdvisoryRequest",
    "CandidateAdvisoryResponse",
    "CandidateEvidence",
    "ColumnSuggestionRequest",
    "ColumnSuggestionResponse",
    "CriticalMismatchEvidence",
    "DeterministicConfidence",
    "DeterministicRuleDecision",
    "DeterministicStatus",
    "DifficultValueFieldContext",
    "DifficultValueRequest",
    "DifficultValueResponse",
    "DisabledLLMProvider",
    "GroqLLMProvider",
    "LLMProvider",
    "LLMProviderConfigurationError",
    "LLMProviderDisabledError",
    "LLMProviderEmptyResponseError",
    "LLMProviderError",
    "LLMProviderHTTPError",
    "LLMProviderMalformedJSONError",
    "LLMProviderResponseStructureError",
    "LLMProviderResult",
    "LLMProviderTimeoutError",
    "LLMUsageMetadata",
    "create_llm_provider",
]
