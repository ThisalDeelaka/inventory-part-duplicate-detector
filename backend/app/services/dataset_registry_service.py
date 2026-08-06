from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import re
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.contracts.dataset_registry import (
    AdvanceDatasetVersionStatusCommand,
    CreateDatasetCommand,
    DatasetArtifactKind,
    DatasetArtifactRecord,
    DatasetArtifactRegistrationResult,
    DatasetRecord,
    DatasetStatus,
    DatasetVersionRecord,
    DatasetVersionRegistrationResult,
    DatasetVersionStatus,
    RegisterDatasetArtifactCommand,
    RegisterDatasetVersionCommand,
)
from app.db.models import Dataset, DatasetArtifact, DatasetVersion
from app.repositories.dataset_registry_repository import (
    DatasetRegistryRepository,
)


class DatasetRegistryError(RuntimeError):
    pass


class DatasetRegistryUnavailableError(DatasetRegistryError):
    pass


class DatasetNotFoundError(DatasetRegistryError):
    pass


class DatasetVersionNotFoundError(DatasetRegistryError):
    pass


class DatasetRegistryConflictError(DatasetRegistryError):
    pass


class InvalidDatasetMetadataError(DatasetRegistryError, ValueError):
    pass


class InvalidDatasetVersionTransitionError(DatasetRegistryError, ValueError):
    pass


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_TRANSITIONS = frozenset(
    {
        (DatasetVersionStatus.REGISTERED, DatasetVersionStatus.STAGED),
        (DatasetVersionStatus.REGISTERED, DatasetVersionStatus.REJECTED),
        (DatasetVersionStatus.STAGED, DatasetVersionStatus.PROFILED),
        (DatasetVersionStatus.STAGED, DatasetVersionStatus.REJECTED),
        (DatasetVersionStatus.PROFILED, DatasetVersionStatus.READY),
        (DatasetVersionStatus.PROFILED, DatasetVersionStatus.REJECTED),
    }
)
_T = TypeVar("_T")


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidDatasetMetadataError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise InvalidDatasetMetadataError(
            f"{field} must be timezone-aware UTC"
        )
    return value.astimezone(timezone.utc)


def _persisted_utc(value: datetime) -> datetime:
    # SQLite does not retain timezone offsets for DateTime(timezone=True).
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _uuid(value: UUID, field: str) -> UUID:
    if not isinstance(value, UUID):
        raise InvalidDatasetMetadataError(f"{field} must be a UUID")
    return value


def _nonnegative(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidDatasetMetadataError(
            f"{field} must be a non-negative integer"
        )
    return value


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise InvalidDatasetMetadataError(
            f"{field} must be 64 lowercase hexadecimal characters"
        )
    return value


def _trimmed(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise InvalidDatasetMetadataError(f"{field} must be a string")
    result = value.strip()
    if not result or len(result) > maximum:
        raise InvalidDatasetMetadataError(
            f"{field} must be non-empty and at most {maximum} characters"
        )
    return result


def _dataset_record(row: Dataset) -> DatasetRecord:
    return DatasetRecord(
        id=row.id,
        name=row.name,
        description=row.description,
        status=DatasetStatus(row.status),
        created_at=_persisted_utc(row.created_at),
        updated_at=_persisted_utc(row.updated_at),
    )


def _version_record(row: DatasetVersion) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        id=row.id,
        dataset_id=row.dataset_id,
        version_number=row.version_number,
        status=DatasetVersionStatus(row.status),
        source_filename=row.source_filename,
        source_media_type=row.source_media_type,
        source_sha256=row.source_sha256,
        source_size_bytes=row.source_size_bytes,
        source_record_count=row.source_record_count,
        created_at=_persisted_utc(row.created_at),
        updated_at=_persisted_utc(row.updated_at),
    )


def _artifact_record(row: DatasetArtifact) -> DatasetArtifactRecord:
    return DatasetArtifactRecord(
        id=row.id,
        dataset_version_id=row.dataset_version_id,
        artifact_kind=DatasetArtifactKind(row.artifact_kind),
        artifact_ordinal=row.artifact_ordinal,
        object_uri=row.object_uri,
        content_sha256=row.content_sha256,
        size_bytes=row.size_bytes,
        media_type=row.media_type,
        created_at=_persisted_utc(row.created_at),
    )


def _is_unavailable(error: OperationalError | ProgrammingError) -> bool:
    if isinstance(error, OperationalError):
        return True
    original = getattr(error, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(
        original, "pgcode", None
    )
    return sqlstate == "42P01"


class DatasetRegistryService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def _run(self, operation: Callable[[DatasetRegistryRepository], _T]) -> _T:
        try:
            with self._session_factory() as session:
                with session.begin():
                    return operation(DatasetRegistryRepository(session))
        except IntegrityError as error:
            raise DatasetRegistryConflictError(
                "Dataset registry uniqueness conflict"
            ) from error
        except (OperationalError, ProgrammingError) as error:
            if _is_unavailable(error):
                raise DatasetRegistryUnavailableError(
                    "Dataset registry is unavailable"
                ) from error
            raise

    def create_dataset(self, command: CreateDatasetCommand) -> DatasetRecord:
        if not isinstance(command, CreateDatasetCommand):
            raise TypeError("command must be a CreateDatasetCommand")
        name = _trimmed(command.name, "name", 255)
        if command.description is not None and not isinstance(
            command.description, str
        ):
            raise InvalidDatasetMetadataError(
                "description must be a string or None"
            )
        created_at = _utc(command.created_at, "created_at")
        updated_at = _utc(command.updated_at, "updated_at")
        if updated_at < created_at:
            raise InvalidDatasetMetadataError(
                "updated_at must not be earlier than created_at"
            )

        def create(repository: DatasetRegistryRepository) -> DatasetRecord:
            row = repository.add_dataset(
                Dataset(
                    id=uuid4(),
                    name=name,
                    description=command.description,
                    status=DatasetStatus.ACTIVE.value,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            return _dataset_record(row)

        return self._run(create)

    def get_dataset(self, dataset_id: UUID) -> DatasetRecord:
        _uuid(dataset_id, "dataset_id")

        def get(repository: DatasetRegistryRepository) -> DatasetRecord:
            row = repository.get_dataset(dataset_id)
            if row is None:
                raise DatasetNotFoundError("Dataset was not found")
            return _dataset_record(row)

        return self._run(get)

    def register_dataset_version(
        self,
        command: RegisterDatasetVersionCommand,
    ) -> DatasetVersionRegistrationResult:
        if not isinstance(command, RegisterDatasetVersionCommand):
            raise TypeError("command must be a RegisterDatasetVersionCommand")
        dataset_id = _uuid(command.dataset_id, "dataset_id")
        filename = _trimmed(command.source_filename, "source_filename", 512)
        if filename in {".", ".."} or any(
            marker in filename for marker in ("/", "\\", "\x00")
        ):
            raise InvalidDatasetMetadataError(
                "source_filename must be display-basename metadata"
            )
        media_type = _trimmed(
            command.source_media_type, "source_media_type", 255
        )
        checksum = _sha256(command.source_sha256, "source_sha256")
        size = _nonnegative(command.source_size_bytes, "source_size_bytes")
        record_count = command.source_record_count
        if record_count is not None:
            record_count = _nonnegative(record_count, "source_record_count")
        created_at = _utc(command.created_at, "created_at")
        updated_at = _utc(command.updated_at, "updated_at")
        if updated_at < created_at:
            raise InvalidDatasetMetadataError(
                "updated_at must not be earlier than created_at"
            )

        def register(
            repository: DatasetRegistryRepository,
        ) -> DatasetVersionRegistrationResult:
            if repository.get_dataset(dataset_id) is None:
                raise DatasetNotFoundError("Dataset was not found")
            existing = repository.find_version_by_source_identity(
                dataset_id, checksum, size
            )
            if existing is not None:
                return DatasetVersionRegistrationResult(
                    version=_version_record(existing), created=False
                )
            maximum = repository.maximum_version_number(dataset_id)
            row = repository.add_version(
                DatasetVersion(
                    id=uuid4(),
                    dataset_id=dataset_id,
                    version_number=(maximum or 0) + 1,
                    status=DatasetVersionStatus.REGISTERED.value,
                    source_filename=filename,
                    source_media_type=media_type,
                    source_sha256=checksum,
                    source_size_bytes=size,
                    source_record_count=record_count,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            return DatasetVersionRegistrationResult(
                version=_version_record(row), created=True
            )

        return self._run(register)

    def register_dataset_artifact(
        self,
        command: RegisterDatasetArtifactCommand,
    ) -> DatasetArtifactRegistrationResult:
        if not isinstance(command, RegisterDatasetArtifactCommand):
            raise TypeError("command must be a RegisterDatasetArtifactCommand")
        version_id = _uuid(command.dataset_version_id, "dataset_version_id")
        if not isinstance(command.artifact_kind, DatasetArtifactKind):
            raise InvalidDatasetMetadataError(
                "artifact_kind must be a DatasetArtifactKind"
            )
        ordinal = _nonnegative(command.artifact_ordinal, "artifact_ordinal")
        object_uri = _trimmed(command.object_uri, "object_uri", 2048)
        checksum = _sha256(command.content_sha256, "content_sha256")
        size = _nonnegative(command.size_bytes, "size_bytes")
        media_type = _trimmed(command.media_type, "media_type", 255)
        created_at = _utc(command.created_at, "created_at")

        def register(
            repository: DatasetRegistryRepository,
        ) -> DatasetArtifactRegistrationResult:
            if repository.get_version(version_id) is None:
                raise DatasetVersionNotFoundError(
                    "Dataset version was not found"
                )
            existing = repository.find_artifact_by_slot(
                version_id, command.artifact_kind.value, ordinal
            )
            if existing is not None:
                matches = (
                    existing.object_uri == object_uri
                    and existing.content_sha256 == checksum
                    and existing.size_bytes == size
                    and existing.media_type == media_type
                    and _persisted_utc(existing.created_at) == created_at
                )
                if not matches:
                    raise DatasetRegistryConflictError(
                        "Artifact slot already contains different metadata"
                    )
                return DatasetArtifactRegistrationResult(
                    artifact=_artifact_record(existing), created=False
                )
            owner = repository.find_artifact_by_object_uri(object_uri)
            if owner is not None:
                raise DatasetRegistryConflictError(
                    "Object URI is already registered"
                )
            row = repository.add_artifact(
                DatasetArtifact(
                    id=uuid4(),
                    dataset_version_id=version_id,
                    artifact_kind=command.artifact_kind.value,
                    artifact_ordinal=ordinal,
                    object_uri=object_uri,
                    content_sha256=checksum,
                    size_bytes=size,
                    media_type=media_type,
                    created_at=created_at,
                )
            )
            return DatasetArtifactRegistrationResult(
                artifact=_artifact_record(row), created=True
            )

        return self._run(register)

    def advance_dataset_version_status(
        self,
        command: AdvanceDatasetVersionStatusCommand,
    ) -> DatasetVersionRecord:
        if not isinstance(command, AdvanceDatasetVersionStatusCommand):
            raise TypeError(
                "command must be an AdvanceDatasetVersionStatusCommand"
            )
        version_id = _uuid(command.dataset_version_id, "dataset_version_id")
        if not isinstance(command.target_status, DatasetVersionStatus):
            raise InvalidDatasetMetadataError(
                "target_status must be a DatasetVersionStatus"
            )
        updated_at = _utc(command.updated_at, "updated_at")

        def advance(
            repository: DatasetRegistryRepository,
        ) -> DatasetVersionRecord:
            row = repository.get_version(version_id)
            if row is None:
                raise DatasetVersionNotFoundError(
                    "Dataset version was not found"
                )
            current = DatasetVersionStatus(row.status)
            if (current, command.target_status) not in _ALLOWED_TRANSITIONS:
                raise InvalidDatasetVersionTransitionError(
                    "Dataset version status transition is not allowed"
                )
            if updated_at < _persisted_utc(row.updated_at):
                raise InvalidDatasetMetadataError(
                    "updated_at must not move backwards"
                )
            row.status = command.target_status.value
            row.updated_at = updated_at
            return _version_record(row)

        return self._run(advance)
