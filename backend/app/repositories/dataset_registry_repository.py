from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Dataset, DatasetArtifact, DatasetVersion


class DatasetRegistryRepository:
    """Registry persistence using a caller-owned transaction and session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_dataset(self, dataset: Dataset) -> Dataset:
        self._session.add(dataset)
        self._session.flush()
        return dataset

    def get_dataset(self, dataset_id: UUID) -> Dataset | None:
        return self._session.get(Dataset, dataset_id)

    def find_version_by_source_identity(
        self,
        dataset_id: UUID,
        source_sha256: str,
        source_size_bytes: int,
    ) -> DatasetVersion | None:
        statement = select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.source_sha256 == source_sha256,
            DatasetVersion.source_size_bytes == source_size_bytes,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def maximum_version_number(self, dataset_id: UUID) -> int | None:
        statement = select(func.max(DatasetVersion.version_number)).where(
            DatasetVersion.dataset_id == dataset_id
        )
        return self._session.execute(statement).scalar_one()

    def add_version(self, version: DatasetVersion) -> DatasetVersion:
        self._session.add(version)
        self._session.flush()
        return version

    def get_version(self, version_id: UUID) -> DatasetVersion | None:
        return self._session.get(DatasetVersion, version_id)

    def find_artifact_by_slot(
        self,
        dataset_version_id: UUID,
        artifact_kind: str,
        artifact_ordinal: int,
    ) -> DatasetArtifact | None:
        statement = select(DatasetArtifact).where(
            DatasetArtifact.dataset_version_id == dataset_version_id,
            DatasetArtifact.artifact_kind == artifact_kind,
            DatasetArtifact.artifact_ordinal == artifact_ordinal,
        )
        return self._session.execute(statement).scalar_one_or_none()

    def find_artifact_by_object_uri(
        self,
        object_uri: str,
    ) -> DatasetArtifact | None:
        statement = select(DatasetArtifact).where(
            DatasetArtifact.object_uri == object_uri
        )
        return self._session.execute(statement).scalar_one_or_none()

    def add_artifact(self, artifact: DatasetArtifact) -> DatasetArtifact:
        self._session.add(artifact)
        self._session.flush()
        return artifact
