import copy
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable


@dataclass(frozen=True)
class _CacheEntry:
    value: dict[str, Any]
    expires_at: float


class LLMCache:
    """Bounded, concurrency-safe, process-local and non-durable LLM cache."""

    def __init__(
        self,
        *,
        enabled: bool,
        max_entries: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = RLock()

    @staticmethod
    def build_key(
        *,
        capability: str,
        request: dict[str, Any],
        provider: str,
        model: str,
        prompt_version: str,
    ) -> str:
        canonical = json.dumps(
            {
                "capability": capability,
                "request": request,
                "provider": provider,
                "model": model,
                "prompt_version": prompt_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _remove_expired(self, now: float) -> None:
        expired = [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]
        for key in expired:
            self._entries.pop(key, None)

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with self._lock:
            self._remove_expired(self._clock())
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return copy.deepcopy(entry.value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            now = self._clock()
            self._remove_expired(now)
            self._entries[key] = _CacheEntry(
                value=copy.deepcopy(value), expires_at=now + self.ttl_seconds
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def stats(self) -> dict[str, int | bool]:
        with self._lock:
            if self.enabled:
                self._remove_expired(self._clock())
            return {
                "enabled": self.enabled,
                "count": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
            }

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
            self._hits = 0
            self._misses = 0
