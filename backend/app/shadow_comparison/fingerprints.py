"""Stable semantic SHA-256 fingerprints for GF-7A comparison artifacts."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum


def _canonical(value):
    if dataclasses.is_dataclass(value):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def shadow_fingerprint(kind: str, value) -> str:
    encoded = json.dumps(
        {"contract": "g2-shadow-comparison-v1", "kind": kind, "value": _canonical(value)},
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
