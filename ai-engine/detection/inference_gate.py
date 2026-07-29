from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from detection.exceptions import (
    InferenceOverloadedError,
)


@dataclass(frozen=True, slots=True)
class InferenceGateSnapshot:
    maximum_concurrent: int
    active: int
    waiting: int
    available: int


class InferenceGate:
    """
    Limit concurrent inference operations and bound queue time.
    """

    def __init__(
        self,
        *,
        maximum_concurrent: int,
        queue_timeout_seconds: float,
    ) -> None:
        if maximum_concurrent <= 0:
            raise ValueError("maximum_concurrent must be positive")

        if queue_timeout_seconds <= 0:
            raise ValueError("queue_timeout_seconds must be positive")

        self.maximum_concurrent = maximum_concurrent
        self.queue_timeout_seconds = queue_timeout_seconds

        self._semaphore = asyncio.Semaphore(maximum_concurrent)
        self._counter_lock = asyncio.Lock()

        self._active = 0
        self._waiting = 0

    @asynccontextmanager
    async def acquire(
        self,
        *,
        correlation_id: UUID,
    ) -> AsyncIterator[None]:
        async with self._counter_lock:
            self._waiting += 1

        try:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(),
                    timeout=(self.queue_timeout_seconds),
                )
            except TimeoutError as exception:
                raise InferenceOverloadedError(
                    correlation_id=correlation_id,
                    retry_after_seconds=1,
                ) from exception
        finally:
            async with self._counter_lock:
                self._waiting -= 1

        async with self._counter_lock:
            self._active += 1

        try:
            yield
        finally:
            async with self._counter_lock:
                self._active -= 1

            self._semaphore.release()

    async def snapshot(
        self,
    ) -> InferenceGateSnapshot:
        async with self._counter_lock:
            active = self._active
            waiting = self._waiting

        return InferenceGateSnapshot(
            maximum_concurrent=(self.maximum_concurrent),
            active=active,
            waiting=waiting,
            available=max(
                0,
                self.maximum_concurrent - active,
            ),
        )
