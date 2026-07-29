from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import numpy as np
import pytest

from streaming.domain import StreamFrame
from streaming.exceptions import (
    FrameQueueClosedError,
    FrameQueueTimeoutError,
)
from streaming.frame_queue import (
    LatestFrameQueue,
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
            (8, 8, 3),
            dtype=np.uint8,
        ),
    )


async def test_capacity_one_retains_latest_frame() -> None:
    queue = LatestFrameQueue(capacity=1)

    await queue.publish(create_frame(1))

    result = await queue.publish(create_frame(2))

    frame = await queue.get()

    assert frame.sequence_number == 2
    assert result.dropped_frames == 1
    assert result.queue_size == 1


async def test_queue_drops_oldest_frame_when_full() -> None:
    queue = LatestFrameQueue(capacity=2)

    await queue.publish(create_frame(1))
    await queue.publish(create_frame(2))
    await queue.publish(create_frame(3))

    first_frame = await queue.get()
    second_frame = await queue.get()

    assert first_frame.sequence_number == 2
    assert second_frame.sequence_number == 3

    snapshot = await queue.snapshot()

    assert snapshot.dropped_frames == 1
    assert snapshot.consumed_frames == 2


async def test_get_times_out_when_no_frame_arrives() -> None:
    queue = LatestFrameQueue()

    with pytest.raises(FrameQueueTimeoutError):
        await queue.get(timeout_seconds=0.05)


async def test_close_wakes_waiting_consumer() -> None:
    queue = LatestFrameQueue()

    consumer = asyncio.create_task(queue.get())

    await asyncio.sleep(0)
    await queue.close()

    with pytest.raises(FrameQueueClosedError):
        await consumer


async def test_publish_rejects_closed_queue() -> None:
    queue = LatestFrameQueue()

    await queue.close()

    with pytest.raises(FrameQueueClosedError):
        await queue.publish(create_frame(1))


async def test_close_can_allow_pending_frame_to_drain() -> None:
    queue = LatestFrameQueue()

    await queue.publish(create_frame(1))
    await queue.close(discard_pending=False)

    frame = await queue.get()

    assert frame.sequence_number == 1

    with pytest.raises(FrameQueueClosedError):
        await queue.get()
