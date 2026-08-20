from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import httpx

from api.main import create_app
from config.settings import Settings, get_settings
from integrations.backend.authentication import (
    BearerTokenBackendAuthenticator,
)
from integrations.backend.incident_sink import (
    BackendIncidentEventSink,
    BackendIncidentSinkConfig,
)
from models.lifecycle import ModelLifecycleManager
from streaming.detection_dispatcher import (
    DetectionEventDispatcher,
    DetectionEventDispatcherSnapshot,
)
from streaming.detection_events import (
    StreamDetectionEvent,
    StreamModelIdentity,
)


@dataclass(slots=True)
class StubLifecycleState:
    value: str


class StubModelLifecycle:
    def __init__(self) -> None:
        self.state = StubLifecycleState(value="created")
        self.last_error: str | None = None

    async def startup(self) -> None:
        self.state = StubLifecycleState(value="ready")

    async def shutdown(self) -> None:
        self.state = StubLifecycleState(value="stopped")


class RecordingDeadLetterSink:
    def __init__(self) -> None:
        self.events: list[StreamDetectionEvent] = []
        self.delivered = asyncio.Event()

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        self.events.append(event)
        self.delivered.set()


class SequenceTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        status_codes: list[int],
    ) -> None:
        if not status_codes:
            raise ValueError("At least one status code is required")

        self._status_codes = status_codes
        self.requests: list[httpx.Request] = []

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.requests.append(request)

        request_index = len(self.requests) - 1

        status_code = self._status_codes[
            min(
                request_index,
                len(self._status_codes) - 1,
            )
        ]

        return httpx.Response(
            status_code=status_code,
            request=request,
        )


class BlockingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.requests: list[httpx.Request] = []

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.requests.append(request)
        self.entered.set()

        await self.release.wait()

        return httpx.Response(
            status_code=202,
            request=request,
        )


def create_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "backend_incident_sink_enabled": (False),
            "stream_event_queue_capacity": 10,
            "stream_event_delivery_workers": 1,
            "stream_event_delivery_timeout_seconds": (1.0),
            "stream_event_retry_initial_delay_seconds": (0.001),
            "stream_event_retry_multiplier": 2.0,
            "stream_event_retry_maximum_delay_seconds": (0.005),
            "stream_event_retry_maximum_attempts": 3,
            "stream_event_shutdown_timeout_seconds": (1.0),
            "stream_event_overflow_policy": ("drop_oldest"),
        }
    )


def create_event() -> StreamDetectionEvent:
    timestamp = datetime.now(UTC)

    return StreamDetectionEvent(
        correlation_id=uuid4(),
        camera_id="camera-integration-001",
        frame_sequence_number=73,
        captured_at=timestamp,
        received_at=timestamp,
        processed_at=timestamp,
        model=StreamModelIdentity(
            name="surveillance-yolo",
            version="yolo26n-coco",
            device="cpu",
        ),
        detections=(),
        inference_duration_ms=5.25,
    )


def create_sink(
    *,
    client: httpx.AsyncClient,
) -> BackendIncidentEventSink:
    return BackendIncidentEventSink(
        config=BackendIncidentSinkConfig(
            endpoint_url=("https://backend.test/internal/v1/ai/detection-events"),
            connect_timeout_seconds=1.0,
            read_timeout_seconds=1.0,
            write_timeout_seconds=1.0,
            pool_timeout_seconds=1.0,
            maximum_connections=5,
            maximum_keepalive_connections=2,
        ),
        authenticator=(
            BearerTokenBackendAuthenticator(token="integration-service-token")
        ),
        client=client,
        close_client_on_shutdown=True,
    )


def create_lifecycle() -> ModelLifecycleManager:
    return cast(
        ModelLifecycleManager,
        StubModelLifecycle(),
    )


async def wait_for_snapshot(
    dispatcher: DetectionEventDispatcher,
    predicate: Callable[
        [DetectionEventDispatcherSnapshot],
        bool,
    ],
    *,
    timeout_seconds: float = 2.0,
) -> DetectionEventDispatcherSnapshot:
    async with asyncio.timeout(timeout_seconds):
        while True:
            snapshot = await dispatcher.snapshot()

            if predicate(snapshot):
                return snapshot

            await asyncio.sleep(0.001)


def dispatcher_tasks() -> list[asyncio.Task[object]]:
    current_task = asyncio.current_task()

    return [
        cast(asyncio.Task[object], task)
        for task in asyncio.all_tasks()
        if task is not current_task
        and not task.done()
        and task.get_name().startswith("stream-event-dispatcher:")
    ]


async def test_application_delivers_authenticated_event() -> None:
    transport = SequenceTransport([202])

    client = httpx.AsyncClient(transport=transport)
    sink = create_sink(client=client)

    application = create_app(
        settings=create_settings(),
        lifecycle=create_lifecycle(),
        stream_detection_sink=sink,
    )

    dispatcher = cast(
        DetectionEventDispatcher,
        application.state.stream_detection_dispatcher,
    )

    event = create_event()

    async with application.router.lifespan_context(application):
        assert dispatcher.is_running is True

        await dispatcher.publish(event)

        snapshot = await wait_for_snapshot(
            dispatcher,
            lambda state: state.delivered_events == 1,
        )

        assert snapshot.failed_events == 0

    assert dispatcher.closed is True
    assert sink.closed is True
    assert client.is_closed is True
    assert dispatcher_tasks() == []

    assert len(transport.requests) == 1

    request = transport.requests[0]

    assert request.method == "POST"
    assert request.headers["Authorization"] == ("Bearer integration-service-token")
    assert request.headers["X-Correlation-ID"] == str(event.correlation_id)

    idempotency_key = request.headers["Idempotency-Key"]

    assert len(idempotency_key) == 64

    payload = json.loads(request.content.decode("utf-8"))

    assert payload["event_id"] == str(event.correlation_id)
    assert payload["camera_id"] == ("camera-integration-001")
    assert payload["frame"]["sequence_number"] == 73


async def test_retryable_response_is_retried() -> None:
    transport = SequenceTransport(
        [
            503,
            202,
        ]
    )

    client = httpx.AsyncClient(transport=transport)
    sink = create_sink(client=client)

    application = create_app(
        settings=create_settings(),
        lifecycle=create_lifecycle(),
        stream_detection_sink=sink,
    )

    dispatcher = cast(
        DetectionEventDispatcher,
        application.state.stream_detection_dispatcher,
    )

    async with application.router.lifespan_context(application):
        await dispatcher.publish(create_event())

        snapshot = await wait_for_snapshot(
            dispatcher,
            lambda state: state.delivered_events == 1,
        )

        assert snapshot.retried_events == 1
        assert snapshot.failed_events == 0

    assert len(transport.requests) == 2
    assert client.is_closed is True


async def test_permanent_response_is_dead_lettered_once() -> None:
    transport = SequenceTransport([422])

    client = httpx.AsyncClient(transport=transport)
    sink = create_sink(client=client)

    dead_letter_sink = RecordingDeadLetterSink()

    application = create_app(
        settings=create_settings(),
        lifecycle=create_lifecycle(),
        stream_detection_sink=sink,
        stream_dead_letter_sink=dead_letter_sink,
    )

    dispatcher = cast(
        DetectionEventDispatcher,
        application.state.stream_detection_dispatcher,
    )

    event = create_event()

    async with application.router.lifespan_context(application):
        await dispatcher.publish(event)

        await asyncio.wait_for(
            dead_letter_sink.delivered.wait(),
            timeout=2.0,
        )

        snapshot = await dispatcher.snapshot()

        assert snapshot.retried_events == 0
        assert snapshot.failed_events == 1
        assert snapshot.dead_lettered_events == 1

    assert len(transport.requests) == 1
    assert dead_letter_sink.events == [event]
    assert client.is_closed is True


async def test_slow_backend_does_not_block_publish() -> None:
    transport = BlockingTransport()

    client = httpx.AsyncClient(transport=transport)
    sink = create_sink(client=client)

    application = create_app(
        settings=create_settings(),
        lifecycle=create_lifecycle(),
        stream_detection_sink=sink,
    )

    dispatcher = cast(
        DetectionEventDispatcher,
        application.state.stream_detection_dispatcher,
    )

    async with application.router.lifespan_context(application):
        await asyncio.wait_for(
            dispatcher.publish(create_event()),
            timeout=0.1,
        )

        await asyncio.wait_for(
            transport.entered.wait(),
            timeout=1.0,
        )

        snapshot = await dispatcher.snapshot()

        assert snapshot.active_deliveries == 1
        assert snapshot.delivered_events == 0

        transport.release.set()

        snapshot = await wait_for_snapshot(
            dispatcher,
            lambda state: state.delivered_events == 1,
        )

        assert snapshot.failed_events == 0

    assert client.is_closed is True
    assert dispatcher_tasks() == []
