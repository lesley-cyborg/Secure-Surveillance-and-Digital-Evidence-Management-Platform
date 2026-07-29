from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
)
from streaming.source import StreamSource


class FakeStreamSource:
    def __init__(
        self,
        config: CameraStreamConfig,
    ) -> None:
        self._config = config
        self._is_open = False

    @property
    def config(self) -> CameraStreamConfig:
        return self._config

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self) -> None:
        self._is_open = True

    def read(self) -> StreamFrame:
        timestamp = datetime.now(UTC)

        return StreamFrame(
            camera_id=self._config.camera_id,
            sequence_number=0,
            captured_at=timestamp,
            received_at=timestamp,
            image=np.zeros(
                (8, 8, 3),
                dtype=np.uint8,
            ),
        )

    def close(self) -> None:
        self._is_open = False


def test_structural_source_implements_protocol() -> None:
    source = FakeStreamSource(
        CameraStreamConfig(
            camera_id="camera-001",
            name="Main entrance",
            source_uri=("rtsp://10.0.0.5/stream"),
        )
    )

    assert isinstance(
        source,
        StreamSource,
    )

    source.open()

    assert source.is_open is True
    assert source.read().camera_id == "camera-001"

    source.close()

    assert source.is_open is False
