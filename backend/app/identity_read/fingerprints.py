"""Canonical semantic SHA-256 fingerprints for GF-9A read contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum


def canonical_value(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: canonical_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    return value


def identity_read_fingerprint(namespace: str, value) -> str:
    payload = {"namespace": namespace, "semantic_content": canonical_value(value)}
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
