import json

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import LlmAdvisorySnapshot, utcnow
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
from app.llm.service_contracts import CandidateAdvisoryResult, LLMCapability
from app.llm.services import LLMStructuredOutputError


CAPABILITY = LLMCapability.CANDIDATE_ADVISORY.value


class SnapshotPersistenceError(Exception):
    pass


def safe_error_category(exc: Exception) -> str:
    if isinstance(exc, LLMProviderDisabledError):
        return "disabled"
    if isinstance(exc, LLMProviderConfigurationError):
        return "configuration"
    if isinstance(exc, LLMProviderTimeoutError):
        return "timeout"
    if isinstance(exc, LLMProviderHTTPError):
        return "provider_failure"
    if isinstance(exc, (LLMProviderEmptyResponseError, LLMProviderMalformedJSONError, LLMProviderResponseStructureError, LLMStructuredOutputError)):
        return "invalid_provider_output"
    return "llm_failure"


def _value(value):
    return getattr(value, "value", value)


def _bounded_json(values) -> str:
    bounded = [str(value)[:512] for value in list(values or [])[:10]]
    return json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))


def _upsert(
    db: Session, candidate_id: int, values: dict, capability: LLMCapability
) -> LlmAdvisorySnapshot:
    """Commit the route-owned session, which must have no unrelated pending mutations.

    The unique constraint protects durable correctness during simultaneous first inserts;
    conflicts are not retried here, and a later explicit user retry is safe.
    """
    try:
        snapshot = db.query(LlmAdvisorySnapshot).filter(
            LlmAdvisorySnapshot.candidate_id == candidate_id,
            LlmAdvisorySnapshot.capability == capability.value,
        ).first()
        if snapshot is None:
            snapshot = LlmAdvisorySnapshot(
                candidate_id=candidate_id, capability=capability.value
            )
            db.add(snapshot)
        now = utcnow()
        values.update(generated_at=now, updated_at=now)
        for name, value in values.items():
            setattr(snapshot, name, value)
        db.commit()
        db.refresh(snapshot)
        return snapshot
    except Exception as exc:
        db.rollback()
        raise SnapshotPersistenceError("advisory snapshot persistence failed") from exc


def persist_candidate_advisory_result(
    db: Session,
    candidate_id: int,
    result: CandidateAdvisoryResult,
    capability: LLMCapability = LLMCapability.CANDIDATE_ADVISORY,
) -> LlmAdvisorySnapshot:
    metadata = result.metadata
    advisory = result.advisory
    available = advisory is not None
    values = {
        "state": "AVAILABLE" if available else "INELIGIBLE",
        "llm_used": metadata.llm_used,
        "cache_hit": metadata.cache_hit if available else False,
        "provider": str(metadata.provider)[:100] if available else None,
        "model": str(metadata.model)[:200] if available else None,
        "prompt_version": str(metadata.prompt_version)[:100] if available else None,
        "assessment": _value(advisory.assessment) if advisory else None,
        "confidence": advisory.confidence if advisory else None,
        "recommended_action": _value(advisory.recommended_action) if advisory else None,
        "supporting_evidence": _bounded_json(advisory.supporting_evidence) if advisory else None,
        "conflicting_evidence": _bounded_json(advisory.conflicting_evidence) if advisory else None,
        "bypass_reason": result.eligibility.reason.value[:200] if advisory is None else None,
        "safe_error_category": None,
        "deterministic_result_authoritative": True,
    }
    return _upsert(db, candidate_id, values, capability)


def persist_candidate_advisory_failure(
    db: Session,
    candidate_id: int,
    exc: Exception,
    configuration: Settings,
    capability: LLMCapability = LLMCapability.CANDIDATE_ADVISORY,
) -> LlmAdvisorySnapshot:
    category = safe_error_category(exc)
    values = {
        "state": "FAILED",
        "llm_used": category in {"timeout", "provider_failure", "invalid_provider_output"},
        "cache_hit": False,
        "provider": str(configuration.llm_provider)[:100],
        "model": str(configuration.groq_model)[:200],
        "prompt_version": PROMPT_VERSIONS[capability][:100],
        "assessment": None,
        "confidence": None,
        "recommended_action": None,
        "supporting_evidence": None,
        "conflicting_evidence": None,
        "bypass_reason": None,
        "safe_error_category": category,
        "deterministic_result_authoritative": True,
    }
    return _upsert(db, candidate_id, values, capability)
