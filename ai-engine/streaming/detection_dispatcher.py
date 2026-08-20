from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from enum import StrEnum

import structlog

from streaming.detection_events import (
    StreamDetectionEvent,
)
from streaming.event_sink import (
    NullStreamDetectionEventSink,
    PermanentStreamDetectionEventDeliveryError,
    StreamDetectionEventSink,
)

logger = structlog.get_logger(__name__)


class DetectionEventDispatcherError(Exception):
    """Base exception for event-dispatcher failures."""


class DetectionEventDispatcherClosedError(DetectionEventDispatcherError):
    """Raised when an event is published after closure."""


class EventQueueOverflowPolicy(StrEnum):
    """Behaviour used when the bounded queue is full."""

    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"


@dataclass(
    frozen=True,
    slots=True,
)
class DetectionEventDispatcherConfig:
    """Immutable dispatcher configuration."""

    queue_capacity: int = 1_000
    delivery_workers: int = 1

    delivery_timeout_seconds: float = 10.0

    retry_initial_delay_seconds: float = 0.5
    retry_multiplier: float = 2.0
    retry_maximum_delay_seconds: float = 30.0
    maximum_delivery_attempts: int = 5

    shutdown_timeout_seconds: float = 15.0

    overflow_policy: EventQueueOverflowPolicy = EventQueueOverflowPolicy.DROP_OLDEST

    def __post_init__(self) -> None:
        if self.queue_capacity < 1:
            raise ValueError("queue_capacity must be at least 1")

        if self.delivery_workers < 1:
            raise ValueError("delivery_workers must be at least 1")

        self._validate_positive_finite(
            self.delivery_timeout_seconds,
            field_name="delivery_timeout_seconds",
        )
        self._validate_positive_finite(
            self.retry_initial_delay_seconds,
            field_name=("retry_initial_delay_seconds"),
        )
        self._validate_positive_finite(
            self.retry_maximum_delay_seconds,
            field_name=("retry_maximum_delay_seconds"),
        )
        self._validate_positive_finite(
            self.shutdown_timeout_seconds,
            field_name="shutdown_timeout_seconds",
        )

        if not math.isfinite(self.retry_multiplier):
            raise ValueError("retry_multiplier must be finite")

        if self.retry_multiplier < 1:
            raise ValueError("retry_multiplier must be at least 1")

        if self.retry_maximum_delay_seconds < self.retry_initial_delay_seconds:
            raise ValueError(
                "retry_maximum_delay_seconds cannot "
                "be less than "
                "retry_initial_delay_seconds"
            )

        if self.maximum_delivery_attempts < 1:
            raise ValueError("maximum_delivery_attempts must be at least 1")

    @staticmethod
    def _validate_positive_finite(
        value: float,
        *,
        field_name: str,
    ) -> None:
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must be finite")

        if value <= 0:
            raise ValueError(f"{field_name} must be positive")


@dataclass(
    frozen=True,
    slots=True,
)
class DetectionEventDispatcherSnapshot:
    """Read-only dispatcher runtime state."""

    queue_capacity: int
    queue_size: int

    delivery_workers: int
    active_deliveries: int

    accepting_events: bool
    running: bool
    closed: bool

    published_events: int
    delivered_events: int
    retried_events: int
    failed_events: int

    dead_lettered_events: int
    dead_letter_failures: int

    dropped_events: int
    shutdown_timeouts: int


@dataclass(slots=True)
class _DispatcherCounters:
    published_events: int = 0
    delivered_events: int = 0
    retried_events: int = 0
    failed_events: int = 0

    dead_lettered_events: int = 0
    dead_letter_failures: int = 0

    dropped_events: int = 0
    shutdown_timeouts: int = 0

    active_deliveries: int = 0


class DetectionEventDispatcher:
    """Bounded asynchronous detection-event dispatcher."""

    def __init__(
        self,
        *,
        destination: StreamDetectionEventSink,
        config: DetectionEventDispatcherConfig,
        dead_letter_sink: (StreamDetectionEventSink | None) = None,
    ) -> None:
        self._destination = destination
        self._dead_letter_sink = (
            dead_letter_sink
            if dead_letter_sink is not None
            else NullStreamDetectionEventSink()
        )
        self._config = config

        self._queue: asyncio.Queue[StreamDetectionEvent] = asyncio.Queue(
            maxsize=config.queue_capacity
        )

        self._worker_tasks: tuple[
            asyncio.Task[None],
            ...,
        ] = ()

        self._lifecycle_lock = asyncio.Lock()
        self._metrics_lock = asyncio.Lock()

        self._counters = _DispatcherCounters()

        self._started = False
        self._accepting_events = False
        self._closed = False

    @property
    def config(
        self,
    ) -> DetectionEventDispatcherConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._started and any(not task.done() for task in self._worker_tasks)

    @property
    def closed(self) -> bool:
        return self._closed

    async def start(self) -> None:
        """Start background delivery workers."""

        async with self._lifecycle_lock:
            if self._closed:
                raise DetectionEventDispatcherClosedError(
                    "Detection event dispatcher has been closed"
                )

            if self._started:
                return

            self._worker_tasks = tuple(
                asyncio.create_task(
                    self._delivery_loop(),
                    name=(f"stream-event-dispatcher:{worker_index}"),
                )
                for worker_index in range(self._config.delivery_workers)
            )

            self._started = True
            self._accepting_events = True

        logger.info(
            "detection_event_dispatcher_started",
            queue_capacity=(self._config.queue_capacity),
            delivery_workers=(self._config.delivery_workers),
            overflow_policy=(self._config.overflow_policy.value),
        )

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        """Accept an event without waiting for delivery."""

        if not self._accepting_events or self._closed:
            raise DetectionEventDispatcherClosedError(
                "Detection event dispatcher is not accepting events"
            )

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            accepted = await self._handle_queue_full(event)

            if not accepted:
                return

        async with self._metrics_lock:
            self._counters.published_events += 1

    async def snapshot(
        self,
    ) -> DetectionEventDispatcherSnapshot:
        async with self._metrics_lock:
            return DetectionEventDispatcherSnapshot(
                queue_capacity=(self._config.queue_capacity),
                queue_size=self._queue.qsize(),
                delivery_workers=(self._config.delivery_workers),
                active_deliveries=(self._counters.active_deliveries),
                accepting_events=(self._accepting_events),
                running=self.is_running,
                closed=self._closed,
                published_events=(self._counters.published_events),
                delivered_events=(self._counters.delivered_events),
                retried_events=(self._counters.retried_events),
                failed_events=(self._counters.failed_events),
                dead_lettered_events=(self._counters.dead_lettered_events),
                dead_letter_failures=(self._counters.dead_letter_failures),
                dropped_events=(self._counters.dropped_events),
                shutdown_timeouts=(self._counters.shutdown_timeouts),
            )

    async def shutdown(self) -> None:
        """Stop intake, drain accepted events and close."""

        async with self._lifecycle_lock:
            if self._closed:
                return

            self._accepting_events = False

            if not self._started:
                self._closed = True
                return

            worker_tasks = self._worker_tasks

        shutdown_timed_out = False

        try:
            await asyncio.wait_for(
                self._queue.join(),
                timeout=(self._config.shutdown_timeout_seconds),
            )
        except TimeoutError:
            shutdown_timed_out = True

            dropped_events = self._discard_pending_events()

            async with self._metrics_lock:
                self._counters.shutdown_timeouts += 1
                self._counters.dropped_events += dropped_events

            logger.warning(
                "detection_event_dispatcher_shutdown_timed_out",
                dropped_events=dropped_events,
            )
        finally:
            for task in worker_tasks:
                task.cancel()

            await asyncio.gather(
                *worker_tasks,
                return_exceptions=True,
            )

            async with self._lifecycle_lock:
                self._worker_tasks = ()
                self._started = False
                self._closed = True

        logger.info(
            "detection_event_dispatcher_stopped",
            shutdown_timed_out=shutdown_timed_out,
        )

    async def _handle_queue_full(
        self,
        event: StreamDetectionEvent,
    ) -> bool:
        if self._config.overflow_policy is EventQueueOverflowPolicy.DROP_NEWEST:
            async with self._metrics_lock:
                self._counters.dropped_events += 1

            logger.warning(
                "detection_event_queue_event_dropped",
                policy=(EventQueueOverflowPolicy.DROP_NEWEST.value),
                camera_id=event.camera_id,
                correlation_id=(str(event.correlation_id)),
            )

            return False

        try:
            dropped_event = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            self._queue.put_nowait(event)

            return True

        self._queue.task_done()
        self._queue.put_nowait(event)

        async with self._metrics_lock:
            self._counters.dropped_events += 1

        logger.warning(
            "detection_event_queue_event_dropped",
            policy=(EventQueueOverflowPolicy.DROP_OLDEST.value),
            camera_id=(dropped_event.camera_id),
            correlation_id=(str(dropped_event.correlation_id)),
        )

        return True

    async def _delivery_loop(self) -> None:
        while True:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                raise

            async with self._metrics_lock:
                self._counters.active_deliveries += 1

            try:
                await self._deliver_with_retry(event)
            finally:
                async with self._metrics_lock:
                    self._counters.active_deliveries -= 1

                self._queue.task_done()


    async def _deliver_with_retry(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        attempt_number = 1
        retry_delay_seconds = self._config.retry_initial_delay_seconds

        while True:
            try:
                await asyncio.wait_for(
                    self._destination.publish(event),
                    timeout=(self._config.delivery_timeout_seconds),
                )

            except asyncio.CancelledError:
                raise

            except PermanentStreamDetectionEventDeliveryError as exception:
                async with self._metrics_lock:
                    self._counters.failed_events += 1

                logger.error(
                    "detection_event_delivery_failed",
                    camera_id=event.camera_id,
                    correlation_id=str(event.correlation_id),
                    attempts=attempt_number,
                    error_type=(type(exception).__name__),
                    permanent=True,
                )

                await self._send_to_dead_letter(event)

                return

            except Exception as exception:
                if attempt_number < self._config.maximum_delivery_attempts:
                    async with self._metrics_lock:
                        self._counters.retried_events += 1

                    logger.warning(
                        "detection_event_delivery_retry_scheduled",
                        camera_id=event.camera_id,
                        correlation_id=str(event.correlation_id),
                        attempt_number=attempt_number,
                        error_type=(type(exception).__name__),
                        delay_seconds=(retry_delay_seconds),
                    )

                    await asyncio.sleep(retry_delay_seconds)

                    retry_delay_seconds = min(
                        self._config.retry_maximum_delay_seconds,
                        retry_delay_seconds * self._config.retry_multiplier,
                    )

                    attempt_number += 1

                    continue

                async with self._metrics_lock:
                    self._counters.failed_events += 1

                logger.error(
                    "detection_event_delivery_failed",
                    camera_id=event.camera_id,
                    correlation_id=str(event.correlation_id),
                    attempts=attempt_number,
                    error_type=(type(exception).__name__),
                    permanent=False,
                )

                await self._send_to_dead_letter(event)

                return

            async with self._metrics_lock:
                self._counters.delivered_events += 1

            return

    async def _send_to_dead_letter(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        try:
            await asyncio.wait_for(
                self._dead_letter_sink.publish(event),
                timeout=(self._config.delivery_timeout_seconds),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exception:
            async with self._metrics_lock:
                self._counters.dead_letter_failures += 1

            logger.error(
                "detection_event_dead_letter_failed",
                camera_id=event.camera_id,
                correlation_id=(str(event.correlation_id)),
                error_type=(type(exception).__name__),
            )

            return

        async with self._metrics_lock:
            self._counters.dead_lettered_events += 1

    def _discard_pending_events(self) -> int:
        dropped_events = 0

        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return dropped_events

            self._queue.task_done()
            dropped_events += 1
