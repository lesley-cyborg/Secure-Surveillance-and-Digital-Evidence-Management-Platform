from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from streaming.domain import CameraStreamConfig
from streaming.manager import ManagedStreamWorker


type StreamWorkerBuilder = Callable[
    [CameraStreamConfig],
    ManagedStreamWorker,
]


@runtime_checkable
class StreamWorkerFactory(Protocol):
    """Construct a worker for one validated camera configuration."""

    def create(
        self,
        config: CameraStreamConfig,
    ) -> ManagedStreamWorker: ...


@dataclass(slots=True)
class CallableStreamWorkerFactory:
    """Factory backed by an application composition function."""

    builder: StreamWorkerBuilder

    def create(
        self,
        config: CameraStreamConfig,
    ) -> ManagedStreamWorker:
        return self.builder(config)