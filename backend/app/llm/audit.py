import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from enum import Enum
from threading import RLock
from typing import Callable

from pydantic import Field

from app.llm.contracts import ShortText, StrictContract
from app.llm.service_contracts import LLMCapability


class LLMAuditOutcome(str, Enum):
    SUCCESS = "success"
    CACHE_HIT = "cache_hit"
    DISABLED = "disabled"
    PROVIDER_FAILURE = "provider_failure"
    VALIDATION_FAILURE = "validation_failure"
    INELIGIBLE = "ineligible"


class LLMAuditEvent(StrictContract):
    event_id: str = Field(min_length=1, max_length=64)
    capability: LLMCapability
    timestamp: datetime
    provider: ShortText
    model: str = Field(min_length=1, max_length=200)
    prompt_version: ShortText
    request_hash: str = Field(min_length=64, max_length=64)
    outcome: LLMAuditOutcome
    latency_ms: float = Field(ge=0)
    cache_hit: bool
    provider_request_id: str | None = Field(default=None, max_length=200)
    validation_result: str = Field(min_length=1, max_length=40)
    failure_category: str | None = Field(default=None, max_length=80)
    candidate_id: int | None = Field(default=None, gt=0)
    advisory_assessment: str | None = Field(default=None, max_length=50)


class LLMAuditStore:
    """Bounded, concurrency-safe, process-local and non-durable audit metadata."""

    def __init__(
        self,
        *,
        enabled: bool,
        max_entries: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.enabled = enabled
        self.max_entries = max_entries
        self._clock = clock
        self._events: list[LLMAuditEvent] = []
        self._lock = RLock()

    def record(self, **fields) -> LLMAuditEvent | None:
        if not self.enabled:
            return None
        event = LLMAuditEvent(
            event_id=uuid.uuid4().hex,
            timestamp=datetime.fromtimestamp(self._clock(), UTC),
            **fields,
        )
        with self._lock:
            self._events.append(event)
            if len(self._events) > self.max_entries:
                del self._events[: len(self._events) - self.max_entries]
        return event.model_copy(deep=True)

    def events(self) -> list[LLMAuditEvent]:
        with self._lock:
            return [event.model_copy(deep=True) for event in self._events]

    def summary(self) -> dict[str, object]:
        with self._lock:
            counts = Counter(event.outcome.value for event in self._events)
            return {
                "enabled": self.enabled,
                "count": len(self._events),
                "outcomes": dict(counts),
            }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
