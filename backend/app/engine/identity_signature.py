"""Pure R14 contracts for future identity signatures and signed evidence.

This module is intentionally unused by the production runtime.  It represents
record-local semantic observations and pair evidence without extracting,
classifying, scoring, persisting, or publishing them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, replace
from enum import Enum


IDENTITY_SIGNATURE_CONTRACT_VERSION = "identity-signature-contract-v1"
SIGNED_IDENTITY_EVIDENCE_CONTRACT_VERSION = (
    "signed-identity-evidence-contract-v1"
)


class IdentitySourceField(str, Enum):
    PART_NUMBER = "PART_NUMBER"
    DESCRIPTION = "DESCRIPTION"
    MASTER_DESCRIPTION = "MASTER_DESCRIPTION"
    TYPE_DESIGNATION = "TYPE_DESIGNATION"
    DIMENSION_QUALITY = "DIMENSION_QUALITY"
    OTHER_EXISTING_BOUNDED_SOURCE = "OTHER_EXISTING_BOUNDED_SOURCE"


class IdentitySemanticCategory(str, Enum):
    OBJECT_OR_CONSTRUCT = "OBJECT_OR_CONSTRUCT"
    ASSEMBLY_COMPONENT_ROLE = "ASSEMBLY_COMPONENT_ROLE"
    MODEL_TYPE_IDENTITY = "MODEL_TYPE_IDENTITY"
    VARIANT_IDENTITY = "VARIANT_IDENTITY"
    CRITICAL_IDENTITY_ATTRIBUTE = "CRITICAL_IDENTITY_ATTRIBUTE"


class IdentityObservationState(str, Enum):
    OBSERVED = "OBSERVED"
    UNKNOWN = "UNKNOWN"
    UNRESOLVED = "UNRESOLVED"


class SignedEvidenceChannel(str, Enum):
    IDENTITY_SUPPORT = "IDENTITY_SUPPORT"
    ATTRIBUTE_SUPPORT = "ATTRIBUTE_SUPPORT"
    LEXICAL_SUPPORT = "LEXICAL_SUPPORT"
    IDENTITY_CONTRADICTION = "IDENTITY_CONTRADICTION"


def _text(value: str) -> str:
    return str(value or "").strip()


def _canonical_tuple(values) -> tuple:
    return tuple(sorted(set(values), key=_sort_key))


def _canonical(value):
    if dataclasses.is_dataclass(value):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.name not in {"signature_fingerprint", "evidence_fingerprint"}
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list, set, frozenset)):
        normalized = [_canonical(item) for item in value]
        return sorted(normalized, key=_sort_key)
    return value


def _sort_key(value) -> str:
    return json.dumps(
        _canonical(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_identity_json(value) -> str:
    return json.dumps(
        _canonical(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _fingerprint(kind: str, version: str, value) -> str:
    material = {
        "contract_version": version,
        "kind": kind,
        "value": _canonical(value),
    }
    return hashlib.sha256(canonical_identity_json(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceObservation:
    source_field: IdentitySourceField
    normalized_evidence: tuple[str, ...]
    provenance_code: str

    def __post_init__(self):
        normalized = tuple(
            sorted({_text(item) for item in self.normalized_evidence if _text(item)})
        )
        object.__setattr__(self, "normalized_evidence", normalized)
        object.__setattr__(self, "provenance_code", _text(self.provenance_code))
        if not self.provenance_code:
            raise ValueError("source observation requires provenance_code")


@dataclass(frozen=True)
class IdentityObservation:
    semantic_category: IdentitySemanticCategory
    semantic_key: str
    normalized_value: str
    state: IdentityObservationState
    sources: tuple[SourceObservation, ...]
    reason_code: str

    def __post_init__(self):
        object.__setattr__(self, "semantic_key", _text(self.semantic_key))
        object.__setattr__(self, "normalized_value", _text(self.normalized_value))
        object.__setattr__(self, "sources", _canonical_tuple(self.sources))
        object.__setattr__(self, "reason_code", _text(self.reason_code))
        if not self.semantic_key or not self.reason_code:
            raise ValueError("identity observation requires semantic_key and reason_code")
        if self.state == IdentityObservationState.OBSERVED and (
            not self.normalized_value or not self.sources
        ):
            raise ValueError("observed identity fact requires value and source")
        if self.state == IdentityObservationState.UNKNOWN and self.normalized_value:
            raise ValueError("unknown identity fact cannot assert a normalized value")


def _validate_observations(
    observations: tuple[IdentityObservation, ...],
    category: IdentitySemanticCategory,
    *,
    state: IdentityObservationState | None = None,
) -> tuple[IdentityObservation, ...]:
    values = _canonical_tuple(observations)
    if any(item.semantic_category != category for item in values):
        raise ValueError(f"observation category must be {category.value}")
    if state is not None and any(item.state != state for item in values):
        raise ValueError(f"observation state must be {state.value}")
    return values


@dataclass(frozen=True)
class IdentitySignature:
    contract_version: str
    derivation_version: str
    record_reference: str
    object_construct_observations: tuple[IdentityObservation, ...]
    assembly_component_role_observations: tuple[IdentityObservation, ...]
    model_type_observations: tuple[IdentityObservation, ...]
    variant_observations: tuple[IdentityObservation, ...]
    critical_attribute_observations: tuple[IdentityObservation, ...]
    unresolved_observations: tuple[IdentityObservation, ...]
    unknown_categories: tuple[IdentitySemanticCategory, ...]
    signature_fingerprint: str = ""

    def __post_init__(self):
        if self.contract_version != IDENTITY_SIGNATURE_CONTRACT_VERSION:
            raise ValueError("unsupported identity-signature contract version")
        object.__setattr__(self, "derivation_version", _text(self.derivation_version))
        object.__setattr__(self, "record_reference", _text(self.record_reference))
        if not self.derivation_version or not self.record_reference:
            raise ValueError("identity signature requires derivation version and record reference")
        mappings = (
            ("object_construct_observations", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT),
            (
                "assembly_component_role_observations",
                IdentitySemanticCategory.ASSEMBLY_COMPONENT_ROLE,
            ),
            ("model_type_observations", IdentitySemanticCategory.MODEL_TYPE_IDENTITY),
            ("variant_observations", IdentitySemanticCategory.VARIANT_IDENTITY),
            (
                "critical_attribute_observations",
                IdentitySemanticCategory.CRITICAL_IDENTITY_ATTRIBUTE,
            ),
        )
        for field_name, category in mappings:
            object.__setattr__(
                self,
                field_name,
                _validate_observations(getattr(self, field_name), category),
            )
        unresolved = _canonical_tuple(self.unresolved_observations)
        if any(item.state != IdentityObservationState.UNRESOLVED for item in unresolved):
            raise ValueError("unresolved_observations must be explicitly UNRESOLVED")
        object.__setattr__(self, "unresolved_observations", unresolved)
        object.__setattr__(self, "unknown_categories", _canonical_tuple(self.unknown_categories))


@dataclass(frozen=True)
class SignedEvidenceFact:
    channel: SignedEvidenceChannel
    semantic_category: IdentitySemanticCategory
    semantic_key: str
    observed_fact: str
    source_observations_1: tuple[SourceObservation, ...]
    source_observations_2: tuple[SourceObservation, ...]
    normalized_matches: tuple[str, ...]
    reason_code: str

    def __post_init__(self):
        object.__setattr__(self, "semantic_key", _text(self.semantic_key))
        object.__setattr__(self, "observed_fact", _text(self.observed_fact))
        object.__setattr__(
            self, "source_observations_1", _canonical_tuple(self.source_observations_1)
        )
        object.__setattr__(
            self, "source_observations_2", _canonical_tuple(self.source_observations_2)
        )
        object.__setattr__(
            self,
            "normalized_matches",
            tuple(sorted({_text(item) for item in self.normalized_matches if _text(item)})),
        )
        object.__setattr__(self, "reason_code", _text(self.reason_code))
        if not self.semantic_key or not self.observed_fact or not self.reason_code:
            raise ValueError("signed evidence fact requires semantic key, fact, and reason")
        if not self.source_observations_1 or not self.source_observations_2:
            raise ValueError("signed evidence fact requires provenance for both records")
        if not self.normalized_matches:
            raise ValueError("signed evidence fact requires normalized matched evidence")


def _reverse_fact(fact: SignedEvidenceFact) -> SignedEvidenceFact:
    return replace(
        fact,
        source_observations_1=fact.source_observations_2,
        source_observations_2=fact.source_observations_1,
    )


@dataclass(frozen=True)
class SignedIdentityEvidence:
    contract_version: str
    record_reference_1: str
    record_reference_2: str
    signature_version_1: str
    signature_version_2: str
    signature_fingerprint_1: str
    signature_fingerprint_2: str
    facts: tuple[SignedEvidenceFact, ...]
    evidence_fingerprint: str = ""

    def __post_init__(self):
        if self.contract_version != SIGNED_IDENTITY_EVIDENCE_CONTRACT_VERSION:
            raise ValueError("unsupported signed-evidence contract version")
        fields = (
            "record_reference_1", "record_reference_2",
            "signature_version_1", "signature_version_2",
            "signature_fingerprint_1", "signature_fingerprint_2",
        )
        for field_name in fields:
            object.__setattr__(self, field_name, _text(getattr(self, field_name)))
        if any(not getattr(self, field_name) for field_name in fields):
            raise ValueError("signed evidence requires both signature identities")
        if self.record_reference_1 == self.record_reference_2:
            raise ValueError("signed evidence cannot describe a self pair")
        facts = self.facts
        if self.record_reference_2 < self.record_reference_1:
            values_1 = (
                self.record_reference_2,
                self.signature_version_2,
                self.signature_fingerprint_2,
            )
            values_2 = (
                self.record_reference_1,
                self.signature_version_1,
                self.signature_fingerprint_1,
            )
            object.__setattr__(self, "record_reference_1", values_1[0])
            object.__setattr__(self, "signature_version_1", values_1[1])
            object.__setattr__(self, "signature_fingerprint_1", values_1[2])
            object.__setattr__(self, "record_reference_2", values_2[0])
            object.__setattr__(self, "signature_version_2", values_2[1])
            object.__setattr__(self, "signature_fingerprint_2", values_2[2])
            facts = tuple(_reverse_fact(item) for item in facts)
        object.__setattr__(self, "facts", _canonical_tuple(facts))


def identity_signature_fingerprint(signature: IdentitySignature) -> str:
    return _fingerprint(
        "identity-signature", IDENTITY_SIGNATURE_CONTRACT_VERSION, signature
    )


def with_identity_signature_fingerprint(signature: IdentitySignature) -> IdentitySignature:
    return replace(
        signature,
        signature_fingerprint=identity_signature_fingerprint(signature),
    )


def signed_identity_evidence_fingerprint(evidence: SignedIdentityEvidence) -> str:
    return _fingerprint(
        "signed-identity-evidence",
        SIGNED_IDENTITY_EVIDENCE_CONTRACT_VERSION,
        evidence,
    )


def with_signed_identity_evidence_fingerprint(
    evidence: SignedIdentityEvidence,
) -> SignedIdentityEvidence:
    return replace(
        evidence,
        evidence_fingerprint=signed_identity_evidence_fingerprint(evidence),
    )
