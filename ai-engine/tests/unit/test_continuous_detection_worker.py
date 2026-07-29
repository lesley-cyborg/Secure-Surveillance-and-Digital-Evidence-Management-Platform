from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock

import numpy as np
import pytest

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
    StreamState,
)
from streaming.exceptions import (
    StreamNotOpenError,
    StreamOpenError,
    StreamReadError,
    StreamWorkerDisposedError,
)
from streaming.frame_queue import (
    LatestFrameQueue,
)
from streaming.frame_sampler import (
    FrameSampler,
)
from streaming.reconnect_policy import (
    ReconnectPolicy,
    ReconnectPolicyConfig,
)
from streaming.worker import (
    ContinuousDetectionWorker,
)


class IncrementingClock:
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


class ScriptedStreamSource:
    def __init__(
        self,
        *,
        config: CameraStreamConfig,
        frames: list[StreamFrame] | None = None,
        open_failures: int = 0,
        always_fail_open: bool = False,
        empty_read_delay_seconds: float = 0.01,
    ) -> None:
        self._config = config
        self._frames = deque(frames or [])
        self._open_failures = open_failures
        self._always_fail_open = always_fail_open
        self._empty_read_delay_seconds = empty_read_delay_seconds

        self._is_open = False
        self._lock = Lock()

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

    def open(self) -> None:
        with self._lock:
            self.open_calls += 1

            if self._always_fail_open:
                raise StreamOpenError("scripted open failure")

            if self._open_failures > 0:
                self._open_failures -= 1

                raise StreamOpenError("scripted open failure")

            self._is_open = True

    def read(self) -> StreamFrame:
        with self._lock:
            if not self._is_open:
                raise StreamNotOpenError("source is not open")

            self.read_calls += 1

            if self._frames:
                return self._frames.popleft()

        time.sleep(self._empty_read_delay_seconds)

        raise StreamReadError("no scripted frame available")

    def close(self) -> None:
        with self._lock:
            self.close_calls += 1
            self._is_open = False


class RecordingSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(
        self,
        delay_seconds: float,
    ) -> None:
        self.delays.append(delay_seconds)
        await asyncio.sleep(0)


def create_config(
    *,
    maximum_consecutive_read_failures: int = 1,
    queue_capacity: int = 1,
) -> CameraStreamConfig:
    return CameraStreamConfig(
        camera_id="camera-001",
        name="Main entrance",
        source_uri=("rtsp://operator:secret@10.0.0.5:554/stream"),
        target_fps=10.0,
        confidence_threshold=0.35,
        queue_capacity=queue_capacity,
        maximum_consecutive_read_failures=(maximum_consecutive_read_failures),
    )


def create_frame(
    sequence_number: int,
) -> StreamFrame:
    timestamp = datetime.now(UTC)

    return StreamFrame(
        camera_id="camera-001",
        sequence_number=sequence_number,
        captured_at=timestamp,
        received_at=timestamp,
        image=np.zeros(
            (16, 16, 3),
            dtype=np.uint8,
        ),
    )


def create_policy(
    *,
    maximum_attempts: int | None = None,
    sleeper: RecordingSleeper | None = None,
) -> ReconnectPolicy:
    return ReconnectPolicy(
        config=ReconnectPolicyConfig(
            initial_delay_seconds=0.01,
            multiplier=1.0,
            maximum_delay_seconds=0.01,
            jitter_ratio=0.0,
            maximum_attempts=maximum_attempts,
        ),
        sleep=sleeper,
    )


async def wait_for_condition(
    condition: Callable[[], bool],
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


async def test_worker_processes_sampled_frame() -> None:
    config = create_config()

    source = ScriptedStreamSource(
        config=config,
        frames=[
            create_frame(0),
        ],
    )

    processed_event = asyncio.Event()
    processed_sequences: list[int] = []

    async def process_frame(
        frame: StreamFrame,
        confidence_threshold: float,
    ) -> object:
        assert confidence_threshold == 0.35

        processed_sequences.append(frame.sequence_number)
        processed_event.set()

        return {
            "detections": [],
        }

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
            clock=IncrementingClock(),
        ),
        frame_queue=LatestFrameQueue(
            capacity=config.queue_capacity,
        ),
        reconnect_policy=create_policy(),
        process_frame=process_frame,
    )

    await worker.start()

    try:
        await asyncio.wait_for(
            processed_event.wait(),
            timeout=3.0,
        )

        snapshot = await worker.snapshot()

        assert processed_sequences == [0]
        assert snapshot.runtime.frames_received == 1
        assert snapshot.runtime.frames_published == 1
        assert snapshot.runtime.frames_processed == 1
        assert snapshot.runtime.detection_failures == 0
        assert snapshot.runtime.last_frame_at is not None
    finally:
        await worker.stop()

    stopped = await worker.snapshot()

    assert stopped.runtime.state is StreamState.STOPPED
    assert stopped.running is False
    assert source.close_calls >= 1


async def test_worker_reconnects_after_open_failure() -> None:
    config = create_config()
    sleeper = RecordingSleeper()

    source = ScriptedStreamSource(
        config=config,
        frames=[
            create_frame(0),
        ],
        open_failures=1,
    )

    processed_event = asyncio.Event()

    async def process_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        processed_event.set()
        return None

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
            clock=IncrementingClock(),
        ),
        frame_queue=LatestFrameQueue(
            capacity=config.queue_capacity,
        ),
        reconnect_policy=create_policy(
            sleeper=sleeper,
        ),
        process_frame=process_frame,
    )

    await worker.start()

    try:
        await wait_for_condition(
            lambda: source.open_calls >= 2,
            timeout_seconds=3.0,
        )

        await asyncio.wait_for(
            processed_event.wait(),
            timeout=3.0,
        )

        snapshot = await worker.snapshot()

        assert source.open_calls >= 2
        assert snapshot.runtime.reconnect_attempts >= 1

        assert sleeper.delays
        assert sleeper.delays[0] == pytest.approx(0.01)
    finally:
        await worker.stop()


async def test_detection_failure_does_not_stop_worker() -> None:
    config = create_config(
        queue_capacity=2,
    )

    source = ScriptedStreamSource(
        config=config,
        frames=[
            create_frame(0),
            create_frame(1),
        ],
    )

    second_frame_processed = asyncio.Event()
    attempts = 0

    async def process_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        nonlocal attempts

        attempts += 1

        if attempts == 1:
            raise RuntimeError("scripted detection failure")

        second_frame_processed.set()
        return None

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
            clock=IncrementingClock(),
        ),
        frame_queue=LatestFrameQueue(
            capacity=config.queue_capacity,
        ),
        reconnect_policy=create_policy(),
        process_frame=process_frame,
    )

    await worker.start()

    try:
        await asyncio.wait_for(
            second_frame_processed.wait(),
            timeout=3.0,
        )

        snapshot = await worker.snapshot()

        assert attempts == 2
        assert snapshot.runtime.detection_failures == 1
        assert snapshot.runtime.frames_processed >= 1
        assert snapshot.runtime.state in {
            StreamState.CONNECTED,
            StreamState.CONNECTING,
            StreamState.RECONNECTING,
        }
    finally:
        await worker.stop()


async def test_exhausted_retries_mark_worker_failed() -> None:
    config = create_config()
    sleeper = RecordingSleeper()

    source = ScriptedStreamSource(
        config=config,
        always_fail_open=True,
    )

    async def process_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        raise AssertionError("No frame should be processed")

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
            clock=IncrementingClock(),
        ),
        frame_queue=LatestFrameQueue(capacity=config.queue_capacity),
        reconnect_policy=create_policy(
            maximum_attempts=1,
            sleeper=sleeper,
        ),
        process_frame=process_frame,
    )

    await worker.start()

    async def worker_failed() -> bool:
        snapshot = await worker.snapshot()

        return snapshot.runtime.state is StreamState.FAILED

    deadline = asyncio.get_running_loop().time() + 1.0

    while True:
        if await worker_failed():
            break

        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Worker did not enter FAILED state")

        await asyncio.sleep(0.01)

    snapshot = await worker.snapshot()

    assert snapshot.runtime.state is StreamState.FAILED
    assert snapshot.runtime.reconnect_attempts == 1
    assert snapshot.runtime.last_error is not None
    assert source.open_calls >= 2

    await worker.stop()


async def test_stop_cancels_worker_and_closes_source() -> None:
    config = create_config()

    source = ScriptedStreamSource(
        config=config,
        empty_read_delay_seconds=0.02,
    )

    async def process_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        return None

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
            clock=IncrementingClock(),
        ),
        frame_queue=LatestFrameQueue(capacity=config.queue_capacity),
        reconnect_policy=create_policy(),
        process_frame=process_frame,
    )

    await worker.start()

    await wait_for_condition(lambda: source.open_calls >= 1)

    await asyncio.wait_for(
        worker.stop(),
        timeout=1.0,
    )

    snapshot = await worker.snapshot()

    assert snapshot.running is False
    assert snapshot.runtime.state is StreamState.STOPPED
    assert source.is_open is False
    assert source.close_calls >= 1


async def test_disposed_worker_cannot_restart() -> None:
    config = create_config()

    source = ScriptedStreamSource(config=config)

    async def process_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        return None

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
        ),
        frame_queue=LatestFrameQueue(capacity=config.queue_capacity),
        reconnect_policy=create_policy(),
        process_frame=process_frame,
    )

    await worker.dispose()

    snapshot = await worker.snapshot()

    assert snapshot.disposed is True
    assert snapshot.queue.closed is True

    with pytest.raises(StreamWorkerDisposedError):
        await worker.start()


async def test_repeated_read_failures_exhaust_retries() -> None:
    config = create_config()
    sleeper = RecordingSleeper()

    # Opening succeeds, but there are no valid frames.
    source = ScriptedStreamSource(
        config=config,
        frames=[],
    )

    async def process_frame(
        _: StreamFrame,
        __: float,
    ) -> object:
        raise AssertionError("No frame should be processed")

    worker = ContinuousDetectionWorker(
        config=config,
        source=source,
        sampler=FrameSampler(
            target_fps=config.target_fps,
            clock=IncrementingClock(),
        ),
        frame_queue=LatestFrameQueue(
            capacity=config.queue_capacity,
        ),
        reconnect_policy=create_policy(
            maximum_attempts=2,
            sleeper=sleeper,
        ),
        process_frame=process_frame,
    )

    await worker.start()

    try:
        deadline = asyncio.get_running_loop().time() + 3.0

        while True:
            snapshot = await worker.snapshot()

            if snapshot.runtime.state is StreamState.FAILED:
                break

            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Worker did not exhaust read-failure retries")

            await asyncio.sleep(0.01)

        assert snapshot.runtime.reconnect_attempts == 2
        assert snapshot.reconnect.exhausted is True
        assert source.open_calls == 3
        assert len(sleeper.delays) == 2
    finally:
        await worker.stop()
