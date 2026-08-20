from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from typing import NoReturn
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import (
    HTTPError as Urllib3HTTPError,
)

from app.core.config import Settings
from app.modules.evidence.errors import (
    EvidenceObjectNotFoundError,
    EvidenceStorageConfigurationError,
    EvidenceStorageIntegrityError,
    EvidenceStorageUnavailableError,
)
from app.modules.evidence.storage import (
    StoredEvidenceObject,
)


@dataclass(
    frozen=True,
    slots=True,
)
class MinioEndpoint:
    endpoint: str
    secure: bool


def parse_minio_endpoint(
    value: str,
) -> MinioEndpoint:
    normalized = value.strip()

    if not normalized:
        raise ValueError("MinIO endpoint must not be empty")

    candidate = normalized if "://" in normalized else f"http://{normalized}"

    parsed = urlparse(candidate)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        raise ValueError("MinIO endpoint must use http or https")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("MinIO credentials must not be embedded in the endpoint")

    if parsed.hostname is None:
        raise ValueError("MinIO endpoint hostname is missing")

    if parsed.path not in {
        "",
        "/",
    }:
        raise ValueError("MinIO endpoint must not contain a URL path")

    if parsed.query or parsed.fragment:
        raise ValueError("MinIO endpoint must not contain query parameters or fragments")

    try:
        port = parsed.port
    except ValueError as exception:
        raise ValueError("MinIO endpoint port is invalid") from exception

    host = parsed.hostname

    if ":" in host:
        host = f"[{host}]"

    endpoint = f"{host}:{port}" if port is not None else host

    return MinioEndpoint(
        endpoint=endpoint,
        secure=parsed.scheme == "https",
    )


class MinioEvidenceObjectStorage:
    """MinIO adapter for encrypted forensic objects."""

    def __init__(
        self,
        *,
        client: Minio,
        bucket: str,
        require_versioning: bool = True,
    ) -> None:
        if not bucket.strip():
            raise ValueError("bucket must not be empty")

        self._client = client
        self.bucket = bucket.strip()
        self.require_versioning = require_versioning

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        bucket: str | None = None,
        require_versioning: bool = True,
    ) -> MinioEvidenceObjectStorage:
        connection = parse_minio_endpoint(settings.minio_endpoint)

        client = Minio(
            endpoint=connection.endpoint,
            access_key=(settings.minio_access_key.get_secret_value()),
            secret_key=(settings.minio_secret_key.get_secret_value()),
            secure=connection.secure,
        )

        return cls(
            client=client,
            bucket=(bucket or settings.minio_bucket),
            require_versioning=(require_versioning),
        )

    async def ensure_ready(
        self,
    ) -> None:
        try:
            exists = await asyncio.to_thread(
                self._client.bucket_exists,
                self.bucket,
            )

            if not exists:
                raise (
                    EvidenceStorageConfigurationError("Configured evidence bucket does not exist")
                )

            if not self.require_versioning:
                return

            configuration = await asyncio.to_thread(
                self._client.get_bucket_versioning,
                self.bucket,
            )

            status = configuration.status or ""

            if status.casefold() != "enabled":
                raise (
                    EvidenceStorageConfigurationError("Evidence bucket versioning is not enabled")
                )

        except S3Error as exception:
            self._raise_s3_error(
                exception,
                operation="storage readiness check",
            )

        except (
            Urllib3HTTPError,
            OSError,
        ) as exception:
            self._raise_transport_error(
                exception,
                operation="storage readiness check",
            )

    async def put_object(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> StoredEvidenceObject:
        if not object_key.strip():
            raise ValueError("object_key must not be empty")

        if not payload:
            raise ValueError("payload must not be empty")

        if not content_type.strip():
            raise ValueError("content_type must not be empty")

        await self.ensure_ready()

        operation = partial(
            self._client.put_object,
            bucket_name=self.bucket,
            object_name=object_key,
            data=BytesIO(payload),
            length=len(payload),
            content_type=content_type,
            metadata=dict(metadata or {}),
        )

        try:
            result = await asyncio.to_thread(operation)
        except (
            Urllib3HTTPError,
            OSError,
        ) as exception:
            self._raise_transport_error(
                exception,
                operation="object upload",
            )

        version_id = result.version_id or None

        if self.require_versioning and version_id is None:
            raise (EvidenceStorageConfigurationError("MinIO did not return an object version ID"))

        stored = await self.stat_object(
            object_key=object_key,
            version_id=version_id,
        )

        if stored.size_bytes != len(payload):
            raise EvidenceStorageIntegrityError(
                "Stored evidence size does not match uploaded payload"
            )

        return stored

    async def get_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> bytes:
        try:
            return await asyncio.to_thread(
                self._get_object_sync,
                object_key,
                version_id,
            )
        except S3Error as exception:
            self._raise_s3_error(
                exception,
                operation="object retrieval",
            )

        except (
            Urllib3HTTPError,
            OSError,
        ) as exception:
            self._raise_transport_error(
                exception,
                operation="object retrieval",
            )

    async def stat_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> StoredEvidenceObject:
        operation = partial(
            self._client.stat_object,
            bucket_name=self.bucket,
            object_name=object_key,
            version_id=version_id,
        )

        try:
            result = await asyncio.to_thread(operation)
        except S3Error as exception:
            self._raise_s3_error(
                exception,
                operation="object stat",
            )

        except (
            Urllib3HTTPError,
            OSError,
        ) as exception:
            self._raise_transport_error(
                exception,
                operation="object stat",
            )

        size_bytes = result.size

        if size_bytes is None:
            raise EvidenceStorageIntegrityError("MinIO did not return an object size")

        return StoredEvidenceObject(
            bucket=self.bucket,
            object_key=object_key,
            version_id=(result.version_id or None),
            etag=result.etag or None,
            size_bytes=size_bytes,
            content_type=(result.content_type or None),
        )

    async def delete_for_compensation(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> None:
        operation = partial(
            self._client.remove_object,
            bucket_name=self.bucket,
            object_name=object_key,
            version_id=version_id,
        )

        try:
            await asyncio.to_thread(operation)
        except S3Error as exception:
            self._raise_s3_error(
                exception,
                operation=("compensating object deletion"),
            )

        except (
            Urllib3HTTPError,
            OSError,
        ) as exception:
            self._raise_transport_error(
                exception,
                operation=("compensating object deletion"),
            )

    def _get_object_sync(
        self,
        object_key: str,
        version_id: str | None,
    ) -> bytes:
        response = self._client.get_object(
            bucket_name=self.bucket,
            object_name=object_key,
            version_id=version_id,
        )

        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    @staticmethod
    def _raise_s3_error(
        exception: S3Error,
        *,
        operation: str,
    ) -> NoReturn:
        if exception.code in {
            "NoSuchKey",
            "NoSuchObject",
            "NoSuchVersion",
        }:
            raise EvidenceObjectNotFoundError(
                f"Evidence object was not found during {operation}"
            ) from exception

        if exception.code == "NoSuchBucket":
            raise EvidenceStorageConfigurationError(
                "Configured evidence bucket does not exist"
            ) from exception

        if exception.code in {
            "AccessDenied",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
        }:
            raise EvidenceStorageConfigurationError(
                "MinIO credentials or permissions are invalid"
            ) from exception

        raise EvidenceStorageUnavailableError(f"MinIO failed during {operation}") from exception

    @staticmethod
    def _raise_transport_error(
        exception: Exception,
        *,
        operation: str,
    ) -> NoReturn:
        raise EvidenceStorageUnavailableError(
            f"MinIO transport failed during {operation}"
        ) from exception
