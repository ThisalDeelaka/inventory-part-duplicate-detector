"""Deterministic blinded-pack generation for offline GF-12 human review."""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.benchmarks.contracts import canonical_json, stable_fingerprint
from app.benchmarks.human_review_protocol import (
    BlindedReviewRecord,
    DatasetClassification,
    HUMAN_REVIEW_PROTOCOL_VERSION,
    HumanReviewValidationError,
    REVIEW_PACK_VERSION,
    ReviewStratum,
    ValidationDatasetDescriptor,
    validate_blinded_record,
    validate_dataset_descriptor,
)


PILOT_SAMPLING_SEED = 1201
PREFERRED_REVIEW_UNIT_MIN = 2
PREFERRED_REVIEW_UNIT_MAX = 12

STRATUM_TARGETS = (
    (ReviewStratum.LIKELY_DUPLICATE_GROUP, 15),
    (ReviewStratum.POSSIBLE_DUPLICATE_GROUP_REVIEW, 15),
    (ReviewStratum.CONFLICT, 10),
    (ReviewStratum.DEFERRED, 10),
    (ReviewStratum.UNASSIGNED_CANDIDATE_NEIGHBORHOOD, 10),
)


class PilotEvidenceClassification(str, Enum):
    PILOT_EVIDENCE_ELIGIBLE = "PILOT_EVIDENCE_ELIGIBLE"
    SYNTHETIC_TEST_FIXTURE_ONLY = "SYNTHETIC_TEST_FIXTURE_ONLY"


@dataclass(frozen=True)
class PilotCandidateUnit:
    source_unit_reference: str
    stratum: ReviewStratum
    records: tuple[BlindedReviewRecord, ...]
    system_status: str
    system_grouping: tuple[tuple[str, ...], ...]
    internal_evidence: tuple[tuple[str, str | int | bool | None], ...] = ()


@dataclass(frozen=True)
class BlindedReviewUnit:
    review_unit_id: str
    records: tuple[BlindedReviewRecord, ...]
    size_classification: str


@dataclass(frozen=True)
class BlindedReviewPack:
    review_protocol_version: str
    review_pack_version: str
    dataset_id: str
    dataset_version: str
    dataset_fingerprint: str
    evidence_classification: PilotEvidenceClassification
    sampling_seed: int
    review_units: tuple[BlindedReviewUnit, ...]
    pack_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    def to_json(self, *, pretty: bool = True) -> str:
        return canonical_json(self, pretty=pretty)


@dataclass(frozen=True)
class PrivateEvaluationUnit:
    review_unit_id: str
    source_unit_reference: str
    source_record_refs: tuple[str, ...]
    system_status: str
    system_grouping: tuple[tuple[str, ...], ...]
    sampling_stratum: ReviewStratum
    internal_evidence: tuple[tuple[str, str | int | bool | None], ...]


@dataclass(frozen=True)
class PilotSamplingCount:
    stratum: ReviewStratum
    target_count: int
    available_count: int
    selected_count: int
    shortage_count: int


@dataclass(frozen=True)
class ExcludedReviewUnit:
    source_unit_reference: str
    record_count: int
    reason_code: str


@dataclass(frozen=True)
class PrivateEvaluationManifest:
    review_protocol_version: str
    review_pack_version: str
    dataset_id: str
    dataset_version: str
    dataset_fingerprint: str
    evidence_classification: PilotEvidenceClassification
    production_result_fingerprint: str
    sampling_seed: int
    review_units: tuple[PrivateEvaluationUnit, ...]
    sampling_counts: tuple[PilotSamplingCount, ...]
    exclusions: tuple[ExcludedReviewUnit, ...]
    blinded_pack_fingerprint: str
    manifest_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    def to_json(self, *, pretty: bool = True) -> str:
        return canonical_json(self, pretty=pretty)


@dataclass(frozen=True)
class PilotPackBuildResult:
    blinded_pack: BlindedReviewPack
    private_manifest: PrivateEvaluationManifest


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in sorted(value.items())}
    return value


def _review_unit_id(
    descriptor: ValidationDatasetDescriptor,
    refs: tuple[str, ...],
    production_result_fingerprint: str,
) -> str:
    digest = stable_fingerprint({
        "review_pack_version": REVIEW_PACK_VERSION,
        "dataset_id": descriptor.dataset_id,
        "dataset_version": descriptor.dataset_version,
        "dataset_fingerprint": descriptor.dataset_fingerprint,
        "production_result_fingerprint": production_result_fingerprint,
        "record_refs": refs,
    })
    return f"hru-{digest}"


def _selection_rank(review_unit_id: str, seed: int) -> str:
    return hashlib.sha256(
        canonical_json({
            "review_pack_version": REVIEW_PACK_VERSION,
            "sampling_seed": seed,
            "review_unit_id": review_unit_id,
        }).encode("utf-8")
    ).hexdigest()


def _validate_candidate(unit: PilotCandidateUnit) -> tuple[str, ...]:
    if not unit.source_unit_reference or len(unit.source_unit_reference) > 256:
        raise HumanReviewValidationError("SOURCE_REVIEW_UNIT_REFERENCE_INVALID")
    if unit.internal_evidence != tuple(sorted(unit.internal_evidence)):
        raise HumanReviewValidationError("INTERNAL_EVIDENCE_NOT_CANONICAL")
    refs = tuple(record.stable_record_reference for record in unit.records)
    for record in unit.records:
        validate_blinded_record(record)
    if len(refs) != len(set(refs)):
        raise HumanReviewValidationError("REVIEW_UNIT_RECORD_DUPLICATE")
    if refs != tuple(sorted(refs)):
        raise HumanReviewValidationError("REVIEW_UNIT_RECORDS_NOT_CANONICAL")
    assigned = []
    for group in unit.system_grouping:
        if len(group) < 2 or len(group) != len(set(group)):
            raise HumanReviewValidationError("SYSTEM_GROUPING_INVALID")
        if group != tuple(sorted(group)):
            raise HumanReviewValidationError("SYSTEM_GROUPING_NOT_CANONICAL")
        assigned.extend(group)
    if unit.system_grouping != tuple(sorted(unit.system_grouping)):
        raise HumanReviewValidationError("SYSTEM_PARTITION_NOT_CANONICAL")
    if any(reference not in set(refs) for reference in assigned):
        raise HumanReviewValidationError("SYSTEM_GROUPING_UNKNOWN_RECORD")
    if len(assigned) != len(set(assigned)):
        raise HumanReviewValidationError("SYSTEM_GROUPING_OVERLAP")
    return refs


def _build_pack(
    descriptor: ValidationDatasetDescriptor,
    *,
    production_result_fingerprint: str,
    candidate_units: tuple[PilotCandidateUnit, ...],
    seed: int,
    evidence_classification: PilotEvidenceClassification,
) -> PilotPackBuildResult:
    if seed != PILOT_SAMPLING_SEED:
        raise HumanReviewValidationError("PILOT_SAMPLING_SEED_INVALID")
    if not production_result_fingerprint or len(production_result_fingerprint) > 256:
        raise HumanReviewValidationError("PRODUCTION_RESULT_FINGERPRINT_INVALID")

    eligible: dict[ReviewStratum, list[tuple[str, PilotCandidateUnit]]] = {
        stratum: [] for stratum, _target in STRATUM_TARGETS
    }
    exclusions = []
    unit_ids = set()
    source_references = set()
    for unit in candidate_units:
        refs = _validate_candidate(unit)
        if unit.source_unit_reference in source_references:
            raise HumanReviewValidationError("SOURCE_REVIEW_UNIT_DUPLICATE")
        source_references.add(unit.source_unit_reference)
        if len(refs) < PREFERRED_REVIEW_UNIT_MIN:
            exclusions.append(ExcludedReviewUnit(
                unit.source_unit_reference, len(refs), "REVIEW_UNIT_BELOW_MINIMUM",
            ))
            continue
        if len(refs) > PREFERRED_REVIEW_UNIT_MAX:
            exclusions.append(ExcludedReviewUnit(
                unit.source_unit_reference, len(refs), "LARGE_REVIEW_UNIT_EXCLUDED",
            ))
            continue
        unit_id = _review_unit_id(descriptor, refs, production_result_fingerprint)
        if unit_id in unit_ids:
            raise HumanReviewValidationError("REVIEW_UNIT_ID_COLLISION")
        unit_ids.add(unit_id)
        eligible[unit.stratum].append((unit_id, unit))

    selected = []
    sampling_counts = []
    for stratum, target in STRATUM_TARGETS:
        available = sorted(
            eligible[stratum], key=lambda item: (_selection_rank(item[0], seed), item[0])
        )
        chosen = available[:target]
        selected.extend(chosen)
        sampling_counts.append(PilotSamplingCount(
            stratum=stratum,
            target_count=target,
            available_count=len(available),
            selected_count=len(chosen),
            shortage_count=max(0, target - len(chosen)),
        ))

    blinded_units = tuple(BlindedReviewUnit(
        review_unit_id=unit_id,
        records=unit.records,
        size_classification="STANDARD_REVIEW_UNIT",
    ) for unit_id, unit in selected)
    private_units = tuple(PrivateEvaluationUnit(
        review_unit_id=unit_id,
        source_unit_reference=unit.source_unit_reference,
        source_record_refs=tuple(record.stable_record_reference for record in unit.records),
        system_status=unit.system_status,
        system_grouping=unit.system_grouping,
        sampling_stratum=unit.stratum,
        internal_evidence=unit.internal_evidence,
    ) for unit_id, unit in selected)

    pack_payload = {
        "review_protocol_version": HUMAN_REVIEW_PROTOCOL_VERSION,
        "review_pack_version": REVIEW_PACK_VERSION,
        "dataset_id": descriptor.dataset_id,
        "dataset_version": descriptor.dataset_version,
        "dataset_fingerprint": descriptor.dataset_fingerprint,
        "evidence_classification": evidence_classification,
        "sampling_seed": seed,
        "review_units": blinded_units,
    }
    pack_fingerprint = stable_fingerprint(pack_payload)
    pack = BlindedReviewPack(**pack_payload, pack_fingerprint=pack_fingerprint)
    manifest_payload = {
        "review_protocol_version": HUMAN_REVIEW_PROTOCOL_VERSION,
        "review_pack_version": REVIEW_PACK_VERSION,
        "dataset_id": descriptor.dataset_id,
        "dataset_version": descriptor.dataset_version,
        "dataset_fingerprint": descriptor.dataset_fingerprint,
        "evidence_classification": evidence_classification,
        "production_result_fingerprint": production_result_fingerprint,
        "sampling_seed": seed,
        "review_units": private_units,
        "sampling_counts": tuple(sampling_counts),
        "exclusions": tuple(sorted(
            exclusions, key=lambda item: (item.source_unit_reference, item.reason_code)
        )),
        "blinded_pack_fingerprint": pack_fingerprint,
    }
    manifest = PrivateEvaluationManifest(
        **manifest_payload,
        manifest_fingerprint=stable_fingerprint(manifest_payload),
    )
    return PilotPackBuildResult(pack, manifest)


def build_blinded_review_pack(
    descriptor: ValidationDatasetDescriptor,
    *,
    production_result_fingerprint: str,
    candidate_units: tuple[PilotCandidateUnit, ...],
    seed: int = PILOT_SAMPLING_SEED,
) -> PilotPackBuildResult:
    """Build an evidence-eligible pack only after explicit dataset authorization."""

    validate_dataset_descriptor(descriptor)
    if descriptor.classification != DatasetClassification.AUTHORIZED_HUMAN_VALIDATION_DATASET:
        raise HumanReviewValidationError("HUMAN_REVIEW_DATASET_REQUIRED")
    return _build_pack(
        descriptor,
        production_result_fingerprint=production_result_fingerprint,
        candidate_units=candidate_units,
        seed=seed,
        evidence_classification=PilotEvidenceClassification.PILOT_EVIDENCE_ELIGIBLE,
    )


def build_synthetic_smoke_review_pack(
    descriptor: ValidationDatasetDescriptor,
    *,
    production_result_fingerprint: str,
    candidate_units: tuple[PilotCandidateUnit, ...],
    seed: int = PILOT_SAMPLING_SEED,
) -> PilotPackBuildResult:
    """Exercise the pipeline with fixtures that can never become human evidence."""

    validate_dataset_descriptor(descriptor)
    if descriptor.classification != DatasetClassification.SYNTHETIC_ONLY:
        raise HumanReviewValidationError("SYNTHETIC_FIXTURE_CLASSIFICATION_REQUIRED")
    return _build_pack(
        descriptor,
        production_result_fingerprint=production_result_fingerprint,
        candidate_units=candidate_units,
        seed=seed,
        evidence_classification=PilotEvidenceClassification.SYNTHETIC_TEST_FIXTURE_ONLY,
    )


def candidate_units_from_identity_snapshot(
    snapshot,
    *,
    records_by_reference: dict[str, BlindedReviewRecord],
    unassigned_candidate_neighborhoods: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> tuple[PilotCandidateUnit, ...]:
    """Adapt authoritative results without searching for or deciding new candidates."""

    units = []

    def records_for(refs: tuple[str, ...]) -> tuple[BlindedReviewRecord, ...]:
        if any(reference not in records_by_reference for reference in refs):
            raise HumanReviewValidationError("AUTHORITATIVE_UNIT_RECORD_MISSING")
        return tuple(records_by_reference[reference] for reference in sorted(refs))

    for group in snapshot.groups:
        refs = tuple(sorted(member.stable_record_reference for member in group.members))
        stratum = ReviewStratum(group.status.value)
        units.append(PilotCandidateUnit(
            source_unit_reference=group.versioned_group_key.group_reference,
            stratum=stratum,
            records=records_for(refs),
            system_status=group.status.value,
            system_grouping=(refs,),
            internal_evidence=(("source_group_fingerprint", group.source_group_fingerprint),),
        ))
    for conflict in snapshot.conflicts:
        refs = tuple(sorted(conflict.involved_record_references))
        units.append(PilotCandidateUnit(
            source_unit_reference=conflict.conflict_reference,
            stratum=ReviewStratum.CONFLICT,
            records=records_for(refs),
            system_status="CONFLICT",
            system_grouping=(),
            internal_evidence=(("source_conflict_fingerprint", conflict.source_conflict_fingerprint),),
        ))
    for deferred in snapshot.deferred_work_units:
        refs = tuple(sorted(deferred.record_references))
        units.append(PilotCandidateUnit(
            source_unit_reference=deferred.deferred_reference,
            stratum=ReviewStratum.DEFERRED,
            records=records_for(refs),
            system_status="DEFERRED",
            system_grouping=(),
            internal_evidence=(("source_deferred_fingerprint", deferred.source_deferred_fingerprint),),
        ))

    unassigned = {
        item.stable_record_reference for item in snapshot.unassigned_records
    }
    for neighborhood_reference, raw_refs in unassigned_candidate_neighborhoods:
        refs = tuple(sorted(raw_refs))
        if not set(refs) <= unassigned:
            raise HumanReviewValidationError("UNASSIGNED_NEIGHBORHOOD_SCOPE_INVALID")
        units.append(PilotCandidateUnit(
            source_unit_reference=neighborhood_reference,
            stratum=ReviewStratum.UNASSIGNED_CANDIDATE_NEIGHBORHOOD,
            records=records_for(refs),
            system_status="UNASSIGNED",
            system_grouping=(),
            internal_evidence=(("authoritative_neighborhood_reference", neighborhood_reference),),
        ))
    return tuple(units)
