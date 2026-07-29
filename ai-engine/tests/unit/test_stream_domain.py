from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
    StreamRuntimeSnapshot,
    StreamState,
)


def test_camera_config_accepts_valid_rtsp_uri() -> None:
    config = CameraStreamConfig(
        camera_id="camera-001",
        name="Main entrance",
        source_uri=("rtsp://operator:secret@10.0.0.5:554/stream"),
    )

    assert config.camera_id == "camera-001"
    assert config.target_fps == 1.0
    assert config.queue_capacity == 1
    assert config.redacted_source_uri == "rtsp://10.0.0.5:554/stream"


def test_camera_config_does_not_expose_credentials() -> None:
    config = CameraStreamConfig(
        camera_id="camera-001",
        name="Main entrance",
        source_uri=("rtsp://operator:secret@10.0.0.5/stream"),
    )

    representation = repr(config)

    assert "operator" not in representation
    assert "secret" not in representation
    assert config.source_uri not in representation


def test_camera_config_rejects_non_rtsp_uri() -> None:
    with pytest.raises(
        ValueError,
        match="rtsp or rtsps",
    ):
        CameraStreamConfig(
            camera_id="camera-001",
            name="Main entrance",
            source_uri=("http://10.0.0.5/video"),
        )


def test_stream_frame_reports_dimensions() -> None:
    captured_at = datetime.now(UTC)
    received_at = datetime.now(UTC)

    frame = StreamFrame(
        camera_id="camera-001",
        sequence_number=7,
        captured_at=captured_at,
        received_at=received_at,
        image=np.zeros(
            (480, 640, 3),
            dtype=np.uint8,
        ),
    )

    assert frame.width == 640
    assert frame.height == 480
    assert frame.channels == 3
    assert frame.capture_latency_ms >= 0


def test_stream_frame_rejects_invalid_pixel_type() -> None:
    with pytest.raises(
        ValueError,
        match="uint8",
    ):
        StreamFrame(
            camera_id="camera-001",
            sequence_number=0,
            captured_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            image=np.zeros(
                (10, 10, 3),
                dtype=np.float32,
            ),
        )


def test_runtime_snapshot_rejects_negative_counters() -> None:
    with pytest.raises(
        ValueError,
        match="frames_received",
    ):
        StreamRuntimeSnapshot(
            camera_id="camera-001",
            state=StreamState.CONNECTED,
            updated_at=datetime.now(UTC),
            frames_received=-1,
        )
