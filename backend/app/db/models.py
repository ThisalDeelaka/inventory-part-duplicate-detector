from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


_LOWERCASE_SHA256_CHECK = (
    "length({column}) = 64 AND lower({column}) = {column} AND "
    "replace(replace(replace(replace(replace(replace(replace(replace("
    "replace(replace(replace(replace(replace(replace(replace(replace("
    "{column}, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), "
    "'5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), "
    "'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''"
)

_ASCII_WHITESPACE = (" ", "\t", "\n", "\r", "\f", "\v")


def _ascii_whitespace_nonempty_check(column: str) -> str:
    expression = column
    for character in _ASCII_WHITESPACE:
        expression = f"replace({expression}, '{character}', '')"
    return f"length({expression}) > 0"


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            _ascii_whitespace_nonempty_check("name"),
            name="name_nonempty",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="status",
        ),
        Index("ix_datasets_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "version_number",
            name="uq_dataset_versions_dataset_id_version_number",
        ),
        UniqueConstraint(
            "dataset_id",
            "source_sha256",
            "source_size_bytes",
            name=(
                "uq_dataset_versions_dataset_id_source_sha256_"
                "source_size_bytes"
            ),
        ),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint(
            "status IN ('REGISTERED', 'STAGED', 'PROFILED', 'READY', 'REJECTED')",
            name="status",
        ),
        CheckConstraint(
            _ascii_whitespace_nonempty_check("source_filename"),
            name="source_filename_nonempty",
        ),
        CheckConstraint(
            _ascii_whitespace_nonempty_check("source_media_type"),
            name="source_media_type_nonempty",
        ),
        CheckConstraint(
            _LOWERCASE_SHA256_CHECK.format(column="source_sha256"),
            name="source_sha256_format",
        ),
        CheckConstraint(
            "source_size_bytes >= 0",
            name="source_size_bytes_nonnegative",
        ),
        CheckConstraint(
            "source_record_count IS NULL OR source_record_count >= 0",
            name="source_record_count_nonnegative",
        ),
        Index("ix_dataset_versions_dataset_id", "dataset_id"),
        Index("ix_dataset_versions_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "datasets.id",
            name="fk_dataset_versions_dataset_id_datasets",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_record_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DatasetArtifact(Base):
    __tablename__ = "dataset_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id",
            "artifact_kind",
            "artifact_ordinal",
            name=(
                "uq_dataset_artifacts_dataset_version_id_artifact_kind_"
                "artifact_ordinal"
            ),
        ),
        UniqueConstraint(
            "object_uri",
            name="uq_dataset_artifacts_object_uri",
        ),
        CheckConstraint(
            "artifact_kind IN ('SOURCE_CSV', 'SCHEMA_PROFILE_JSON', "
            "'CANONICAL_PARQUET')",
            name="artifact_kind",
        ),
        CheckConstraint(
            "artifact_ordinal >= 0",
            name="artifact_ordinal_nonnegative",
        ),
        CheckConstraint(
            _ascii_whitespace_nonempty_check("object_uri"),
            name="object_uri_nonempty",
        ),
        CheckConstraint(
            _LOWERCASE_SHA256_CHECK.format(column="content_sha256"),
            name="content_sha256_format",
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        CheckConstraint(
            _ascii_whitespace_nonempty_check("media_type"),
            name="media_type_nonempty",
        ),
        Index(
            "ix_dataset_artifacts_dataset_version_id",
            "dataset_version_id",
        ),
        Index(
            "ix_dataset_artifacts_dataset_version_id_artifact_kind",
            "dataset_version_id",
            "artifact_kind",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    dataset_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "dataset_versions.id",
            name=(
                "fk_dataset_artifacts_dataset_version_id_dataset_versions"
            ),
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    artifact_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    artifact_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    object_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


LEGACY_STARTUP_TABLES = (
    DuplicateScan.__table__,
    DuplicateCandidate.__table__,
    DuplicateFeedback.__table__,
    ScanWarning.__table__,
    RuleExclusionAudit.__table__,
)
