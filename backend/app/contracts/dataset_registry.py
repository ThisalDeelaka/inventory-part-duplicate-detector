from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class DatasetStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class DatasetVersionStatus(str, Enum):
    REGISTERED = "REGISTERED"
    STAGED = "STAGED"
    PROFILED = "PROFILED"
    READY = "READY"
    REJECTED = "REJECTED"


class DatasetArtifactKind(str, Enum):
    SOURCE_CSV = "SOURCE_CSV"
    SCHEMA_PROFILE_JSON = "SCHEMA_PROFILE_JSON"
    CANONICAL_PARQUET = "CANONICAL_PARQUET"


@dataclass(frozen=True, slots=True)
class CreateDatasetCommand:
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    id: UUID
    name: str
    description: str | None
    status: DatasetStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RegisterDatasetVersionCommand:
    dataset_id: UUID
    source_filename: str
    source_media_type: str
    source_sha256: str
    source_size_bytes: int
    source_record_count: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DatasetVersionRecord:
    id: UUID
    dataset_id: UUID
    version_number: int
    status: DatasetVersionStatus
    source_filename: str
    source_media_type: str
    source_sha256: str
    source_size_bytes: int
    source_record_count: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DatasetVersionRegistrationResult:
    version: DatasetVersionRecord
    created: bool


@dataclass(frozen=True, slots=True)
class RegisterDatasetArtifactCommand:
    dataset_version_id: UUID
    artifact_kind: DatasetArtifactKind
    artifact_ordinal: int
    object_uri: str
    content_sha256: str
    size_bytes: int
    media_type: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DatasetArtifactRecord:
    id: UUID
    dataset_version_id: UUID
    artifact_kind: DatasetArtifactKind
    artifact_ordinal: int
    object_uri: str
    content_sha256: str
    size_bytes: int
    media_type: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DatasetArtifactRegistrationResult:
    artifact: DatasetArtifactRecord
    created: bool


@dataclass(frozen=True, slots=True)
class AdvanceDatasetVersionStatusCommand:
    dataset_version_id: UUID
    target_status: DatasetVersionStatus
    updated_at: datetime
