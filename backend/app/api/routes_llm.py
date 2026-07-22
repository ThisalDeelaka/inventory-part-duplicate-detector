from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.database import get_db
from app.db.models import DuplicateCandidate
from app.llm.audit import LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.contracts import DifficultValueRequest
from app.llm.exceptions import (
    LLMProviderConfigurationError,
    LLMProviderDisabledError,
    LLMProviderEmptyResponseError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderResponseStructureError,
    LLMProviderTimeoutError,
)
from app.llm.prompts import PROMPT_VERSIONS
from app.llm.provider import LLMProvider
from app.llm.runtime import (
    get_llm_audit,
    get_llm_cache,
    get_llm_provider_factory,
    get_llm_settings,
)
from app.llm.service_contracts import (
    CandidateAdvisoryResult,
    ColumnSuggestionAPIRequest,
    ColumnSuggestionResult,
    DifficultValueResult,
    LLMStatusResponse,
)
from app.llm.services import (
    CandidateAdvisoryService,
    ColumnSuggestionService,
    DifficultValueInterpretationService,
    LLMStructuredOutputError,
)
from app.services.llm_snapshot_service import (
    SnapshotPersistenceError,
    persist_candidate_advisory_failure,
    persist_candidate_advisory_result,
)


router = APIRouter(prefix="/api/llm", tags=["llm-assistance"])


def _safe_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMProviderDisabledError):
        return HTTPException(
            503,
            {"category": "disabled", "message": "LLM assistance is disabled"},
        )
    if isinstance(exc, LLMProviderConfigurationError):
        return HTTPException(
            503,
            {
                "category": "configuration",
                "message": "LLM provider configuration is unavailable",
            },
        )
    if isinstance(exc, LLMProviderTimeoutError):
        return HTTPException(
            504,
            {"category": "timeout", "message": "LLM provider request timed out"},
        )
    if isinstance(exc, LLMProviderHTTPError):
        return HTTPException(
            502,
            {
                "category": "provider_failure",
                "message": "LLM provider request failed",
            },
        )
    if isinstance(
        exc,
        (
            LLMProviderEmptyResponseError,
            LLMProviderMalformedJSONError,
            LLMProviderResponseStructureError,
            LLMStructuredOutputError,
        ),
    ):
        return HTTPException(
            502,
            {
                "category": "invalid_provider_output",
                "message": "LLM provider output was unavailable or invalid",
            },
        )
    return HTTPException(
        500, {"category": "llm_failure", "message": "LLM assistance failed safely"}
    )


def _service_kwargs(
    configuration: Settings,
    cache: LLMCache,
    audit: LLMAuditStore,
    provider_factory: Callable[[Settings], LLMProvider],
) -> dict:
    return {
        "configuration": configuration,
        "cache": cache,
        "audit": audit,
        "provider_factory": provider_factory,
    }


@router.get("/status", response_model=LLMStatusResponse)
def status(
    configuration: Settings = Depends(get_llm_settings),
    cache: LLMCache = Depends(get_llm_cache),
    audit: LLMAuditStore = Depends(get_llm_audit),
):
    cache_stats = cache.stats()
    audit_summary = audit.summary()
    provider_configured = bool(
        configuration.llm_demo_enabled
        and configuration.llm_provider == "groq"
        and configuration.groq_api_key.get_secret_value().strip()
    )
    return LLMStatusResponse(
        enabled=configuration.llm_demo_enabled,
        provider=configuration.llm_provider,
        model=configuration.groq_model,
        provider_configured=provider_configured,
        cache_enabled=bool(cache_stats["enabled"]),
        cache_count=int(cache_stats["count"]),
        cache_hits=int(cache_stats["hits"]),
        cache_misses=int(cache_stats["misses"]),
        audit_enabled=bool(audit_summary["enabled"]),
        audit_count=int(audit_summary["count"]),
        prompt_versions=PROMPT_VERSIONS,
    )


@router.post("/column-suggestions", response_model=ColumnSuggestionResult)
async def column_suggestion(
    request: ColumnSuggestionAPIRequest,
    configuration: Settings = Depends(get_llm_settings),
    cache: LLMCache = Depends(get_llm_cache),
    audit: LLMAuditStore = Depends(get_llm_audit),
    provider_factory: Callable[[Settings], LLMProvider] = Depends(
        get_llm_provider_factory
    ),
):
    service = ColumnSuggestionService(
        **_service_kwargs(configuration, cache, audit, provider_factory)
    )
    try:
        return await service.suggest(request)
    except Exception as exc:
        raise _safe_http_error(exc) from None


@router.post("/difficult-values/interpret", response_model=DifficultValueResult)
async def difficult_value(
    request: DifficultValueRequest,
    configuration: Settings = Depends(get_llm_settings),
    cache: LLMCache = Depends(get_llm_cache),
    audit: LLMAuditStore = Depends(get_llm_audit),
    provider_factory: Callable[[Settings], LLMProvider] = Depends(
        get_llm_provider_factory
    ),
):
    service = DifficultValueInterpretationService(
        **_service_kwargs(configuration, cache, audit, provider_factory)
    )
    try:
        return await service.interpret(request)
    except Exception as exc:
        raise _safe_http_error(exc) from None


@router.post(
    "/candidates/{candidate_id}/advisory", response_model=CandidateAdvisoryResult
)
async def candidate_advisory(
    candidate_id: int,
    db: Session = Depends(get_db),
    configuration: Settings = Depends(get_llm_settings),
    cache: LLMCache = Depends(get_llm_cache),
    audit: LLMAuditStore = Depends(get_llm_audit),
    provider_factory: Callable[[Settings], LLMProvider] = Depends(
        get_llm_provider_factory
    ),
):
    candidate = (
        db.query(DuplicateCandidate)
        .filter(DuplicateCandidate.id == candidate_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    service = CandidateAdvisoryService(
        **_service_kwargs(configuration, cache, audit, provider_factory)
    )
    try:
        result = await service.advise(candidate)
        persist_candidate_advisory_result(db, candidate.id, result)
        return result
    except SnapshotPersistenceError:
        raise HTTPException(
            500,
            {
                "category": "snapshot_persistence_failure",
                "message": "LLM advisory could not be saved safely",
            },
        ) from None
    except Exception as exc:
        try:
            persist_candidate_advisory_failure(db, candidate.id, exc, configuration)
        except SnapshotPersistenceError:
            raise HTTPException(
                500,
                {
                    "category": "snapshot_persistence_failure",
                    "message": "LLM advisory outcome could not be saved safely",
                },
            ) from None
        raise _safe_http_error(exc) from None
