from __future__ import annotations

from collections.abc import AsyncIterator

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from httpx import (
    ASGITransport,
    AsyncClient,
)

from api.main import create_app
from config.settings import Settings
from detection.detector import FrameArray
from detection.model_registry import (
    ModelRegistry,
)
from detection.schemas import (
    DeviceType,
    ModelIdentity,
    PixelBoundingBox,
    RawDetection,
)


class FakeDetector:
    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(
            name="fake-security-detector",
            version="1.0.0",
            device=DeviceType.CPU,
            labels=(
                "person",
                "vehicle",
            ),
        )

    @property
    def is_ready(self) -> bool:
        return True

    def detect(
        self,
        frame: FrameArray,
    ) -> tuple[RawDetection, ...]:
        height, width = frame.shape[:2]

        return (
            RawDetection(
                class_id=0,
                label="person",
                confidence=0.95,
                bounding_box=PixelBoundingBox(
                    x_min=width * 0.25,
                    y_min=height * 0.25,
                    x_max=width * 0.75,
                    y_max=height * 0.75,
                ),
            ),
            RawDetection(
                class_id=1,
                label="vehicle",
                confidence=0.25,
                bounding_box=PixelBoundingBox(
                    x_min=10,
                    y_min=10,
                    x_max=40,
                    y_max=40,
                ),
            ),
        )


def _settings(
    *,
    maximum_upload_bytes: int = (1_000_000),
) -> Settings:
    return Settings(
        environment="test",
        maximum_upload_bytes=(maximum_upload_bytes),
        maximum_image_width=1920,
        maximum_image_height=1080,
        maximum_image_pixels=2_073_600,
        upload_chunk_size=128,
    )


def _registry_with_fake_model() -> ModelRegistry:
    registry = ModelRegistry()

    registry.register(
        FakeDetector(),
        make_default=True,
    )

    return registry


def _create_test_app(
    *,
    maximum_upload_bytes: int = (1_000_000),
    include_model: bool = True,
) -> FastAPI:
    registry = _registry_with_fake_model() if include_model else ModelRegistry()

    return create_app(
        settings=_settings(maximum_upload_bytes=(maximum_upload_bytes)),
        registry=registry,
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    application = _create_test_app()

    transport = ASGITransport(app=application)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client


def _encoded_jpeg() -> bytes:
    image = np.zeros(
        (100, 200, 3),
        dtype=np.uint8,
    )

    success, encoded = cv2.imencode(
        ".jpg",
        image,
    )

    assert success is True

    return encoded.tobytes()


@pytest.mark.asyncio
async def test_health_reports_ready_model(
    client: AsyncClient,
) -> None:
    response = await client.get("/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "healthy"
    assert body["registered_models"] == 1
    assert body["ready_models"] == 1
    assert body["environment"] == "test"


@pytest.mark.asyncio
async def test_model_list_reports_registered_model(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/models")

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 1
    assert body["items"][0]["model"]["name"] == "fake-security-detector"
    assert body["items"][0]["model"]["version"] == "1.0.0"
    assert body["items"][0]["is_ready"] is True


@pytest.mark.asyncio
async def test_image_detection_uses_fake_model(
    client: AsyncClient,
) -> None:
    correlation_id = "e4182d5e-f315-43cc-84e4-a16cc3275adb"

    response = await client.post(
        "/api/v1/detect/image",
        headers={"X-Correlation-ID": (correlation_id)},
        files={
            "file": (
                "camera-frame.jpg",
                _encoded_jpeg(),
                "image/jpeg",
            )
        },
        data={
            "confidence_threshold": "0.5",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == correlation_id

    body = response.json()

    assert body["correlation_id"] == (correlation_id)
    assert body["model"]["name"] == ("fake-security-detector")
    assert body["frame"]["width"] == 200
    assert body["frame"]["height"] == 100
    assert len(body["detections"]) == 1

    detection = body["detections"][0]

    assert detection["label"] == "person"
    assert detection["bounding_box"]["x_min"] == pytest.approx(0.25)
    assert detection["bounding_box"]["y_min"] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_image_analysis_uses_bounded_upload_and_correlation_id(
    client: AsyncClient,
) -> None:
    correlation_id = "2c66f4b3-4b33-4c6c-a5b9-bc3c34c3a85e"

    response = await client.post(
        "/api/v1/analyze/image",
        headers={"X-Correlation-ID": correlation_id},
        files={
            "file": (
                "camera-frame.jpg",
                _encoded_jpeg(),
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.json()["ocr"] == []
    assert response.json()["faces"] == []


@pytest.mark.asyncio
async def test_image_analysis_rejects_oversized_upload() -> None:
    application = _create_test_app(maximum_upload_bytes=10)

    transport = ASGITransport(app=application)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/analyze/image",
            headers={"X-Correlation-ID": "f2a4a06b-2b22-4f66-9a45-3cfaa91cd5fc"},
            files={
                "file": (
                    "camera-frame.jpg",
                    _encoded_jpeg(),
                    "image/jpeg",
                )
            },
        )

    assert response.status_code == 413
    assert response.headers["X-Correlation-ID"] == (
        "f2a4a06b-2b22-4f66-9a45-3cfaa91cd5fc"
    )
    assert response.json()["error_code"] == "FrameTooLargeError"


@pytest.mark.asyncio
async def test_unsupported_media_returns_415(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/detect/image",
        files={
            "file": (
                "camera-frame.gif",
                b"GIF89a",
                "image/gif",
            )
        },
    )

    assert response.status_code == 415

    body = response.json()

    assert body["error_code"] == ("UnsupportedMediaTypeError")
    assert body["correlation_id"] is not None


@pytest.mark.asyncio
async def test_corrupt_image_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/detect/image",
        files={
            "file": (
                "camera-frame.jpg",
                b"\xff\xd8\xffcorrupt",
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error_code"] == ("InvalidFrameError")
    assert body["correlation_id"] is not None


@pytest.mark.asyncio
async def test_oversized_upload_returns_413() -> None:
    application = _create_test_app(
        maximum_upload_bytes=10,
    )

    transport = ASGITransport(app=application)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/detect/image",
            files={
                "file": (
                    "camera-frame.jpg",
                    _encoded_jpeg(),
                    "image/jpeg",
                )
            },
        )

    assert response.status_code == 413

    body = response.json()

    assert body["error_code"] == ("FrameTooLargeError")


@pytest.mark.asyncio
async def test_missing_default_model_returns_503() -> None:
    application = _create_test_app(
        include_model=False,
    )

    transport = ASGITransport(app=application)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/detect/image",
            files={
                "file": (
                    "camera-frame.jpg",
                    _encoded_jpeg(),
                    "image/jpeg",
                )
            },
        )

    assert response.status_code == 503

    body = response.json()

    assert body["error_code"] == ("DefaultDetectorNotConfiguredError")
    assert body["correlation_id"] is not None


@pytest.mark.asyncio
async def test_liveness_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "service": "secure-surveillance-ai-engine",
        "version": "0.1.0",
        "status": "alive",
    }
