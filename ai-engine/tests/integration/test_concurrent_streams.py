from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from threading import Event as ThreadEvent
from threading import Lock

import numpy as np

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
    StreamState,
)
from streaming.exceptions import (
    StreamNotOpenError,
    StreamOpenError,
    StreamReadError,
)
from streaming.frame_queue import LatestFrameQueue
from streaming.frame_sampler import FrameSampler
from streaming.manager import StreamManager
from streaming.reconnect_policy import (
    ReconnectPolicy,
    ReconnectPolicyConfig,
)
from streaming.worker import (
    ContinuousDetectionWorker,
    FrameProcessingFunction,
)

type AsyncCondition = Callable[
    [],
    Awaitable[bool],
]

type SyncCondition = Callable[
    [],
    bool,
]

INTEGRATION_TIMEOUT_SECONDS = 10.0


class IncrementingClock:
    """Deterministic sampler clock accepting each test frame."""

    def __init__(
        self,
        *,
        step_seconds: float = 1.0,
    ) -> None:
        self._value = 0.0
        self._step_seconds = step_seconds

    def __call__(self) -> float:
        current = self._value
        self._value += self._step_seconds
        return current


class BufferedStreamSource:
    """Thread-safe finite stream source for integration tests.

    The worker still invokes this source through asyncio.to_thread(), so
    the test exercises the production capture boundary without requiring
    a real RTSP server.
    """

    def __init__(
        self,
        *,
        config: CameraStreamConfig,
        frames: list[StreamFrame] | None = None,
        always_fail_open: bool = False,
        additional_reads_gate: ThreadEvent | None = None,
        empty_read_delay_seconds: float = 0.01,
    ) -> None:
        self._config = config
        self._frames = deque(frames or [])
        self._always_fail_open = always_fail_open
        self._additional_reads_gate = additional_reads_gate
        self._empty_read_delay_seconds = empty_read_delay_seconds

        self._lock = Lock()
        self._is_open = False

        self.open_calls = 0
        self.read_calls = 0
        self.close_calls = 0

    @property
    def config(self) -> CameraStreamConfig:
        return self._config

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._is_open

    @property
    def remaining_frames(self) -> int:
        with self._lock:
            return len(self._frames)

    def open(self) -> None:
        with self._lock:
            self.open_calls += 1

            if self._always_fail_open:
                raise StreamOpenError("scripted stream-open failure")

            self._is_open = True

    def read(self) -> StreamFrame:
        with self._lock:
            if not self._is_open:
                raise StreamNotOpenError("stream source is not open")

            self.read_calls += 1
            current_read = self.read_calls

        # Used by the queue-pressure test. It prevents frame two from
        # being emitted until detection has started processing frame one.
        if current_read > 1 and self._additional_reads_gate is not None:
            gate_opened = self._additional_reads_gate.wait(timeout=1.0)

            if not gate_opened:
                raise StreamReadError("timed out waiting for additional-read gate")

        with self._lock:
            if not self._is_open:
                raise StreamNotOpenError("stream source was closed")

            if self._frames:
                return self._frames.popleft()

        # Keep blocking reads bounded. Cancelling asyncio.to_thread()
        # does not terminate its underlying thread immediately.
        time.sleep(self._empty_read_delay_seconds)

        raise StreamReadError("no buffered frame available")

    def close(self) -> None:
        with self._lock:
            self.close_calls += 1
            self._is_open = False


async def immediate_sleep(
    _: float,
) -> None:
    """Reconnect sleeper that yields without real delays."""

    await asyncio.sleep(0)


def create_config(
    camera_id: str,
    *,
    queue_capacity: int = 1,
    maximum_consecutive_read_failures: int = 1_000,
) -> CameraStreamConfig:
    return CameraStreamConfig(
        camera_id=camera_id,
        name=f"Camera {camera_id}",
        source_uri=(f"rtsp://operator:secret@10.0.0.5:554/{camera_id}"),
        target_fps=30.0,
        confidence_threshold=0.35,
        queue_capacity=queue_capacity,
        maximum_consecutive_read_failures=(maximum_consecutive_read_failures),
    )


def create_frame(
    camera_id: str,
    sequence_number: int,
) -> StreamFrame:
    timestamp = datetime.now(UTC)

    return StreamFrame(
        camera_id=camera_id,
        sequence_number=sequence_number,
        captured_at=timestamp,
        received_at=timestamp,
        image=np.zeros(
            (16, 16, 3),
            dtype=np.uint8,
        ),
    )


def create_frames(
    camera_id: str,
    count: int,
) -> list[StreamFrame]:
    return [
        create_frame(
            camera_id,
            sequence_number,
        )
        for sequence_number in range(count)
    ]


def create_worker(
    *,
    config: CameraStreamConfig,
    source: BufferedStreamSource,
    process_frame: FrameProcessingFunction,
    maximum_reconnect_attempts: int | None = None,
) -> ContinuousDetectionWorker:
    return ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
            clock=IncrementingClock(),
        ),
        frame_queue=LatestFrameQueue(
            capacity=config.queue_capacity,
        ),
        reconnect_policy=ReconnectPolicy(
            config=ReconnectPolicyConfig(
                initial_delay_seconds=0.01,
                multiplier=1.0,
                maximum_delay_seconds=0.01,
                jitter_ratio=0.0,
                maximum_attempts=(maximum_reconnect_attempts),
            ),
            sleep=immediate_sleep,
        ),
        process_frame=process_frame,
    )


async def wait_for_condition(
    condition: SyncCondition,
    *,
    timeout_seconds: float = 1.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    while True:
        if condition():
            return

        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Timed out waiting for condition")

        await asyncio.sleep(0.01)


async def wait_for_async_condition(
    condition: AsyncCondition,
    *,
    timeout_seconds: float = 1.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    while True:
        if await condition():
            return

        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Timed out waiting for asynchronous condition")

        await asyncio.sleep(0.01)


async def test_camera_detections_run_concurrently() -> None:
    manager = StreamManager()

    camera_ids = (
        "camera-001",
        "camera-002",
    )

    detection_entered = {camera_id: asyncio.Event() for camera_id in camera_ids}
    detection_completed = {camera_id: asyncio.Event() for camera_id in camera_ids}

    release_detection = asyncio.Event()

    async def process_frame(
        frame: StreamFrame,
        confidence_threshold: float,
    ) -> object:
        assert confidence_threshold == 0.35

        detection_entered[frame.camera_id].set()

        await release_detection.wait()

        detection_completed[frame.camera_id].set()

        return {
            "camera_id": frame.camera_id,
            "sequence_number": (frame.sequence_number),
        }

    workers: list[ContinuousDetectionWorker] = []

    for camera_id in camera_ids:
        config = create_config(camera_id)
        source = BufferedStreamSource(
            config=config,
            frames=create_frames(
                camera_id,
                1,
            ),
        )

        worker = create_worker(
            config=config,
            source=source,
            process_frame=process_frame,
        )

        workers.append(worker)
        await manager.register(worker)

    try:
        await manager.start_all()

        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in detection_entered.values())),
            timeout=INTEGRATION_TIMEOUT_SECONDS,
        )

        # Both processors reached the shared release point. This proves
        # one camera's inference does not serialize every other worker.
        snapshot = await manager.snapshot()

        assert snapshot.total_workers == 2
        assert snapshot.running_workers == 2
        assert all(worker.running for worker in snapshot.workers)

        release_detection.set()

        release_detection.set()

        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in detection_completed.values())),
            timeout=INTEGRATION_TIMEOUT_SECONDS,
        )

        for worker in workers:
            worker_snapshot = await worker.snapshot()

            assert worker_snapshot.runtime.frames_processed == 1
            assert worker_snapshot.runtime.detection_failures == 0
    finally:
        release_detection.set()
        await manager.shutdown()


async def test_slow_detection_drops_stale_frames() -> None:
    manager = StreamManager()
    camera_id = "camera-pressure"

    config = create_config(
        camera_id,
        queue_capacity=1,
    )

    permit_additional_reads = ThreadEvent()
    release_detection = asyncio.Event()
    first_detection_started = asyncio.Event()

    processed_sequences: list[int] = []

    source = BufferedStreamSource(
        config=config,
        frames=create_frames(
            camera_id,
            10,
        ),
        additional_reads_gate=(permit_additional_reads),
    )

    async def process_frame(
        frame: StreamFrame,
        _: float,
    ) -> object:
        processed_sequences.append(frame.sequence_number)

        if frame.sequence_number == 0:
            # Allow capture to emit frames 1-9 while detection remains
            # deliberately blocked on frame 0.
            permit_additional_reads.set()
            first_detection_started.set()

            await release_detection.wait()

        return {
            "sequence_number": (frame.sequence_number),
        }

    worker = create_worker(
        config=config,
        source=source,
        process_frame=process_frame,
    )

    await manager.register(worker)

    try:
        await manager.start(camera_id)

        await asyncio.wait_for(
            first_detection_started.wait(),
            timeout=1.0,
        )

        await wait_for_condition(
            lambda: source.remaining_frames == 0,
            timeout_seconds=INTEGRATION_TIMEOUT_SECONDS,
        )

        async def all_frames_received() -> bool:
            snapshot = await worker.snapshot()

            return snapshot.runtime.frames_received >= 10

        await wait_for_async_condition(all_frames_received)

        blocked_snapshot = await worker.snapshot()

        assert blocked_snapshot.runtime.frames_received == 10
        assert blocked_snapshot.runtime.frames_dropped >= 8

        release_detection.set()

        await wait_for_condition(
            lambda: len(processed_sequences) >= 2,
        )

        # Capacity one retains only the newest frame while inference is
        # occupied by frame zero.
        assert processed_sequences == [
            0,
            9,
        ]

        final_snapshot = await worker.snapshot()

        assert final_snapshot.runtime.frames_processed == 2
        assert final_snapshot.runtime.frames_dropped >= 8
    finally:
        release_detection.set()
        permit_additional_reads.set()
        await manager.shutdown()


async def test_failed_camera_does_not_stop_healthy_camera() -> None:
    manager = StreamManager()

    failed_config = create_config(
        "camera-failed",
        maximum_consecutive_read_failures=1,
    )
    healthy_config = create_config("camera-healthy")

    failed_source = BufferedStreamSource(
        config=failed_config,
        always_fail_open=True,
    )
    healthy_source = BufferedStreamSource(
        config=healthy_config,
        frames=create_frames(
            healthy_config.camera_id,
            1,
        ),
    )

    healthy_processed = asyncio.Event()

    async def reject_unexpected_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        raise AssertionError("Failed camera must not produce a frame")

    async def process_healthy_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        healthy_processed.set()

        return {
            "detections": [],
        }

    failed_worker = create_worker(
        config=failed_config,
        source=failed_source,
        process_frame=reject_unexpected_frame,
        maximum_reconnect_attempts=1,
    )
    healthy_worker = create_worker(
        config=healthy_config,
        source=healthy_source,
        process_frame=process_healthy_frame,
    )

    await manager.register(failed_worker)
    await manager.register(healthy_worker)

    try:
        await manager.start_all()

        await asyncio.wait_for(
            healthy_processed.wait(),
            timeout=1.0,
        )

        async def failed_worker_reached_terminal_state() -> bool:
            snapshot = await failed_worker.snapshot()

            return snapshot.runtime.state is StreamState.FAILED and not snapshot.running

        await wait_for_async_condition(
            failed_worker_reached_terminal_state,
            timeout_seconds=2.0,
        )

        failed_snapshot = await failed_worker.snapshot()
        healthy_snapshot = await healthy_worker.snapshot()
        manager_snapshot = await manager.snapshot()

        assert failed_snapshot.runtime.state is StreamState.FAILED
        assert failed_snapshot.running is False

        assert healthy_snapshot.runtime.frames_processed >= 1
        assert healthy_snapshot.running is True

        assert manager_snapshot.total_workers == 2
        assert manager_snapshot.failed_workers == 1
        assert manager_snapshot.running_workers == 1
    finally:
        await manager.shutdown()


async def test_manager_shutdown_cleans_all_worker_tasks() -> None:
    manager = StreamManager()

    workers: list[ContinuousDetectionWorker] = []
    sources: list[BufferedStreamSource] = []

    async def process_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        return {
            "detections": [],
        }

    for index in range(1, 4):
        camera_id = f"camera-{index:03d}"
        config = create_config(camera_id)

        source = BufferedStreamSource(
            config=config,
        )
        worker = create_worker(
            config=config,
            source=source,
            process_frame=process_frame,
        )

        sources.append(source)
        workers.append(worker)

        await manager.register(worker)

    await manager.start_all()

    await wait_for_condition(
        lambda: source.remaining_frames == 0,
        timeout_seconds=INTEGRATION_TIMEOUT_SECONDS,
    )

    await asyncio.wait_for(
        manager.shutdown(),
        timeout=2.0,
    )

    assert manager.closed is True
    assert await manager.camera_ids() == ()

    for worker in workers:
        snapshot = await worker.snapshot()

        assert snapshot.running is False
        assert snapshot.disposed is True
        assert snapshot.queue.closed is True

    assert all(source.is_open is False for source in sources)
    assert all(source.close_calls >= 1 for source in sources)

    # Allow cancelled task callbacks to finish before inspecting the
    # event loop.
    await asyncio.sleep(0)

    task_prefixes = (
        "continuous-detection:",
        "camera-capture:",
        "camera-detection:",
    )

    current_task = asyncio.current_task()

    leaked_worker_tasks = [
        task
        for task in asyncio.all_tasks()
        if (
            task is not current_task
            and not task.done()
            and task.get_name().startswith(task_prefixes)
        )
    ]

    assert leaked_worker_tasks == []

    # Shutdown is idempotent.
    await manager.shutdown()
