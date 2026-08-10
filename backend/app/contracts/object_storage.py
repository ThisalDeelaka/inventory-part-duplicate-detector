from __future__ import annotations

import ipaddress
import math
import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from app.contracts.dataset_registry import DatasetArtifactKind


OBJECT_IO_CHUNK_SIZE_BYTES = 1_048_576
MAX_SINGLE_PUT_BYTES = 5_000_000_000

_BUCKET_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DNS_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class ObjectStorageError(Exception):
    """Base error for the provider-neutral object-storage boundary."""


class ObjectStorageConfigurationError(ObjectStorageError):
    pass


class ObjectStorageUnavailableError(ObjectStorageError):
    pass


class ObjectNotFoundError(ObjectStorageError):
    pass


class ObjectConflictError(ObjectStorageError):
    pass


class ObjectIntegrityError(ObjectStorageError):
    pass


class ObjectStorageOperationError(ObjectStorageError):
    pass


def _required_trimmed(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ObjectStorageConfigurationError(f"{name} must be a string")
    trimmed = value.strip()
    if not trimmed or any(ord(character) < 32 or ord(character) == 127 for character in trimmed):
        raise ObjectStorageConfigurationError(f"{name} is invalid")
    return trimmed


@dataclass(frozen=True, slots=True)
class ObjectStorageSettings:
    endpoint_url: str | None
    region: str
    bucket: str
    access_key_id: str | None = field(default=None, repr=False, compare=False)
    secret_access_key: str | None = field(default=None, repr=False, compare=False)
    session_token: str | None = field(default=None, repr=False, compare=False)
    verify_tls: bool = True
    addressing_style: str = "path"
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 60.0
    total_max_attempts: int = 3

    def __post_init__(self) -> None:
        region = _required_trimmed(self.region, "region")
        bucket = _required_trimmed(self.bucket, "bucket")
        if not _BUCKET_RE.fullmatch(bucket) or ".." in bucket:
            raise ObjectStorageConfigurationError("bucket is invalid")
        try:
            ipaddress.IPv4Address(bucket)
        except ipaddress.AddressValueError:
            pass
        else:
            raise ObjectStorageConfigurationError("bucket must not be an IPv4 address")

        endpoint = self.endpoint_url
        endpoint_is_loopback = False
        if endpoint is not None:
            if not isinstance(endpoint, str) or any(
                ord(character) < 32 or ord(character) == 127 for character in endpoint
            ):
                raise ObjectStorageConfigurationError("endpoint_url is invalid")
            endpoint = _required_trimmed(endpoint, "endpoint_url")
            try:
                parsed = urlsplit(endpoint)
                port = parsed.port
            except ValueError as exc:
                raise ObjectStorageConfigurationError("endpoint_url is invalid") from exc
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
                or parsed.netloc.endswith(":")
            ):
                raise ObjectStorageConfigurationError("endpoint_url is invalid")
            if port is not None and not 1 <= port <= 65535:
                raise ObjectStorageConfigurationError("endpoint_url port is invalid")

            hostname = parsed.hostname
            if "%" in hostname or "\\" in hostname:
                raise ObjectStorageConfigurationError("endpoint_url hostname is invalid")
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                try:
                    hostname.encode("ascii")
                except UnicodeEncodeError as exc:
                    raise ObjectStorageConfigurationError(
                        "endpoint_url hostname must be ASCII"
                    ) from exc
                labels = hostname.split(".")
                if (
                    len(hostname) > 253
                    or not labels
                    or any(not _DNS_LABEL_RE.fullmatch(label) for label in labels)
                    or ("." in hostname and all(character in "0123456789." for character in hostname))
                ):
                    raise ObjectStorageConfigurationError("endpoint_url hostname is invalid")
                normalized_hostname = hostname.lower()
                is_ipv6 = False
                endpoint_is_loopback = normalized_hostname == "localhost"
            else:
                normalized_hostname = str(address)
                is_ipv6 = isinstance(address, ipaddress.IPv6Address)
                endpoint_is_loopback = address.is_loopback

            netloc = f"[{normalized_hostname}]" if is_ipv6 else normalized_hostname
            if port is not None:
                netloc = f"{netloc}:{port}"
            endpoint = urlunsplit((parsed.scheme, netloc, "", "", ""))

        pair_present = self.access_key_id is not None and self.secret_access_key is not None
        if (self.access_key_id is None) != (self.secret_access_key is None):
            raise ObjectStorageConfigurationError("access key ID and secret key must be supplied together")
        if self.session_token is not None and not pair_present:
            raise ObjectStorageConfigurationError("session token requires an explicit credential pair")
        for value, name in (
            (self.access_key_id, "access_key_id"),
            (self.secret_access_key, "secret_access_key"),
            (self.session_token, "session_token"),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ObjectStorageConfigurationError(f"{name} is invalid")
        if not isinstance(self.verify_tls, bool):
            raise ObjectStorageConfigurationError("verify_tls must be a boolean")
        if not self.verify_tls and endpoint is None:
            raise ObjectStorageConfigurationError("verify_tls=False requires an explicit endpoint_url")
        if not self.verify_tls and not endpoint_is_loopback:
            raise ObjectStorageConfigurationError("verify_tls=False requires a loopback endpoint")
        if self.addressing_style not in {"path", "virtual"}:
            raise ObjectStorageConfigurationError("addressing_style must be path or virtual")
        for value, name in (
            (self.connect_timeout_seconds, "connect_timeout_seconds"),
            (self.read_timeout_seconds, "read_timeout_seconds"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ObjectStorageConfigurationError(f"{name} must be finite and positive")
        if isinstance(self.total_max_attempts, bool) or not isinstance(self.total_max_attempts, int) or self.total_max_attempts <= 0:
            raise ObjectStorageConfigurationError("total_max_attempts must be a positive integer")

        object.__setattr__(self, "endpoint_url", endpoint)
        object.__setattr__(self, "region", region)
        object.__setattr__(self, "bucket", bucket)


@dataclass(frozen=True, slots=True)
class ObjectArtifactIdentity:
    dataset_id: UUID
    dataset_version_id: UUID
    artifact_kind: DatasetArtifactKind
    artifact_ordinal: int
    content_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, UUID) or not isinstance(self.dataset_version_id, UUID):
            raise ObjectStorageConfigurationError("dataset IDs must be UUID instances")
        if not isinstance(self.artifact_kind, DatasetArtifactKind):
            raise ObjectStorageConfigurationError("artifact_kind is invalid")
        if isinstance(self.artifact_ordinal, bool) or not isinstance(self.artifact_ordinal, int) or not 0 <= self.artifact_ordinal <= 99_999_999:
            raise ObjectStorageConfigurationError("artifact_ordinal is out of range")
        if not isinstance(self.content_sha256, str) or not _SHA256_RE.fullmatch(self.content_sha256):
            raise ObjectStorageConfigurationError("content_sha256 must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class ObjectKey:
    bucket: str
    key: str
    uri: str
    identity: ObjectArtifactIdentity


@dataclass(frozen=True, slots=True)
class PutObjectRequest:
    identity: ObjectArtifactIdentity
    stream: object = field(repr=False, compare=False)
    expected_size_bytes: int
    media_type: str
    _entry_position: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ObjectArtifactIdentity):
            raise ObjectStorageConfigurationError("identity is invalid")
        if isinstance(self.expected_size_bytes, bool) or not isinstance(self.expected_size_bytes, int) or not 0 <= self.expected_size_bytes <= MAX_SINGLE_PUT_BYTES:
            raise ObjectStorageConfigurationError("expected_size_bytes is out of range")
        media_type = _required_trimmed(self.media_type, "media_type")
        if len(media_type) > 255:
            raise ObjectStorageConfigurationError("media_type is too long")
        try:
            if (
                not callable(getattr(self.stream, "read", None))
                or not callable(getattr(self.stream, "seek", None))
                or not callable(getattr(self.stream, "tell", None))
                or not callable(getattr(self.stream, "seekable", None))
            ):
                raise ObjectStorageConfigurationError(
                    "stream must be binary readable and seekable"
                )
            seekable = self.stream.seekable()
            position = self.stream.tell()
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            raise ObjectStorageConfigurationError("stream must be binary readable and seekable") from exc
        if seekable is not True or isinstance(position, bool) or not isinstance(position, int) or position < 0:
            raise ObjectStorageConfigurationError("stream entry position is invalid")
        object.__setattr__(self, "media_type", media_type)
        object.__setattr__(self, "_entry_position", position)

    @property
    def entry_position(self) -> int:
        return self._entry_position


@dataclass(frozen=True, slots=True)
class StoredObjectMetadata:
    object_key: ObjectKey
    size_bytes: int
    media_type: str
    etag: str
    version_id: str | None


@dataclass(frozen=True, slots=True)
class PutObjectResult:
    metadata: StoredObjectMetadata
    created: bool


class BinaryWritableSink(Protocol):
    def write(self, data: bytes) -> int | None: ...


class ObjectStorageClient(Protocol):
    def check_readiness(self) -> None: ...
    def put_verified_object(self, request: PutObjectRequest) -> PutObjectResult: ...
    def get_object_metadata(self, identity: ObjectArtifactIdentity) -> StoredObjectMetadata: ...
    def download_verified_object(self, identity: ObjectArtifactIdentity, sink: BinaryWritableSink) -> StoredObjectMetadata: ...


_ARTIFACT_SLUGS = {
    DatasetArtifactKind.SOURCE_CSV: "source-csv",
    DatasetArtifactKind.SCHEMA_PROFILE_JSON: "schema-profile-json",
    DatasetArtifactKind.CANONICAL_PARQUET: "canonical-parquet",
}


def build_object_key(bucket: str, identity: ObjectArtifactIdentity) -> ObjectKey:
    if not isinstance(identity, ObjectArtifactIdentity):
        raise ObjectStorageConfigurationError("identity is invalid")
    validated_bucket = ObjectStorageSettings(endpoint_url=None, region="validation", bucket=bucket).bucket
    key = (
        f"v1/datasets/{identity.dataset_id}/versions/{identity.dataset_version_id}/"
        f"artifacts/{_ARTIFACT_SLUGS[identity.artifact_kind]}/"
        f"{identity.artifact_ordinal:08d}/{identity.content_sha256}"
    )
    return ObjectKey(validated_bucket, key, f"s3://{validated_bucket}/{key}", identity)
