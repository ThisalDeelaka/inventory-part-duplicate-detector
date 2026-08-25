"""GF-2 discovery-run lifecycle and proposal adapters.

This module records what discovery considered worth comparing. It deliberately
contains no duplicate status, identity confidence, human decision, or LLM data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.constants import MODEL_VERSION, SOURCE_ROW_INDEX_FIELD
from app.db.models import IdentityDiscoveryRun as IdentityDiscoveryRunRow
from app.db.models import IdentityNeighborProposal
from app.discovery.contracts import (
    ChannelProvenance,
    DiscoveryChannel,
    DiscoveryRunStatus,
    IdentityDiscoveryRun,
    NeighborProposal,
)
from app.engine.candidate_generator import MAX_CANDIDATE_PAIRS
from app.repositories.discovery_repository import DiscoveryRepository
from app.services.character_retrieval import character_retrieval_contract_payload
from app.services.lexical_retrieval import (
    lexical_strategy_contract_payload,
    select_lexical_strategy,
)


DISCOVERY_ALGORITHM_VERSION = "identity-discovery-v5-bounded-lexical-strategy"
DISCOVERY_CONFIGURATION_VERSION = "identity-discovery-config-v5"
NEIGHBOR_PROPOSAL_VERSION = "neighbor-proposal-v1"
_MAX_WARNING_CODES = 20
_MAX_CONTEXT_ITEMS = 20


@dataclass
class _ProposalAggregate:
    record_id_1: int
    record_id_2: int
    channel_values: dict[str, dict] = field(default_factory=dict)
    reciprocal_channels: set[str] = field(default_factory=set)
    priority: float = 0.0
    context: dict[str, object] = field(default_factory=dict)
    truncated: bool = False
    degraded: bool = False


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _configuration_payload(
    configuration, scan_mode: str, selected_fields: list[str], record_count: int
) -> dict:
    hybrid_enabled = bool(getattr(configuration, "hybrid_retrieval_enabled", True))
    payload = {
        "configuration_version": DISCOVERY_CONFIGURATION_VERSION,
        "scan_mode": scan_mode,
        "selected_fields": sorted(set(selected_fields)),
        "standard_pair_cap": MAX_CANDIDATE_PAIRS,
        "hybrid_enabled": hybrid_enabled,
        "neighborhood_max_members": int(
            getattr(configuration, "identity_neighborhood_max_members", 20)
        ),
    }
    if not hybrid_enabled:
        return payload

    def value(name, default):
        return getattr(configuration, name, default)

    payload.update({
        "hybrid_lexical_top_k": int(value("hybrid_retrieval_lexical_top_k", 5)),
        "lexical_retrieval": lexical_strategy_contract_payload(
            int(value("hybrid_retrieval_lexical_top_k", 5))
        ),
        "selected_lexical_strategy": select_lexical_strategy(record_count),
        "eligible_record_count": record_count,
        "hybrid_vector_top_k": int(value("hybrid_retrieval_vector_top_k", 5)),
        "hybrid_final_top_k": int(value("hybrid_retrieval_final_top_k", 10)),
        "hybrid_global_cap": int(value("hybrid_retrieval_max_pairs_per_scan", 500)),
        "hybrid_family_cap": int(value("hybrid_retrieval_family_max", 25)),
        "hybrid_tier_caps": {
            "TIER_A": int(value("hybrid_retrieval_tier_a_max", 250)),
            "TIER_B": int(value("hybrid_retrieval_tier_b_max", 200)),
            "TIER_C": int(value("hybrid_retrieval_tier_c_max", 50)),
        },
        "local_embedding_enabled": bool(value("local_embedding_enabled", True)),
        "local_embedding_model": str(value("local_embedding_model", "sklearn-hashing-domain-v1")),
    })
    if payload["local_embedding_enabled"]:
        payload["character_retrieval"] = character_retrieval_contract_payload(
            record_count, payload["hybrid_vector_top_k"]
        )
    return payload


def discovery_fingerprint(catalog_records, configuration, scan_mode, selected_fields) -> tuple[str, str]:
    config = _configuration_payload(
        configuration, scan_mode, selected_fields, len(catalog_records)
    )
    payload = {
        "algorithm_version": DISCOVERY_ALGORITHM_VERSION,
        "configuration": config,
        "records": [
            {
                "source_row_index": record.source_row_index,
                "source_record_fingerprint": record.source_record_fingerprint,
            }
            for record in sorted(catalog_records, key=lambda item: item.source_row_index)
        ],
    }
    return _sha256(payload), _canonical_json(config)


def _run_contract(row) -> IdentityDiscoveryRun:
    return IdentityDiscoveryRun(
        discovery_run_id=row.id,
        scan_id=row.scan_id,
        discovery_fingerprint=row.discovery_fingerprint,
        algorithm_version=row.algorithm_version,
        configuration_version=row.configuration_version,
        normalization_version=row.normalization_version,
        started_at=row.started_at,
        completed_at=row.completed_at,
        status=DiscoveryRunStatus(row.status),
        records_total=row.records_total,
        records_with_any_proposal=row.records_with_any_proposal,
        records_without_proposal=row.records_without_proposal,
        proposal_count=row.proposal_count,
        truncated_record_count=row.truncated_record_count,
        deferred_family_count=row.deferred_family_count,
        degraded=bool(row.degraded),
        warning_codes=tuple(json.loads(row.warning_codes_json or "[]")),
        provider_request_count=row.provider_request_count,
        safe_error_category=row.safe_error_category,
        neighborhood_count=row.neighborhood_count,
        records_in_at_least_one_neighborhood=row.records_in_at_least_one_neighborhood,
        records_with_proposals_but_no_neighborhood=(
            row.records_with_proposals_but_no_neighborhood
        ),
        truncated_neighborhood_count=row.truncated_neighborhood_count,
        max_candidate_neighbor_count=row.max_candidate_neighbor_count,
        max_included_member_count=row.max_included_member_count,
    )


def start_discovery_run(db, *, scan_id, catalog_records, configuration, scan_mode, selected_fields):
    fingerprint, configuration_json = discovery_fingerprint(
        catalog_records, configuration, scan_mode, selected_fields
    )
    repository = DiscoveryRepository(db)
    existing = repository.run_for_scan(scan_id)
    if existing is not None:
        if existing.discovery_fingerprint != fingerprint:
            raise ValueError("scan already has a discovery run for different inputs or configuration")
        if existing.status == DiscoveryRunStatus.FAILED.value:
            raise ValueError("failed primary discovery run is immutable; retry requires a new scan")
        return _run_contract(existing)
    row = repository.add_run(
        scan_id=scan_id,
        discovery_fingerprint=fingerprint,
        algorithm_version=DISCOVERY_ALGORITHM_VERSION,
        configuration_version=DISCOVERY_CONFIGURATION_VERSION,
        normalization_version=MODEL_VERSION,
        configuration_json=configuration_json,
        status=DiscoveryRunStatus.RUNNING.value,
        records_total=len(catalog_records),
        provider_request_count=0,
    )
    return _run_contract(row)


def _record_maps(catalog_records):
    by_source = {record.source_row_index: record for record in catalog_records}
    by_id = {record.record_id: record for record in catalog_records}
    if len(by_source) != len(catalog_records) or len(by_id) != len(catalog_records):
        raise ValueError("canonical catalog identities are not unique")
    return by_source, by_id


def _endpoint_id(record: dict, by_source) -> int:
    source_row_index = record.get(SOURCE_ROW_INDEX_FIELD)
    try:
        catalog = by_source[int(source_row_index)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("proposal endpoint is missing from the canonical scan catalog") from exc
    return catalog.record_id


def _aggregate(aggregates, left_id, right_id):
    if left_id == right_id:
        raise ValueError("a record cannot be proposed to itself")
    record_id_1, record_id_2 = sorted((left_id, right_id))
    return aggregates.setdefault(
        (record_id_1, record_id_2), _ProposalAggregate(record_id_1, record_id_2)
    )


def _add_channel(aggregate, channel, *, rank=None, score=None, reciprocal=False):
    channel = DiscoveryChannel(channel).value
    value = aggregate.channel_values.setdefault(
        channel, {"channel": channel, "rank": None, "score": None, "reciprocal": False}
    )
    if rank is not None:
        value["rank"] = rank if value["rank"] is None else min(value["rank"], rank)
    if score is not None:
        value["score"] = score if value["score"] is None else max(value["score"], score)
    value["reciprocal"] = bool(value["reciprocal"] or reciprocal)
    if reciprocal:
        aggregate.reciprocal_channels.add(channel)


def _standard_adapter(aggregates, standard_pairs, by_source):
    for rank, pair in enumerate(standard_pairs, 1):
        aggregate = _aggregate(
            aggregates,
            _endpoint_id(pair["record_a"], by_source),
            _endpoint_id(pair["record_b"], by_source),
        )
        _add_channel(aggregate, DiscoveryChannel.STANDARD_BLOCKING, rank=rank)
        aggregate.context["standard_matched_fields"] = sorted(set(pair.get("matched_fields", ())))[:20]
        aggregate.context["standard_mismatched_fields"] = sorted(set(pair.get("mismatched_fields", ())))[:20]


def _hybrid_adapter(aggregates, retrieval, engine_records, by_source):
    if retrieval is None:
        return
    for candidate in retrieval.candidates:
        left = engine_records[candidate.left_record_id]
        right = engine_records[candidate.right_record_id]
        aggregate = _aggregate(
            aggregates, _endpoint_id(left, by_source), _endpoint_id(right, by_source)
        )
        ranks = dict(candidate.evidence.channel_ranks)
        scores = dict(candidate.evidence.channel_scores)
        reciprocal = {
            value.removesuffix("_RECIPROCAL")
            for value in candidate.evidence.reciprocal_sources
        }
        for channel in candidate.evidence.retrieval_sources:
            _add_channel(
                aggregate,
                channel,
                rank=ranks.get(channel),
                score=scores.get(channel),
                reciprocal=channel in reciprocal,
            )
        aggregate.priority = max(aggregate.priority, candidate.retrieval_priority)
        aggregate.context.update({
            "retrieval_rank": candidate.retrieval_rank,
            "retrieval_tier": candidate.retrieval_tier.value,
            "blocking_signals": list(candidate.evidence.blocking_signals)[:20],
            "description_specificity_score": candidate.evidence.description_specificity_score,
            "generic_description_penalty": candidate.evidence.generic_description_penalty,
            "conflict_signals": list(candidate.evidence.conflict_signals)[:20],
            "uom_relationship": candidate.evidence.uom_relationship,
            "uom_evidence": candidate.evidence.uom_evidence,
            "uom_penalty": candidate.evidence.uom_penalty,
            "mapping_quality": candidate.evidence.mapping_quality,
            "embedding_model_version": retrieval.embedding_model_version,
        })


def persist_discovery_proposals(
    db, *, discovery_run_id, scan_id, catalog_records, standard_pairs,
    hybrid_result, engine_records
):
    repository = DiscoveryRepository(db)
    run = repository.run_for_scan(scan_id)
    if run is None or run.id != discovery_run_id:
        raise ValueError("discovery run does not belong to the scan")
    if run.status == DiscoveryRunStatus.COMPLETED.value:
        return load_discovery_run(db, discovery_run_id)
    if run.status != DiscoveryRunStatus.RUNNING.value:
        raise ValueError("only a running discovery run can be completed")
    if any(record.scan_id != scan_id for record in catalog_records):
        raise ValueError("proposal catalog contains a cross-scan record")
    by_source, by_id = _record_maps(catalog_records)
    aggregates = {}
    _standard_adapter(aggregates, standard_pairs, by_source)
    _hybrid_adapter(aggregates, hybrid_result, engine_records, by_source)

    warning_codes = set()
    standard_truncated = any(
        warning.get("warning_type") == "PAIR_LIMIT_REACHED"
        for pair in standard_pairs for warning in pair.get("warnings", ())
    )
    hybrid_truncated = bool(
        hybrid_result and hybrid_result.metrics.hybrid_candidates_skipped_by_cap
    )
    if standard_truncated:
        warning_codes.add("STANDARD_PAIR_CAP_REACHED")
    if hybrid_truncated:
        warning_codes.add("HYBRID_CAP_REACHED")

    ordered = sorted(
        aggregates.values(),
        key=lambda item: (-item.priority, item.record_id_1, item.record_id_2),
    )
    rows = []
    for order, aggregate in enumerate(ordered, 1):
        if aggregate.record_id_1 not in by_id or aggregate.record_id_2 not in by_id:
            raise ValueError("proposal endpoint is outside the canonical scan catalog")
        channels = sorted(aggregate.channel_values)
        provenance = [aggregate.channel_values[channel] for channel in channels]
        context = {
            key: aggregate.context[key]
            for key in sorted(aggregate.context)[:_MAX_CONTEXT_ITEMS]
        }
        proposal_key = _sha256({
            "version": NEIGHBOR_PROPOSAL_VERSION,
            "discovery_run_fingerprint": run.discovery_fingerprint,
            "record_ref_keys": sorted((
                by_id[aggregate.record_id_1].record_ref_key,
                by_id[aggregate.record_id_2].record_ref_key,
            )),
            "channels": provenance,
            "context": context,
        })
        rows.append(IdentityNeighborProposal(
            discovery_run_id=run.id,
            scan_id=scan_id,
            record_id_1=aggregate.record_id_1,
            record_id_2=aggregate.record_id_2,
            proposal_key=proposal_key,
            proposal_version=NEIGHBOR_PROPOSAL_VERSION,
            source_channels_json=_canonical_json(channels),
            channel_provenance_json=_canonical_json(provenance),
            reciprocal_channels_json=_canonical_json(sorted(aggregate.reciprocal_channels)),
            proposal_priority=round(aggregate.priority, 4),
            proposal_order=order,
            discovery_context_json=_canonical_json(context),
            truncated=aggregate.truncated,
            degraded=aggregate.degraded,
        ))
    repository.add_proposals(rows)
    covered = {
        record_id
        for aggregate in ordered
        for record_id in (aggregate.record_id_1, aggregate.record_id_2)
    }
    run.records_with_any_proposal = len(covered)
    run.records_without_proposal = run.records_total - len(covered)
    run.proposal_count = len(rows)
    # Current hybrid metrics report that a cap was reached, but do not identify
    # the exact lost endpoint set. GF-2 therefore keeps record-level truncation
    # nullable rather than fabricating precision.
    run.truncated_record_count = None if (standard_truncated or hybrid_truncated) else 0
    run.deferred_family_count = None
    run.degraded = bool(warning_codes)
    run.warning_codes_json = _canonical_json(sorted(warning_codes)[:_MAX_WARNING_CODES])
    db.flush()
    return _run_contract(run)


def mark_discovery_failed(db, discovery_run_id: int, error: Exception) -> None:
    row = db.get(IdentityDiscoveryRunRow, discovery_run_id)
    if row is None or row.status == DiscoveryRunStatus.COMPLETED.value:
        return
    safe_category = getattr(error, "safe_category", None)
    category = (
        re.sub(r"[^A-Z0-9_]+", "_", str(safe_category).upper())[:80]
        if safe_category
        else re.sub(r"[^A-Z0-9_]+", "_", type(error).__name__.upper())[:80]
    )
    row.status = DiscoveryRunStatus.FAILED.value
    row.safe_error_category = category or "DISCOVERY_FAILURE"
    row.completed_at = datetime.now(timezone.utc)
    row.records_with_any_proposal = 0
    row.records_without_proposal = row.records_total
    row.proposal_count = 0
    row.neighborhood_count = 0
    row.records_in_at_least_one_neighborhood = 0
    row.records_with_proposals_but_no_neighborhood = 0
    row.truncated_neighborhood_count = 0
    row.max_candidate_neighbor_count = 0
    row.max_included_member_count = 0
    db.flush()


def load_discovery_run(db, discovery_run_id: int) -> IdentityDiscoveryRun:
    row = db.get(IdentityDiscoveryRunRow, discovery_run_id)
    if row is None:
        raise ValueError("discovery run does not exist")
    return _run_contract(row)


def load_neighbor_proposals(db, discovery_run_id: int) -> tuple[NeighborProposal, ...]:
    rows = DiscoveryRepository(db).proposals_for_run(discovery_run_id)
    result = []
    for row in rows:
        provenance = tuple(
            ChannelProvenance(
                channel=DiscoveryChannel(item["channel"]),
                rank=item.get("rank"),
                score=item.get("score"),
                reciprocal=bool(item.get("reciprocal")),
            )
            for item in json.loads(row.channel_provenance_json)
        )
        context = json.loads(row.discovery_context_json)
        result.append(NeighborProposal(
            proposal_id=row.id,
            discovery_run_id=row.discovery_run_id,
            scan_id=row.scan_id,
            record_id_1=row.record_id_1,
            record_id_2=row.record_id_2,
            proposal_key=row.proposal_key,
            proposal_version=row.proposal_version,
            source_channels=tuple(
                DiscoveryChannel(value) for value in json.loads(row.source_channels_json)
            ),
            channel_provenance=provenance,
            reciprocal_channels=tuple(
                DiscoveryChannel(value) for value in json.loads(row.reciprocal_channels_json)
            ),
            proposal_priority=row.proposal_priority,
            proposal_order=row.proposal_order,
            discovery_context_json=_canonical_json(context),
            truncated=bool(row.truncated),
            degraded=bool(row.degraded),
        ))
    return tuple(result)
