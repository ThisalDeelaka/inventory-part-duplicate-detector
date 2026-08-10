from __future__ import annotations

import hashlib
import io
import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    EndpointConnectionError,
    LoginError,
    MetadataRetrievalError,
    NoAuthTokenError,
    ParamValidationError,
    ProxyConnectionError,
    ReadTimeoutError,
    ResponseStreamingError,
    SSOError,
    SSLError,
    TokenRetrievalError,
    UnknownCredentialError,
    UnknownEndpointError,
)

from app.contracts.dataset_registry import DatasetArtifactKind
from app.contracts.object_storage import (
    MAX_SINGLE_PUT_BYTES,
    OBJECT_IO_CHUNK_SIZE_BYTES,
    ObjectArtifactIdentity,
    ObjectConflictError,
    ObjectIntegrityError,
    ObjectNotFoundError,
    ObjectStorageConfigurationError,
    ObjectStorageOperationError,
    ObjectStorageUnavailableError,
    PutObjectRequest,
    build_object_key,
    ObjectStorageSettings,
)
from app.storage.s3_object_storage import S3ObjectStorageClient


DATASET_ID = UUID("AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE")
VERSION_ID = UUID("11111111-2222-4333-8444-555555555555")


def identity(payload: bytes = b"payload", kind: DatasetArtifactKind = DatasetArtifactKind.SOURCE_CSV, ordinal: int = 7) -> ObjectArtifactIdentity:
    return ObjectArtifactIdentity(DATASET_ID, VERSION_ID, kind, ordinal, hashlib.sha256(payload).hexdigest())


def settings(**changes: Any) -> ObjectStorageSettings:
    values = {
        "endpoint_url": "http://127.0.0.1:59000",
        "region": "us-east-1",
        "bucket": "inventory-datasets-test",
        "access_key_id": "test-key",
        "secret_access_key": "test-secret",
        "verify_tls": False,
    }
    values.update(changes)
    return ObjectStorageSettings(**values)


def provider_metadata(object_identity: ObjectArtifactIdentity, payload: bytes = b"payload", media_type: str = "text/csv", *, body: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ContentLength": len(payload),
        "ContentType": media_type,
        "ETag": '"opaque-etag"',
        "Metadata": {
            "dataset-id": str(object_identity.dataset_id),
            "dataset-version-id": str(object_identity.dataset_version_id),
            "artifact-kind": object_identity.artifact_kind.value,
            "artifact-ordinal": str(object_identity.artifact_ordinal),
            "sha256": object_identity.content_sha256,
        },
    }
    if body is not None:
        result["Body"] = body
    return result


def client_error(code: str, status: int | None, operation: str = "HeadObject") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "unsafe provider detail"}, "ResponseMetadata": {"HTTPStatusCode": status}},
        operation,
    )


class FakeBody:
    def __init__(self, payload: bytes, read_limit_log: list[int] | None = None) -> None:
        self._stream = io.BytesIO(payload)
        self.closed = False
        self.close_count = 0
        self.read_limit_log = read_limit_log if read_limit_log is not None else []

    def read(self, size: int) -> bytes:
        self.read_limit_log.append(size)
        return self._stream.read(size)

    def close(self) -> None:
        self.close_count += 1
        self.closed = True


class SequenceBody:
    def __init__(self, values: list[Any], *, close_error: Exception | None = None) -> None:
        self.values = values
        self.close_error = close_error
        self.close_count = 0

    def read(self, size: int) -> Any:
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


class RestoreFailingStream(io.BytesIO):
    def __init__(self, payload: bytes, failing_seek_calls: set[int]) -> None:
        super().__init__(payload)
        self._seek_calls = 0
        self._failing_seek_calls = failing_seek_calls

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self._seek_calls += 1
        if self._seek_calls in self._failing_seek_calls:
            raise OSError("raw restoration failure")
        return super().seek(offset, whence)


class ProviderReadFailingStream(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.provider_phase = False

    def read(self, size: int = -1) -> bytes:
        if self.provider_phase:
            raise OSError("raw caller payload failure")
        return super().read(size)


class ProviderTypeFailingStream(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.provider_phase = False

    def read(self, size: int = -1) -> bytes:
        if self.provider_phase:
            raise TypeError("raw caller stream contract failure")
        return super().read(size)


class ProviderExceptionStream(io.BytesIO):
    def __init__(self, payload: bytes, failure: Exception) -> None:
        super().__init__(payload)
        self.failure = failure
        self.provider_phase = False

    def read(self, size: int = -1) -> bytes:
        if self.provider_phase:
            raise self.failure
        return super().read(size)


class TypeErrorOnSeekCallStream(io.BytesIO):
    def __init__(self, payload: bytes, failing_seek_calls: set[int]) -> None:
        super().__init__(payload)
        self._seek_calls = 0
        self._failing_seek_calls = failing_seek_calls

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self._seek_calls += 1
        if self._seek_calls in self._failing_seek_calls:
            raise TypeError("raw caller seek contract failure")
        return super().seek(offset, whence)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.head_bucket_result: Any = {}
        self.put_result: Any = {}
        self.head_result: Any = None
        self.get_result: Any = None

    def _result(self, name: str, kwargs: dict[str, Any], result: Any) -> Any:
        self.calls.append((name, kwargs))
        if isinstance(result, Exception):
            raise result
        return result

    def head_bucket(self, **kwargs: Any) -> Any:
        return self._result("head_bucket", kwargs, self.head_bucket_result)

    def put_object(self, **kwargs: Any) -> Any:
        return self._result("put_object", kwargs, self.put_result)

    def head_object(self, **kwargs: Any) -> Any:
        return self._result("head_object", kwargs, self.head_result)

    def get_object(self, **kwargs: Any) -> Any:
        return self._result("get_object", kwargs, self.get_result)


class ConsumingFakeClient(FakeClient):
    def put_object(self, **kwargs: Any) -> Any:
        self.calls.append(("put_object", kwargs))
        stream = kwargs["Body"]
        stream._stream.provider_phase = True
        stream.read(1)
        return {}


def adapter(fake: FakeClient) -> S3ObjectStorageClient:
    return S3ObjectStorageClient(settings(), client_factory=lambda **_: fake)


def test_settings_are_frozen_and_secrets_are_not_represented_or_compared() -> None:
    value = settings(session_token="token")
    rendered = repr(value)
    assert "test-key" not in rendered and "test-secret" not in rendered and "token" not in rendered
    assert value == settings(access_key_id="other", secret_access_key="different", session_token="different")
    with pytest.raises(FrozenInstanceError):
        value.bucket = "changed"  # type: ignore[misc]


def test_standard_credential_chain_mode_is_valid() -> None:
    value = ObjectStorageSettings(None, " us-east-1 ", "valid-bucket")
    assert value.access_key_id is value.secret_access_key is value.session_token is None
    assert value.region == "us-east-1" and value.verify_tls is True


@pytest.mark.parametrize(
    ("access", "secret", "token"),
    [("a", None, None), (None, "s", None), (None, None, "t"), ("a", None, "t"), (None, "s", "t")],
)
def test_incomplete_credentials_are_rejected(access: str | None, secret: str | None, token: str | None) -> None:
    with pytest.raises(ObjectStorageConfigurationError):
        settings(access_key_id=access, secret_access_key=secret, session_token=token)


def test_complete_pair_and_session_credentials_are_valid() -> None:
    assert settings().session_token is None
    assert settings(session_token="test-token").session_token == "test-token"


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://host",
        "http://user:pass@host",
        "http://host/path",
        "http://host?query=1",
        "http://host#fragment",
        "http://host:99999",
        "http://host\n",
    ],
)
def test_invalid_endpoints_are_rejected(endpoint: str) -> None:
    with pytest.raises(ObjectStorageConfigurationError):
        settings(endpoint_url=endpoint)


def test_endpoint_root_slash_is_normalized_and_http_https_are_valid() -> None:
    assert settings(endpoint_url="http://localhost:9000/").endpoint_url == "http://localhost:9000"
    assert settings(endpoint_url="https://example.com", verify_tls=True).endpoint_url == "https://example.com"


@pytest.mark.parametrize(
    ("endpoint", "normalized"),
    [
        ("http://localhost:9000", "http://localhost:9000"),
        ("https://example.com", "https://example.com"),
        ("http://127.0.0.1:9000", "http://127.0.0.1:9000"),
        ("http://[::1]:9000", "http://[::1]:9000"),
        ("http://valid-internal-host:9000", "http://valid-internal-host:9000"),
    ],
)
def test_endpoint_accepts_only_valid_ip_or_dns_hosts(endpoint: str, normalized: str) -> None:
    assert settings(endpoint_url=endpoint, verify_tls=True).endpoint_url == normalized


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:9000",
        "https://localhost:9000",
        "http://127.0.0.1:9000",
        "https://127.0.0.1:9000",
        "http://[::1]:9000",
        "https://[::1]:9000",
    ],
)
def test_tls_verification_may_be_disabled_only_for_loopback(endpoint: str) -> None:
    assert settings(endpoint_url=endpoint, verify_tls=False).verify_tls is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com",
        "http://example.com",
        "http://valid-internal-host:9000",
        "https://10.0.0.10:9000",
        "http://192.168.1.10:9000",
        "http://8.8.8.8:9000",
    ],
)
def test_tls_verification_cannot_be_disabled_for_remote_endpoints(endpoint: str) -> None:
    with pytest.raises(ObjectStorageConfigurationError) as caught:
        settings(endpoint_url=endpoint, verify_tls=False)
    assert endpoint not in str(caught.value)


def test_tls_verification_preserves_remote_https_endpoint_support() -> None:
    value = settings(endpoint_url="https://example.com", verify_tls=True)
    assert value.endpoint_url == "https://example.com" and value.verify_tls is True


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://bad host:9000",
        "http://-bad.com:9000",
        "http://bad-.com:9000",
        "http://bad_underscore.com:9000",
        "http://.bad.com:9000",
        "http://bad..com:9000",
        "http://host:0",
        "http://host:",
        "http://[bad",
        "http://[::1",
        "http://[]:9000",
        "http://host%2Eevil:9000",
    ],
)
def test_endpoint_rejects_malformed_hosts_ports_and_ipv6_as_typed_configuration(
    endpoint: str,
) -> None:
    with pytest.raises(ObjectStorageConfigurationError) as caught:
        settings(endpoint_url=endpoint)
    assert not isinstance(caught.value, ValueError)
    assert endpoint not in str(caught.value)


@pytest.mark.parametrize("bucket", ["ab", "Uppercase", "-badname", "badname-", "bad..name", "127.0.0.1", "bad_name"])
def test_invalid_buckets_are_rejected(bucket: str) -> None:
    with pytest.raises(ObjectStorageConfigurationError):
        settings(bucket=bucket)


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint_url": None, "verify_tls": False},
        {"addressing_style": "auto"},
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": float("inf")},
        {"total_max_attempts": 0},
        {"total_max_attempts": True},
    ],
)
def test_invalid_transport_settings_are_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ObjectStorageConfigurationError):
        settings(**changes)


def test_client_is_lazy_cached_and_receives_exact_configuration() -> None:
    fake = FakeClient()
    calls: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeClient:
        calls.append(kwargs)
        return fake

    storage = S3ObjectStorageClient(settings(addressing_style="virtual", session_token="token"), client_factory=factory)
    assert calls == []
    storage.check_readiness()
    storage.check_readiness()
    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["service_name"] == "s3"
    assert kwargs["endpoint_url"] == "http://127.0.0.1:59000"
    assert kwargs["region_name"] == "us-east-1" and kwargs["verify"] is False
    assert kwargs["aws_access_key_id"] == "test-key" and kwargs["aws_secret_access_key"] == "test-secret"
    assert kwargs["aws_session_token"] == "token"
    assert kwargs["config"].retries["mode"] == "standard"
    assert kwargs["config"].retries["total_max_attempts"] == 3
    assert kwargs["config"].s3["addressing_style"] == "virtual"


def test_standard_chain_omits_explicit_credential_kwargs() -> None:
    captured: dict[str, Any] = {}
    fake = FakeClient()

    def factory(**kwargs: Any) -> FakeClient:
        captured.update(kwargs)
        return fake

    storage = S3ObjectStorageClient(ObjectStorageSettings(None, "us-east-1", "valid-bucket"), client_factory=factory)
    storage.check_readiness()
    assert not {"aws_access_key_id", "aws_secret_access_key", "aws_session_token"} & captured.keys()


@pytest.mark.parametrize(
    ("kind", "slug"),
    [
        (DatasetArtifactKind.SOURCE_CSV, "source-csv"),
        (DatasetArtifactKind.SCHEMA_PROFILE_JSON, "schema-profile-json"),
        (DatasetArtifactKind.CANONICAL_PARQUET, "canonical-parquet"),
    ],
)
def test_canonical_key_and_uri_for_every_kind(kind: DatasetArtifactKind, slug: str) -> None:
    object_identity = identity(kind=kind, ordinal=0)
    key = build_object_key("inventory-datasets-test", object_identity)
    expected = (
        f"v1/datasets/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/versions/11111111-2222-4333-8444-555555555555/"
        f"artifacts/{slug}/00000000/{object_identity.content_sha256}"
    )
    assert key.key == expected and key.uri == f"s3://inventory-datasets-test/{expected}"
    assert "127.0.0.1" not in key.uri


def test_ordinal_upper_boundary_and_identity_validation() -> None:
    upper = identity(ordinal=99_999_999)
    assert "/99999999/" in build_object_key("valid-bucket", upper).key
    with pytest.raises(ObjectStorageConfigurationError):
        identity(ordinal=100_000_000)
    with pytest.raises(ObjectStorageConfigurationError):
        ObjectArtifactIdentity(DATASET_ID, VERSION_ID, DatasetArtifactKind.SOURCE_CSV, 0, "A" * 64)


class NonSeekable(io.BytesIO):
    def seekable(self) -> bool:
        return False


def test_request_rejects_nonseekable_and_size_boundaries_without_reading() -> None:
    object_identity = identity(b"")
    with pytest.raises(ObjectStorageConfigurationError):
        PutObjectRequest(object_identity, NonSeekable(), 0, "text/csv")
    accepted = PutObjectRequest(object_identity, io.BytesIO(), MAX_SINGLE_PUT_BYTES, "text/csv")
    assert accepted.expected_size_bytes == 5_000_000_000
    for bad in (-1, 5_000_000_001):
        with pytest.raises(ObjectStorageConfigurationError):
            PutObjectRequest(object_identity, io.BytesIO(), bad, "text/csv")


@pytest.mark.parametrize("seekable_value", [None, False, 7])
def test_request_rejects_missing_noncallable_or_false_seekable(seekable_value: Any) -> None:
    class MalformedStream:
        def read(self, size: int = -1) -> bytes:
            return b""

        def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
            return 0

        def tell(self) -> int:
            return 0

    stream = MalformedStream()
    if seekable_value is not None:
        stream.seekable = seekable_value  # type: ignore[attr-defined]
    with pytest.raises(ObjectStorageConfigurationError):
        PutObjectRequest(identity(b""), stream, 0, "text/csv")


@pytest.mark.parametrize("failing_method", ["seekable", "tell"])
def test_request_converts_structural_type_errors(failing_method: str) -> None:
    class StructuralFailureStream:
        def read(self, size: int = -1) -> bytes:
            return b""

        def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
            return 0

        def seekable(self) -> bool:
            if failing_method == "seekable":
                raise TypeError("raw structural failure")
            return True

        def tell(self) -> int:
            if failing_method == "tell":
                raise TypeError("raw structural failure")
            return 0

    with pytest.raises(ObjectStorageConfigurationError) as caught:
        PutObjectRequest(identity(b""), StructuralFailureStream(), 0, "text/csv")
    assert "raw structural failure" not in str(caught.value)


def test_request_constructor_does_not_read_payload() -> None:
    class ReadCountingStream(io.BytesIO):
        read_count = 0

        def read(self, size: int = -1) -> bytes:
            self.read_count += 1
            return super().read(size)

    stream = ReadCountingStream(b"payload")
    PutObjectRequest(identity(b"payload"), stream, 7, "text/csv")
    assert stream.read_count == 0


@pytest.mark.parametrize("payload,declared", [(b"abc", 4), (b"abcx", 3)])
def test_preflight_size_failures_restore_stream_and_do_not_construct_client(payload: bytes, declared: int) -> None:
    construction_count = 0

    def factory(**_: Any) -> FakeClient:
        nonlocal construction_count
        construction_count += 1
        return FakeClient()

    stream = io.BytesIO(b"prefix" + payload)
    stream.seek(6)
    request = PutObjectRequest(identity(payload[:3]), stream, declared, "text/csv")
    with pytest.raises(ObjectIntegrityError):
        S3ObjectStorageClient(settings(), client_factory=factory).put_verified_object(request)
    assert stream.tell() == 6 and not stream.closed and construction_count == 0


def test_preflight_digest_failure_and_empty_payload() -> None:
    fake = FakeClient()
    stream = io.BytesIO(b"wrong")
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).put_verified_object(PutObjectRequest(identity(b"right"), stream, 5, "text/csv"))
    assert fake.calls == [] and stream.tell() == 0
    empty_identity = identity(b"")
    fake.head_result = provider_metadata(empty_identity, b"", "application/octet-stream")
    result = adapter(fake).put_verified_object(PutObjectRequest(empty_identity, io.BytesIO(), 0, "application/octet-stream"))
    assert result.created is True


def test_upload_rejects_chunk_larger_than_requested_before_provider_construction() -> None:
    class OversizedUploadStream:
        position = 4
        requested_sizes: list[int]

        def __init__(self) -> None:
            self.requested_sizes = []

        def read(self, size: int = -1) -> bytes:
            self.requested_sizes.append(size)
            return b"x" * (2 * OBJECT_IO_CHUNK_SIZE_BYTES)

        def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
            self.position = offset
            return offset

        def tell(self) -> int:
            return self.position

        def seekable(self) -> bool:
            return True

    constructions = 0

    def factory(**kwargs: Any) -> FakeClient:
        nonlocal constructions
        constructions += 1
        return FakeClient()

    stream = OversizedUploadStream()
    request = PutObjectRequest(
        identity(), stream, 2 * OBJECT_IO_CHUNK_SIZE_BYTES + 1, "text/csv"
    )
    with pytest.raises(ObjectIntegrityError, match="requested read size"):
        S3ObjectStorageClient(settings(), client_factory=factory).put_verified_object(request)
    assert stream.requested_sizes == [OBJECT_IO_CHUNK_SIZE_BYTES]
    assert stream.position == 4 and constructions == 0


def test_successful_upload_preflight_requests_at_most_one_mibibyte() -> None:
    class RecordingReadStream(io.BytesIO):
        def __init__(self, payload: bytes) -> None:
            super().__init__(payload)
            self.requested_sizes: list[int] = []

        def read(self, size: int = -1) -> bytes:
            self.requested_sizes.append(size)
            return super().read(size)

    payload = b"x" * (OBJECT_IO_CHUNK_SIZE_BYTES + 3)
    object_identity = identity(payload)
    stream = RecordingReadStream(payload)
    fake = FakeClient()
    fake.head_result = provider_metadata(object_identity, payload)
    adapter(fake).put_verified_object(
        PutObjectRequest(object_identity, stream, len(payload), "text/csv")
    )
    assert stream.requested_sizes == [OBJECT_IO_CHUNK_SIZE_BYTES, 3, 1]
    assert max(stream.requested_sizes) <= OBJECT_IO_CHUNK_SIZE_BYTES


def test_wrong_read_signature_is_typed_before_provider_and_restores_position() -> None:
    class WrongReadSignature:
        position = 3

        def read(self) -> bytes:
            return b"payload"

        def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
            self.position = offset
            return self.position

        def tell(self) -> int:
            return self.position

        def seekable(self) -> bool:
            return True

    fake = FakeClient()
    stream = WrongReadSignature()
    request = PutObjectRequest(identity(b"payload"), stream, 7, "text/csv")
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(request)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "positional argument" not in str(caught.value)
    assert stream.position == 3 and fake.calls == []


@pytest.mark.parametrize("wrong_signature", [True, False])
def test_seek_type_errors_are_typed_without_provider_call(wrong_signature: bool) -> None:
    class SeekTypeErrorStream:
        def read(self, size: int = -1) -> bytes:
            return b""

        def tell(self) -> int:
            return 0

        def seekable(self) -> bool:
            return True

    stream = SeekTypeErrorStream()
    if wrong_signature:
        stream.seek = lambda: 0  # type: ignore[attr-defined]
    else:
        def explicit_failure(offset: int, whence: int = io.SEEK_SET) -> int:
            raise TypeError("raw explicit seek failure")

        stream.seek = explicit_failure  # type: ignore[attr-defined]
    request = PutObjectRequest(identity(b""), stream, 0, "text/csv")
    fake = FakeClient()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(request)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "raw explicit" not in str(caught.value)
    assert len(caught.value.__notes__) == 1
    assert fake.calls == []


def test_explicit_read_type_error_is_typed_and_position_is_restored() -> None:
    class ReadTypeErrorStream(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            raise TypeError("raw explicit read failure")

    stream = ReadTypeErrorStream(b"payload")
    request = PutObjectRequest(identity(b"payload"), stream, 7, "text/csv")
    fake = FakeClient()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(request)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "raw explicit read failure" not in str(caught.value)
    assert stream.tell() == 0 and not stream.closed and fake.calls == []


def test_primary_integrity_error_survives_restoration_type_error() -> None:
    stream = TypeErrorOnSeekCallStream(b"wrong", {2})
    request = PutObjectRequest(identity(b"right"), stream, 5, "text/csv")
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(FakeClient()).put_verified_object(request)
    assert "digest mismatch" in str(caught.value)
    assert caught.value.__cause__ is None
    assert len(caught.value.__notes__) == 1
    assert caught.value.__notes__[0] == (
        "Caller stream restoration failed after the primary operation failure."
    )


def test_successful_verification_restoration_type_error_is_typed() -> None:
    payload = b"payload"
    stream = TypeErrorOnSeekCallStream(payload, {2})
    request = PutObjectRequest(identity(payload), stream, len(payload), "text/csv")
    fake = FakeClient()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(request)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "raw caller seek" not in str(caught.value)
    assert fake.calls == [] and not stream.closed


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (client_error("NoSuchBucket", 404, "HeadBucket"), ObjectStorageUnavailableError),
        (client_error("AccessDenied", 403, "HeadBucket"), ObjectStorageUnavailableError),
        (EndpointConnectionError(endpoint_url="http://safe.invalid"), ObjectStorageUnavailableError),
        (ReadTimeoutError(endpoint_url="http://safe.invalid", error="timeout"), ObjectStorageUnavailableError),
    ],
)
def test_readiness_failure_mapping_is_safe(failure: Exception, expected: type[Exception]) -> None:
    fake = FakeClient()
    fake.head_bucket_result = failure
    with pytest.raises(expected) as caught:
        adapter(fake).check_readiness()
    assert "unsafe provider detail" not in str(caught.value)
    assert [name for name, _ in fake.calls] == ["head_bucket"]


def test_successful_put_is_conditional_exact_and_restores_caller_stream() -> None:
    payload = b"payload"
    object_identity = identity(payload)
    fake = FakeClient()
    fake.head_result = provider_metadata(object_identity, payload)
    stream = io.BytesIO(b"xx" + payload)
    stream.seek(2)
    result = adapter(fake).put_verified_object(PutObjectRequest(object_identity, stream, len(payload), " text/csv "))
    assert result.created is True and stream.tell() == 2 and not stream.closed
    put = next(kwargs for name, kwargs in fake.calls if name == "put_object")
    assert put["IfNoneMatch"] == "*" and put["Body"] is not stream
    assert put["Body"]._stream is stream
    assert put["ContentLength"] == 7 and put["ContentType"] == "text/csv"
    assert put["Metadata"] == provider_metadata(object_identity)["Metadata"]
    assert [name for name, _ in fake.calls] == ["put_object", "head_object"]


@pytest.mark.parametrize(
    "failure",
    [
        TypeError("raw direct client type failure"),
        OSError("raw direct client I/O failure"),
        ValueError("raw direct client value failure"),
    ],
)
def test_direct_put_client_contract_failures_are_operation_errors(failure: Exception) -> None:
    payload = b"payload"
    stream = io.BytesIO(b"xx" + payload)
    stream.seek(2)
    fake = FakeClient()
    fake.put_result = failure
    with pytest.raises(ObjectStorageOperationError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), stream, len(payload), "text/csv")
        )
    assert caught.value.__cause__ is failure
    assert "upload stream" not in str(caught.value).lower()
    assert "raw direct" not in str(caught.value)
    assert stream.tell() == 2 and not stream.closed
    assert [name for name, _ in fake.calls] == ["put_object"]


@pytest.mark.parametrize("code,status", [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409)])
def test_conditional_repeat_is_idempotent_but_mismatch_conflicts(code: str, status: int) -> None:
    payload = b"payload"
    object_identity = identity(payload)
    fake = FakeClient()
    fake.put_result = client_error(code, status, "PutObject")
    fake.head_result = provider_metadata(object_identity, payload)
    result = adapter(fake).put_verified_object(PutObjectRequest(object_identity, io.BytesIO(payload), len(payload), "text/csv"))
    assert result.created is False
    fake.head_result = provider_metadata(object_identity, payload, "application/csv")
    with pytest.raises(ObjectConflictError):
        adapter(fake).put_verified_object(PutObjectRequest(object_identity, io.BytesIO(payload), len(payload), "text/csv"))


def test_post_create_bad_metadata_is_integrity_error() -> None:
    payload = b"payload"
    object_identity = identity(payload)
    fake = FakeClient()
    fake.head_result = provider_metadata(object_identity, payload)
    fake.head_result["Metadata"]["unexpected"] = "value"
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).put_verified_object(PutObjectRequest(object_identity, io.BytesIO(payload), len(payload), "text/csv"))


@pytest.mark.parametrize("code", ["BadRequest", "InvalidRequest", "Unknown"])
def test_generic_http_400_is_an_operation_error(code: str) -> None:
    failure = client_error(code, 400)
    fake = FakeClient()
    fake.head_result = failure
    with pytest.raises(ObjectStorageOperationError) as caught:
        adapter(fake).get_object_metadata(identity())
    assert caught.value.__cause__ is failure
    assert "unsafe provider detail" not in str(caught.value)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("AuthorizationHeaderMalformed", 400),
        ("RequestTimeout", 400),
        ("PermanentRedirect", 301),
        ("Unknown", 301),
        ("Unknown", 408),
        ("SlowDown", 503),
        ("Unknown", 503),
    ],
)
def test_provider_unavailable_codes_and_statuses_take_precedence(
    code: str, status: int
) -> None:
    failure = client_error(code, status)
    fake = FakeClient()
    fake.head_result = failure
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).get_object_metadata(identity())
    assert caught.value.__cause__ is failure
    assert "unsafe provider detail" not in str(caught.value)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("PreconditionFailed", None),
        ("PreconditionFailed", 409),
        ("PreconditionFailed", 412),
        ("ConditionalRequestConflict", None),
        ("ConditionalRequestConflict", 409),
        ("ConditionalRequestConflict", 412),
        ("Unknown", 409),
        ("", 412),
    ],
)
def test_only_compatible_conditional_failures_reconcile(
    code: str, status: int | None
) -> None:
    payload = b"payload"
    object_identity = identity(payload)
    fake = FakeClient()
    fake.put_result = client_error(code, status, "PutObject")
    fake.head_result = provider_metadata(object_identity, payload)
    result = adapter(fake).put_verified_object(
        PutObjectRequest(object_identity, io.BytesIO(payload), len(payload), "text/csv")
    )
    assert result.created is False
    assert [name for name, _ in fake.calls] == ["put_object", "head_object"]


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        ("PreconditionFailed", 403, ObjectStorageUnavailableError),
        ("PreconditionFailed", 401, ObjectStorageUnavailableError),
        ("PreconditionFailed", 408, ObjectStorageUnavailableError),
        ("PreconditionFailed", 503, ObjectStorageUnavailableError),
        ("ConditionalRequestConflict", 400, ObjectStorageOperationError),
        ("ConditionalRequestConflict", 200, ObjectStorageOperationError),
    ],
)
def test_incompatible_conditional_codes_do_not_reconcile(
    code: str, status: int, expected: type[Exception]
) -> None:
    payload = b"payload"
    failure = client_error(code, status, "PutObject")
    fake = FakeClient()
    fake.put_result = failure
    with pytest.raises(expected) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), io.BytesIO(payload), len(payload), "text/csv")
        )
    assert caught.value.__cause__ is failure
    assert [name for name, _ in fake.calls] == ["put_object"]


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("Unknown", 404),
        ("", 404),
        ("NoSuchBucket", 404),
        ("AccessDenied", 403),
        ("PermanentRedirect", 301),
        ("Unknown", 301),
        ("Unknown", 307),
        ("Unknown", 308),
    ],
)
def test_head_bucket_missing_or_redirected_states_are_unavailable(
    code: str, status: int
) -> None:
    failure = client_error(code, status, "HeadBucket")
    fake = FakeClient()
    fake.head_bucket_result = failure
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).check_readiness()
    assert caught.value.__cause__ is failure
    assert not isinstance(caught.value, ObjectNotFoundError)
    assert [name for name, _ in fake.calls] == ["head_bucket"]


def test_post_create_missing_metadata_is_integrity_error_and_restores_stream() -> None:
    payload = b"payload"
    object_identity = identity(payload)
    missing = client_error("NoSuchKey", 404)
    fake = FakeClient()
    fake.head_result = missing
    stream = io.BytesIO(b"xx" + payload)
    stream.seek(2)
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(object_identity, stream, len(payload), "text/csv")
        )
    assert isinstance(caught.value.__cause__, ObjectNotFoundError)
    assert caught.value.__cause__.__cause__ is missing
    assert stream.tell() == 2 and not stream.closed
    assert [name for name, _ in fake.calls] == ["put_object", "head_object"]


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        ("AccessDenied", 403, ObjectStorageUnavailableError),
        ("Unknown", 503, ObjectStorageUnavailableError),
        ("BadRequest", 400, ObjectStorageOperationError),
    ],
)
def test_post_create_nonabsence_failures_keep_provider_taxonomy(
    code: str, status: int, expected: type[Exception]
) -> None:
    payload = b"payload"
    failure = client_error(code, status)
    fake = FakeClient()
    fake.head_result = failure
    with pytest.raises(expected) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), io.BytesIO(payload), len(payload), "text/csv")
        )
    assert caught.value.__cause__ is failure
    assert [name for name, _ in fake.calls] == ["put_object", "head_object"]


def test_metadata_conversion_and_not_found_mapping() -> None:
    object_identity = identity()
    fake = FakeClient()
    fake.head_result = {**provider_metadata(object_identity), "VersionId": "opaque-version"}
    metadata = adapter(fake).get_object_metadata(object_identity)
    assert metadata.etag == '"opaque-etag"' and metadata.version_id == "opaque-version"
    fake.head_result = client_error("NoSuchKey", 404)
    with pytest.raises(ObjectNotFoundError):
        adapter(fake).get_object_metadata(object_identity)
    fake.head_result = client_error("AccessDenied", 403)
    with pytest.raises(ObjectStorageUnavailableError):
        adapter(fake).get_object_metadata(object_identity)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["Metadata"].pop("sha256"),
        lambda value: value["Metadata"].update({"unexpected": "x"}),
        lambda value: value.update(ContentLength=-1),
        lambda value: value.update(ContentType=" text/csv "),
        lambda value: value.update(ETag=""),
        lambda value: value.update(VersionId=7),
        lambda value: value["Metadata"].update({"artifact-ordinal": "007"}),
    ],
)
def test_malformed_metadata_is_integrity_error(mutation: Any) -> None:
    object_identity = identity()
    fake = FakeClient()
    value = provider_metadata(object_identity)
    mutation(value)
    fake.head_result = value
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).get_object_metadata(object_identity)


def test_download_is_bounded_appends_and_closes_only_provider_body() -> None:
    payload = b"x" * (1_048_576 + 3)
    object_identity = identity(payload)
    reads: list[int] = []
    body = FakeBody(payload, reads)
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, payload, body=body)
    sink = io.BytesIO(b"prefix")
    sink.seek(0, io.SEEK_END)
    metadata = adapter(fake).download_verified_object(object_identity, sink)
    assert metadata.size_bytes == len(payload)
    assert sink.getvalue() == b"prefix" + payload and not sink.closed
    assert body.closed and body.close_count == 1
    assert reads[0] == OBJECT_IO_CHUNK_SIZE_BYTES
    assert all(size <= 1_048_576 for size in reads)
    assert [name for name, _ in fake.calls] == ["get_object"]


def test_download_rejects_chunk_larger_than_requested_before_sink_write() -> None:
    class OversizedBody:
        def __init__(self, chunk: bytes) -> None:
            self.chunk = chunk
            self.read_sizes: list[int] = []
            self.close_count = 0

        def read(self, size: int) -> bytes:
            self.read_sizes.append(size)
            return self.chunk

        def close(self) -> None:
            self.close_count += 1

    oversized = b"x" * (OBJECT_IO_CHUNK_SIZE_BYTES + 1)
    object_identity = identity(oversized)
    body = OversizedBody(oversized)
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, oversized, body=body)
    sink = io.BytesIO(b"existing")
    sink.seek(0, io.SEEK_END)
    with pytest.raises(ObjectIntegrityError, match="requested chunk size"):
        adapter(fake).download_verified_object(object_identity, sink)
    assert body.read_sizes == [OBJECT_IO_CHUNK_SIZE_BYTES]
    assert body.close_count == 1
    assert sink.getvalue() == b"existing" and not sink.closed


@pytest.mark.parametrize("actual", [b"short", b"payload-extra", b"payloae"])
def test_download_integrity_failures_close_body_and_preserve_partial_sink(actual: bytes) -> None:
    expected = b"payload"
    object_identity = identity(expected)
    body = FakeBody(actual)
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, expected, body=body)
    sink = io.BytesIO(b"existing")
    sink.seek(0, io.SEEK_END)
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).download_verified_object(object_identity, sink)
    assert body.closed and body.close_count == 1
    assert sink.getvalue().startswith(b"existing") and not sink.closed
    assert [name for name, _ in fake.calls] == ["get_object"]


def test_bad_download_metadata_fails_before_writing() -> None:
    object_identity = identity()
    body = FakeBody(b"payload")
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, body=body)
    fake.get_result["Metadata"].pop("sha256")
    sink = io.BytesIO(b"existing")
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).download_verified_object(object_identity, sink)
    assert sink.getvalue() == b"existing"
    assert body.closed is True and body.close_count == 1


@pytest.mark.parametrize("code", ["NoSuchKey", "NotFound", "", "Unknown"])
def test_status_404_maps_only_recognized_or_unknown_absence(code: str) -> None:
    object_identity = identity()
    fake = FakeClient()
    fake.head_result = client_error(code, 404)
    with pytest.raises(ObjectNotFoundError):
        adapter(fake).get_object_metadata(object_identity)


@pytest.mark.parametrize(
    "code",
    ["AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "NoSuchBucket"],
)
def test_recognized_unavailable_code_overrides_status_404(code: str) -> None:
    object_identity = identity()
    fake = FakeClient()
    fake.head_result = client_error(code, 404)
    with pytest.raises(ObjectStorageUnavailableError):
        adapter(fake).get_object_metadata(object_identity)


def test_readiness_404_is_never_object_absence() -> None:
    fake = FakeClient()
    fake.head_bucket_result = client_error("Unknown", 404, "HeadBucket")
    with pytest.raises(ObjectStorageUnavailableError):
        adapter(fake).check_readiness()


@pytest.mark.parametrize(
    "unsafe_code",
    ["AccessDenied\ncredential=secret", "raw response content", "x" * 65, "control\x00code"],
)
def test_provider_code_rendering_is_bounded_and_safe(unsafe_code: str) -> None:
    object_identity = identity()
    fake = FakeClient()
    fake.head_result = client_error(unsafe_code, 500)
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).get_object_metadata(object_identity)
    message = str(caught.value)
    assert "code=Unknown" in message
    assert unsafe_code not in message
    assert "credential" not in message and "raw response" not in message
    assert "\n" not in message and len(message) < 300


@pytest.mark.parametrize(
    "failure",
    [
        ProxyConnectionError(proxy_url="http://credential@proxy.invalid"),
        SSLError(endpoint_url="https://credential@host.invalid", error="raw TLS response"),
        ConnectionClosedError(endpoint_url="http://credential@host.invalid"),
        ReadTimeoutError(endpoint_url="http://credential@host.invalid", error="raw timeout"),
        ResponseStreamingError(error="raw response body"),
        UnknownEndpointError(service_name="s3", region_name="credential-region"),
    ],
)
def test_streaming_transport_failures_are_safe_typed_and_close_once(failure: Exception) -> None:
    payload = b"partial-and-unread"
    object_identity = identity(payload)
    body = SequenceBody([b"partial", failure])
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, payload, body=body)
    sink = io.BytesIO(b"existing:")
    sink.seek(0, io.SEEK_END)
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).download_verified_object(object_identity, sink)
    assert caught.value.__cause__ is failure
    assert body.close_count == 1
    assert sink.getvalue() == b"existing:partial"
    message = str(caught.value)
    assert "credential" not in message and "raw" not in message


def test_nontransport_botocore_failure_is_operation_error() -> None:
    failure = ParamValidationError(report="raw invalid parameter")
    fake = FakeClient()
    fake.head_bucket_result = failure
    with pytest.raises(ObjectStorageOperationError) as caught:
        adapter(fake).check_readiness()
    assert caught.value.__cause__ is failure
    assert "raw invalid parameter" not in str(caught.value)


def test_body_with_close_but_no_read_closes_once() -> None:
    class CloseOnly:
        close_count = 0

        def close(self) -> None:
            self.close_count += 1

    object_identity = identity()
    body = CloseOnly()
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, body=body)
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).download_verified_object(object_identity, io.BytesIO())
    assert body.close_count == 1


def test_provider_body_wrong_read_signature_is_integrity_error_and_closes_once() -> None:
    class WrongReadSignatureBody:
        close_count = 0

        def read(self) -> bytes:
            return b""

        def close(self) -> None:
            self.close_count += 1

    object_identity = identity()
    body = WrongReadSignatureBody()
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, body=body)
    sink = io.BytesIO()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).download_verified_object(object_identity, sink)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "positional argument" not in str(caught.value)
    assert body.close_count == 1 and not sink.closed


def test_provider_body_explicit_read_type_error_is_integrity_error_and_closes_once() -> None:
    failure = TypeError("raw provider body contract failure")
    object_identity = identity()
    body = SequenceBody([failure])
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, body=body)
    sink = io.BytesIO()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).download_verified_object(object_identity, sink)
    assert caught.value.__cause__ is failure
    assert "raw provider body" not in str(caught.value)
    assert body.close_count == 1 and not sink.closed


def test_provider_body_oserror_remains_operation_error_and_closes_once() -> None:
    failure = OSError("raw provider body I/O failure")
    object_identity = identity()
    body = SequenceBody([failure])
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, body=body)
    with pytest.raises(ObjectStorageOperationError) as caught:
        adapter(fake).download_verified_object(object_identity, io.BytesIO())
    assert caught.value.__cause__ is failure
    assert "raw provider body" not in str(caught.value)
    assert body.close_count == 1


def test_body_with_read_but_no_close_and_none_body_are_rejected() -> None:
    class ReadOnly:
        def read(self, size: int) -> bytes:
            return b""

    object_identity = identity()
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, body=ReadOnly())
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).download_verified_object(object_identity, io.BytesIO())
    fake.get_result = provider_metadata(object_identity)
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).download_verified_object(object_identity, io.BytesIO())


def test_nonbinary_body_chunk_closes_once() -> None:
    object_identity = identity()
    body = SequenceBody(["not-bytes"])
    fake = FakeClient()
    fake.get_result = provider_metadata(object_identity, body=body)
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).download_verified_object(object_identity, io.BytesIO())
    assert body.close_count == 1


def test_preflight_primary_failure_survives_restore_failure() -> None:
    stream = RestoreFailingStream(b"wrong", {2})
    request = PutObjectRequest(identity(b"right"), stream, 5, "text/csv")
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(FakeClient()).put_verified_object(request)
    assert "digest mismatch" in str(caught.value)
    assert any("restoration failed" in note for note in caught.value.__notes__)
    assert "raw restoration failure" not in str(caught.value)


def test_successful_preflight_restore_failure_is_typed() -> None:
    payload = b"payload"
    stream = RestoreFailingStream(payload, {2})
    request = PutObjectRequest(identity(payload), stream, len(payload), "text/csv")
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(FakeClient()).put_verified_object(request)
    assert isinstance(caught.value.__cause__, OSError)
    assert "raw restoration failure" not in str(caught.value)


def test_provider_failure_survives_restore_failure() -> None:
    payload = b"payload"
    failure = client_error("AccessDenied", 403, "PutObject")
    fake = FakeClient()
    fake.put_result = failure
    stream = RestoreFailingStream(payload, {4})
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), stream, len(payload), "text/csv")
        )
    assert caught.value.__cause__ is failure
    assert any("restoration failed" in note for note in caught.value.__notes__)


def test_provider_consumed_upload_stream_oserror_is_integrity_error() -> None:
    payload = b"payload"
    stream = ProviderReadFailingStream(payload)
    fake = ConsumingFakeClient()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), stream, len(payload), "text/csv")
        )
    assert isinstance(caught.value.__cause__, OSError)
    assert "raw caller payload failure" not in str(caught.value)
    assert [name for name, _ in fake.calls] == ["put_object"]


def test_provider_consumed_upload_stream_type_error_is_integrity_error() -> None:
    payload = b"payload"
    stream = ProviderTypeFailingStream(b"xx" + payload)
    stream.seek(2)
    fake = ConsumingFakeClient()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), stream, len(payload), "text/csv")
        )
    assert isinstance(caught.value.__cause__, TypeError)
    assert "raw caller stream" not in str(caught.value)
    assert stream.tell() == 2 and not stream.closed
    assert [name for name, _ in fake.calls] == ["put_object"]


@pytest.mark.parametrize(
    "failure",
    [
        TypeError("raw caller type failure"),
        OSError("raw caller I/O failure"),
        ValueError("raw caller value failure"),
    ],
)
def test_provider_consumption_preserves_caller_stream_failure_origin(
    failure: Exception,
) -> None:
    payload = b"payload"
    stream = ProviderExceptionStream(b"xx" + payload, failure)
    stream.seek(2)
    fake = ConsumingFakeClient()
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), stream, len(payload), "text/csv")
        )
    assert caught.value.__cause__ is failure
    assert "raw caller" not in str(caught.value)
    assert stream.tell() == 2 and not stream.closed
    assert [name for name, _ in fake.calls] == ["put_object"]


def test_download_integrity_primary_survives_close_failure() -> None:
    payload = b"payload"
    body = SequenceBody([b"short", b""], close_error=OSError("raw close failure"))
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).download_verified_object(identity(payload), io.BytesIO())
    assert body.close_count == 1
    assert any("cleanup failed" in note for note in caught.value.__notes__)
    assert "raw close failure" not in str(caught.value)


def test_successful_download_close_failure_is_operation_error() -> None:
    payload = b"payload"
    body = SequenceBody([payload, b""], close_error=OSError("raw close failure"))
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectStorageOperationError) as caught:
        adapter(fake).download_verified_object(identity(payload), io.BytesIO())
    assert body.close_count == 1
    assert isinstance(caught.value.__cause__, OSError)
    assert "raw close failure" not in str(caught.value)


def test_streaming_primary_survives_close_failure() -> None:
    payload = b"payload"
    failure = ResponseStreamingError(error="raw provider response")
    body = SequenceBody([b"part", failure], close_error=OSError("raw close failure"))
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    sink = io.BytesIO()
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).download_verified_object(identity(payload), sink)
    assert caught.value.__cause__ is failure
    assert body.close_count == 1 and sink.getvalue() == b"part"
    assert any("cleanup failed" in note for note in caught.value.__notes__)


@pytest.mark.parametrize("code,status", [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409)])
def test_conditional_conflict_retains_original_provider_cause(code: str, status: int) -> None:
    payload = b"payload"
    original = client_error(code, status, "PutObject")
    fake = FakeClient()
    fake.put_result = original
    fake.head_result = provider_metadata(identity(payload), payload, "application/csv")
    with pytest.raises(ObjectConflictError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), io.BytesIO(payload), len(payload), "text/csv")
        )
    assert caught.value.__cause__ is original
    assert any("Metadata comparison" in note for note in caught.value.__notes__)


def test_conditional_missing_followup_retains_original_provider_cause() -> None:
    payload = b"payload"
    original = client_error("PreconditionFailed", 412, "PutObject")
    fake = FakeClient()
    fake.put_result = original
    fake.head_result = client_error("NoSuchKey", 404)
    with pytest.raises(ObjectStorageOperationError) as caught:
        adapter(fake).put_verified_object(
            PutObjectRequest(identity(payload), io.BytesIO(payload), len(payload), "text/csv")
        )
    assert caught.value.__cause__ is original
    assert "unsafe provider detail" not in str(caught.value)
    assert any("ObjectNotFoundError" in note for note in caught.value.__notes__)


@pytest.mark.parametrize(
    "failure",
    [
        MetadataRetrievalError(error_msg="credential metadata secret"),
        TokenRetrievalError(provider="credential-provider", error_msg="token secret"),
        NoAuthTokenError(),
        SSOError(),
        LoginError(),
        UnknownCredentialError(name="credential-secret-name"),
    ],
)
def test_standard_credential_provider_failures_are_unavailable(failure: Exception) -> None:
    def failing_factory(**kwargs: Any) -> FakeClient:
        raise failure

    storage = S3ObjectStorageClient(settings(), client_factory=failing_factory)
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        storage.check_readiness()
    assert caught.value.__cause__ is failure
    message = str(caught.value)
    assert "secret" not in message and "credential-provider" not in message


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("SlowDown", 503),
        ("InternalError", 500),
        ("ServiceUnavailable", 503),
        ("Unknown", 503),
        ("NoSuchKey", 503),
        ("Throttling", 429),
    ],
)
def test_transient_provider_service_states_are_unavailable(code: str, status: int) -> None:
    object_identity = identity()
    failure = client_error(code, status)
    fake = FakeClient()
    fake.head_result = failure
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).get_object_metadata(object_identity)
    assert caught.value.__cause__ is failure
    assert "unsafe provider detail" not in str(caught.value)


@pytest.mark.parametrize(
    "close_failure",
    [
        RuntimeError("raw close runtime detail"),
        client_error("InternalError", 500, "GetObject"),
    ],
)
def test_successful_download_ordinary_close_failure_is_typed(close_failure: Exception) -> None:
    payload = b"payload"
    body = SequenceBody([payload, b""], close_error=close_failure)
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectStorageOperationError) as caught:
        adapter(fake).download_verified_object(identity(payload), io.BytesIO())
    assert caught.value.__cause__ is close_failure
    assert body.close_count == 1
    assert "raw close" not in str(caught.value) and "unsafe provider detail" not in str(caught.value)


def test_integrity_primary_survives_runtime_close_failure() -> None:
    payload = b"payload"
    body = SequenceBody([b"short", b""], close_error=RuntimeError("raw close detail"))
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).download_verified_object(identity(payload), io.BytesIO())
    assert body.close_count == 1
    assert len(caught.value.__notes__) == 1
    assert "cleanup failed" in caught.value.__notes__[0]


def test_streaming_primary_survives_runtime_close_failure() -> None:
    payload = b"payload"
    streaming = ResponseStreamingError(error="raw stream detail")
    body = SequenceBody([b"part", streaming], close_error=RuntimeError("raw close detail"))
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectStorageUnavailableError) as caught:
        adapter(fake).download_verified_object(identity(payload), io.BytesIO())
    assert caught.value.__cause__ is streaming
    assert body.close_count == 1
    assert len(caught.value.__notes__) == 1
    assert "cleanup failed" in caught.value.__notes__[0]


class WriteResultSink:
    def __init__(self, result: Any = None, failure: Exception | None = None) -> None:
        self.result = result
        self.failure = failure
        self.payload = bytearray()

    def write(self, data: bytes) -> Any:
        if self.failure is not None:
            raise self.failure
        self.payload.extend(data)
        return self.result


@pytest.mark.parametrize("failure", [TypeError("raw type detail"), OSError("raw I/O detail")])
def test_sink_write_contract_exceptions_are_integrity_errors(failure: Exception) -> None:
    payload = b"payload"
    body = FakeBody(payload)
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).download_verified_object(
            identity(payload), WriteResultSink(failure=failure)
        )
    assert caught.value.__cause__ is failure
    assert type(failure).__name__ not in str(caught.value)
    assert body.close_count == 1


def test_text_sink_type_error_is_typed_and_body_closes() -> None:
    payload = b"payload"
    body = FakeBody(payload)
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectIntegrityError) as caught:
        adapter(fake).download_verified_object(identity(payload), io.StringIO())  # type: ignore[arg-type]
    assert isinstance(caught.value.__cause__, TypeError)
    assert "string argument" not in str(caught.value)
    assert body.close_count == 1


@pytest.mark.parametrize("write_result", [None, 7])
def test_sink_accepts_none_or_exact_integer_count(write_result: int | None) -> None:
    payload = b"payload"
    body = FakeBody(payload)
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    sink = WriteResultSink(result=write_result)
    metadata = adapter(fake).download_verified_object(identity(payload), sink)
    assert metadata.size_bytes == 7 and bytes(sink.payload) == payload
    assert body.close_count == 1


@pytest.mark.parametrize("write_result", [True, 7.0, "7", -1, 0, 6, 8])
def test_sink_rejects_noninteger_or_inexact_write_count(write_result: Any) -> None:
    payload = b"payload"
    body = FakeBody(payload)
    fake = FakeClient()
    fake.get_result = provider_metadata(identity(payload), payload, body=body)
    with pytest.raises(ObjectIntegrityError):
        adapter(fake).download_verified_object(
            identity(payload), WriteResultSink(result=write_result)
        )
    assert body.close_count == 1


def test_public_contract_annotations_are_provider_neutral() -> None:
    source = inspect.getsource(__import__("app.contracts.object_storage", fromlist=["*"]))
    assert "boto3" not in source and "botocore" not in source and "StreamingBody" not in source


def test_production_modules_obey_architecture_boundaries() -> None:
    root = Path(__file__).parents[1]
    source = "\n".join(
        (root / relative).read_text(encoding="utf-8")
        for relative in ("app/contracts/object_storage.py", "app/storage/s3_object_storage.py")
    ).lower()
    forbidden = (
        "fastapi",
        "uploadfile",
        "sqlalchemy",
        "alembic",
        "dataset_registry_repository",
        "dataset_registry_service",
        "base.metadata.create_all",
        "requests",
        "httpx",
        "minio sdk",
        "aioboto3",
        "s3transfer",
        "upload_file",
        "download_file",
    )
    assert not [term for term in forbidden if term in source]
