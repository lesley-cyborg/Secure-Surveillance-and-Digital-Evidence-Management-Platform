from __future__ import annotations

from uuid import uuid4

import cv2
import numpy as np
import pytest

from detection.detector import FrameArray
from detection.exceptions import (
    DetectorUnavailableError,
    InferenceError,
    InvalidConfidenceError,
)
from detection.frame_decoder import FrameDecoder
from detection.frame_processor import (
    FrameProcessor,
)
from detection.model_registry import (
    ModelRegistry,
)
from detection.schemas import (
    DeviceType,
    MediaType,
    ModelIdentity,
    PixelBoundingBox,
    RawDetection,
)


class FakeDetector:
    def __init__(
        self,
        *,
        ready: bool = True,
        fail: bool = False,
    ) -> None:
        self._ready = ready
        self._fail = fail

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(
            name="fake-detector",
            version="1.0.0",
            device=DeviceType.CPU,
            labels=("person", "vehicle"),
        )

    @property
    def is_ready(self) -> bool:
        return self._ready

    def detect(
        self,
        frame: FrameArray,
    ) -> tuple[RawDetection, ...]:
        del frame

        if self._fail:
            raise RuntimeError("Fake inference failure")

        return (
            RawDetection(
                class_id=0,
                label="person",
                confidence=0.9,
                bounding_box=PixelBoundingBox(
                    x_min=50,
                    y_min=25,
                    x_max=150,
                    y_max=75,
                ),
            ),
            RawDetection(
                class_id=1,
                label="vehicle",
                confidence=0.2,
                bounding_box=PixelBoundingBox(
                    x_min=10,
                    y_min=10,
                    x_max=40,
                    y_max=40,
                ),
            ),
        )


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


def _processor(
    detector: FakeDetector,
) -> FrameProcessor:
    registry = ModelRegistry()
    registry.register(detector)

    decoder = FrameDecoder(
        maximum_bytes=1_000_000,
        maximum_width=1920,
        maximum_height=1080,
        maximum_pixels=2_073_600,
    )

    return FrameProcessor(
        registry=registry,
        decoder=decoder,
    )


@pytest.mark.asyncio
async def test_processor_filters_and_normalises_detections() -> None:
    processor = _processor(FakeDetector())

    correlation_id = uuid4()

    result = await processor.process_image(
        payload=_encoded_jpeg(),
        media_type=MediaType.JPEG,
        confidence_threshold=0.5,
        correlation_id=correlation_id,
    )

    assert result.correlation_id == (correlation_id)
    assert result.model.name == ("fake-detector")
    assert result.model.version == "1.0.0"
    assert result.inference_duration_ms >= 0

    assert len(result.detections) == 1

    detection = result.detections[0]

    assert detection.label == "person"
    assert detection.bounding_box.x_min == (pytest.approx(0.25))
    assert detection.bounding_box.y_min == (pytest.approx(0.25))
    assert detection.bounding_box.x_max == (pytest.approx(0.75))
    assert detection.bounding_box.y_max == (pytest.approx(0.75))


@pytest.mark.asyncio
async def test_processor_rejects_invalid_threshold() -> None:
    processor = _processor(FakeDetector())

    with pytest.raises(InvalidConfidenceError):
        await processor.process_image(
            payload=_encoded_jpeg(),
            media_type=MediaType.JPEG,
            confidence_threshold=1.5,
        )


@pytest.mark.asyncio
async def test_processor_rejects_unavailable_detector() -> None:
    processor = _processor(FakeDetector(ready=False))

    with pytest.raises(DetectorUnavailableError):
        await processor.process_image(
            payload=_encoded_jpeg(),
            media_type=MediaType.JPEG,
        )


@pytest.mark.asyncio
async def test_processor_wraps_model_failure() -> None:
    processor = _processor(FakeDetector(fail=True))

    correlation_id = uuid4()

    with pytest.raises(InferenceError) as exception:
        await processor.process_image(
            payload=_encoded_jpeg(),
            media_type=MediaType.JPEG,
            correlation_id=correlation_id,
        )

    assert exception.value.correlation_id == correlation_id
