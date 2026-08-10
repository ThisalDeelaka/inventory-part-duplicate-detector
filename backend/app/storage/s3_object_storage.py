from __future__ import annotations

import hashlib
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionError as BotoConnectionError,
    CredentialRetrievalError,
    EndpointResolutionError,
    HTTPClientError,
    LoginError,
    MetadataRetrievalError,
    NoAuthTokenError,
    NoCredentialsError,
    PartialCredentialsError,
    SSOError,
    TokenRetrievalError,
    UnknownCredentialError,
    UnknownEndpointError,
)

from app.contracts.dataset_registry import DatasetArtifactKind
from app.contracts.object_storage import (
    OBJECT_IO_CHUNK_SIZE_BYTES,
    BinaryWritableSink,
    ObjectArtifactIdentity,
    ObjectConflictError,
    ObjectIntegrityError,
    ObjectKey,
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectStorageOperationError,
    ObjectStorageSettings,
    ObjectStorageUnavailableError,
    PutObjectRequest,
    PutObjectResult,
    StoredObjectMetadata,
    build_object_key,
)


_REQUIRED_METADATA_KEYS = frozenset(
    {"dataset-id", "dataset-version-id", "artifact-kind", "artifact-ordinal", "sha256"}
)
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NotFound", "404"})
_UNAVAILABLE_CODES = frozenset(
    {
        "AccessDenied",
        "AllAccessDisabled",
        "AuthorizationHeaderMalformed",
        "CredentialsNotSupported",
        "ExpiredToken",
        "InvalidAccessKeyId",
        "InvalidBucketName",
        "InvalidToken",
        "NoSuchBucket",
        "PermanentRedirect",
        "RequestExpired",
        "RequestTimeout",
        "RequestTimeoutException",
        "SignatureDoesNotMatch",
        "SlowDown",
        "Throttling",
        "ThrottlingException",
        "TokenRefreshRequired",
    }
)
_CONDITIONAL_CODES = frozenset({"PreconditionFailed", "ConditionalRequestConflict"})
_SAFE_PROVIDER_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_TRANSPORT_ERRORS = (
    BotoConnectionError,
    HTTPClientError,
    CredentialRetrievalError,
    EndpointResolutionError,
    LoginError,
    MetadataRetrievalError,
    NoAuthTokenError,
    NoCredentialsError,
    PartialCredentialsError,
    SSOError,
    TokenRetrievalError,
    UnknownCredentialError,
    UnknownEndpointError,
)


def _identity_metadata(identity: ObjectArtifactIdentity) -> dict[str, str]:
    return {
        "dataset-id": str(identity.dataset_id),
        "dataset-version-id": str(identity.dataset_version_id),
        "artifact-kind": identity.artifact_kind.value,
        "artifact-ordinal": str(identity.artifact_ordinal),
        "sha256": identity.content_sha256,
    }


class _CallerStreamHandoffError(Exception):
    def __init__(self, cause: OSError | TypeError | ValueError) -> None:
        super().__init__("caller stream handoff failed")
        self.cause = cause


class _PutObjectBody:
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def _call(self, method: str, *args: Any) -> Any:
        try:
            return getattr(self._stream, method)(*args)
        except (OSError, TypeError, ValueError) as exc:
            raise _CallerStreamHandoffError(exc) from None

    def read(self, size: int = -1) -> Any:
        return self._call("read", size)

    def seek(self, offset: int, whence: int = 0) -> Any:
        return self._call("seek", offset, whence)

    def tell(self) -> Any:
        return self._call("tell")

    def seekable(self) -> Any:
        return self._call("seekable")

    def readable(self) -> Any:
        readable = getattr(self._stream, "readable", None)
        return self._call("readable") if callable(readable) else True

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


class S3ObjectStorageClient:
    def __init__(
        self,
        settings: ObjectStorageSettings,
        *,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or boto3.client
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "service_name": "s3",
                "region_name": self._settings.region,
                "verify": self._settings.verify_tls,
                "config": Config(
                    connect_timeout=self._settings.connect_timeout_seconds,
                    read_timeout=self._settings.read_timeout_seconds,
                    retries={
                        "mode": "standard",
                        "total_max_attempts": self._settings.total_max_attempts,
                    },
                    s3={"addressing_style": self._settings.addressing_style},
                ),
            }
            if self._settings.endpoint_url is not None:
                kwargs["endpoint_url"] = self._settings.endpoint_url
            if self._settings.access_key_id is not None:
                kwargs["aws_access_key_id"] = self._settings.access_key_id
                kwargs["aws_secret_access_key"] = self._settings.secret_access_key
                if self._settings.session_token is not None:
                    kwargs["aws_session_token"] = self._settings.session_token
            try:
                self._client = self._client_factory(**kwargs)
            except _TRANSPORT_ERRORS as exc:
                raise ObjectStorageUnavailableError("S3 client is unavailable") from exc
            except BotoCoreError as exc:
                raise ObjectStorageOperationError("S3 client construction failed") from exc
        return self._client

    def check_readiness(self) -> None:
        try:
            self._get_client().head_bucket(Bucket=self._settings.bucket)
        except (ClientError, BotoCoreError) as exc:
            raise self._map_provider_error(
                "HeadBucket", None, exc, allow_not_found=False, bucket_readiness=True
            ) from exc

    def put_verified_object(self, request: PutObjectRequest) -> PutObjectResult:
        self._preflight(request)
        object_key = build_object_key(self._settings.bucket, request.identity)
        try:
            try:
                request.stream.seek(request.entry_position)
            except (OSError, TypeError, ValueError) as exc:
                raise ObjectIntegrityError(
                    f"upload stream failed before PutObject for {object_key.uri}"
                ) from exc
            try:
                self._get_client().put_object(
                    Bucket=object_key.bucket,
                    Key=object_key.key,
                    Body=_PutObjectBody(request.stream),
                    ContentLength=request.expected_size_bytes,
                    ContentType=request.media_type,
                    Metadata=_identity_metadata(request.identity),
                    IfNoneMatch="*",
                )
            except ClientError as exc:
                if self._is_conditional_failure(exc):
                    return self._resolve_conditional_failure(request, object_key, exc)
                raise self._map_provider_error("PutObject", object_key, exc, allow_not_found=False) from exc
            except BotoCoreError as exc:
                raise self._map_provider_error("PutObject", object_key, exc, allow_not_found=False) from exc
            except _CallerStreamHandoffError as exc:
                raise ObjectIntegrityError(
                    f"upload stream failed during PutObject for {object_key.uri}"
                ) from exc.cause
            except (OSError, TypeError, ValueError) as exc:
                raise ObjectStorageOperationError(
                    f"PutObject client operation failed for {object_key.uri}"
                ) from exc
        finally:
            self._restore_stream(request, sys.exception())

        try:
            metadata = self.get_object_metadata(request.identity)
        except ObjectNotFoundError as exc:
            raise ObjectIntegrityError(
                f"post-create metadata missing for {object_key.uri}"
            ) from exc
        try:
            self._require_put_parity(request, metadata)
        except ObjectConflictError as exc:
            raise ObjectIntegrityError(f"post-create metadata failed for {object_key.uri}") from exc
        return PutObjectResult(metadata=metadata, created=True)

    def get_object_metadata(self, identity: ObjectArtifactIdentity) -> StoredObjectMetadata:
        object_key = build_object_key(self._settings.bucket, identity)
        try:
            response = self._get_client().head_object(Bucket=object_key.bucket, Key=object_key.key)
        except (ClientError, BotoCoreError) as exc:
            raise self._map_provider_error("HeadObject", object_key, exc, allow_not_found=True) from exc
        return self._convert_metadata(response, object_key)

    def download_verified_object(
        self,
        identity: ObjectArtifactIdentity,
        sink: BinaryWritableSink,
    ) -> StoredObjectMetadata:
        if not callable(getattr(sink, "write", None)):
            raise ObjectIntegrityError("download sink must be binary writable")
        object_key = build_object_key(self._settings.bucket, identity)
        try:
            response = self._get_client().get_object(Bucket=object_key.bucket, Key=object_key.key)
        except (ClientError, BotoCoreError) as exc:
            raise self._map_provider_error("GetObject", object_key, exc, allow_not_found=True) from exc

        body = response.get("Body")
        if body is None:
            raise ObjectIntegrityError(f"GetObject returned an invalid body for {object_key.uri}")
        close = getattr(body, "close", None)
        if not callable(close):
            raise ObjectIntegrityError(f"GetObject body cannot be closed for {object_key.uri}")
        try:
            if not callable(getattr(body, "read", None)):
                raise ObjectIntegrityError(f"GetObject returned an invalid body for {object_key.uri}")
            metadata = self._convert_metadata(response, object_key)
            count = 0
            digest = hashlib.sha256()
            while True:
                try:
                    chunk = body.read(OBJECT_IO_CHUNK_SIZE_BYTES)
                except BotoCoreError as exc:
                    raise self._map_provider_error(
                        "GetObjectBody", object_key, exc, allow_not_found=False
                    ) from exc
                except TypeError as exc:
                    raise ObjectIntegrityError(
                        f"GetObject body has an invalid read contract for {object_key.uri}"
                    ) from exc
                except (OSError, ValueError) as exc:
                    raise ObjectStorageOperationError(
                        f"GetObject body read failed for {object_key.uri}"
                    ) from exc
                if not isinstance(chunk, bytes):
                    raise ObjectIntegrityError(f"GetObject returned a non-binary body for {object_key.uri}")
                if len(chunk) > OBJECT_IO_CHUNK_SIZE_BYTES:
                    raise ObjectIntegrityError(
                        f"GetObject body exceeded requested chunk size for {object_key.uri}"
                    )
                if not chunk:
                    break
                count += len(chunk)
                if count > metadata.size_bytes:
                    raise ObjectIntegrityError(f"GetObject exceeded declared length for {object_key.uri}")
                digest.update(chunk)
                try:
                    written = sink.write(chunk)
                except (OSError, TypeError, ValueError) as exc:
                    raise ObjectIntegrityError(
                        f"download sink write failed for {object_key.uri}"
                    ) from exc
                if written is not None and (
                    isinstance(written, bool)
                    or not isinstance(written, int)
                    or written != len(chunk)
                ):
                    raise ObjectIntegrityError(f"download sink accepted a partial write for {object_key.uri}")
            if count != metadata.size_bytes:
                raise ObjectIntegrityError(f"GetObject ended before declared length for {object_key.uri}")
            if digest.hexdigest() != identity.content_sha256:
                raise ObjectIntegrityError(f"GetObject digest mismatch for {object_key.uri}")
            return metadata
        finally:
            self._close_body(close, object_key, sys.exception())

    def _preflight(self, request: PutObjectRequest) -> None:
        remaining = request.expected_size_bytes
        digest = hashlib.sha256()
        try:
            request.stream.seek(request.entry_position)
            while remaining:
                requested_amount = min(OBJECT_IO_CHUNK_SIZE_BYTES, remaining)
                chunk = request.stream.read(requested_amount)
                if not isinstance(chunk, bytes):
                    raise ObjectIntegrityError("upload stream must return bytes")
                if len(chunk) > requested_amount:
                    raise ObjectIntegrityError("upload stream exceeded requested read size")
                if not chunk:
                    raise ObjectIntegrityError("upload stream ended before expected size")
                if len(chunk) > remaining:
                    raise ObjectIntegrityError("upload stream exceeded expected size")
                digest.update(chunk)
                remaining -= len(chunk)
            extra = request.stream.read(1)
            if not isinstance(extra, bytes):
                raise ObjectIntegrityError("upload stream must return bytes")
            if len(extra) > 1:
                raise ObjectIntegrityError("upload stream exceeded requested read size")
            if extra:
                raise ObjectIntegrityError("upload stream contains bytes beyond expected size")
            if digest.hexdigest() != request.identity.content_sha256:
                raise ObjectIntegrityError("upload stream digest mismatch")
        except (OSError, TypeError, ValueError) as exc:
            raise ObjectIntegrityError("upload stream could not be verified") from exc
        finally:
            self._restore_stream(request, sys.exception())

    @staticmethod
    def _restore_stream(request: PutObjectRequest, primary: BaseException | None) -> None:
        try:
            request.stream.seek(request.entry_position)
        except (OSError, TypeError, ValueError) as cleanup_error:
            if primary is not None:
                primary.add_note("Caller stream restoration failed after the primary operation failure.")
                return
            raise ObjectIntegrityError("caller stream position could not be restored") from cleanup_error

    @staticmethod
    def _close_body(
        close: Callable[[], Any],
        object_key: ObjectKey,
        primary: BaseException | None,
    ) -> None:
        try:
            close()
        except Exception as cleanup_error:
            if primary is not None:
                primary.add_note("Provider response body cleanup failed after the primary operation failure.")
                return
            raise ObjectStorageOperationError(
                f"GetObject body cleanup failed for {object_key.uri}"
            ) from cleanup_error

    def _resolve_conditional_failure(
        self,
        request: PutObjectRequest,
        object_key: ObjectKey,
        cause: ClientError,
    ) -> PutObjectResult:
        try:
            metadata = self.get_object_metadata(request.identity)
        except ObjectIntegrityError as exc:
            final = ObjectConflictError(f"immutable object conflicts at {object_key.uri}")
            final.add_note(f"Metadata comparison failed with {type(exc).__name__}.")
            raise final from cause
        except ObjectNotFoundError as exc:
            final = ObjectStorageOperationError(
                f"conditional PutObject could not resolve object at {object_key.uri}"
            )
            final.add_note(f"Follow-up metadata lookup failed with {type(exc).__name__}.")
            raise final from cause
        except ObjectStorageError as exc:
            final_type = (
                ObjectStorageUnavailableError
                if isinstance(exc, ObjectStorageUnavailableError)
                else ObjectStorageOperationError
            )
            final = final_type(f"conditional PutObject follow-up failed at {object_key.uri}")
            final.add_note(f"Follow-up metadata lookup failed with {type(exc).__name__}.")
            raise final from cause
        try:
            self._require_put_parity(request, metadata)
        except ObjectConflictError as exc:
            final = ObjectConflictError(f"immutable object conflicts at {object_key.uri}")
            final.add_note(f"Metadata comparison failed with {type(exc).__name__}.")
            raise final from cause
        return PutObjectResult(metadata=metadata, created=False)

    @staticmethod
    def _require_put_parity(request: PutObjectRequest, metadata: StoredObjectMetadata) -> None:
        if (
            metadata.object_key.identity != request.identity
            or metadata.size_bytes != request.expected_size_bytes
            or metadata.media_type != request.media_type
        ):
            raise ObjectConflictError(f"immutable object metadata conflicts at {metadata.object_key.uri}")

    @staticmethod
    def _convert_metadata(response: Mapping[str, Any], object_key: ObjectKey) -> StoredObjectMetadata:
        metadata = response.get("Metadata")
        if not isinstance(metadata, Mapping) or set(metadata) != _REQUIRED_METADATA_KEYS:
            raise ObjectIntegrityError(f"object metadata key set is invalid for {object_key.uri}")
        expected = _identity_metadata(object_key.identity)
        if any(not isinstance(value, str) for value in metadata.values()) or dict(metadata) != expected:
            raise ObjectIntegrityError(f"object identity metadata is invalid for {object_key.uri}")
        size = response.get("ContentLength")
        media_type = response.get("ContentType")
        etag = response.get("ETag")
        version_id = response.get("VersionId")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ObjectIntegrityError(f"object length is invalid for {object_key.uri}")
        if not isinstance(media_type, str) or not media_type.strip() or media_type != media_type.strip() or len(media_type) > 255:
            raise ObjectIntegrityError(f"object content type is invalid for {object_key.uri}")
        if not isinstance(etag, str) or not etag:
            raise ObjectIntegrityError(f"object ETag is invalid for {object_key.uri}")
        if version_id is not None and (not isinstance(version_id, str) or not version_id):
            raise ObjectIntegrityError(f"object version ID is invalid for {object_key.uri}")
        return StoredObjectMetadata(object_key, size, media_type, etag, version_id)

    @staticmethod
    def _error_parts(error: ClientError) -> tuple[str, int | None]:
        response = error.response if isinstance(error.response, dict) else {}
        error_details = response.get("Error") if isinstance(response.get("Error"), dict) else {}
        metadata = response.get("ResponseMetadata") if isinstance(response.get("ResponseMetadata"), dict) else {}
        raw_code = error_details.get("Code")
        code = (
            raw_code
            if isinstance(raw_code, str) and _SAFE_PROVIDER_CODE_RE.fullmatch(raw_code)
            else "Unknown"
        )
        status = metadata.get("HTTPStatusCode")
        return code, status if isinstance(status, int) and not isinstance(status, bool) else None

    @classmethod
    def _is_conditional_failure(cls, error: ClientError) -> bool:
        code, status = cls._error_parts(error)
        if code in _UNAVAILABLE_CODES or cls._is_unavailable_status(status):
            return False
        if code in _CONDITIONAL_CODES:
            return status in {None, 409, 412}
        return code == "Unknown" and status in {409, 412}

    @staticmethod
    def _is_unavailable_status(status: int | None) -> bool:
        return status in {301, 307, 308, 401, 403, 408, 429} or (
            status is not None and 500 <= status <= 599
        )

    @classmethod
    def _map_provider_error(
        cls,
        operation: str,
        object_key: ObjectKey | None,
        error: ClientError | BotoCoreError,
        *,
        allow_not_found: bool,
        bucket_readiness: bool = False,
    ) -> Exception:
        location = object_key.uri if object_key is not None else "configured bucket"
        if isinstance(error, _TRANSPORT_ERRORS):
            return ObjectStorageUnavailableError(f"{operation} unavailable for {location}")
        if isinstance(error, ClientError):
            code, status = cls._error_parts(error)
            safe = f"{operation} failed for {location} (code={code}, status={status})"
            if (
                code in _UNAVAILABLE_CODES
                or cls._is_unavailable_status(status)
                or (bucket_readiness and status == 404)
            ):
                return ObjectStorageUnavailableError(safe)
            if allow_not_found and (
                (code in _NOT_FOUND_CODES and status in {None, 404})
                or (code == "Unknown" and status == 404)
            ):
                return ObjectNotFoundError(safe)
            return ObjectStorageOperationError(safe)
        if isinstance(error, BotoCoreError):
            return ObjectStorageOperationError(f"{operation} provider operation failed for {location}")
        return ObjectStorageOperationError(f"{operation} failed for {location}")
