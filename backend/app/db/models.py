from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import relationship

from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class DuplicateScan(Base):
    __tablename__ = "duplicate_scan"
    id = Column(Integer, primary_key=True)
    scan_name = Column(String(200), nullable=False)
    source_type = Column(String(30), default="CSV", nullable=False)
    selected_fields = Column(Text, default="[]", nullable=False)
    threshold = Column(Float, nullable=False)
    status = Column(String(30), default="RUNNING", nullable=False)
    total_records = Column(Integer, default=0)
    total_candidates = Column(Integer, default=0)
    warnings_count = Column(Integer, default=0)
    rejections_count = Column(Integer, default=0)
    scan_mode = Column(String(60), default="SAME_SITE_DUPLICATE", nullable=False)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True))
    model_version = Column(String(50), nullable=False)
    candidates = relationship("DuplicateCandidate", cascade="all, delete-orphan")
    warnings = relationship("ScanWarning", cascade="all, delete-orphan")
    rejections = relationship("RuleExclusionAudit", cascade="all, delete-orphan")
    llm_triage_run = relationship(
        "LlmTriageRun", cascade="all, delete-orphan", uselist=False
    )


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidate"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    contract_a = Column(String(100))
    source_row_index_a = Column(Integer)
    part_no_a = Column(String(200), nullable=False)
    description_a = Column(Text, nullable=False)
    contract_b = Column(String(100))
    source_row_index_b = Column(Integer)
    part_no_b = Column(String(200), nullable=False)
    description_b = Column(Text, nullable=False)
    similarity_score = Column(Float, nullable=False)
    confidence_level = Column(String(20), nullable=False)
    description_similarity = Column(Float, nullable=False)
    tfidf_score = Column(Float, nullable=False)
    fuzzy_score = Column(Float, nullable=False)
    part_no_similarity = Column(Float, nullable=False)
    technical_token_score = Column(Float, nullable=False)
    matched_fields = Column(Text, default="[]")
    mismatched_fields = Column(Text, default="[]")
    explanation = Column(Text, nullable=False)
    recommended_action = Column(String(200), nullable=False)
    business_status = Column(String(80), default="POSSIBLE_DUPLICATE_REVIEW", nullable=False)
    rule_decision = Column(String(50), default="ALLOW", nullable=False)
    rejection_reason = Column(String(120), default="")
    scan_mode = Column(String(60), default="SAME_SITE_DUPLICATE", nullable=False)
    critical_mismatches = Column(Text, default="[]")
    variant_attributes_a = Column(Text, default="{}")
    variant_attributes_b = Column(Text, default="{}")
    generic_description_warning = Column(String(10), default="false")
    application_context_a = Column(Text, default="[]")
    application_context_b = Column(Text, default="[]")
    application_context_warning = Column(String(10), default="false")
    normalized_description_a = Column(Text, default="")
    normalized_description_b = Column(Text, default="")
    normalized_part_no_a = Column(Text, default="")
    normalized_part_no_b = Column(Text, default="")
    review_status = Column(String(30), default="UNREVIEWED", nullable=False)
    reviewed_by = Column(String(100))
    reviewed_at = Column(DateTime(timezone=True))
    feedback = relationship("DuplicateFeedback", cascade="all, delete-orphan")
    llm_advisory_snapshots = relationship("LlmAdvisorySnapshot", cascade="all, delete-orphan")


class LlmAdvisorySnapshot(Base):
    __tablename__ = "llm_advisory_snapshot"
    __table_args__ = (
        UniqueConstraint("candidate_id", "capability", name="uq_llm_snapshot_candidate_capability"),
    )

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("duplicate_candidate.id"), nullable=False, index=True)
    capability = Column(String(50), nullable=False)
    state = Column(String(30), nullable=False)
    llm_used = Column(Boolean, nullable=False, default=False)
    cache_hit = Column(Boolean, nullable=False, default=False)
    provider = Column(String(100))
    model = Column(String(200))
    prompt_version = Column(String(100))
    assessment = Column(String(50))
    confidence = Column(Float)
    recommended_action = Column(String(80))
    supporting_evidence = Column(Text)
    conflicting_evidence = Column(Text)
    bypass_reason = Column(String(200))
    safe_error_category = Column(String(80))
    deterministic_result_authoritative = Column(Boolean, nullable=False, default=True)
    generated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class LlmTriageRun(Base):
    __tablename__ = "llm_triage_run"

    id = Column(Integer, primary_key=True)
    scan_id = Column(
        Integer, ForeignKey("duplicate_scan.id"), nullable=False, unique=True, index=True
    )
    state = Column(String(40), nullable=False, default="QUEUED")
    total_eligible = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)
    likely_duplicate_count = Column(Integer, nullable=False, default=0)
    downgraded_count = Column(Integer, nullable=False, default=0)
    human_review_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_safe_error_category = Column(String(80))


class LlmSemanticProfile(Base):
    __tablename__ = "llm_semantic_profile"
    __table_args__ = (
        UniqueConstraint(
            "evidence_fingerprint", "model", "prompt_version",
            name="uq_llm_semantic_profile_identity",
        ),
    )

    id = Column(Integer, primary_key=True)
    evidence_fingerprint = Column(String(64), nullable=False, index=True)
    model = Column(String(200), nullable=False)
    prompt_version = Column(String(100), nullable=False)
    profile_json = Column(Text)
    state = Column(String(30), nullable=False, default="PENDING")
    safe_error_category = Column(String(80))
    generated_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CandidateDiscoveryMetadata(Base):
    __tablename__ = "candidate_discovery_metadata"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_candidate_discovery_candidate"),
    )

    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("duplicate_candidate.id"), nullable=False, index=True)
    source = Column(String(60), nullable=False, default="DETERMINISTIC_STANDARD")
    rescue_score = Column(Float)
    rank = Column(Integer)
    signals_json = Column(Text, default="[]", nullable=False)
    resolution_source = Column(String(60))
    retrieval_sources_json = Column(Text, default="[]", nullable=False)
    retrieval_score = Column(Float)
    retrieval_priority = Column(Float)
    retrieval_tier = Column(String(20))
    lexical_score = Column(Float)
    vector_score = Column(Float)
    description_specificity_score = Column(Float)
    generic_description_penalty = Column(Float)
    retrieval_conflict_signals_json = Column(Text, default="[]", nullable=False)
    reciprocal_sources_json = Column(Text, default="[]", nullable=False)
    uom_relationship = Column(String(50))
    uom_evidence = Column(String(80))
    uom_penalty = Column(Float)
    mapping_quality = Column(String(40))
    retrieval_rank = Column(Integer)
    embedding_model_version = Column(String(200))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class RecallRescuePair(Base):
    __tablename__ = "llm_recall_rescue_pair"
    __table_args__ = (
        UniqueConstraint("scan_id", "left_fingerprint", "right_fingerprint", name="uq_recall_pair"),
    )

    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    left_fingerprint = Column(String(64), nullable=False)
    right_fingerprint = Column(String(64), nullable=False)
    left_evidence_json = Column(Text, nullable=False)
    right_evidence_json = Column(Text, nullable=False)
    rescue_score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)
    signals_json = Column(Text, default="[]", nullable=False)
    state = Column(String(30), nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class LlmEnhancementRun(Base):
    __tablename__ = "llm_enhancement_run"

    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, unique=True, index=True)
    unique_records_total = Column(Integer, nullable=False, default=0)
    profiles_cached = Column(Integer, nullable=False, default=0)
    profiles_requested = Column(Integer, nullable=False, default=0)
    profiles_available = Column(Integer, nullable=False, default=0)
    profiles_failed = Column(Integer, nullable=False, default=0)
    enrichment_batches_sent = Column(Integer, nullable=False, default=0)
    provider_request_count = Column(Integer, nullable=False, default=0)
    enrichment_records_sent = Column(Integer, nullable=False, default=0)
    locally_resolved_count = Column(Integer, nullable=False, default=0)
    pairwise_fallback_count = Column(Integer, nullable=False, default=0)
    standard_candidate_count = Column(Integer, nullable=False, default=0)
    rescue_pool_considered_count = Column(Integer, nullable=False, default=0)
    rescue_candidate_count = Column(Integer, nullable=False, default=0)
    rescue_likely_duplicate_count = Column(Integer, nullable=False, default=0)
    rescue_human_review_count = Column(Integer, nullable=False, default=0)
    rescue_failed_count = Column(Integer, nullable=False, default=0)
    rescue_skipped_by_cap_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class LocalEmbeddingCache(Base):
    __tablename__ = "local_embedding_cache"
    __table_args__ = (
        UniqueConstraint("record_fingerprint", "embedding_model_version", name="uq_local_embedding_identity"),
    )
    id = Column(Integer, primary_key=True)
    record_fingerprint = Column(String(64), nullable=False, index=True)
    embedding_model_version = Column(String(200), nullable=False)
    vector_json = Column(Text)
    state = Column(String(30), nullable=False, default="AVAILABLE")
    generated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class HybridRetrievalRun(Base):
    __tablename__ = "hybrid_retrieval_run"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, unique=True, index=True)
    records_indexed = Column(Integer, nullable=False, default=0)
    lexical_candidates_generated = Column(Integer, nullable=False, default=0)
    vector_candidates_generated = Column(Integer, nullable=False, default=0)
    exact_description_candidates = Column(Integer, nullable=False, default=0)
    part_family_candidates = Column(Integer, nullable=False, default=0)
    technical_identity_candidates = Column(Integer, nullable=False, default=0)
    reciprocal_candidates = Column(Integer, nullable=False, default=0)
    generic_penalized_candidates = Column(Integer, nullable=False, default=0)
    conflict_penalized_candidates = Column(Integer, nullable=False, default=0)
    uom_same_pairs_considered = Column(Integer)
    uom_convertible_pairs_considered = Column(Integer)
    uom_different_basis_pairs_considered = Column(Integer)
    uom_missing_or_wildcard_pairs_considered = Column(Integer)
    uom_malformed_or_unknown_pairs_considered = Column(Integer)
    multi_source_candidates = Column(Integer, nullable=False, default=0)
    tier_a_candidates = Column(Integer, nullable=False, default=0)
    tier_b_candidates = Column(Integer, nullable=False, default=0)
    tier_c_candidates = Column(Integer, nullable=False, default=0)
    hybrid_candidates_added = Column(Integer, nullable=False, default=0)
    hybrid_candidates_added_with_uom_difference = Column(Integer)
    hybrid_candidates_added_with_uom_unknown = Column(Integer)
    hybrid_post_scoring_excluded_count = Column(Integer)
    hybrid_post_scoring_exclusion_reasons_json = Column(Text)
    hybrid_candidates_skipped_by_cap = Column(Integer, nullable=False, default=0)
    average_candidates_per_record = Column(Float, nullable=False, default=0)
    max_candidates_for_any_record = Column(Integer, nullable=False, default=0)
    largest_description_family_candidates = Column(Integer, nullable=False, default=0)
    candidate_family_concentration = Column(Float, nullable=False, default=0)
    retrieval_runtime_ms = Column(Float, nullable=False, default=0)
    embedding_model_version = Column(String(200), nullable=False)
    provider_request_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class IdentityDiscoveryRun(Base):
    __tablename__ = "identity_discovery_run"
    __table_args__ = (
        UniqueConstraint("scan_id", name="uq_identity_discovery_scan"),
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_identity_discovery_status",
        ),
        CheckConstraint(
            "provider_request_count = 0", name="ck_identity_discovery_provider_zero"
        ),
    )

    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    discovery_fingerprint = Column(String(64), nullable=False, index=True)
    algorithm_version = Column(String(80), nullable=False)
    configuration_version = Column(String(80), nullable=False)
    normalization_version = Column(String(80), nullable=False)
    configuration_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="RUNNING", index=True)
    records_total = Column(Integer, nullable=False, default=0)
    records_with_any_proposal = Column(Integer, nullable=False, default=0)
    records_without_proposal = Column(Integer, nullable=False, default=0)
    proposal_count = Column(Integer, nullable=False, default=0)
    truncated_record_count = Column(Integer)
    deferred_family_count = Column(Integer)
    degraded = Column(Boolean, nullable=False, default=False)
    warning_codes_json = Column(Text, nullable=False, default="[]")
    provider_request_count = Column(Integer, nullable=False, default=0)
    safe_error_category = Column(String(80))
    neighborhood_count = Column(Integer, nullable=False, default=0)
    records_in_at_least_one_neighborhood = Column(Integer, nullable=False, default=0)
    records_with_proposals_but_no_neighborhood = Column(Integer, nullable=False, default=0)
    truncated_neighborhood_count = Column(Integer, nullable=False, default=0)
    max_candidate_neighbor_count = Column(Integer, nullable=False, default=0)
    max_included_member_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True))


class IdentityNeighborProposal(Base):
    __tablename__ = "identity_neighbor_proposal"
    __table_args__ = (
        UniqueConstraint(
            "discovery_run_id", "record_id_1", "record_id_2",
            name="uq_identity_neighbor_run_pair",
        ),
        UniqueConstraint(
            "discovery_run_id", "proposal_key", name="uq_identity_neighbor_run_key"
        ),
        CheckConstraint("record_id_1 < record_id_2", name="ck_identity_neighbor_order"),
        Index("ix_identity_neighbor_scan_endpoints", "scan_id", "record_id_1", "record_id_2"),
    )

    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(
        Integer, ForeignKey("identity_discovery_run.id"), nullable=False, index=True
    )
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    record_id_1 = Column(
        Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True
    )
    record_id_2 = Column(
        Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True
    )
    proposal_key = Column(String(64), nullable=False)
    proposal_version = Column(String(80), nullable=False)
    source_channels_json = Column(Text, nullable=False)
    channel_provenance_json = Column(Text, nullable=False)
    reciprocal_channels_json = Column(Text, nullable=False, default="[]")
    proposal_priority = Column(Float, nullable=False, default=0)
    proposal_order = Column(Integer, nullable=False)
    discovery_context_json = Column(Text, nullable=False, default="{}")
    truncated = Column(Boolean, nullable=False, default=False)
    degraded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityNeighborhoodSnapshot(Base):
    __tablename__ = "identity_neighborhood_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "discovery_run_id", "anchor_record_id", "algorithm_version",
            "configuration_fingerprint", name="uq_identity_neighborhood_anchor",
        ),
        UniqueConstraint(
            "discovery_run_id", "neighborhood_fingerprint",
            name="uq_identity_neighborhood_fingerprint",
        ),
        CheckConstraint("member_count >= 2", name="ck_identity_neighborhood_min_members"),
        CheckConstraint("max_members >= 2", name="ck_identity_neighborhood_max_members"),
        CheckConstraint(
            "member_count <= max_members", name="ck_identity_neighborhood_bounded"
        ),
        CheckConstraint(
            "candidate_neighbor_count >= included_neighbor_count",
            name="ck_identity_neighborhood_candidate_count",
        ),
        CheckConstraint(
            "member_count = included_neighbor_count + 1",
            name="ck_identity_neighborhood_member_count",
        ),
        Index("ix_identity_neighborhood_scan_anchor", "scan_id", "anchor_record_id"),
    )

    id = Column(Integer, primary_key=True)
    discovery_run_id = Column(
        Integer, ForeignKey("identity_discovery_run.id"), nullable=False, index=True
    )
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    anchor_record_id = Column(
        Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True
    )
    algorithm_version = Column(String(80), nullable=False)
    configuration_fingerprint = Column(String(64), nullable=False)
    max_members = Column(Integer, nullable=False)
    candidate_neighbor_count = Column(Integer, nullable=False)
    included_neighbor_count = Column(Integer, nullable=False)
    member_count = Column(Integer, nullable=False)
    is_truncated = Column(Boolean, nullable=False, default=False, index=True)
    degraded = Column(Boolean, nullable=False, default=False)
    warning_codes_json = Column(Text, nullable=False, default="[]")
    neighborhood_fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityNeighborhoodMember(Base):
    __tablename__ = "identity_neighborhood_member"
    __table_args__ = (
        UniqueConstraint(
            "neighborhood_id", "record_id", name="uq_identity_neighborhood_member"
        ),
        UniqueConstraint(
            "neighborhood_id", "member_order", name="uq_identity_neighborhood_order"
        ),
        CheckConstraint(
            "role IN ('ANCHOR', 'DIRECT_NEIGHBOR')",
            name="ck_identity_neighborhood_member_role",
        ),
        CheckConstraint("member_order >= 0", name="ck_identity_neighborhood_member_order"),
        CheckConstraint(
            "(role = 'ANCHOR' AND source_proposal_id IS NULL) OR "
            "(role = 'DIRECT_NEIGHBOR' AND source_proposal_id IS NOT NULL)",
            name="ck_identity_neighborhood_member_source",
        ),
        Index("ix_identity_neighborhood_member_scan_record", "scan_id", "record_id"),
    )

    id = Column(Integer, primary_key=True)
    neighborhood_id = Column(
        Integer, ForeignKey("identity_neighborhood_snapshot.id"), nullable=False, index=True
    )
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    record_id = Column(
        Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True
    )
    role = Column(String(30), nullable=False)
    member_order = Column(Integer, nullable=False)
    source_proposal_id = Column(
        Integer, ForeignKey("identity_neighbor_proposal.id"), index=True
    )
    discovery_priority = Column(Float)
    proposal_order = Column(Integer)
    source_channels_json = Column(Text, nullable=False, default="[]")


class DuplicateFeedback(Base):
    __tablename__ = "duplicate_feedback"
    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("duplicate_candidate.id"), nullable=False, index=True)
    user_decision = Column(String(30), nullable=False)
    user_comment = Column(Text)
    created_by = Column(String(100), default="demo-reviewer", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScanWarning(Base):
    __tablename__ = "scan_warning"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    warning_type = Column(String(80), nullable=False)
    message = Column(Text, nullable=False)
    record_reference = Column(String(200))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class RuleExclusionAudit(Base):
    __tablename__ = "rule_exclusion_audit"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    contract_a = Column(String(100))
    source_row_index_a = Column(Integer)
    part_no_a = Column(String(200), nullable=False)
    description_a = Column(Text, nullable=False)
    contract_b = Column(String(100))
    source_row_index_b = Column(Integer)
    part_no_b = Column(String(200), nullable=False)
    description_b = Column(Text, nullable=False)
    similarity_score = Column(Float, nullable=False)
    confidence_level = Column(String(20), nullable=False)
    business_status = Column(String(80), nullable=False)
    rule_decision = Column(String(50), nullable=False)
    rejection_reason = Column(String(120), nullable=False)
    critical_mismatches = Column(Text, default="[]")
    explanation = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityGroupProjectionRun(Base):
    __tablename__ = "identity_group_projection_run"
    __table_args__ = (
        UniqueConstraint(
            "scan_id", "algorithm_version", "evidence_fingerprint",
            name="uq_identity_projection_evidence",
        ),
        CheckConstraint("status IN ('COMPLETED', 'FAILED')", name="ck_identity_projection_status"),
    )
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    algorithm_version = Column(String(80), nullable=False)
    edge_classifier_version = Column(String(80), nullable=False)
    evidence_fingerprint = Column(String(64), nullable=False)
    max_group_validation_members = Column(Integer, nullable=False)
    engine_version = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="COMPLETED")
    records_seen = Column(Integer, nullable=False)
    seed_edges = Column(Integer, nullable=False)
    provisional_components = Column(Integer, nullable=False)
    accepted_groups = Column(Integer, nullable=False)
    likely_groups = Column(Integer, nullable=False)
    review_groups = Column(Integer, nullable=False)
    conflicting_families = Column(Integer, nullable=False)
    oversized_families = Column(Integer, nullable=False)
    ambiguous_families = Column(Integer, nullable=False, default=0)
    internal_pairs_total = Column(Integer, nullable=False)
    internal_pairs_reused = Column(Integer, nullable=False)
    internal_pairs_rescored = Column(Integer, nullable=False)
    cannot_links_found = Column(Integer, nullable=False)
    max_component_size = Column(Integer, nullable=False)
    max_accepted_group_size = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ScanRecordSnapshot(Base):
    __tablename__ = "scan_record_snapshot"
    __table_args__ = (
        UniqueConstraint("scan_id", "record_ref_key", name="uq_scan_record_ref"),
        UniqueConstraint("scan_id", "source_row_index", name="uq_scan_record_source_row"),
    )
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    record_ref_key = Column(String(64), nullable=False)
    source_row_index = Column(Integer)
    source_record_fingerprint = Column(String(64))
    contract = Column(String(100))
    part_no = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    normalized_part_no = Column(Text, nullable=False, default="")
    normalized_description = Column(Text, nullable=False, default="")
    uom = Column(String(128))
    type_code = Column(String(128))
    prime_commodity = Column(String(128))
    second_commodity = Column(String(128))
    accounting_group = Column(String(128))
    part_product_code = Column(String(128))
    part_product_family = Column(String(128))
    product_category_id = Column(String(128))
    hsn_sac_code = Column(String(128))
    hazard_code = Column(String(128))
    normalization_version = Column(String(80))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityGroupSnapshot(Base):
    __tablename__ = "identity_group_snapshot"
    __table_args__ = (
        UniqueConstraint("projection_run_id", "hypothesis_key", name="uq_group_run_hypothesis"),
        CheckConstraint(
            "group_status IN ('LIKELY_DUPLICATE_GROUP', 'POSSIBLE_DUPLICATE_GROUP_REVIEW')",
            name="ck_group_snapshot_status",
        ),
        CheckConstraint("group_size >= 2", name="ck_group_snapshot_min_size"),
    )
    id = Column(Integer, primary_key=True)
    projection_run_id = Column(Integer, ForeignKey("identity_group_projection_run.id"), nullable=False, index=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    hypothesis_key = Column(String(64), nullable=False, index=True)
    projection_algorithm_version = Column(String(80), nullable=False)
    group_status = Column(String(60), nullable=False, index=True)
    group_size = Column(Integer, nullable=False)
    supporting_edge_count = Column(Integer, nullable=False)
    review_edge_count = Column(Integer, nullable=False)
    non_groupable_internal_count = Column(Integer, nullable=False)
    internal_pair_count = Column(Integer, nullable=False)
    internal_pairs_reused = Column(Integer, nullable=False)
    internal_pairs_rescored = Column(Integer, nullable=False)
    evidence_completeness = Column(Float, nullable=False)
    distinct_uoms_json = Column(Text, nullable=False, default="[]")
    same_uom_pair_count = Column(Integer, nullable=False)
    convertible_uom_pair_count = Column(Integer, nullable=False)
    different_basis_pair_count = Column(Integer, nullable=False)
    missing_or_wildcard_pair_count = Column(Integer, nullable=False)
    malformed_or_unknown_pair_count = Column(Integer, nullable=False)
    possible_mapping_error_count = Column(Integer, nullable=False)
    reason_codes_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityGroupMemberSnapshot(Base):
    __tablename__ = "identity_group_member_snapshot"
    __table_args__ = (
        UniqueConstraint("group_snapshot_id", "record_snapshot_id", name="uq_group_member_record"),
        UniqueConstraint("group_snapshot_id", "member_index", name="uq_group_member_index"),
        CheckConstraint("member_index >= 0", name="ck_group_member_index_nonnegative"),
    )
    id = Column(Integer, primary_key=True)
    group_snapshot_id = Column(Integer, ForeignKey("identity_group_snapshot.id"), nullable=False, index=True)
    record_snapshot_id = Column(Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True)
    member_index = Column(Integer, nullable=False)
    record_ref_key = Column(String(64), nullable=False)


class IdentityFamilyDiagnosticSnapshot(Base):
    __tablename__ = "identity_family_diagnostic_snapshot"
    __table_args__ = (
        UniqueConstraint("projection_run_id", "diagnostic_key", name="uq_family_run_key"),
        CheckConstraint(
            "diagnostic_status IN ('CONFLICTING_FAMILY', 'DEFERRED_OVERSIZED_FAMILY', "
            "'DEFERRED_AMBIGUOUS_RECORD_FAMILY')",
            name="ck_family_diagnostic_status",
        ),
    )
    id = Column(Integer, primary_key=True)
    projection_run_id = Column(Integer, ForeignKey("identity_group_projection_run.id"), nullable=False, index=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    diagnostic_key = Column(String(64), nullable=False)
    diagnostic_status = Column(String(60), nullable=False, index=True)
    member_count = Column(Integer, nullable=False)
    seed_edge_count = Column(Integer, nullable=False)
    internal_pair_count = Column(Integer, nullable=False, default=0)
    internal_pairs_reused = Column(Integer, nullable=False, default=0)
    internal_pairs_rescored = Column(Integer, nullable=False, default=0)
    cannot_link_count = Column(Integer, nullable=False, default=0)
    reason_codes_json = Column(Text, nullable=False, default="[]")
    projection_algorithm_version = Column(String(80), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityFamilyDiagnosticMemberSnapshot(Base):
    __tablename__ = "identity_family_diagnostic_member_snapshot"
    __table_args__ = (
        UniqueConstraint("diagnostic_snapshot_id", "record_snapshot_id", name="uq_family_member_record"),
        UniqueConstraint("diagnostic_snapshot_id", "member_index", name="uq_family_member_index"),
        CheckConstraint("member_index >= 0", name="ck_family_member_index_nonnegative"),
    )
    id = Column(Integer, primary_key=True)
    diagnostic_snapshot_id = Column(Integer, ForeignKey("identity_family_diagnostic_snapshot.id"), nullable=False, index=True)
    record_snapshot_id = Column(Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True)
    member_index = Column(Integer, nullable=False)
    record_ref_key = Column(String(64), nullable=False)


class IdentityGroupEdgeSnapshot(Base):
    __tablename__ = "identity_group_edge_snapshot"
    __table_args__ = (
        CheckConstraint(
            "(group_snapshot_id IS NOT NULL AND diagnostic_snapshot_id IS NULL) OR "
            "(group_snapshot_id IS NULL AND diagnostic_snapshot_id IS NOT NULL)",
            name="ck_edge_one_snapshot_owner",
        ),
        CheckConstraint("left_record_snapshot_id < right_record_snapshot_id", name="ck_edge_record_order"),
        CheckConstraint(
            "edge_class IN ('STRONG_SUPPORT', 'REVIEW_SUPPORT', 'CANNOT_LINK', 'NON_GROUPABLE')",
            name="ck_snapshot_edge_class",
        ),
        CheckConstraint(
            "evidence_source IN ('PERSISTED_CANDIDATE', 'PERSISTED_EXCLUSION', "
            "'HUMAN_FEEDBACK', 'G1_LOCAL_RESCORING')",
            name="ck_snapshot_edge_source",
        ),
        UniqueConstraint(
            "group_snapshot_id", "left_record_snapshot_id", "right_record_snapshot_id",
            name="uq_group_internal_edge",
        ),
        UniqueConstraint(
            "diagnostic_snapshot_id", "left_record_snapshot_id", "right_record_snapshot_id",
            name="uq_family_internal_edge",
        ),
    )
    id = Column(Integer, primary_key=True)
    group_snapshot_id = Column(Integer, ForeignKey("identity_group_snapshot.id"), index=True)
    diagnostic_snapshot_id = Column(Integer, ForeignKey("identity_family_diagnostic_snapshot.id"), index=True)
    left_record_snapshot_id = Column(Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True)
    right_record_snapshot_id = Column(Integer, ForeignKey("scan_record_snapshot.id"), nullable=False, index=True)
    edge_class = Column(String(40), nullable=False)
    reason_codes_json = Column(Text, nullable=False, default="[]")
    evidence_source = Column(String(40), nullable=False)
    candidate_id = Column(Integer, ForeignKey("duplicate_candidate.id"))
    exclusion_id = Column(Integer, ForeignKey("rule_exclusion_audit.id"))
    deterministic_score = Column(Float)
    deterministic_status = Column(String(80))
    critical_mismatches_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityGroupReviewEvent(Base):
    __tablename__ = "identity_group_review_event"
    __table_args__ = (
        CheckConstraint(
            "decision_type IN ('CONFIRM_ALL_AS_ONE', 'CONFIRM_SELECTED', "
            "'SPLIT_PARTITIONS', 'KEEP_ALL_SEPARATE', 'UNSURE')",
            name="ck_group_review_decision_type",
        ),
        UniqueConstraint("supersedes_review_event_id", name="uq_group_review_superseded_once"),
        Index("uq_group_review_initial_group", "initial_group_snapshot_id", unique=True),
    )
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    projection_run_id = Column(Integer, ForeignKey("identity_group_projection_run.id"), nullable=False, index=True)
    group_snapshot_id = Column(Integer, ForeignKey("identity_group_snapshot.id"), nullable=False, index=True)
    group_hypothesis_key = Column(String(64), nullable=False)
    decision_type = Column(String(40), nullable=False, index=True)
    reviewer = Column(String(100), nullable=False)
    comment = Column(Text)
    supersedes_review_event_id = Column(Integer, ForeignKey("identity_group_review_event.id"), index=True)
    initial_group_snapshot_id = Column(Integer, ForeignKey("identity_group_snapshot.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdentityGroupReviewPartition(Base):
    __tablename__ = "identity_group_review_partition"
    __table_args__ = (
        UniqueConstraint("review_event_id", "partition_index", name="uq_group_review_partition_index"),
        CheckConstraint("partition_index >= 0", name="ck_group_review_partition_index"),
    )
    id = Column(Integer, primary_key=True)
    review_event_id = Column(Integer, ForeignKey("identity_group_review_event.id"), nullable=False, index=True)
    partition_index = Column(Integer, nullable=False)


class IdentityGroupReviewPartitionMember(Base):
    __tablename__ = "identity_group_review_partition_member"
    __table_args__ = (
        UniqueConstraint("review_event_id", "record_ref_key", name="uq_group_review_member_once"),
        UniqueConstraint("partition_id", "member_index", name="uq_group_review_partition_member_index"),
        CheckConstraint("member_index >= 0", name="ck_group_review_member_index"),
    )
    id = Column(Integer, primary_key=True)
    review_event_id = Column(Integer, ForeignKey("identity_group_review_event.id"), nullable=False, index=True)
    partition_id = Column(Integer, ForeignKey("identity_group_review_partition.id"), nullable=False, index=True)
    member_index = Column(Integer, nullable=False)
    record_ref_key = Column(String(64), nullable=False, index=True)


class HumanIdentityConstraint(Base):
    __tablename__ = "human_identity_constraint"
    __table_args__ = (
        CheckConstraint("left_record_ref_key < right_record_ref_key", name="ck_human_constraint_order"),
        CheckConstraint("constraint_type IN ('MUST_LINK', 'CANNOT_LINK')", name="ck_human_constraint_type"),
        UniqueConstraint(
            "source_review_event_id", "left_record_ref_key", "right_record_ref_key",
            name="uq_human_constraint_event_pair",
        ),
    )
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, ForeignKey("duplicate_scan.id"), nullable=False, index=True)
    left_record_ref_key = Column(String(64), nullable=False, index=True)
    right_record_ref_key = Column(String(64), nullable=False, index=True)
    constraint_type = Column(String(20), nullable=False, index=True)
    source_review_event_id = Column(Integer, ForeignKey("identity_group_review_event.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


def _reject_review_history_mutation(_mapper, _connection, _target):
    raise ValueError("group review history is append-only")


for _append_only_model in (
    IdentityGroupReviewEvent,
    IdentityGroupReviewPartition,
    IdentityGroupReviewPartitionMember,
    HumanIdentityConstraint,
):
    event.listen(_append_only_model, "before_update", _reject_review_history_mutation)
    event.listen(_append_only_model, "before_delete", _reject_review_history_mutation)


def _reject_scan_record_mutation(_mapper, _connection, _target):
    raise ValueError("canonical scan record snapshots are immutable")


event.listen(ScanRecordSnapshot, "before_update", _reject_scan_record_mutation)
event.listen(ScanRecordSnapshot, "before_delete", _reject_scan_record_mutation)


def _reject_neighborhood_mutation(_mapper, _connection, _target):
    raise ValueError("identity neighborhood snapshots are immutable")


for _neighborhood_model in (IdentityNeighborhoodSnapshot, IdentityNeighborhoodMember):
    event.listen(_neighborhood_model, "before_update", _reject_neighborhood_mutation)
    event.listen(_neighborhood_model, "before_delete", _reject_neighborhood_mutation)
