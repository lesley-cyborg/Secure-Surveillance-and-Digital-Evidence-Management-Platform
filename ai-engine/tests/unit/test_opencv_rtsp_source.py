from __future__ import annotations

import os
from collections.abc import Sequence

import cv2
import numpy as np
import pytest

from streaming.domain import (
    CameraStreamConfig,
    FrameArray,
    StreamTransport,
)
from streaming.exceptions import (
    StreamDisabledError,
    StreamNotOpenError,
    StreamOpenError,
    StreamReadError,
)
from streaming.opencv_rtsp_source import (
    OpenCvRtspSource,
)


class FakeCapture:
    def __init__(
        self,
        *,
        open_result: bool = True,
        frames: (
            list[
                tuple[
                    bool,
                    FrameArray | None,
                ]
            ]
            | None
        ) = None,
    ) -> None:
        self.open_result = open_result
        self.opened = False
        self.frames = frames or []

        self.open_calls = 0
        self.read_calls = 0
        self.release_calls = 0

        self.opened_uri: str | None = None
        self.opened_backend: int | None = None
        self.opened_parameters: list[int] = []
        self.ffmpeg_options_during_open: str | None = None

    def open(
        self,
        filename: str,
        api_preference: int,
        params: Sequence[int],
    ) -> bool:
        self.open_calls += 1
        self.opened_uri = filename
        self.opened_backend = api_preference
        self.opened_parameters = list(params)
        self.ffmpeg_options_during_open = os.environ.get(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS"
        )

        self.opened = self.open_result

        return self.open_result

    def isOpened(self) -> bool:
        return self.opened

    def read(
        self,
    ) -> tuple[
        bool,
        FrameArray | None,
    ]:
        self.read_calls += 1

        if not self.frames:
            return False, None

        return self.frames.pop(0)

    def release(self) -> None:
        self.release_calls += 1
        self.opened = False

    def get(
        self,
        property_id: int,
    ) -> float:
        if property_id == int(cv2.CAP_PROP_POS_MSEC):
            return 125.5

        return 0.0

    def getBackendName(self) -> str:
        return "FFMPEG"


def create_config(
    *,
    enabled: bool = True,
    transport: StreamTransport = (StreamTransport.TCP),
) -> CameraStreamConfig:
    return CameraStreamConfig(
        camera_id="camera-001",
        name="Main entrance",
        source_uri=("rtsp://operator:secret@10.0.0.5:554/stream"),
        enabled=enabled,
        transport=transport,
        connect_timeout_seconds=3.0,
        read_timeout_seconds=4.0,
    )


def test_open_uses_backend_and_timeout_parameters() -> None:
    capture = FakeCapture()

    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=lambda: capture,
        backend_api=999,
    )

    source.open()

    assert source.is_open is True
    assert source.backend_name == "FFMPEG"
    assert capture.open_calls == 1
    assert capture.opened_backend == 999

    assert capture.opened_parameters == [
        int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC),
        3000,
        int(cv2.CAP_PROP_READ_TIMEOUT_MSEC),
        4000,
    ]


def test_open_is_idempotent() -> None:
    capture = FakeCapture()

    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=lambda: capture,
    )

    source.open()
    source.open()

    assert capture.open_calls == 1


def test_open_rejects_disabled_camera() -> None:
    source = OpenCvRtspSource(
        config=create_config(enabled=False),
        capture_factory=FakeCapture,
    )

    with pytest.raises(StreamDisabledError):
        source.open()


def test_open_failure_releases_capture_and_redacts_uri() -> None:
    capture = FakeCapture(open_result=False)

    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=lambda: capture,
    )

    with pytest.raises(StreamOpenError) as error:
        source.open()

    message = str(error.value)

    assert "operator" not in message
    assert "secret" not in message
    assert "rtsp://10.0.0.5:554/stream" in message
    assert capture.release_calls == 1


def test_read_rejects_unopened_source() -> None:
    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=FakeCapture,
    )

    with pytest.raises(StreamNotOpenError):
        source.read()


def test_read_returns_valid_stream_frame() -> None:
    capture = FakeCapture(
        frames=[
            (
                True,
                np.zeros(
                    (480, 640, 3),
                    dtype=np.uint8,
                ),
            ),
            (
                True,
                np.zeros(
                    (720, 1280, 3),
                    dtype=np.uint8,
                ),
            ),
        ]
    )

    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=lambda: capture,
    )

    source.open()

    first = source.read()
    second = source.read()

    assert first.camera_id == "camera-001"
    assert first.sequence_number == 0
    assert first.width == 640
    assert first.height == 480
    assert first.source_timestamp_ms == 125.5

    assert second.sequence_number == 1
    assert second.width == 1280
    assert second.height == 720


def test_read_failure_raises_stream_read_error() -> None:
    capture = FakeCapture(
        frames=[
            (False, None),
        ]
    )

    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=lambda: capture,
    )

    source.open()

    with pytest.raises(
        StreamReadError,
        match="did not return a frame",
    ):
        source.read()


def test_close_releases_capture_and_is_idempotent() -> None:
    capture = FakeCapture()

    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=lambda: capture,
    )

    source.open()
    source.close()
    source.close()

    assert source.is_open is False
    assert capture.release_calls == 1


def test_tcp_transport_is_applied_only_during_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variable_name = "OPENCV_FFMPEG_CAPTURE_OPTIONS"

    monkeypatch.setenv(
        variable_name,
        "video_codec;h264",
    )

    capture = FakeCapture()

    source = OpenCvRtspSource(
        config=create_config(transport=StreamTransport.TCP),
        capture_factory=lambda: capture,
    )

    source.open()

    assert capture.ffmpeg_options_during_open == "video_codec;h264|rtsp_transport;tcp"

    assert os.environ[variable_name] == "video_codec;h264"


def test_context_manager_closes_capture() -> None:
    capture = FakeCapture()

    source = OpenCvRtspSource(
        config=create_config(),
        capture_factory=lambda: capture,
    )

    with source as opened_source:
        assert opened_source.is_open is True

    assert source.is_open is False
    assert capture.release_calls == 1
