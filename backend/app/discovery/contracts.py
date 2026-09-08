"""Immutable GF-2 discovery-only contracts.

Retrieval priority and proposal rank describe discovery ordering only. Neither
is identity confidence, duplicate probability, or a business decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DiscoveryRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DiscoveryChannel(str, Enum):
    STANDARD_BLOCKING = "STANDARD_BLOCKING"
    EXACT_DESCRIPTION = "EXACT_DESCRIPTION"
    PART_NUMBER_FAMILY = "PART_NUMBER_FAMILY"
    LEXICAL = "LEXICAL"
    CHAR_VECTOR = "CHAR_VECTOR"
    TECHNICAL_IDENTITY = "TECHNICAL_IDENTITY"


class NeighborhoodMemberRole(str, Enum):
    ANCHOR = "ANCHOR"
    DIRECT_NEIGHBOR = "DIRECT_NEIGHBOR"


@dataclass(frozen=True)
class ChannelProvenance:
    channel: DiscoveryChannel
    rank: int | None = None
    score: float | None = None
    reciprocal: bool = False


@dataclass(frozen=True)
class IdentityDiscoveryRun:
    discovery_run_id: int
    scan_id: int
    discovery_fingerprint: str
    algorithm_version: str
    configuration_version: str
    normalization_version: str
    started_at: datetime
    completed_at: datetime | None
    status: DiscoveryRunStatus
    records_total: int
    records_with_any_proposal: int
    records_without_proposal: int
    proposal_count: int
    truncated_record_count: int | None
    deferred_family_count: int | None
    degraded: bool
    warning_codes: tuple[str, ...]
    provider_request_count: int
    safe_error_category: str | None
    neighborhood_count: int
    records_in_at_least_one_neighborhood: int
    records_with_proposals_but_no_neighborhood: int
    truncated_neighborhood_count: int
    max_candidate_neighbor_count: int
    max_included_member_count: int


@dataclass(frozen=True)
class NeighborProposal:
    proposal_id: int
    discovery_run_id: int
    scan_id: int
    record_id_1: int
    record_id_2: int
    proposal_key: str
    proposal_version: str
    source_channels: tuple[DiscoveryChannel, ...]
    channel_provenance: tuple[ChannelProvenance, ...]
    reciprocal_channels: tuple[DiscoveryChannel, ...]
    proposal_priority: float
    proposal_order: int
    discovery_context_json: str
    truncated: bool
    degraded: bool


@dataclass(frozen=True)
class IdentityNeighborhood:
    neighborhood_id: int
    discovery_run_id: int
    scan_id: int
    anchor_record_id: int
    algorithm_version: str
    configuration_fingerprint: str
    max_members: int
    candidate_neighbor_count: int
    included_neighbor_count: int
    member_count: int
    is_truncated: bool
    degraded: bool
    warning_codes: tuple[str, ...]
    created_at: datetime
    neighborhood_fingerprint: str


@dataclass(frozen=True)
class IdentityNeighborhoodMember:
    member_id: int
    neighborhood_id: int
    scan_id: int
    record_id: int
    role: NeighborhoodMemberRole
    member_order: int
    source_proposal_id: int | None
    discovery_priority: float | None
    proposal_order: int | None
    source_channels: tuple[DiscoveryChannel, ...]
