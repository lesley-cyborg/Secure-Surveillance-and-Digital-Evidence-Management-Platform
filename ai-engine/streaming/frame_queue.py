from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from streaming.domain import StreamFrame
from streaming.exceptions import (
    FrameQueueClosedError,
    FrameQueueTimeoutError,
)


@dataclass(
    frozen=True,
    slots=True,
)
class FramePublishResult:
    """Result of publishing one frame."""

    dropped_frames: int
    queue_size: int
    total_published_frames: int


@dataclass(
    frozen=True,
    slots=True,
)
class FrameQueueSnapshot:
    """Current queue state and cumulative counters."""

    capacity: int
    size: int
    closed: bool

    published_frames: int
    consumed_frames: int
    dropped_frames: int


class LatestFrameQueue:
    """Bounded asynchronous queue that discards oldest frames.

    Capacity 1 gives strict latest-frame behaviour. Higher capacities
    retain a small recent window while still preventing unbounded
    memory growth.
    """

    def __init__(
        self,
        *,
        capacity: int = 1,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")

        self._capacity = capacity
        self._frames: deque[StreamFrame] = deque()
        self._condition = asyncio.Condition()

        self._closed = False
        self._published_frames = 0
        self._consumed_frames = 0
        self._dropped_frames = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def closed(self) -> bool:
        return self._closed

    async def publish(
        self,
        frame: StreamFrame,
    ) -> FramePublishResult:
        """Publish a frame without waiting for queue capacity."""

        async with self._condition:
            if self._closed:
                raise FrameQueueClosedError("Cannot publish to a closed frame queue")

            dropped_frames = 0

            while len(self._frames) >= self._capacity:
                self._frames.popleft()
                dropped_frames += 1

            self._frames.append(frame)

            self._published_frames += 1
            self._dropped_frames += dropped_frames

            queue_size = len(self._frames)

            self._condition.notify(1)

            return FramePublishResult(
                dropped_frames=dropped_frames,
                queue_size=queue_size,
                total_published_frames=(self._published_frames),
            )

    async def get(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> StreamFrame:
        """Wait for and return the oldest retained frame."""

        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        async with self._condition:
            try:
                if timeout_seconds is None:
                    await self._condition.wait_for(self._frame_available_or_closed)
                else:
                    await asyncio.wait_for(
                        self._condition.wait_for(self._frame_available_or_closed),
                        timeout=timeout_seconds,
                    )
            except TimeoutError as exception:
                raise FrameQueueTimeoutError(
                    "Timed out waiting for a camera frame"
                ) from exception

            if self._frames:
                frame = self._frames.popleft()
                self._consumed_frames += 1

                return frame

            raise FrameQueueClosedError("Frame queue is closed")

    async def clear(self) -> int:
        """Discard all pending frames."""

        async with self._condition:
            discarded_frames = len(self._frames)

            self._frames.clear()
            self._dropped_frames += discarded_frames

            return discarded_frames

    async def close(
        self,
        *,
        discard_pending: bool = True,
    ) -> None:
        """Close the queue and wake blocked consumers."""

        async with self._condition:
            if self._closed:
                return

            self._closed = True

            if discard_pending:
                discarded_frames = len(self._frames)
                self._frames.clear()
                self._dropped_frames += discarded_frames

            self._condition.notify_all()

    async def snapshot(
        self,
    ) -> FrameQueueSnapshot:
        async with self._condition:
            return FrameQueueSnapshot(
                capacity=self._capacity,
                size=len(self._frames),
                closed=self._closed,
                published_frames=(self._published_frames),
                consumed_frames=(self._consumed_frames),
                dropped_frames=(self._dropped_frames),
            )

    def _frame_available_or_closed(
        self,
    ) -> bool:
        return bool(self._frames) or self._closed
