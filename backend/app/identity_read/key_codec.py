"""URL-safe serialization for projection-scoped identity group keys."""

from __future__ import annotations

import base64
import json

from app.identity_read.contracts import (
    IdentityReadProjectionContract,
    VersionedIdentityGroupKey,
)


IDENTITY_GROUP_KEY_VERSION = "igk1"


class InvalidVersionedIdentityGroupKey(ValueError):
    pass


def serialize_versioned_identity_group_key(key: VersionedIdentityGroupKey) -> str:
    if key.scan_id <= 0 or not str(key.group_reference).strip():
        raise InvalidVersionedIdentityGroupKey("invalid versioned identity group key")
    payload = json.dumps(
        {"g": key.group_reference, "p": key.projection_contract.value, "s": key.scan_id},
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{IDENTITY_GROUP_KEY_VERSION}.{encoded}"


def parse_versioned_identity_group_key(value: str) -> VersionedIdentityGroupKey:
    try:
        version, encoded = str(value).split(".", 1)
        if version != IDENTITY_GROUP_KEY_VERSION or not encoded:
            raise ValueError
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        if set(payload) != {"g", "p", "s"}:
            raise ValueError
        scan_id = int(payload["s"])
        group_reference = payload["g"]
        if scan_id <= 0 or not isinstance(group_reference, str) or not group_reference.strip():
            raise ValueError
        if len(group_reference) > 200:
            raise ValueError
        return VersionedIdentityGroupKey(
            scan_id=scan_id,
            projection_contract=IdentityReadProjectionContract(payload["p"]),
            group_reference=group_reference,
        )
    except Exception as exc:
        raise InvalidVersionedIdentityGroupKey(
            "invalid versioned identity group key"
        ) from exc
