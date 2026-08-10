import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from pydantic import ValidationError

from app.core.config import Settings
from app.llm.contracts import (
    InventoryRecordEnrichmentRequest,
    InventoryRecordEnrichmentResponse,
    InventoryRecordEvidence,
    InventorySemanticProfile,
)
from app.llm.prompts import (
    INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
    SYSTEM_PROMPTS,
    build_prompts,
)
from app.llm.service_contracts import LLMCapability


ENRICHMENT_CAPABILITY = LLMCapability.INVENTORY_RECORD_ENRICHMENT
FINGERPRINT_VERSION = "semantic-evidence-v1"
TENANT_DICTIONARY_VERSION = "domain-dictionary-v1"
PROFILE_FIELDS = (
    "canonical_item", "product_type", "purpose", "model", "material",
    "size_or_dimension", "rating", "side", "placement", "application",
    "technical_role",
)


def _clean(value, limit: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text[:limit]


def bounded_record_evidence(record_id: str, record: dict) -> InventoryRecordEvidence:
    return InventoryRecordEvidence(
        record_id=str(record_id)[:128],
        part_number=_clean(record.get("PART_NO"), 128),
        description=_clean(record.get("DESCRIPTION"), 2048) or "UNKNOWN",
        uom=_clean(record.get("UNIT_MEAS"), 128),
        site_or_contract=_clean(record.get("CONTRACT"), 128),
        product_category=_clean(record.get("PRODUCT_CATEGORY_ID"), 128),
        hsn_sac_code=_clean(record.get("HSN_SAC_CODE"), 128),
    )


def semantic_evidence_fingerprint(
    evidence: InventoryRecordEvidence,
    model: str,
    prompt_version: str = INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
) -> str:
    values = evidence.model_dump(mode="json", exclude={"record_id"})
    normalized = {
        key: (re.sub(r"\s+", " ", value).strip().casefold() if value else None)
        for key, value in sorted(values.items())
    }
    payload = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "tenant_dictionary_version": TENANT_DICTIONARY_VERSION,
        "model": model,
        "prompt_version": prompt_version,
        "evidence": normalized,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def profile_json(profile: InventorySemanticProfile) -> str:
    return json.dumps(
        profile.model_dump(mode="json", exclude={"record_id"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def profile_from_json(value: str, record_id: str = "cached") -> InventorySemanticProfile:
    payload = json.loads(value)
    payload["record_id"] = record_id
    return InventorySemanticProfile.model_validate(payload)


@dataclass(frozen=True)
class BatchEnrichmentResult:
    profiles: dict[str, InventorySemanticProfile]
    unresolved_ids: tuple[str, ...]
    unknown_ids: tuple[str, ...]


class SemanticEnrichmentService:
    def __init__(self, configuration: Settings, provider_factory) -> None:
        self.configuration = configuration
        self.provider_factory = provider_factory

    async def enrich_batch(
        self, records: Iterable[InventoryRecordEvidence]
    ) -> BatchEnrichmentResult:
        request = InventoryRecordEnrichmentRequest(records=list(records))
        requested = {record.record_id for record in request.records}
        system_prompt, user_prompt = build_prompts(ENRICHMENT_CAPABILITY, request)
        result = await self.provider_factory(self.configuration).complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        raw_profiles = result.content.get("profiles") if isinstance(result.content, dict) else None
        profiles: dict[str, InventorySemanticProfile] = {}
        unknown: list[str] = []
        if isinstance(raw_profiles, list):
            for raw in raw_profiles[:20]:
                try:
                    profile = InventorySemanticProfile.model_validate(raw)
                except (ValidationError, TypeError):
                    continue
                if profile.record_id not in requested:
                    unknown.append(profile.record_id)
                    continue
                profiles.setdefault(profile.record_id, profile)
        unresolved = tuple(sorted(requested - profiles.keys()))
        return BatchEnrichmentResult(profiles, unresolved, tuple(sorted(set(unknown))))


@dataclass(frozen=True)
class SemanticComparison:
    assessment: str
    reason_codes: tuple[str, ...]


def _norm(value: str | None) -> str:
    if not value or value.upper() == "UNKNOWN":
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _equivalent(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    left_tokens, right_tokens = set(left.split()), set(right.split())
    if not left_tokens or not right_tokens:
        return False
    overlap = left_tokens & right_tokens
    return bool(
        left_tokens <= right_tokens
        or right_tokens <= left_tokens
        or len(overlap) / len(left_tokens | right_tokens) >= 0.6
    )


def _meaningful_conflict(left: str, right: str) -> bool:
    if _equivalent(left, right):
        return False
    left_tokens, right_tokens = set(left.split()), set(right.split())
    return bool(left_tokens and right_tokens and not (left_tokens & right_tokens))


def compare_semantic_profiles(
    left: InventorySemanticProfile,
    right: InventorySemanticProfile,
) -> SemanticComparison:
    conflict_codes = {
        "product_type": "PRODUCT_TYPE_CONFLICT",
        "purpose": "PURPOSE_CONFLICT",
        "model": "MODEL_CONFLICT",
        "material": "MATERIAL_CONFLICT",
        "size_or_dimension": "SIZE_OR_RATING_CONFLICT",
        "rating": "SIZE_OR_RATING_CONFLICT",
        "side": "SIDE_OR_PLACEMENT_CONFLICT",
        "placement": "SIDE_OR_PLACEMENT_CONFLICT",
        "application": "APPLICATION_CONFLICT",
        "technical_role": "TECHNICAL_ROLE_CONFLICT",
    }
    conflicts = []
    matches = []
    for field in PROFILE_FIELDS:
        a, b = _norm(getattr(left, field)), _norm(getattr(right, field))
        if a and b:
            if _equivalent(a, b):
                matches.append(field)
            elif field in conflict_codes and _meaningful_conflict(a, b):
                conflicts.append(conflict_codes[field])
    if conflicts:
        return SemanticComparison("SUPPORTS_NON_DUPLICATE", tuple(dict.fromkeys(conflicts)))

    canonical_a, canonical_b = _norm(left.canonical_item), _norm(right.canonical_item)
    product_a, product_b = _norm(left.product_type), _norm(right.product_type)
    qualifiers_a = {_norm(item) for item in left.identity_qualifiers if _norm(item)}
    qualifiers_b = {_norm(item) for item in right.identity_qualifiers if _norm(item)}
    specific = bool(
        (canonical_a and _equivalent(canonical_a, canonical_b) and len(canonical_a) >= 4)
        or (product_a and _equivalent(product_a, product_b) and len(product_a) >= 4 and len(matches) >= 2)
    )
    if specific:
        codes = ["SEMANTIC_EQUIVALENCE"]
        if qualifiers_a and qualifiers_b and qualifiers_a == qualifiers_b:
            codes.append("ABBREVIATION_OR_ALIAS")
        return SemanticComparison("SUPPORTS_DUPLICATE", tuple(codes))
    return SemanticComparison("INCONCLUSIVE", ())


def enrichment_response_schema() -> dict:
    return InventoryRecordEnrichmentResponse.model_json_schema(mode="validation")
