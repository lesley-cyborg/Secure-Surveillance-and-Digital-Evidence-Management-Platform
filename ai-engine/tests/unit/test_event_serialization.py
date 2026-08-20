from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from streaming.detection_events import (
    StreamBoundingBox,
    StreamDetection,
    StreamDetectionEvent,
    StreamModelIdentity,
)
from streaming.event_serialization import (
    EVENT_SCHEMA_VERSION,
    EVENT_TYPE,
    create_event_idempotency_key,
    serialize_stream_detection_event,
    stream_detection_event_to_payload,
)


def create_event() -> StreamDetectionEvent:
    captured_at = datetime(
        2026,
        7,
        31,
        1,
        0,
        0,
        123456,
        tzinfo=UTC,
    )

    return StreamDetectionEvent(
        correlation_id=uuid4(),
        camera_id="camera-001",
        frame_sequence_number=42,
        captured_at=captured_at,
        received_at=(captured_at + timedelta(milliseconds=10)),
        processed_at=(captured_at + timedelta(milliseconds=25)),
        model=StreamModelIdentity(
            name="surveillance-yolo",
            version="yolo26n-coco",
            device="cpu",
        ),
        detections=(
            StreamDetection(
                class_id=0,
                label="person",
                confidence=0.94,
                bounding_box=StreamBoundingBox(
                    x_min=0.1,
                    y_min=0.2,
                    x_max=0.8,
                    y_max=0.9,
                ),
            ),
        ),
        inference_duration_ms=8.5,
    )


def test_payload_contains_backend_contract() -> None:
    event = create_event()

    payload = stream_detection_event_to_payload(event)

    assert payload["schema_version"] == EVENT_SCHEMA_VERSION
    assert payload["event_type"] == EVENT_TYPE
    assert payload["event_id"] == str(event.correlation_id)
    assert payload["camera_id"] == "camera-001"

    assert payload["frame"]["sequence_number"] == 42
    assert payload["frame"]["captured_at"].endswith("Z")
    assert payload["frame"]["received_at"].endswith("Z")

    assert payload["model"] == {
        "name": "surveillance-yolo",
        "version": "yolo26n-coco",
        "device": "cpu",
    }

    assert payload["detection_count"] == 1
    assert len(payload["detections"]) == 1

    detection = payload["detections"][0]

    assert detection["class_id"] == 0
    assert detection["label"] == "person"
    assert detection["confidence"] == 0.94
    assert detection["bounding_box"] == {
        "x_min": 0.1,
        "y_min": 0.2,
        "x_max": 0.8,
        "y_max": 0.9,
    }

    assert payload["inference"]["duration_ms"] == 8.5
    assert payload["inference"]["processed_at"].endswith("Z")


def test_serialization_is_deterministic() -> None:
    event = create_event()

    first = serialize_stream_detection_event(event)
    second = serialize_stream_detection_event(event)

    assert first == second
    assert first.startswith(b"{")
    assert first.endswith(b"}")


def test_idempotency_key_is_deterministic() -> None:
    event = create_event()

    first = create_event_idempotency_key(event)
    second = create_event_idempotency_key(event)

    assert first == second
    assert len(first) == 64
    assert first.isalnum()


def test_idempotency_key_changes_with_event() -> None:
    event = create_event()

    changed_event = replace(
        event,
        frame_sequence_number=43,
    )

    assert create_event_idempotency_key(event) != create_event_idempotency_key(
        changed_event
    )


def test_serialized_event_excludes_sensitive_data() -> None:
    serialized = (
        serialize_stream_detection_event(create_event()).decode("utf-8").casefold()
    )

    assert "source_uri" not in serialized
    assert "rtsp://" not in serialized
    assert "password" not in serialized
    assert '"image"' not in serialized
    assert "image_bytes" not in serialized
