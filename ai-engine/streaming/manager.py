from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from streaming.domain import (
    CameraStreamConfig,
    StreamState,
)
from streaming.exceptions import (
    StreamManagerClosedError,
    StreamManagerOperationError,
    StreamWorkerAlreadyRegisteredError,
    StreamWorkerDisposedError,
    StreamWorkerNotRegisteredError,
)


class WorkerRuntimeView(Protocol):
    """Runtime information required by the manager."""

    @property
    def state(self) -> StreamState: ...


class WorkerSnapshotView(Protocol):
    """Worker snapshot information required by the manager."""

    @property
    def runtime(self) -> WorkerRuntimeView: ...

    @property
    def running(self) -> bool: ...

    @property
    def disposed(self) -> bool: ...


class ManagedStreamWorker(Protocol):
    """Structural interface accepted by StreamManager."""

    @property
    def config(self) -> CameraStreamConfig: ...

    @property
    def is_running(self) -> bool: ...

    @property
    def disposed(self) -> bool: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def dispose(self) -> None: ...

    async def snapshot(self) -> WorkerSnapshotView: ...


type WorkerOperation = Callable[
    [ManagedStreamWorker],
    Awaitable[None],
]

type WorkerEntry = tuple[
    str,
    ManagedStreamWorker,
]


@dataclass(
    frozen=True,
    slots=True,
)
class ManagedWorkerSnapshot:
    """Manager-level view of one registered worker."""

    camera_id: str
    state: StreamState
    running: bool
    disposed: bool


@dataclass(
    frozen=True,
    slots=True,
)
class StreamManagerSnapshot:
    """Aggregate state of all registered camera workers."""

    closed: bool

    total_workers: int
    running_workers: int
    failed_workers: int
    disposed_workers: int

    workers: tuple[ManagedWorkerSnapshot, ...]


async def _start_worker(
    worker: ManagedStreamWorker,
) -> None:
    await worker.start()


async def _stop_worker(
    worker: ManagedStreamWorker,
) -> None:
    await worker.stop()


async def _dispose_worker(
    worker: ManagedStreamWorker,
) -> None:
    await worker.dispose()


class StreamManager:
    """Registry and lifecycle coordinator for camera workers."""

    def __init__(self) -> None:
        self._workers: dict[
            str,
            ManagedStreamWorker,
        ] = {}

        self._closed = False

        # Protects the worker registry and closed flag.
        self._registry_lock = asyncio.Lock()

        # Prevents lifecycle operations such as start and shutdown
        # from racing with each other.
        self._operation_lock = asyncio.Lock()

    @property
    def closed(self) -> bool:
        return self._closed

    async def register(
        self,
        worker: ManagedStreamWorker,
    ) -> None:
        """Register one worker by its camera ID."""

        camera_id = worker.config.camera_id

        async with self._operation_lock:
            async with self._registry_lock:
                self._ensure_open_unlocked()

                if worker.disposed:
                    raise StreamWorkerDisposedError(
                        f"Cannot register disposed worker {camera_id!r}"
                    )

                if camera_id in self._workers:
                    raise StreamWorkerAlreadyRegisteredError(
                        f"Camera worker {camera_id!r} is already registered"
                    )

                self._workers[camera_id] = worker

    async def unregister(
        self,
        camera_id: str,
        *,
        dispose: bool = True,
    ) -> ManagedStreamWorker:
        """Remove one worker from the registry.

        By default, the removed worker is permanently disposed.
        """

        async with self._operation_lock:
            async with self._registry_lock:
                self._ensure_open_unlocked()

                worker = self._workers.pop(
                    camera_id,
                    None,
                )

                if worker is None:
                    raise StreamWorkerNotRegisteredError(
                        f"Camera worker {camera_id!r} is not registered"
                    )

            if dispose:
                await worker.dispose()

            return worker

    async def get(
        self,
        camera_id: str,
    ) -> ManagedStreamWorker:
        """Return a registered worker."""

        async with self._registry_lock:
            worker = self._workers.get(camera_id)

            if worker is None:
                raise StreamWorkerNotRegisteredError(
                    f"Camera worker {camera_id!r} is not registered"
                )

            return worker

    async def camera_ids(
        self,
    ) -> tuple[str, ...]:
        """Return registered camera IDs in deterministic order."""

        async with self._registry_lock:
            return tuple(sorted(self._workers))

    async def start(
        self,
        camera_id: str,
    ) -> None:
        """Start one registered camera worker."""

        async with self._operation_lock:
            worker = await self._get_open_worker(camera_id)

            await worker.start()

    async def stop(
        self,
        camera_id: str,
    ) -> None:
        """Stop one registered camera worker."""

        async with self._operation_lock:
            worker = await self._get_open_worker(camera_id)

            await worker.stop()

    async def start_all(self) -> None:
        """Start every registered worker concurrently."""

        async with self._operation_lock:
            entries = await self._open_entries()

            await self._run_many(
                operation_name="start_all",
                entries=entries,
                operation=_start_worker,
            )

    async def stop_all(self) -> None:
        """Stop every registered worker concurrently."""

        async with self._operation_lock:
            entries = await self._open_entries()

            await self._run_many(
                operation_name="stop_all",
                entries=entries,
                operation=_stop_worker,
            )

    async def snapshot(
        self,
    ) -> StreamManagerSnapshot:
        """Return aggregate status for all registered workers."""

        async with self._registry_lock:
            closed = self._closed

            entries = tuple(
                sorted(
                    self._workers.items(),
                    key=lambda item: item[0],
                )
            )

        worker_snapshots = await asyncio.gather(
            *(worker.snapshot() for _, worker in entries)
        )

        managed_snapshots = tuple(
            ManagedWorkerSnapshot(
                camera_id=camera_id,
                state=worker_snapshot.runtime.state,
                running=worker_snapshot.running,
                disposed=worker_snapshot.disposed,
            )
            for (
                camera_id,
                _,
            ), worker_snapshot in zip(
                entries,
                worker_snapshots,
                strict=True,
            )
        )

        return StreamManagerSnapshot(
            closed=closed,
            total_workers=len(managed_snapshots),
            running_workers=sum(snapshot.running for snapshot in managed_snapshots),
            failed_workers=sum(
                snapshot.state is StreamState.FAILED for snapshot in managed_snapshots
            ),
            disposed_workers=sum(snapshot.disposed for snapshot in managed_snapshots),
            workers=managed_snapshots,
        )

    async def shutdown(self) -> None:
        """Dispose all workers and permanently close the manager.

        The registry is cleared atomically before disposal starts,
        preventing new workers from being registered during shutdown.
        """

        async with self._operation_lock:
            async with self._registry_lock:
                if self._closed:
                    return

                self._closed = True

                entries = tuple(
                    sorted(
                        self._workers.items(),
                        key=lambda item: item[0],
                    )
                )

                self._workers.clear()

            await self._run_many(
                operation_name="shutdown",
                entries=entries,
                operation=_dispose_worker,
            )

    async def _get_open_worker(
        self,
        camera_id: str,
    ) -> ManagedStreamWorker:
        async with self._registry_lock:
            self._ensure_open_unlocked()

            worker = self._workers.get(camera_id)

            if worker is None:
                raise StreamWorkerNotRegisteredError(
                    f"Camera worker {camera_id!r} is not registered"
                )

            return worker

    async def _open_entries(
        self,
    ) -> tuple[WorkerEntry, ...]:
        async with self._registry_lock:
            self._ensure_open_unlocked()

            return tuple(
                sorted(
                    self._workers.items(),
                    key=lambda item: item[0],
                )
            )

    def _ensure_open_unlocked(self) -> None:
        if self._closed:
            raise StreamManagerClosedError("Stream manager has been shut down")

    @staticmethod
    async def _run_many(
        *,
        operation_name: str,
        entries: tuple[WorkerEntry, ...],
        operation: WorkerOperation,
    ) -> None:
        if not entries:
            return

        results = await asyncio.gather(
            *(operation(worker) for _, worker in entries),
            return_exceptions=True,
        )

        failures: dict[
            str,
            BaseException,
        ] = {}

        for (
            camera_id,
            _,
        ), result in zip(
            entries,
            results,
            strict=True,
        ):
            if isinstance(
                result,
                asyncio.CancelledError,
            ):
                raise result

            if isinstance(
                result,
                BaseException,
            ):
                failures[camera_id] = result

        if failures:
            raise StreamManagerOperationError(
                operation=operation_name,
                failures=failures,
            )
