from app.llm.audit import LLMAuditOutcome, LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.service_contracts import LLMCapability


class Clock:
    def __init__(self, value=100.0):
        self.value = value

    def __call__(self):
        return self.value


def _key(cache, **overrides):
    values = {
        "capability": "column_suggestion",
        "request": {"source_column": "Mystery"},
        "provider": "groq",
        "model": "model-a",
        "prompt_version": "v1",
    }
    values.update(overrides)
    return cache.build_key(**values)


def test_cache_key_changes_for_every_required_dimension():
    cache = LLMCache(enabled=True, max_entries=10, ttl_seconds=10)
    base = _key(cache)
    variants = {
        _key(cache, capability="difficult_value"),
        _key(cache, request={"source_column": "Other"}),
        _key(cache, provider="other"),
        _key(cache, model="model-b"),
        _key(cache, prompt_version="v2"),
    }
    assert base not in variants
    assert len(variants) == 5


def test_cache_hit_ttl_lru_capacity_and_reset():
    clock = Clock()
    cache = LLMCache(
        enabled=True, max_entries=2, ttl_seconds=10, clock=clock
    )
    one, two, three = (_key(cache, request={"id": value}) for value in (1, 2, 3))
    cache.set(one, {"value": 1})
    cache.set(two, {"value": 2})
    assert cache.get(one) == {"value": 1}
    cache.set(three, {"value": 3})
    assert cache.get(two) is None
    assert cache.get(one) == {"value": 1}

    clock.value += 11
    assert cache.get(one) is None
    assert cache.stats()["count"] == 0
    cache.reset()
    assert cache.stats() == {"enabled": True, "count": 0, "hits": 0, "misses": 0}


def test_disabled_cache_stores_nothing_and_values_are_copied():
    disabled = LLMCache(enabled=False, max_entries=2, ttl_seconds=10)
    key = _key(disabled)
    disabled.set(key, {"secret": "not stored"})
    assert disabled.get(key) is None
    assert disabled.stats()["count"] == 0

    enabled = LLMCache(enabled=True, max_entries=2, ttl_seconds=10)
    value = {"nested": {"safe": "value"}}
    enabled.set(key, value)
    value["nested"]["safe"] = "changed"
    assert enabled.get(key)["nested"]["safe"] == "value"


def _audit_fields(outcome=LLMAuditOutcome.SUCCESS):
    return {
        "capability": LLMCapability.COLUMN_SUGGESTION,
        "provider": "groq",
        "model": "model",
        "prompt_version": "v1",
        "request_hash": "a" * 64,
        "outcome": outcome,
        "latency_ms": 1,
        "cache_hit": outcome == LLMAuditOutcome.CACHE_HIT,
        "validation_result": "valid",
    }


def test_audit_is_bounded_safe_and_resettable():
    store = LLMAuditStore(enabled=True, max_entries=2, clock=Clock())
    first = store.record(**_audit_fields(LLMAuditOutcome.SUCCESS))
    store.record(**_audit_fields(LLMAuditOutcome.CACHE_HIT))
    store.record(**_audit_fields(LLMAuditOutcome.INELIGIBLE))

    events = store.events()
    assert len(events) == 2
    assert first.event_id not in {event.event_id for event in events}
    serialized = str([event.model_dump() for event in events]).lower()
    for prohibited in (
        "authorization",
        "api_key",
        "system_prompt",
        "user_prompt",
        "raw_response",
        "complete_row",
    ):
        assert prohibited not in serialized
    assert all(not isinstance(value, Exception) for event in events for value in event.__dict__.values())
    store.reset()
    assert store.summary()["count"] == 0


def test_disabled_audit_records_nothing():
    store = LLMAuditStore(enabled=False, max_entries=2)
    assert store.record(**_audit_fields()) is None
    assert store.events() == []
