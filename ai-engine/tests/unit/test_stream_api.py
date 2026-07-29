from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from httpx import (
    ASGITransport,
    AsyncClient,
)

from api.error_handlers import (
    install_safe_validation_error_handler,
)
from api.routes.streams import router
from streaming.domain import (
    CameraStreamConfig,
    StreamState,
)
from streaming.manager import StreamManager


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


class FakeWorker:
    def __init__(
        self,
        config: CameraStreamConfig,
    ) -> None:
        self._config = config
        self._running = False
        self._disposed = False
        self._state = StreamState.STOPPED

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
        self._running = True
        self._state = StreamState.CONNECTED

    async def stop(self) -> None:
        self._running = False
        self._state = StreamState.STOPPED

    async def dispose(self) -> None:
        self._running = False
        self._disposed = True
        self._state = StreamState.STOPPED

    async def snapshot(
        self,
    ) -> FakeWorkerSnapshot:
        return FakeWorkerSnapshot(
            runtime=FakeRuntimeSnapshot(
                state=self._state
            ),
            running=self._running,
            disposed=self._disposed,
        )


class FakeWorkerFactory:
    def __init__(self) -> None:
        self.workers: dict[
            str,
            FakeWorker,
        ] = {}

    def create(
        self,
        config: CameraStreamConfig,
    ) -> FakeWorker:
        worker = FakeWorker(config)

        self.workers[
            config.camera_id
        ] = worker

        return worker


def create_test_application(
    manager: StreamManager,
    factory: FakeWorkerFactory,
) -> FastAPI:
    app = FastAPI()

    install_safe_validation_error_handler(
        app
    )

    app.state.stream_manager = manager
    app.state.stream_worker_factory = factory

    app.include_router(
        router,
        prefix="/api/v1",
    )

    return app


def registration_payload(
    *,
    camera_id: str = "camera-001",
) -> dict[str, object]:
    return {
        "camera_id": camera_id,
        "name": "Main entrance",
        "source_uri": (
            "rtsp://operator:secret@"
            "10.0.0.5:554/stream"
        ),
        "target_fps": 5.0,
        "confidence_threshold": 0.35,
        "queue_capacity": 1,
        "maximum_consecutive_read_failures": 3,
    }


async def test_register_response_redacts_credentials() -> None:
    manager = StreamManager()
    factory = FakeWorkerFactory()
    app = create_test_application(
        manager,
        factory,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/streams",
            json=registration_payload(),
        )

    assert response.status_code == 201
    assert response.json()["camera_id"] == (
        "camera-001"
    )

    assert "source_uri" not in response.text
    assert "operator" not in response.text
    assert "secret" not in response.text


async def test_duplicate_registration_returns_conflict() -> None:
    manager = StreamManager()
    factory = FakeWorkerFactory()
    app = create_test_application(
        manager,
        factory,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/v1/streams",
            json=registration_payload(),
        )
        second = await client.post(
            "/api/v1/streams",
            json=registration_payload(),
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "secret" not in second.text


async def test_start_stop_and_get_stream() -> None:
    manager = StreamManager()
    factory = FakeWorkerFactory()
    app = create_test_application(
        manager,
        factory,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.post(
            "/api/v1/streams",
            json=registration_payload(),
        )

        started = await client.post(
            "/api/v1/streams/camera-001/start"
        )

        loaded = await client.get(
            "/api/v1/streams/camera-001"
        )

        stopped = await client.post(
            "/api/v1/streams/camera-001/stop"
        )

    assert started.status_code == 200
    assert started.json()["running"] is True

    assert loaded.status_code == 200
    assert loaded.json()["state"] == "connected"

    assert stopped.status_code == 200
    assert stopped.json()["running"] is False


async def test_list_and_batch_operations() -> None:
    manager = StreamManager()
    factory = FakeWorkerFactory()
    app = create_test_application(
        manager,
        factory,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.post(
            "/api/v1/streams",
            json=registration_payload(
                camera_id="camera-001"
            ),
        )
        await client.post(
            "/api/v1/streams",
            json=registration_payload(
                camera_id="camera-002"
            ),
        )

        started = await client.post(
            "/api/v1/streams/actions/start-all"
        )

        stopped = await client.post(
            "/api/v1/streams/actions/stop-all"
        )

    assert started.status_code == 200
    assert started.json()["total_workers"] == 2
    assert started.json()["running_workers"] == 2

    assert stopped.status_code == 200
    assert stopped.json()["running_workers"] == 0


async def test_unregister_disposes_stream() -> None:
    manager = StreamManager()
    factory = FakeWorkerFactory()
    app = create_test_application(
        manager,
        factory,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.post(
            "/api/v1/streams",
            json=registration_payload(),
        )

        response = await client.delete(
            "/api/v1/streams/camera-001"
        )

        missing = await client.get(
            "/api/v1/streams/camera-001"
        )

    assert response.status_code == 204
    assert missing.status_code == 404

    assert (
        factory.workers[
            "camera-001"
        ].disposed
        is True
    )


async def test_validation_error_does_not_echo_uri() -> None:
    manager = StreamManager()
    factory = FakeWorkerFactory()
    app = create_test_application(
        manager,
        factory,
    )

    payload = registration_payload()
    payload["target_fps"] = 0

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/streams",
            json=payload,
        )

    assert response.status_code == 422

    assert "operator" not in response.text
    assert "secret" not in response.text
    assert "10.0.0.5" not in response.text