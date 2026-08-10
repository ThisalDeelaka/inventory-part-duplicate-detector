from __future__ import annotations

import ast
import hashlib
import io
import inspect
import os
import textwrap
from urllib.parse import urlsplit
from uuid import UUID

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError

from app.contracts.dataset_registry import DatasetArtifactKind
from app.contracts.object_storage import (
    ObjectArtifactIdentity,
    ObjectConflictError,
    ObjectNotFoundError,
    ObjectStorageSettings,
    PutObjectRequest,
)
from app.storage.s3_object_storage import S3ObjectStorageClient


_REQUIRED_ENV = (
    "OBJECT_STORAGE_TEST_ENDPOINT_URL",
    "OBJECT_STORAGE_TEST_REGION",
    "OBJECT_STORAGE_TEST_BUCKET",
    "OBJECT_STORAGE_TEST_ACCESS_KEY_ID",
    "OBJECT_STORAGE_TEST_SECRET_ACCESS_KEY",
    "OBJECT_STORAGE_TEST_VERIFY_TLS",
    "OBJECT_STORAGE_TEST_ADDRESSING_STYLE",
)
_SIGNAL_ENV = (*_REQUIRED_ENV, "OBJECT_STORAGE_TEST_SESSION_TOKEN", "MINIO_TEST_API_PORT")


def _fail_live_configuration(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _validated_environment() -> dict[str, str]:
    supplied = {name: os.environ.get(name) for name in _REQUIRED_ENV}
    if all(os.environ.get(name) is None for name in _SIGNAL_ENV):
        pytest.skip("object-storage integration environment is not configured")
    missing = [name for name, value in supplied.items() if value is None]
    if missing:
        _fail_live_configuration("object-storage integration environment is incomplete")
    if os.environ.get("OBJECT_STORAGE_TEST_SESSION_TOKEN") is not None:
        _fail_live_configuration("OBJECT_STORAGE_TEST_SESSION_TOKEN is not approved")
    values = {name: value for name, value in supplied.items() if value is not None}
    endpoint = None
    try:
        endpoint = urlsplit(values["OBJECT_STORAGE_TEST_ENDPOINT_URL"])
    except ValueError:
        pass
    if endpoint is None:
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL is invalid")
    port_value = os.environ.get("MINIO_TEST_API_PORT", "59000")
    selected_port = None
    try:
        selected_port = int(port_value)
    except ValueError:
        pass
    if selected_port is None or not 1 <= selected_port <= 65535:
        _fail_live_configuration("MINIO_TEST_API_PORT is invalid")
    endpoint_port = None
    try:
        endpoint_port = endpoint.port
    except ValueError:
        pass
    if endpoint_port is None:
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL port is invalid")
    if endpoint.scheme != "http":
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL scheme is not approved")
    if endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL host is not approved")
    if endpoint.username is not None or endpoint.password is not None:
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL user information is not approved")
    if endpoint.path not in {"", "/"}:
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL path is not approved")
    if endpoint.query or endpoint.fragment:
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL query or fragment is not approved")
    if endpoint_port != selected_port:
        _fail_live_configuration("OBJECT_STORAGE_TEST_ENDPOINT_URL port does not match the selected port")
    if values["OBJECT_STORAGE_TEST_REGION"] != "us-east-1":
        _fail_live_configuration("OBJECT_STORAGE_TEST_REGION is not approved")
    if values["OBJECT_STORAGE_TEST_BUCKET"] != "inventory-datasets-test":
        _fail_live_configuration("OBJECT_STORAGE_TEST_BUCKET is not approved")
    if values["OBJECT_STORAGE_TEST_ACCESS_KEY_ID"] != "inventory_test":
        _fail_live_configuration("OBJECT_STORAGE_TEST_ACCESS_KEY_ID is not approved")
    if values["OBJECT_STORAGE_TEST_SECRET_ACCESS_KEY"] != "inventory_test_only_2026":
        _fail_live_configuration("OBJECT_STORAGE_TEST_SECRET_ACCESS_KEY is not approved")
    if values["OBJECT_STORAGE_TEST_VERIFY_TLS"] != "false":
        _fail_live_configuration("OBJECT_STORAGE_TEST_VERIFY_TLS is not approved")
    if values["OBJECT_STORAGE_TEST_ADDRESSING_STYLE"] != "path":
        _fail_live_configuration("OBJECT_STORAGE_TEST_ADDRESSING_STYLE is not approved")
    return values


def _clear_live_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SIGNAL_ENV:
        monkeypatch.delenv(name, raising=False)


def _set_approved_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    approved = {
        "OBJECT_STORAGE_TEST_ENDPOINT_URL": "http://127.0.0.1:59000",
        "OBJECT_STORAGE_TEST_REGION": "us-east-1",
        "OBJECT_STORAGE_TEST_BUCKET": "inventory-datasets-test",
        "OBJECT_STORAGE_TEST_ACCESS_KEY_ID": "inventory_test",
        "OBJECT_STORAGE_TEST_SECRET_ACCESS_KEY": "inventory_test_only_2026",
        "OBJECT_STORAGE_TEST_VERIFY_TLS": "false",
        "OBJECT_STORAGE_TEST_ADDRESSING_STYLE": "path",
    }
    _clear_live_environment(monkeypatch)
    for name, value in approved.items():
        monkeypatch.setenv(name, value)


def test_environment_gate_skips_only_when_all_nine_signals_are_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_live_environment(monkeypatch)
    with pytest.raises(pytest.skip.Exception, match="not configured"):
        _validated_environment()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MINIO_TEST_API_PORT", "59000"),
        ("OBJECT_STORAGE_TEST_REGION", "us-east-1"),
        ("OBJECT_STORAGE_TEST_SESSION_TOKEN", "unapproved-token"),
    ],
)
def test_environment_gate_rejects_lone_signal(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    _clear_live_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        _validated_environment()


@pytest.mark.parametrize("port", ["not-a-number", "0", "65536", "-1"])
def test_environment_gate_rejects_invalid_selected_port(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    _set_approved_environment(monkeypatch)
    monkeypatch.setenv("MINIO_TEST_API_PORT", port)
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        _validated_environment()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://user:password@127.0.0.1:59000",
        "http://127.0.0.1:59000/path",
        "http://127.0.0.1:59000?query=1",
        "http://127.0.0.1:59000#fragment",
    ],
)
def test_environment_gate_rejects_unsafe_endpoint_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    _set_approved_environment(monkeypatch)
    monkeypatch.setenv("OBJECT_STORAGE_TEST_ENDPOINT_URL", endpoint)
    client_calls = 0

    def forbidden_client(**kwargs: object) -> object:
        nonlocal client_calls
        client_calls += 1
        raise AssertionError("boto3 client construction was not gated")

    monkeypatch.setattr(boto3, "client", forbidden_client)
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        _validated_environment()
    assert client_calls == 0


def test_environment_gate_accepts_complete_approved_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_approved_environment(monkeypatch)
    values = _validated_environment()
    assert values["OBJECT_STORAGE_TEST_ENDPOINT_URL"] == "http://127.0.0.1:59000"
    monkeypatch.setenv("MINIO_TEST_API_PORT", "59000")
    assert _validated_environment() == values


@pytest.mark.parametrize(
    ("name", "sentinel", "supplied_value"),
    [
        ("OBJECT_STORAGE_TEST_ACCESS_KEY_ID", "REAL_ACCESS_KEY_SENTINEL", "REAL_ACCESS_KEY_SENTINEL"),
        ("OBJECT_STORAGE_TEST_SECRET_ACCESS_KEY", "REAL_SECRET_SENTINEL", "REAL_SECRET_SENTINEL"),
        ("OBJECT_STORAGE_TEST_SESSION_TOKEN", "REAL_SESSION_TOKEN_SENTINEL", "REAL_SESSION_TOKEN_SENTINEL"),
        (
            "OBJECT_STORAGE_TEST_ENDPOINT_URL",
            "SIGNED_QUERY_SENTINEL",
            "http://127.0.0.1:59000?X-Amz-Signature=SIGNED_QUERY_SENTINEL",
        ),
        (
            "OBJECT_STORAGE_TEST_ENDPOINT_URL",
            "FRAGMENT_TOKEN_SENTINEL",
            "http://127.0.0.1:59000#FRAGMENT_TOKEN_SENTINEL",
        ),
        (
            "OBJECT_STORAGE_TEST_ENDPOINT_URL",
            "USERINFO_PASSWORD_SENTINEL",
            "http://user:USERINFO_PASSWORD_SENTINEL@127.0.0.1:59000",
        ),
        ("MINIO_TEST_API_PORT", "INVALID_PORT_SENTINEL", "INVALID_PORT_SENTINEL"),
    ],
)
def test_environment_gate_failure_diagnostics_are_value_free(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    sentinel: str,
    supplied_value: str,
) -> None:
    _set_approved_environment(monkeypatch)
    monkeypatch.setenv(name, supplied_value)
    client_calls = 0

    def forbidden_client(**kwargs: object) -> object:
        nonlocal client_calls
        client_calls += 1
        raise AssertionError("boto3 client construction was not gated")

    monkeypatch.setattr(boto3, "client", forbidden_client)
    with pytest.raises(pytest.fail.Exception) as caught:
        _validated_environment()
    rendered = str(caught.value)
    assert sentinel not in rendered
    assert supplied_value not in rendered
    for linked in (caught.value.__cause__, caught.value.__context__):
        if linked is not None:
            assert sentinel not in str(linked)
            assert supplied_value not in str(linked)
    assert client_calls == 0


def test_live_environment_validator_has_only_fixed_explicit_failures() -> None:
    source = textwrap.dedent(inspect.getsource(_validated_environment))
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree))
    fail_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_fail_live_configuration"
    ]
    assert fail_calls
    assert all(
        len(call.args) == 1
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
        for call in fail_calls
    )


@pytest.mark.object_storage_integration
def test_minio_object_storage_contract() -> None:
    values = _validated_environment()
    direct = boto3.client(
        service_name="s3",
        endpoint_url=values["OBJECT_STORAGE_TEST_ENDPOINT_URL"],
        region_name=values["OBJECT_STORAGE_TEST_REGION"],
        aws_access_key_id=values["OBJECT_STORAGE_TEST_ACCESS_KEY_ID"],
        aws_secret_access_key=values["OBJECT_STORAGE_TEST_SECRET_ACCESS_KEY"],
        verify=False,
        config=Config(
            connect_timeout=5,
            read_timeout=60,
            retries={"mode": "standard", "total_max_attempts": 3},
            s3={"addressing_style": "path"},
        ),
    )
    try:
        bucket = values["OBJECT_STORAGE_TEST_BUCKET"]
        try:
            direct.head_bucket(Bucket=bucket)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            assert status == 404, "fixed integration bucket was inaccessible rather than absent"
        else:
            pytest.fail("fixed integration bucket already exists; refusing to adopt it")
        direct.create_bucket(Bucket=bucket)

        settings = ObjectStorageSettings(
            endpoint_url=values["OBJECT_STORAGE_TEST_ENDPOINT_URL"],
            region=values["OBJECT_STORAGE_TEST_REGION"],
            bucket=bucket,
            access_key_id=values["OBJECT_STORAGE_TEST_ACCESS_KEY_ID"],
            secret_access_key=values["OBJECT_STORAGE_TEST_SECRET_ACCESS_KEY"],
            verify_tls=False,
            addressing_style="path",
        )
        storage = S3ObjectStorageClient(settings)
        storage.check_readiness()

        payload = b"part_number,description\nA-1,Known integration payload\n"
        digest = hashlib.sha256(payload).hexdigest()
        identity = ObjectArtifactIdentity(
            dataset_id=UUID("11111111-2222-4333-8444-555555555555"),
            dataset_version_id=UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
            artifact_kind=DatasetArtifactKind.SOURCE_CSV,
            artifact_ordinal=0,
            content_sha256=digest,
        )
        first_stream = io.BytesIO(payload)
        request = PutObjectRequest(identity, first_stream, len(payload), "text/csv")
        created = storage.put_verified_object(request)
        assert created.created is True
        expected_key = (
            f"v1/datasets/{identity.dataset_id}/versions/{identity.dataset_version_id}/"
            f"artifacts/source-csv/00000000/{digest}"
        )
        assert created.metadata.object_key.key == expected_key
        assert created.metadata.object_key.uri == f"s3://{bucket}/{expected_key}"
        assert first_stream.tell() == 0 and not first_stream.closed

        assert storage.get_object_metadata(identity) == created.metadata
        sink = io.BytesIO(b"prefix:")
        sink.seek(0, io.SEEK_END)
        downloaded = storage.download_verified_object(identity, sink)
        assert downloaded == created.metadata
        assert sink.getvalue() == b"prefix:" + payload and not sink.closed

        repeat_stream = io.BytesIO(payload)
        repeat = storage.put_verified_object(
            PutObjectRequest(identity, repeat_stream, len(payload), "text/csv")
        )
        assert repeat.created is False
        assert repeat.metadata == created.metadata
        assert repeat_stream.tell() == 0 and not repeat_stream.closed

        conflict_stream = io.BytesIO(payload)
        with pytest.raises(ObjectConflictError):
            storage.put_verified_object(
                PutObjectRequest(identity, conflict_stream, len(payload), "application/csv")
            )
        assert conflict_stream.tell() == 0 and not conflict_stream.closed

        missing = ObjectArtifactIdentity(
            identity.dataset_id,
            identity.dataset_version_id,
            identity.artifact_kind,
            1,
            "0" * 64,
        )
        with pytest.raises(ObjectNotFoundError):
            storage.get_object_metadata(missing)
    finally:
        close = getattr(direct, "close", None)
        if callable(close):
            close()
