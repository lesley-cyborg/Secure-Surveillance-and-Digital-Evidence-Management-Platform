from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from app.modules.evidence.errors import (
    EvidenceStorageUnavailableError,
)
from app.modules.evidence.minio_storage import (
    MinioEvidenceObjectStorage,
)
from minio import Minio
from urllib3.exceptions import (
    HTTPError as Urllib3HTTPError,
)

TransportExceptionFactory = Callable[
    [str],
    Exception,
]


def create_storage() -> MinioEvidenceObjectStorage:
    client = Minio(
        endpoint="127.0.0.1:9000",
        access_key="test-access-key",
        secret_key="test-secret-key",
        secure=False,
    )

    return MinioEvidenceObjectStorage(
        client=client,
        bucket="evidence",
        require_versioning=False,
    )


@pytest.fixture(
    params=[
        Urllib3HTTPError,
        OSError,
    ],
    ids=[
        "urllib3-http-error",
        "os-error",
    ],
)
def transport_exception_factory(
    request: pytest.FixtureRequest,
) -> TransportExceptionFactory:
    exception_type = cast(
        type[Exception],
        request.param,
    )

    def factory(
        message: str,
    ) -> Exception:
        return exception_type(message)

    return factory


@pytest.mark.asyncio
async def test_readiness_transport_failure_is_translated(
    monkeypatch: pytest.MonkeyPatch,
    transport_exception_factory: (TransportExceptionFactory),
) -> None:
    storage = create_storage()

    def fail_bucket_exists(
        self: Minio,
        bucket_name: str,
    ) -> bool:
        del (
            self,
            bucket_name,
        )

        raise transport_exception_factory("forced readiness transport failure")

    monkeypatch.setattr(
        Minio,
        "bucket_exists",
        fail_bucket_exists,
    )

    with pytest.raises(
        EvidenceStorageUnavailableError,
        match="storage readiness check",
    ) as exception_info:
        await storage.ensure_ready()

    assert isinstance(
        exception_info.value.__cause__,
        (
            Urllib3HTTPError,
            OSError,
        ),
    )


@pytest.mark.asyncio
async def test_upload_transport_failure_is_translated(
    monkeypatch: pytest.MonkeyPatch,
    transport_exception_factory: (TransportExceptionFactory),
) -> None:
    storage = create_storage()

    def bucket_exists(
        self: Minio,
        bucket_name: str,
    ) -> bool:
        del (
            self,
            bucket_name,
        )

        return True

    def fail_put_object(
        self: Minio,
        **kwargs: object,
    ) -> object:
        del (
            self,
            kwargs,
        )

        raise transport_exception_factory("forced upload transport failure")

    monkeypatch.setattr(
        Minio,
        "bucket_exists",
        bucket_exists,
    )

    monkeypatch.setattr(
        Minio,
        "put_object",
        fail_put_object,
    )

    with pytest.raises(
        EvidenceStorageUnavailableError,
        match="object upload",
    ) as exception_info:
        await storage.put_object(
            object_key=("transport-test/upload.sspe"),
            payload=b"encrypted-payload",
            content_type=("application/octet-stream"),
        )

    assert isinstance(
        exception_info.value.__cause__,
        (
            Urllib3HTTPError,
            OSError,
        ),
    )


@pytest.mark.asyncio
async def test_retrieval_transport_failure_is_translated(
    monkeypatch: pytest.MonkeyPatch,
    transport_exception_factory: (TransportExceptionFactory),
) -> None:
    storage = create_storage()

    def fail_get_object(
        self: Minio,
        **kwargs: object,
    ) -> object:
        del (
            self,
            kwargs,
        )

        raise transport_exception_factory("forced retrieval transport failure")

    monkeypatch.setattr(
        Minio,
        "get_object",
        fail_get_object,
    )

    with pytest.raises(
        EvidenceStorageUnavailableError,
        match="object retrieval",
    ) as exception_info:
        await storage.get_object(
            object_key=("transport-test/get.sspe"),
            version_id="version-1",
        )

    assert isinstance(
        exception_info.value.__cause__,
        (
            Urllib3HTTPError,
            OSError,
        ),
    )


@pytest.mark.asyncio
async def test_stat_transport_failure_is_translated(
    monkeypatch: pytest.MonkeyPatch,
    transport_exception_factory: (TransportExceptionFactory),
) -> None:
    storage = create_storage()

    def fail_stat_object(
        self: Minio,
        **kwargs: object,
    ) -> object:
        del (
            self,
            kwargs,
        )

        raise transport_exception_factory("forced stat transport failure")

    monkeypatch.setattr(
        Minio,
        "stat_object",
        fail_stat_object,
    )

    with pytest.raises(
        EvidenceStorageUnavailableError,
        match="object stat",
    ) as exception_info:
        await storage.stat_object(
            object_key=("transport-test/stat.sspe"),
            version_id="version-1",
        )

    assert isinstance(
        exception_info.value.__cause__,
        (
            Urllib3HTTPError,
            OSError,
        ),
    )


@pytest.mark.asyncio
async def test_compensation_transport_failure_is_translated(
    monkeypatch: pytest.MonkeyPatch,
    transport_exception_factory: (TransportExceptionFactory),
) -> None:
    storage = create_storage()

    def fail_remove_object(
        self: Minio,
        **kwargs: object,
    ) -> object:
        del (
            self,
            kwargs,
        )

        raise transport_exception_factory("forced compensation transport failure")

    monkeypatch.setattr(
        Minio,
        "remove_object",
        fail_remove_object,
    )

    with pytest.raises(
        EvidenceStorageUnavailableError,
        match=("compensating object deletion"),
    ) as exception_info:
        await storage.delete_for_compensation(
            object_key=("transport-test/compensation.sspe"),
            version_id="version-1",
        )

    assert isinstance(
        exception_info.value.__cause__,
        (
            Urllib3HTTPError,
            OSError,
        ),
    )
