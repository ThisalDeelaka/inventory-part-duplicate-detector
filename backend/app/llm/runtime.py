from collections.abc import Callable

from app.core.config import Settings, settings
from app.llm.audit import LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.factory import create_llm_provider
from app.llm.provider import LLMProvider


_cache = LLMCache(
    enabled=settings.llm_cache_enabled,
    max_entries=settings.llm_cache_max_entries,
    ttl_seconds=settings.llm_cache_ttl_seconds,
)
_audit = LLMAuditStore(
    enabled=settings.llm_audit_enabled,
    max_entries=settings.llm_audit_max_entries,
)


def get_llm_settings() -> Settings:
    return settings


def get_llm_cache() -> LLMCache:
    return _cache


def get_llm_audit() -> LLMAuditStore:
    return _audit


def get_llm_provider_factory() -> Callable[[Settings], LLMProvider]:
    return create_llm_provider


def reset_llm_runtime_state() -> None:
    _cache.reset()
    _audit.reset()
