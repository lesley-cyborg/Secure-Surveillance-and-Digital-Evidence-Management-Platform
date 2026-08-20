from __future__ import annotations

import asyncio
import os

import pytest

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
    StreamState,
    StreamTransport,
)
from streaming.frame_queue import LatestFrameQueue
from streaming.frame_sampler import FrameSampler
from streaming.opencv_rtsp_source import (
    OpenCvRtspSource,
)
from streaming.reconnect_policy import (
    ReconnectPolicy,
    ReconnectPolicyConfig,
)
from streaming.worker import (
    ContinuousDetectionWorker,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.rtsp,
]


def rtsp_integration_enabled() -> bool:
    return (
        os.getenv(
            "RUN_RTSP_INTEGRATION",
            "",
        ).strip()
        == "1"
    )


@pytest.mark.asyncio
async def test_real_rtsp_stream_reaches_worker() -> None:
    if not rtsp_integration_enabled():
        pytest.skip("Set RUN_RTSP_INTEGRATION=1 to run the Docker RTSP test")

    source_uri = os.getenv(
        "RTSP_TEST_URI",
        "rtsp://127.0.0.1:8554/synthetic",
    )

    config = CameraStreamConfig(
        camera_id="camera-rtsp-integration",
        name="Synthetic RTSP camera",
        source_uri=source_uri,
        enabled=True,
        transport=StreamTransport.TCP,
        target_fps=5.0,
        confidence_threshold=0.35,
        queue_capacity=1,
        maximum_consecutive_read_failures=3,
    )

    source = OpenCvRtspSource(
        config=config,
    )

    processed_frames: list[StreamFrame] = []
    enough_frames_processed = asyncio.Event()

    async def process_frame(
        frame: StreamFrame,
        confidence_threshold: float,
    ) -> object:
        assert frame.camera_id == config.camera_id
        assert confidence_threshold == 0.35

        assert frame.image.ndim == 3
        assert frame.image.shape[0] > 0
        assert frame.image.shape[1] > 0
        assert frame.image.shape[2] == 3

        processed_frames.append(frame)

        if len(processed_frames) >= 3:
            enough_frames_processed.set()

        return {
            "camera_id": frame.camera_id,
            "sequence_number": frame.sequence_number,
            "shape": frame.image.shape,
        }

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
        ),
        frame_queue=LatestFrameQueue(
            capacity=config.queue_capacity,
        ),
        reconnect_policy=ReconnectPolicy(
            config=ReconnectPolicyConfig(
                initial_delay_seconds=0.25,
                multiplier=2.0,
                maximum_delay_seconds=2.0,
                jitter_ratio=0.0,
                maximum_attempts=20,
            ),
        ),
        process_frame=process_frame,
    )

    try:
        await worker.start()

        await asyncio.wait_for(
            enough_frames_processed.wait(),
            timeout=30.0,
        )

        snapshot = await worker.snapshot()

        assert snapshot.running is True
        assert snapshot.disposed is False

        assert snapshot.runtime.state in {
            StreamState.CONNECTED,
            StreamState.CONNECTING,
        }

        assert snapshot.runtime.connected_at is not None
        assert snapshot.runtime.last_frame_at is not None

        assert snapshot.runtime.frames_received >= 3
        assert snapshot.runtime.frames_published >= 3
        assert snapshot.runtime.frames_processed >= 3
        assert snapshot.runtime.detection_failures == 0

        assert snapshot.queue.capacity == 1
        assert len(processed_frames) >= 3

        sequence_numbers = [frame.sequence_number for frame in processed_frames]

        assert sequence_numbers == sorted(sequence_numbers)
        assert len(set(sequence_numbers)) == len(sequence_numbers)
    finally:
        await worker.dispose()

    disposed_snapshot = await worker.snapshot()

    assert disposed_snapshot.running is False
    assert disposed_snapshot.disposed is True
    assert disposed_snapshot.queue.closed is True
    assert source.is_open is False
