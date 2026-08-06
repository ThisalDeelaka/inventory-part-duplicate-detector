from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.contracts.dataset_registry import (
    AdvanceDatasetVersionStatusCommand,
    CreateDatasetCommand,
    DatasetArtifactKind,
    DatasetRecord,
    DatasetStatus,
    DatasetVersionStatus,
    RegisterDatasetArtifactCommand,
    RegisterDatasetVersionCommand,
)
from app.db.models import Dataset, DatasetArtifact, DatasetVersion
from app.repositories.dataset_registry_repository import (
    DatasetRegistryRepository,
)
from app.services.dataset_registry_service import (
    DatasetNotFoundError,
    DatasetRegistryConflictError,
    DatasetRegistryService,
    DatasetRegistryUnavailableError,
    DatasetVersionNotFoundError,
    InvalidDatasetMetadataError,
    InvalidDatasetVersionTransitionError,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
INI_PATH = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
ALLOWED_TRANSITIONS = {
    (DatasetVersionStatus.REGISTERED, DatasetVersionStatus.STAGED),
    (DatasetVersionStatus.REGISTERED, DatasetVersionStatus.REJECTED),
    (DatasetVersionStatus.STAGED, DatasetVersionStatus.PROFILED),
    (DatasetVersionStatus.STAGED, DatasetVersionStatus.REJECTED),
    (DatasetVersionStatus.PROFILED, DatasetVersionStatus.READY),
    (DatasetVersionStatus.PROFILED, DatasetVersionStatus.REJECTED),
}
ASCII_WHITESPACE_ONLY = ("", " ", "\t", "\n", "\r", "\f", "\v", " \t\r\n\f\v ")


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "registry.sqlite"
    config = Config(str(INI_PATH))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0002_dataset_registry")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    factory = sessionmaker(bind=engine)
    try:
        yield engine, factory, DatasetRegistryService(factory)
    finally:
        engine.dispose()


def _dataset_command(name: str = " Dataset One ") -> CreateDatasetCommand:
    return CreateDatasetCommand(name, None, NOW, NOW)


def _version_command(
    dataset_id: UUID,
    checksum: str = SHA_A,
    size: int = 10,
    filename: str = " source.csv ",
    media_type: str = " text/csv ",
) -> RegisterDatasetVersionCommand:
    return RegisterDatasetVersionCommand(
        dataset_id=dataset_id,
        source_filename=filename,
        source_media_type=media_type,
        source_sha256=checksum,
        source_size_bytes=size,
        source_record_count=2,
        created_at=NOW,
        updated_at=NOW,
    )


def _artifact_command(
    version_id: UUID,
    kind: DatasetArtifactKind = DatasetArtifactKind.SOURCE_CSV,
    ordinal: int = 0,
    uri: str = " s3://opaque/source ",
    checksum: str = SHA_A,
) -> RegisterDatasetArtifactCommand:
    return RegisterDatasetArtifactCommand(
        dataset_version_id=version_id,
        artifact_kind=kind,
        artifact_ordinal=ordinal,
        object_uri=uri,
        content_sha256=checksum,
        size_bytes=10,
        media_type=" text/csv ",
        created_at=NOW,
    )


def test_dataset_contract_create_get_duplicate_names_and_validation(registry):
    engine, _factory, service = registry
    first = service.create_dataset(_dataset_command())
    second = service.create_dataset(_dataset_command("Dataset One"))

    assert isinstance(first, DatasetRecord)
    assert isinstance(first.id, UUID)
    assert first.name == "Dataset One"
    assert first.status is DatasetStatus.ACTIVE
    assert first.created_at.tzinfo is timezone.utc
    assert first.id != second.id
    assert service.get_dataset(first.id) == first
    with pytest.raises(FrozenInstanceError):
        first.name = "changed"
    with pytest.raises(DatasetNotFoundError):
        service.get_dataset(uuid4())

    invalid = [
        *(CreateDatasetCommand(value, None, NOW, NOW) for value in ASCII_WHITESPACE_ONLY),
        CreateDatasetCommand("x" * 256, None, NOW, NOW),
        CreateDatasetCommand("valid", None, NOW.replace(tzinfo=None), NOW),
        CreateDatasetCommand("valid", None, NOW, NOW - timedelta(seconds=1)),
    ]
    for command_value in invalid:
        with pytest.raises(InvalidDatasetMetadataError):
            service.create_dataset(command_value)
    with Session(engine) as session:
        assert session.scalar(select(Dataset).where(Dataset.name == "valid")) is None


def test_source_version_numbering_scope_identity_and_immutability(registry):
    _engine, _factory, service = registry
    dataset_a = service.create_dataset(_dataset_command("A"))
    dataset_b = service.create_dataset(_dataset_command("B"))

    first = service.register_dataset_version(_version_command(dataset_a.id))
    second = service.register_dataset_version(
        _version_command(dataset_a.id, SHA_B, 20, "second.csv")
    )
    cross_dataset = service.register_dataset_version(
        _version_command(dataset_b.id)
    )
    repeated = service.register_dataset_version(
        _version_command(
            dataset_a.id,
            SHA_A,
            10,
            "different-name.csv",
            "application/octet-stream",
        )
    )

    assert first.created is True
    assert first.version.version_number == 1
    assert first.version.status is DatasetVersionStatus.REGISTERED
    assert first.version.source_filename == "source.csv"
    assert first.version.source_media_type == "text/csv"
    assert second.version.version_number == 2
    assert cross_dataset.version.version_number == 1
    assert repeated.created is False
    assert repeated.version == first.version


@pytest.mark.parametrize(
    "change",
    [
        {"source_sha256": "A" * 64},
        {"source_sha256": "a" * 63},
        {"source_sha256": "g" * 64},
        {"source_size_bytes": -1},
        {"source_record_count": -1},
        {"source_filename": "../source.csv"},
        {"source_filename": "folder/source.csv"},
        {"source_filename": "folder\\source.csv"},
        {"source_filename": "."},
        {"source_media_type": " "},
        *(
            {field: value}
            for field in ("source_filename", "source_media_type")
            for value in ASCII_WHITESPACE_ONLY
        ),
    ],
)
def test_source_version_metadata_validation_and_missing_dataset(
    registry, change
):
    _engine, _factory, service = registry
    dataset = service.create_dataset(_dataset_command())
    values = _version_command(dataset.id).__dict__ if hasattr(
        _version_command(dataset.id), "__dict__"
    ) else {
        field: getattr(_version_command(dataset.id), field)
        for field in _version_command(dataset.id).__dataclass_fields__
    }
    values.update(change)
    with pytest.raises(InvalidDatasetMetadataError):
        service.register_dataset_version(RegisterDatasetVersionCommand(**values))

    with pytest.raises(DatasetNotFoundError):
        service.register_dataset_version(_version_command(uuid4()))


@pytest.mark.parametrize(
    ("start", "target"),
    sorted(ALLOWED_TRANSITIONS, key=lambda item: (item[0].value, item[1].value)),
)
def test_all_allowed_lifecycle_transitions(registry, start, target):
    engine, _factory, service = registry
    dataset = service.create_dataset(_dataset_command(str(uuid4())))
    version = service.register_dataset_version(
        _version_command(dataset.id, uuid4().hex * 2, 10)
    ).version
    with Session(engine) as session, session.begin():
        row = session.get(DatasetVersion, version.id)
        row.status = start.value
    result = service.advance_dataset_version_status(
        AdvanceDatasetVersionStatusCommand(
            version.id, target, NOW + timedelta(minutes=1)
        )
    )
    assert result.status is target
    assert result.id == version.id
    assert result.source_sha256 == version.source_sha256
    assert result.created_at == version.created_at


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (start, target)
        for start in DatasetVersionStatus
        for target in DatasetVersionStatus
        if (start, target) not in ALLOWED_TRANSITIONS
    ],
)
def test_disallowed_terminal_same_and_skipped_lifecycle_transitions(
    registry, start, target
):
    engine, _factory, service = registry
    dataset = service.create_dataset(_dataset_command(str(uuid4())))
    version = service.register_dataset_version(
        _version_command(dataset.id, uuid4().hex * 2, 10)
    ).version
    with Session(engine) as session, session.begin():
        row = session.get(DatasetVersion, version.id)
        row.status = start.value
    with pytest.raises(InvalidDatasetVersionTransitionError):
        service.advance_dataset_version_status(
            AdvanceDatasetVersionStatusCommand(
                version.id, target, NOW + timedelta(minutes=1)
            )
        )
    with Session(engine) as session:
        assert session.get(DatasetVersion, version.id).status == start.value


def test_lifecycle_timestamp_monotonicity_and_missing_version(registry):
    _engine, _factory, service = registry
    dataset = service.create_dataset(_dataset_command())
    version = service.register_dataset_version(_version_command(dataset.id)).version
    with pytest.raises(InvalidDatasetMetadataError):
        service.advance_dataset_version_status(
            AdvanceDatasetVersionStatusCommand(
                version.id,
                DatasetVersionStatus.STAGED,
                NOW - timedelta(seconds=1),
            )
        )
    with pytest.raises(DatasetVersionNotFoundError):
        service.advance_dataset_version_status(
            AdvanceDatasetVersionStatusCommand(
                uuid4(), DatasetVersionStatus.STAGED, NOW
            )
        )


def test_artifact_kinds_slots_idempotency_and_conflicts(registry):
    engine, _factory, service = registry
    dataset = service.create_dataset(_dataset_command())
    version = service.register_dataset_version(_version_command(dataset.id)).version

    created = []
    for ordinal, kind in enumerate(DatasetArtifactKind):
        created.append(
            service.register_dataset_artifact(
                _artifact_command(
                    version.id,
                    kind,
                    ordinal,
                    f" s3://opaque/{ordinal} ",
                    chr(ord("a") + ordinal) * 64,
                )
            )
        )
    assert all(result.created for result in created)
    repeated = service.register_dataset_artifact(
        _artifact_command(version.id, uri="s3://opaque/0")
    )
    assert repeated.created is False
    assert repeated.artifact == created[0].artifact

    with pytest.raises(DatasetRegistryConflictError):
        service.register_dataset_artifact(
            _artifact_command(version.id, uri="s3://opaque/conflict", checksum=SHA_B)
        )
    with pytest.raises(DatasetRegistryConflictError):
        service.register_dataset_artifact(
            _artifact_command(version.id, ordinal=9, uri="s3://opaque/0")
        )
    distinct_checksum = service.register_dataset_artifact(
        _artifact_command(
            version.id, ordinal=9, uri="s3://opaque/9", checksum=SHA_A
        )
    )
    assert distinct_checksum.created is True
    with Session(engine) as session:
        assert session.scalar(
            select(func.count(DatasetArtifact.id)).where(
                DatasetArtifact.dataset_version_id == version.id
            )
        ) == 4


@pytest.mark.parametrize(
    "change",
    [
        {"content_sha256": "A" * 64},
        {"content_sha256": "a" * 63},
        {"content_sha256": "z" * 64},
        {"artifact_ordinal": -1},
        {"size_bytes": -1},
        {"object_uri": " "},
        {"media_type": " "},
        *(
            {field: value}
            for field in ("object_uri", "media_type")
            for value in ASCII_WHITESPACE_ONLY
        ),
    ],
)
def test_artifact_validation_and_missing_version(registry, change):
    _engine, _factory, service = registry
    dataset = service.create_dataset(_dataset_command())
    version = service.register_dataset_version(_version_command(dataset.id)).version
    original = _artifact_command(version.id)
    values = {
        field: getattr(original, field)
        for field in original.__dataclass_fields__
    }
    values.update(change)
    with pytest.raises(InvalidDatasetMetadataError):
        service.register_dataset_artifact(RegisterDatasetArtifactCommand(**values))
    with pytest.raises(DatasetVersionNotFoundError):
        service.register_dataset_artifact(_artifact_command(uuid4()))


def test_repository_never_commits_or_closes_caller_session(registry):
    engine, _factory, _service = registry
    session = Session(engine)
    repository = DatasetRegistryRepository(session)
    row = Dataset(
        id=uuid4(),
        name="rollback",
        description=None,
        status=DatasetStatus.ACTIVE.value,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.add_dataset(row)
    assert session.is_active
    session.rollback()
    assert session.is_active
    assert session.get(Dataset, row.id) is None
    session.close()


def test_service_closes_owned_session_after_success_and_failure(registry):
    engine, _factory, _service = registry
    closed: list[bool] = []

    class TrackingSession(Session):
        def close(self) -> None:
            closed.append(True)
            super().close()

    service = DatasetRegistryService(
        sessionmaker(bind=engine, class_=TrackingSession)
    )
    created = service.create_dataset(_dataset_command())
    assert created.name == "Dataset One"
    assert len(closed) == 1
    with pytest.raises(DatasetNotFoundError):
        service.get_dataset(uuid4())
    assert len(closed) == 2


def test_integrity_race_is_conflict_without_retry(registry, monkeypatch):
    _engine, _factory, service = registry
    dataset = service.create_dataset(_dataset_command())
    calls = 0

    def fail(_repository, _row):
        nonlocal calls
        calls += 1
        raise IntegrityError("insert", {}, Exception("constraint"))

    monkeypatch.setattr(DatasetRegistryRepository, "add_version", fail)
    with pytest.raises(DatasetRegistryConflictError) as captured:
        service.register_dataset_version(_version_command(dataset.id))
    assert isinstance(captured.value.__cause__, IntegrityError)
    assert calls == 1


def test_every_operation_fails_closed_when_registry_tables_are_absent(tmp_path):
    path = tmp_path / "legacy.sqlite"
    config = Config(str(INI_PATH))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0001_current_schema")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    service = DatasetRegistryService(sessionmaker(bind=engine))
    dataset_id = uuid4()
    version_id = uuid4()
    operations = [
        lambda: service.create_dataset(_dataset_command()),
        lambda: service.get_dataset(dataset_id),
        lambda: service.register_dataset_version(_version_command(dataset_id)),
        lambda: service.register_dataset_artifact(_artifact_command(version_id)),
        lambda: service.advance_dataset_version_status(
            AdvanceDatasetVersionStatusCommand(
                version_id, DatasetVersionStatus.STAGED, NOW
            )
        ),
    ]
    try:
        before = set(inspect(engine).get_table_names())
        for operation in operations:
            with pytest.raises(DatasetRegistryUnavailableError) as captured:
                operation()
            assert captured.value.__cause__ is not None
        assert set(inspect(engine).get_table_names()) == before
        assert not {"datasets", "dataset_versions", "dataset_artifacts"}.intersection(
            before
        )
    finally:
        engine.dispose()
