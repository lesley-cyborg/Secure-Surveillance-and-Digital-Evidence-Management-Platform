from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from streaming.domain import (
    CameraStreamConfig,
    StreamState,
)
from streaming.exceptions import (
    StreamManagerClosedError,
    StreamWorkerAlreadyRegisteredError,
    StreamWorkerNotRegisteredError,
)
from streaming.manager import (
    StreamManager,
)


@dataclass(
    frozen=True,
    slots=True,
)
class FakeRuntimeSnapshot:
    state: StreamState


@dataclass(
    frozen=True,
    slots=True,
)
class FakeWorkerSnapshot:
    runtime: FakeRuntimeSnapshot
    running: bool
    disposed: bool


class ConcurrencyProbe:
    def __init__(self) -> None:
        self.active_operations = 0
        self.maximum_active_operations = 0

    async def enter(self) -> None:
        self.active_operations += 1
        self.maximum_active_operations = max(
            self.maximum_active_operations,
            self.active_operations,
        )

        try:
            await asyncio.sleep(0.02)
        finally:
            self.active_operations -= 1


class FakeWorker:
    def __init__(
        self,
        *,
        camera_id: str,
        probe: ConcurrencyProbe | None = None,
    ) -> None:
        self._config = create_config(camera_id)
        self._probe = probe

        self._running = False
        self._disposed = False
        self._state = StreamState.STOPPED

        self.start_calls = 0
        self.stop_calls = 0
        self.dispose_calls = 0

    @property
    def config(self) -> CameraStreamConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def disposed(self) -> bool:
        return self._disposed

    async def start(self) -> None:
        self.start_calls += 1

        if self._disposed:
            raise RuntimeError("disposed worker cannot start")

        if self._probe is not None:
            await self._probe.enter()

        self._running = True
        self._state = StreamState.CONNECTED

    async def stop(self) -> None:
        self.stop_calls += 1

        if self._probe is not None:
            await self._probe.enter()

        self._running = False

        if not self._disposed:
            self._state = StreamState.STOPPED

    async def dispose(self) -> None:
        self.dispose_calls += 1

        if self._probe is not None:
            await self._probe.enter()

        self._running = False
        self._disposed = True
        self._state = StreamState.STOPPED

    async def snapshot(
        self,
    ) -> FakeWorkerSnapshot:
        return FakeWorkerSnapshot(
            runtime=FakeRuntimeSnapshot(state=self._state),
            running=self._running,
            disposed=self._disposed,
        )

    def mark_failed(self) -> None:
        self._running = False
        self._state = StreamState.FAILED


def create_config(
    camera_id: str,
) -> CameraStreamConfig:
    return CameraStreamConfig(
        camera_id=camera_id,
        name=f"Camera {camera_id}",
        source_uri=(f"rtsp://operator:secret@10.0.0.5:554/{camera_id}"),
        target_fps=5.0,
        confidence_threshold=0.35,
        queue_capacity=1,
        maximum_consecutive_read_failures=1,
    )


async def test_manager_registers_and_returns_worker() -> None:
    manager = StreamManager()
    worker = FakeWorker(camera_id="camera-001")

    await manager.register(worker)

    registered = await manager.get("camera-001")

    assert registered is worker
    assert await manager.camera_ids() == ("camera-001",)


async def test_manager_rejects_duplicate_camera_id() -> None:
    manager = StreamManager()

    await manager.register(FakeWorker(camera_id="camera-001"))

    with pytest.raises(StreamWorkerAlreadyRegisteredError):
        await manager.register(FakeWorker(camera_id="camera-001"))


async def test_manager_rejects_unknown_camera() -> None:
    manager = StreamManager()

    with pytest.raises(StreamWorkerNotRegisteredError):
        await manager.start("missing-camera")


async def test_manager_starts_and_stops_independent_worker() -> None:
    manager = StreamManager()

    first = FakeWorker(camera_id="camera-001")
    second = FakeWorker(camera_id="camera-002")

    await manager.register(first)
    await manager.register(second)

    await manager.start("camera-001")

    assert first.is_running is True
    assert second.is_running is False

    await manager.stop("camera-001")

    assert first.is_running is False
    assert first.start_calls == 1
    assert first.stop_calls == 1
    assert second.start_calls == 0


async def test_start_all_runs_workers_concurrently() -> None:
    manager = StreamManager()
    probe = ConcurrencyProbe()

    workers = [
        FakeWorker(
            camera_id=f"camera-{index:03d}",
            probe=probe,
        )
        for index in range(1, 4)
    ]

    for worker in workers:
        await manager.register(worker)

    await manager.start_all()

    assert all(worker.is_running for worker in workers)
    assert probe.maximum_active_operations >= 2


async def test_unregister_disposes_worker() -> None:
    manager = StreamManager()
    worker = FakeWorker(camera_id="camera-001")

    await manager.register(worker)

    removed = await manager.unregister("camera-001")

    assert removed is worker
    assert worker.disposed is True
    assert worker.dispose_calls == 1
    assert await manager.camera_ids() == ()


async def test_snapshot_reports_aggregate_status() -> None:
    manager = StreamManager()

    running_worker = FakeWorker(camera_id="camera-001")
    failed_worker = FakeWorker(camera_id="camera-002")
    stopped_worker = FakeWorker(camera_id="camera-003")

    await manager.register(running_worker)
    await manager.register(failed_worker)
    await manager.register(stopped_worker)

    await running_worker.start()
    failed_worker.mark_failed()

    snapshot = await manager.snapshot()

    assert snapshot.closed is False
    assert snapshot.total_workers == 3
    assert snapshot.running_workers == 1
    assert snapshot.failed_workers == 1
    assert snapshot.disposed_workers == 0

    assert [worker.camera_id for worker in snapshot.workers] == [
        "camera-001",
        "camera-002",
        "camera-003",
    ]


async def test_shutdown_disposes_all_workers_concurrently() -> None:
    manager = StreamManager()
    probe = ConcurrencyProbe()

    workers = [
        FakeWorker(
            camera_id=f"camera-{index:03d}",
            probe=probe,
        )
        for index in range(1, 4)
    ]

    for worker in workers:
        await manager.register(worker)

    await manager.shutdown()

    assert manager.closed is True
    assert all(worker.disposed for worker in workers)
    assert probe.maximum_active_operations >= 2
    assert await manager.camera_ids() == ()

    # Repeated shutdown is safe.
    await manager.shutdown()

    with pytest.raises(StreamManagerClosedError):
        await manager.register(FakeWorker(camera_id="camera-004"))
