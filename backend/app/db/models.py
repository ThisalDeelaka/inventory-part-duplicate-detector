from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    custom_fields_used = Column(Text, default="[]", nullable=False)
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
    part_no_a = Column(String(200), nullable=False)
    description_a = Column(Text, nullable=False)
    contract_b = Column(String(100))
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


class CustomField(Base):
    __tablename__ = "custom_field"
    id = Column(Integer, primary_key=True)
    field_key = Column(String(120), unique=True, nullable=False)
    display_label = Column(String(200), nullable=False)
    mode = Column(String(20), nullable=False, default="SUPPORTING")
    aliases = Column(Text, default="[]", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


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
    part_no_a = Column(String(200), nullable=False)
    description_a = Column(Text, nullable=False)
    contract_b = Column(String(100))
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
