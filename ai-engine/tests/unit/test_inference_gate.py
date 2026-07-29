from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from detection.exceptions import (
    InferenceOverloadedError,
)
from detection.inference_gate import (
    InferenceGate,
)


@pytest.mark.asyncio
async def test_gate_tracks_active_inference() -> None:
    gate = InferenceGate(
        maximum_concurrent=1,
        queue_timeout_seconds=1.0,
    )

    async with gate.acquire(
        correlation_id=uuid4(),
    ):
        snapshot = await gate.snapshot()

        assert snapshot.active == 1
        assert snapshot.waiting == 0
        assert snapshot.available == 0

    snapshot = await gate.snapshot()

    assert snapshot.active == 0
    assert snapshot.waiting == 0
    assert snapshot.available == 1


@pytest.mark.asyncio
async def test_gate_rejects_request_after_timeout() -> None:
    gate = InferenceGate(
        maximum_concurrent=1,
        queue_timeout_seconds=0.01,
    )

    async with gate.acquire(
        correlation_id=uuid4(),
    ):
        with pytest.raises(InferenceOverloadedError) as exception:
            async with gate.acquire(
                correlation_id=uuid4(),
            ):
                pytest.fail("Second request unexpectedly acquired capacity")

    assert exception.value.retry_after_seconds == 1


@pytest.mark.asyncio
async def test_gate_allows_next_request_after_release() -> None:
    gate = InferenceGate(
        maximum_concurrent=1,
        queue_timeout_seconds=1.0,
    )

    async with gate.acquire(
        correlation_id=uuid4(),
    ):
        await asyncio.sleep(0)

    async with gate.acquire(
        correlation_id=uuid4(),
    ):
        snapshot = await gate.snapshot()

        assert snapshot.active == 1
        assert snapshot.available == 0


@pytest.mark.asyncio
async def test_gate_tracks_waiting_request() -> None:
    gate = InferenceGate(
        maximum_concurrent=1,
        queue_timeout_seconds=1.0,
    )

    release_first = asyncio.Event()
    first_acquired = asyncio.Event()
    second_acquired = asyncio.Event()

    async def hold_first_slot() -> None:
        async with gate.acquire(
            correlation_id=uuid4(),
        ):
            first_acquired.set()
            await release_first.wait()

    async def wait_for_second_slot() -> None:
        async with gate.acquire(
            correlation_id=uuid4(),
        ):
            second_acquired.set()

    first_task = asyncio.create_task(hold_first_slot())

    await first_acquired.wait()

    second_task = asyncio.create_task(wait_for_second_slot())

    await asyncio.sleep(0)

    snapshot = await gate.snapshot()

    assert snapshot.active == 1
    assert snapshot.waiting == 1
    assert second_acquired.is_set() is False

    release_first.set()

    await first_task
    await second_task

    final_snapshot = await gate.snapshot()

    assert final_snapshot.active == 0
    assert final_snapshot.waiting == 0
