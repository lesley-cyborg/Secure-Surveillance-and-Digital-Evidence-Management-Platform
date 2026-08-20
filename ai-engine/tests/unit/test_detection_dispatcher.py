from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from streaming.detection_dispatcher import (
    DetectionEventDispatcher,
    DetectionEventDispatcherClosedError,
    DetectionEventDispatcherConfig,
    EventQueueOverflowPolicy,
)
from streaming.detection_events import (
    StreamDetectionEvent,
    StreamModelIdentity,
)
from streaming.event_sink import (
    PermanentStreamDetectionEventDeliveryError,
)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StreamDetectionEvent] = []
        self.delivered = asyncio.Event()

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        self.events.append(event)
        self.delivered.set()


class BlockingSink:
    def __init__(self) -> None:
        self.events: list[StreamDetectionEvent] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        self.events.append(event)
        self.entered.set()

        await self.release.wait()


class FailThenSucceedSink:
    def __init__(
        self,
        *,
        failures_before_success: int,
    ) -> None:
        self.failures_before_success = failures_before_success
        self.attempts = 0
        self.delivered = asyncio.Event()

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        del event

        self.attempts += 1

        if self.attempts <= self.failures_before_success:
            raise RuntimeError("temporary delivery failure")

        self.delivered.set()


class AlwaysFailingSink:
    def __init__(self) -> None:
        self.attempts = 0

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        del event

        self.attempts += 1

        raise RuntimeError("permanent delivery failure")


class NeverReturningSink:
    def __init__(self) -> None:
        self.attempts = 0

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        del event

        self.attempts += 1

        await asyncio.Event().wait()


class PermanentlyFailingSink:
    def __init__(self) -> None:
        self.attempts = 0

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        del event

        self.attempts += 1

        raise PermanentStreamDetectionEventDeliveryError("permanent failure")


def create_event(
    sequence_number: int,
) -> StreamDetectionEvent:
    timestamp = datetime.now(UTC)

    return StreamDetectionEvent(
        correlation_id=uuid4(),
        camera_id="camera-001",
        frame_sequence_number=(sequence_number),
        captured_at=timestamp,
        received_at=timestamp,
        processed_at=timestamp,
        model=StreamModelIdentity(
            name="surveillance-yolo",
            version="yolo26n-coco",
            device="cpu",
        ),
        detections=(),
        inference_duration_ms=1.0,
    )


def create_config(
    *,
    queue_capacity: int = 10,
    delivery_workers: int = 1,
    maximum_delivery_attempts: int = 3,
    overflow_policy: EventQueueOverflowPolicy = (EventQueueOverflowPolicy.DROP_OLDEST),
) -> DetectionEventDispatcherConfig:
    return DetectionEventDispatcherConfig(
        queue_capacity=queue_capacity,
        delivery_workers=delivery_workers,
        delivery_timeout_seconds=0.05,
        retry_initial_delay_seconds=0.001,
        retry_multiplier=2.0,
        retry_maximum_delay_seconds=0.005,
        maximum_delivery_attempts=(maximum_delivery_attempts),
        shutdown_timeout_seconds=1.0,
        overflow_policy=overflow_policy,
    )


async def test_dispatcher_delivers_event() -> None:
    sink = RecordingSink()

    dispatcher = DetectionEventDispatcher(
        destination=sink,
        config=create_config(),
    )

    await dispatcher.start()

    await dispatcher.publish(create_event(1))

    await asyncio.wait_for(
        sink.delivered.wait(),
        timeout=1.0,
    )

    await dispatcher.shutdown()

    snapshot = await dispatcher.snapshot()

    assert len(sink.events) == 1
    assert snapshot.published_events == 1
    assert snapshot.delivered_events == 1
    assert snapshot.failed_events == 0
    assert snapshot.closed is True
    assert snapshot.running is False


async def test_publish_does_not_wait_for_slow_sink() -> None:
    sink = BlockingSink()

    dispatcher = DetectionEventDispatcher(
        destination=sink,
        config=create_config(queue_capacity=2),
    )

    await dispatcher.start()

    await asyncio.wait_for(
        dispatcher.publish(create_event(1)),
        timeout=0.1,
    )

    await asyncio.wait_for(
        sink.entered.wait(),
        timeout=1.0,
    )

    await asyncio.wait_for(
        dispatcher.publish(create_event(2)),
        timeout=0.1,
    )

    snapshot = await dispatcher.snapshot()

    assert snapshot.active_deliveries == 1
    assert snapshot.queue_size == 1

    sink.release.set()

    await dispatcher.shutdown()

    assert len(sink.events) == 2


async def test_permanent_failure_is_not_retried() -> None:
    destination = PermanentlyFailingSink()
    dead_letter_sink = RecordingSink()

    dispatcher = DetectionEventDispatcher(
        destination=destination,
        dead_letter_sink=dead_letter_sink,
        config=create_config(maximum_delivery_attempts=5),
    )

    await dispatcher.start()
    await dispatcher.publish(create_event(1))

    await asyncio.wait_for(
        dead_letter_sink.delivered.wait(),
        timeout=1.0,
    )

    await dispatcher.shutdown()

    snapshot = await dispatcher.snapshot()

    assert destination.attempts == 1
    assert snapshot.retried_events == 0
    assert snapshot.failed_events == 1
    assert snapshot.dead_lettered_events == 1


async def test_transient_failure_is_retried() -> None:
    sink = FailThenSucceedSink(failures_before_success=2)

    dispatcher = DetectionEventDispatcher(
        destination=sink,
        config=create_config(maximum_delivery_attempts=3),
    )

    await dispatcher.start()
    await dispatcher.publish(create_event(1))

    await asyncio.wait_for(
        sink.delivered.wait(),
        timeout=1.0,
    )

    await dispatcher.shutdown()

    snapshot = await dispatcher.snapshot()

    assert sink.attempts == 3
    assert snapshot.retried_events == 2
    assert snapshot.delivered_events == 1
    assert snapshot.failed_events == 0


async def test_permanent_failure_is_dead_lettered() -> None:
    destination = AlwaysFailingSink()
    dead_letter_sink = RecordingSink()

    dispatcher = DetectionEventDispatcher(
        destination=destination,
        dead_letter_sink=dead_letter_sink,
        config=create_config(maximum_delivery_attempts=2),
    )

    await dispatcher.start()
    await dispatcher.publish(create_event(1))

    await asyncio.wait_for(
        dead_letter_sink.delivered.wait(),
        timeout=1.0,
    )

    await dispatcher.shutdown()

    snapshot = await dispatcher.snapshot()

    assert destination.attempts == 2
    assert len(dead_letter_sink.events) == 1

    assert snapshot.retried_events == 1
    assert snapshot.failed_events == 1
    assert snapshot.dead_lettered_events == 1


async def test_delivery_timeout_is_retried() -> None:
    destination = NeverReturningSink()
    dead_letter_sink = RecordingSink()

    dispatcher = DetectionEventDispatcher(
        destination=destination,
        dead_letter_sink=dead_letter_sink,
        config=create_config(maximum_delivery_attempts=2),
    )

    await dispatcher.start()
    await dispatcher.publish(create_event(1))

    await asyncio.wait_for(
        dead_letter_sink.delivered.wait(),
        timeout=1.0,
    )

    await dispatcher.shutdown()

    snapshot = await dispatcher.snapshot()

    assert destination.attempts == 2
    assert snapshot.retried_events == 1
    assert snapshot.failed_events == 1
    assert snapshot.dead_lettered_events == 1


async def test_drop_oldest_retains_newest_event() -> None:
    sink = BlockingSink()

    dispatcher = DetectionEventDispatcher(
        destination=sink,
        config=create_config(
            queue_capacity=1,
            overflow_policy=(EventQueueOverflowPolicy.DROP_OLDEST),
        ),
    )

    await dispatcher.start()

    first_event = create_event(1)
    second_event = create_event(2)
    third_event = create_event(3)

    await dispatcher.publish(first_event)

    await asyncio.wait_for(
        sink.entered.wait(),
        timeout=1.0,
    )

    await dispatcher.publish(second_event)
    await dispatcher.publish(third_event)

    snapshot = await dispatcher.snapshot()

    assert snapshot.queue_size == 1
    assert snapshot.dropped_events == 1
    assert snapshot.published_events == 3

    sink.release.set()

    await dispatcher.shutdown()

    delivered_sequences = [event.frame_sequence_number for event in sink.events]

    assert delivered_sequences == [
        1,
        3,
    ]


async def test_shutdown_drains_accepted_events() -> None:
    sink = RecordingSink()

    dispatcher = DetectionEventDispatcher(
        destination=sink,
        config=create_config(queue_capacity=5),
    )

    await dispatcher.start()

    for sequence_number in range(3):
        await dispatcher.publish(create_event(sequence_number))

    await dispatcher.shutdown()

    snapshot = await dispatcher.snapshot()

    assert len(sink.events) == 3
    assert snapshot.delivered_events == 3
    assert snapshot.queue_size == 0
    assert snapshot.closed is True


async def test_publish_after_shutdown_is_rejected() -> None:
    dispatcher = DetectionEventDispatcher(
        destination=RecordingSink(),
        config=create_config(),
    )

    await dispatcher.start()
    await dispatcher.shutdown()

    with pytest.raises(DetectionEventDispatcherClosedError):
        await dispatcher.publish(create_event(1))
