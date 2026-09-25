from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


def _require_non_empty(
    value: str,
    *,
    field_name: str,
) -> str:
    normalised = value.strip()

    if not normalised:
        raise ValueError(f"{field_name} cannot be empty")

    return normalised


def _require_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(
    frozen=True,
    slots=True,
)
class StreamBoundingBox:
    """Normalised detection coordinates."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        coordinates = {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
        }

        for field_name, value in coordinates.items():
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")

            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between 0 and 1")

        if self.x_max <= self.x_min:
            raise ValueError("x_max must be greater than x_min")

        if self.y_max <= self.y_min:
            raise ValueError("y_max must be greater than y_min")


@dataclass(
    frozen=True,
    slots=True,
)
class StreamDetection:
    """One normalised object detection."""

    class_id: int
    label: str
    confidence: float
    bounding_box: StreamBoundingBox

    def __post_init__(self) -> None:
        if self.class_id < 0:
            raise ValueError("class_id cannot be negative")

        object.__setattr__(
            self,
            "label",
            _require_non_empty(
                self.label,
                field_name="label",
            ),
        )

        if not math.isfinite(self.confidence):
            raise ValueError("confidence must be finite")

        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(
    frozen=True,
    slots=True,
)
class StreamModelIdentity:
    """Detection model identity stored in an event."""

    name: str
    version: str
    device: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _require_non_empty(
                self.name,
                field_name="model name",
            ),
        )
        object.__setattr__(
            self,
            "version",
            _require_non_empty(
                self.version,
                field_name="model version",
            ),
        )
        object.__setattr__(
            self,
            "device",
            _require_non_empty(
                self.device,
                field_name="model device",
            ),
        )


@dataclass(
    frozen=True,
    slots=True,
)
class StreamDetectionEvent:
    """Camera-aware result of one successful inference."""

    correlation_id: UUID
    camera_id: str
    frame_sequence_number: int

    captured_at: datetime
    received_at: datetime
    processed_at: datetime

    model: StreamModelIdentity
    detections: tuple[StreamDetection, ...]

    inference_duration_ms: float
    schema_version: Literal["1.0", "1.1"] = "1.0"
    analysis: dict[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "camera_id",
            _require_non_empty(
                self.camera_id,
                field_name="camera_id",
            ),
        )

        if self.frame_sequence_number < 0:
            raise ValueError("frame_sequence_number cannot be negative")

        _require_aware_datetime(
            self.captured_at,
            field_name="captured_at",
        )
        _require_aware_datetime(
            self.received_at,
            field_name="received_at",
        )
        _require_aware_datetime(
            self.processed_at,
            field_name="processed_at",
        )

        if self.received_at < self.captured_at:
            raise ValueError("received_at cannot be earlier than captured_at")

        if not math.isfinite(self.inference_duration_ms):
            raise ValueError("inference_duration_ms must be finite")

        if self.inference_duration_ms < 0:
            raise ValueError("inference_duration_ms cannot be negative")

        if (self.schema_version == "1.1") != (self.analysis is not None):
            raise ValueError("schema version 1.1 requires analysis data")

    @property
    def detection_count(self) -> int:
        return len(self.detections)

    @property
    def contains_detections(self) -> bool:
        return bool(self.detections)
