from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TypedDict

from streaming.detection_events import StreamDetectionEvent

EVENT_SCHEMA_VERSION = "1.0"
EVENT_TYPE = "camera.detection.completed"


class BoundingBoxPayload(TypedDict):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class DetectionPayload(TypedDict):
    class_id: int
    label: str
    confidence: float
    bounding_box: BoundingBoxPayload


class FramePayload(TypedDict):
    sequence_number: int
    captured_at: str
    received_at: str


class ModelPayload(TypedDict):
    name: str
    version: str
    device: str


class InferencePayload(TypedDict):
    duration_ms: float
    processed_at: str


class StreamDetectionEventPayload(TypedDict):
    schema_version: str
    event_type: str
    event_id: str
    camera_id: str
    frame: FramePayload
    model: ModelPayload
    detections: list[DetectionPayload]
    detection_count: int
    inference: InferencePayload


def _format_datetime(value: datetime) -> str:
    """Format a timestamp as canonical UTC ISO-8601."""

    utc_value = value.astimezone(UTC)

    return utc_value.isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def stream_detection_event_to_payload(
    event: StreamDetectionEvent,
) -> StreamDetectionEventPayload:
    """Convert an internal event to the backend contract."""

    detections: list[DetectionPayload] = [
        {
            "class_id": detection.class_id,
            "label": detection.label,
            "confidence": detection.confidence,
            "bounding_box": {
                "x_min": detection.bounding_box.x_min,
                "y_min": detection.bounding_box.y_min,
                "x_max": detection.bounding_box.x_max,
                "y_max": detection.bounding_box.y_max,
            },
        }
        for detection in event.detections
    ]

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": EVENT_TYPE,
        "event_id": str(event.correlation_id),
        "camera_id": event.camera_id,
        "frame": {
            "sequence_number": (event.frame_sequence_number),
            "captured_at": _format_datetime(event.captured_at),
            "received_at": _format_datetime(event.received_at),
        },
        "model": {
            "name": event.model.name,
            "version": event.model.version,
            "device": event.model.device,
        },
        "detections": detections,
        "detection_count": len(detections),
        "inference": {
            "duration_ms": (event.inference_duration_ms),
            "processed_at": _format_datetime(event.processed_at),
        },
    }


def serialize_stream_detection_event(
    event: StreamDetectionEvent,
) -> bytes:
    """Serialize an event using deterministic JSON."""

    payload = stream_detection_event_to_payload(event)

    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def create_event_idempotency_key(
    event: StreamDetectionEvent,
) -> str:
    """Create a stable key for duplicate suppression."""

    serialized_event = serialize_stream_detection_event(event)

    return hashlib.sha256(serialized_event).hexdigest()
