from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit

import numpy as np
from numpy.typing import NDArray

type FrameArray = NDArray[np.uint8]


class StreamState(StrEnum):
    """Runtime state of a managed camera stream."""

    DISABLED = "disabled"
    STOPPED = "stopped"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    STOPPING = "stopping"


class StreamTransport(StrEnum):
    """Preferred RTSP transport."""

    AUTO = "auto"
    TCP = "tcp"
    UDP = "udp"


@dataclass(
    frozen=True,
    slots=True,
)
class CameraStreamConfig:
    """Immutable configuration for one camera stream."""

    camera_id: str
    name: str

    # Prevent credentials from appearing in repr() and logs.
    source_uri: str = field(
        repr=False,
    )

    enabled: bool = True
    transport: StreamTransport = StreamTransport.TCP

    target_fps: float = 1.0
    confidence_threshold: float = 0.35
    queue_capacity: int = 1

    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 10.0
    maximum_consecutive_read_failures: int = 3

    def __post_init__(self) -> None:
        camera_id = self.camera_id.strip()
        name = self.name.strip()
        source_uri = self.source_uri.strip()

        if not camera_id:
            raise ValueError("camera_id cannot be empty")

        if not name:
            raise ValueError("camera name cannot be empty")

        if not source_uri:
            raise ValueError("source_uri cannot be empty")

        parsed_uri = urlsplit(source_uri)

        if parsed_uri.scheme.lower() not in {
            "rtsp",
            "rtsps",
        }:
            raise ValueError("source_uri must use rtsp or rtsps")

        if not parsed_uri.hostname:
            raise ValueError("source_uri must contain a hostname")

        try:
            _ = parsed_uri.port
        except ValueError as exception:
            raise ValueError("source_uri contains an invalid port") from exception

        if not 0 < self.target_fps <= 60:
            raise ValueError("target_fps must be between 0 and 60")

        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")

        if not 1 <= self.queue_capacity <= 32:
            raise ValueError("queue_capacity must be between 1 and 32")

        if self.connect_timeout_seconds <= 0:
            raise ValueError("connect_timeout_seconds must be positive")

        if self.read_timeout_seconds <= 0:
            raise ValueError("read_timeout_seconds must be positive")

        if self.maximum_consecutive_read_failures < 1:
            raise ValueError("maximum_consecutive_read_failures must be at least 1")

        object.__setattr__(
            self,
            "camera_id",
            camera_id,
        )
        object.__setattr__(
            self,
            "name",
            name,
        )
        object.__setattr__(
            self,
            "source_uri",
            source_uri,
        )

    @property
    def redacted_source_uri(self) -> str:
        """Return a safe URI suitable for logs."""

        parsed_uri = urlsplit(self.source_uri)

        hostname = parsed_uri.hostname or ""

        if ":" in hostname:
            hostname = f"[{hostname}]"

        port = f":{parsed_uri.port}" if parsed_uri.port is not None else ""

        return urlunsplit(
            (
                parsed_uri.scheme.lower(),
                f"{hostname}{port}",
                parsed_uri.path,
                "",
                "",
            )
        )


@dataclass(
    frozen=True,
    slots=True,
)
class StreamFrame:
    """One decoded BGR frame received from a camera."""

    camera_id: str
    sequence_number: int
    captured_at: datetime
    received_at: datetime

    image: FrameArray = field(
        repr=False,
        compare=False,
    )

    source_timestamp_ms: float | None = None

    def __post_init__(self) -> None:
        camera_id = self.camera_id.strip()

        if not camera_id:
            raise ValueError("camera_id cannot be empty")

        if self.sequence_number < 0:
            raise ValueError("sequence_number cannot be negative")

        _validate_aware_datetime(
            self.captured_at,
            field_name="captured_at",
        )
        _validate_aware_datetime(
            self.received_at,
            field_name="received_at",
        )

        if not isinstance(
            self.image,
            np.ndarray,
        ):
            raise TypeError("image must be a NumPy array")

        if self.image.dtype != np.uint8:
            raise ValueError("image must use uint8 pixels")

        if self.image.ndim != 3:
            raise ValueError("image must have three dimensions")

        if self.image.shape[2] != 3:
            raise ValueError("image must contain three BGR channels")

        if self.image.size == 0:
            raise ValueError("image cannot be empty")

        if self.source_timestamp_ms is not None and self.source_timestamp_ms < 0:
            raise ValueError("source_timestamp_ms cannot be negative")

        object.__setattr__(
            self,
            "camera_id",
            camera_id,
        )

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def channels(self) -> int:
        return int(self.image.shape[2])

    @property
    def capture_latency_ms(self) -> float:
        duration = self.received_at - self.captured_at

        return max(
            0.0,
            duration.total_seconds() * 1000,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class StreamRuntimeSnapshot:
    """Read-only runtime status returned by the manager and API."""

    camera_id: str
    state: StreamState
    updated_at: datetime

    connected_at: datetime | None = None
    last_frame_at: datetime | None = None

    frames_received: int = 0
    frames_published: int = 0
    frames_dropped: int = 0
    frames_processed: int = 0
    detection_failures: int = 0
    reconnect_attempts: int = 0

    last_error: str | None = None

    def __post_init__(self) -> None:
        if not self.camera_id.strip():
            raise ValueError("camera_id cannot be empty")

        _validate_aware_datetime(
            self.updated_at,
            field_name="updated_at",
        )

        for field_name in (
            "frames_received",
            "frames_published",
            "frames_dropped",
            "frames_processed",
            "detection_failures",
            "reconnect_attempts",
        ):
            value = getattr(
                self,
                field_name,
            )

            if value < 0:
                raise ValueError(f"{field_name} cannot be negative")


def _validate_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
