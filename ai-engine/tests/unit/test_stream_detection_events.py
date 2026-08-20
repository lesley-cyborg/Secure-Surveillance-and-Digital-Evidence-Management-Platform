from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from streaming.detection_events import (
    StreamBoundingBox,
    StreamDetection,
    StreamDetectionEvent,
    StreamModelIdentity,
)


def create_event() -> StreamDetectionEvent:
    captured_at = datetime.now(UTC)

    return StreamDetectionEvent(
        correlation_id=uuid4(),
        camera_id="camera-001",
        frame_sequence_number=42,
        captured_at=captured_at,
        received_at=(
            captured_at
            + timedelta(milliseconds=20)
        ),
        processed_at=(
            captured_at
            + timedelta(milliseconds=50)
        ),
        model=StreamModelIdentity(
            name="surveillance-yolo",
            version="yolo26n-coco",
            device="cpu",
        ),
        detections=(
            StreamDetection(
                class_id=0,
                label=" person ",
                confidence=0.91,
                bounding_box=StreamBoundingBox(
                    x_min=0.1,
                    y_min=0.2,
                    x_max=0.7,
                    y_max=0.9,
                ),
            ),
        ),
        inference_duration_ms=12.5,
    )


def test_event_preserves_camera_detection_context() -> None:
    event = create_event()

    assert event.camera_id == "camera-001"
    assert event.frame_sequence_number == 42
    assert event.model.name == "surveillance-yolo"
    assert event.model.version == "yolo26n-coco"
    assert event.model.device == "cpu"

    assert event.detection_count == 1
    assert event.contains_detections is True

    detection = event.detections[0]

    assert detection.label == "person"
    assert detection.confidence == 0.91
    assert detection.bounding_box.x_min == 0.1
    assert detection.bounding_box.y_max == 0.9


def test_event_is_immutable() -> None:
    event = create_event()

    with pytest.raises(FrozenInstanceError):
        event.camera_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    (
        "x_min",
        "y_min",
        "x_max",
        "y_max",
    ),
    [
        (-0.1, 0.1, 0.5, 0.5),
        (0.1, -0.1, 0.5, 0.5),
        (0.1, 0.1, 1.1, 0.5),
        (0.1, 0.1, 0.5, 1.1),
        (0.5, 0.1, 0.5, 0.9),
        (0.1, 0.9, 0.5, 0.8),
    ],
)
def test_bounding_box_rejects_invalid_coordinates(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> None:
    with pytest.raises(ValueError):
        StreamBoundingBox(
            x_min=x_min,
            y_min=y_min,
            x_max=x_max,
            y_max=y_max,
        )


def test_event_rejects_naive_timestamps() -> None:
    timestamp = datetime.now()

    with pytest.raises(
        ValueError,
        match="captured_at must be timezone-aware",
    ):
        StreamDetectionEvent(
            correlation_id=uuid4(),
            camera_id="camera-001",
            frame_sequence_number=1,
            captured_at=timestamp,
            received_at=timestamp,
            processed_at=timestamp,
            model=StreamModelIdentity(
                name="model",
                version="1",
                device="cpu",
            ),
            detections=(),
            inference_duration_ms=1.0,
        )