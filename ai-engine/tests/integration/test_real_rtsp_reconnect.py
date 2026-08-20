from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
    StreamState,
    StreamTransport,
)
from streaming.frame_queue import LatestFrameQueue
from streaming.frame_sampler import FrameSampler
from streaming.opencv_rtsp_source import OpenCvRtspSource
from streaming.reconnect_policy import (
    ReconnectPolicy,
    ReconnectPolicyConfig,
)
from streaming.worker import ContinuousDetectionWorker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.rtsp,
]


type SnapshotCondition = Callable[
    [object],
    bool,
]


def rtsp_integration_enabled() -> bool:
    return (
        os.getenv(
            "RUN_RTSP_INTEGRATION",
            "",
        ).strip()
        == "1"
    )


def get_compose_file() -> Path:
    configured_path = os.getenv(
        "RTSP_COMPOSE_FILE",
        "",
    ).strip()

    if configured_path:
        compose_file = Path(configured_path).resolve()
    else:
        platform_root = Path(__file__).resolve().parents[3]

        compose_file = platform_root / "docker" / "rtsp-test" / "compose.yml"

    if not compose_file.is_file():
        raise RuntimeError(f"RTSP Compose file was not found: {compose_file}")

    return compose_file


def run_compose(
    *arguments: str,
) -> None:
    docker_executable = shutil.which("docker")

    if docker_executable is None:
        raise RuntimeError("Docker executable was not found")

    command = [
        docker_executable,
        "compose",
        "-f",
        str(get_compose_file()),
        *arguments,
    ]

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Docker Compose command failed.\n"
            f"Command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


async def wait_for_reconnect_attempt(
    worker: ContinuousDetectionWorker,
    *,
    timeout_seconds: float = 45.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    while True:
        snapshot = await worker.snapshot()

        if snapshot.runtime.reconnect_attempts >= 1:
            return

        if snapshot.runtime.state is StreamState.FAILED:
            raise AssertionError("Worker failed before reconnection could be verified")

        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Worker did not enter its reconnection path")

        await asyncio.sleep(0.25)


@pytest.mark.asyncio
async def test_worker_recovers_after_publisher_restart() -> None:
    if not rtsp_integration_enabled():
        pytest.skip("Set RUN_RTSP_INTEGRATION=1 to run the Docker RTSP test")

    source_uri = os.getenv(
        "RTSP_TEST_URI",
        "rtsp://127.0.0.1:8554/synthetic",
    )

    config = CameraStreamConfig(
        camera_id="camera-rtsp-reconnect",
        name="Synthetic reconnect camera",
        source_uri=source_uri,
        enabled=True,
        transport=StreamTransport.TCP,
        target_fps=5.0,
        confidence_threshold=0.35,
        queue_capacity=1,
        maximum_consecutive_read_failures=1,
    )

    source = OpenCvRtspSource(
        config=config,
    )

    initial_frames_ready = asyncio.Event()
    recovered_frame_ready = asyncio.Event()

    processed_frames: list[StreamFrame] = []

    recovery_baseline: int | None = None

    async def process_frame(
        frame: StreamFrame,
        confidence_threshold: float,
    ) -> object:
        assert confidence_threshold == 0.35
        assert frame.camera_id == config.camera_id

        assert frame.image.ndim == 3
        assert frame.image.shape[0] > 0
        assert frame.image.shape[1] > 0
        assert frame.image.shape[2] == 3

        processed_frames.append(frame)

        if len(processed_frames) >= 3:
            initial_frames_ready.set()

        if recovery_baseline is not None and len(processed_frames) > recovery_baseline:
            recovered_frame_ready.set()

        return {
            "camera_id": frame.camera_id,
            "sequence_number": (frame.sequence_number),
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
                maximum_attempts=50,
            ),
        ),
        process_frame=process_frame,
    )

    publisher_stopped = False

    try:
        await worker.start()

        await asyncio.wait_for(
            initial_frames_ready.wait(),
            timeout=30.0,
        )

        initial_snapshot = await worker.snapshot()

        assert initial_snapshot.runtime.frames_processed >= 3

        await asyncio.to_thread(
            run_compose,
            "stop",
            "rtsp-publisher",
        )
        publisher_stopped = True

        await wait_for_reconnect_attempt(
            worker,
        )

        interrupted_snapshot = await worker.snapshot()

        assert interrupted_snapshot.runtime.reconnect_attempts >= 1
        assert interrupted_snapshot.runtime.state is not StreamState.FAILED

        recovery_baseline = len(processed_frames)

        await asyncio.to_thread(
            run_compose,
            "start",
            "rtsp-publisher",
        )
        publisher_stopped = False

        await asyncio.wait_for(
            recovered_frame_ready.wait(),
            timeout=60.0,
        )

        recovered_snapshot = await worker.snapshot()

        assert recovered_snapshot.running is True
        assert recovered_snapshot.runtime.state is not StreamState.FAILED
        assert recovered_snapshot.runtime.reconnect_attempts >= 1
        assert recovered_snapshot.runtime.frames_processed > recovery_baseline
        assert recovered_snapshot.runtime.detection_failures == 0
    finally:
        if publisher_stopped:
            await asyncio.to_thread(
                run_compose,
                "start",
                "rtsp-publisher",
            )

        await worker.dispose()

    final_snapshot = await worker.snapshot()

    assert final_snapshot.running is False
    assert final_snapshot.disposed is True
    assert final_snapshot.queue.closed is True
    assert source.is_open is False
