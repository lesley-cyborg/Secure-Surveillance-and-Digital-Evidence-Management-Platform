from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from integrations.backend.authentication import (
    BackendRequestAuthenticator,
    BearerTokenBackendAuthenticator,
)
from integrations.backend.errors import (
    BackendAuthenticationError,
    BackendConfigurationError,
    PermanentBackendRequestError,
    RetryableBackendRequestError,
)
from integrations.backend.incident_sink import (
    BackendIncidentEventSink,
    BackendIncidentSinkConfig,
)
from streaming.detection_events import (
    StreamDetectionEvent,
    StreamModelIdentity,
)


def create_event() -> StreamDetectionEvent:
    timestamp = datetime.now(UTC)

    return StreamDetectionEvent(
        correlation_id=uuid4(),
        camera_id="camera-001",
        frame_sequence_number=42,
        captured_at=timestamp,
        received_at=timestamp,
        processed_at=timestamp,
        model=StreamModelIdentity(
            name="surveillance-yolo",
            version="yolo26n-coco",
            device="cpu",
        ),
        detections=(),
        inference_duration_ms=8.5,
    )


def create_config() -> BackendIncidentSinkConfig:
    return BackendIncidentSinkConfig(
        endpoint_url=("https://backend.test/internal/v1/ai/detection-events"),
        connect_timeout_seconds=0.1,
        read_timeout_seconds=0.1,
        write_timeout_seconds=0.1,
        pool_timeout_seconds=0.1,
        maximum_connections=5,
        maximum_keepalive_connections=2,
    )


def create_authenticator() -> BearerTokenBackendAuthenticator:
    return BearerTokenBackendAuthenticator(token="service-secret-token")


def test_bearer_authenticator_builds_headers() -> None:
    correlation_id = uuid4()
    authenticator = create_authenticator()

    assert isinstance(
        authenticator,
        BackendRequestAuthenticator,
    )

    headers = authenticator.build_headers(
        body=b'{"event":"example"}',
        idempotency_key="abc123",
        correlation_id=correlation_id,
    )

    assert headers["Authorization"] == ("Bearer service-secret-token")
    assert headers["Content-Type"] == ("application/json")
    assert headers["Accept"] == ("application/json")
    assert headers["Idempotency-Key"] == ("abc123")
    assert headers["X-Correlation-ID"] == (str(correlation_id))


def test_authenticator_repr_hides_token() -> None:
    authenticator = BearerTokenBackendAuthenticator(token="super-secret-token")

    representation = repr(authenticator)

    assert "super-secret-token" not in representation


@pytest.mark.parametrize(
    "token",
    [
        "",
        "   ",
        "secret\rheader",
        "secret\nheader",
    ],
)
def test_authenticator_rejects_invalid_token(
    token: str,
) -> None:
    with pytest.raises(BackendAuthenticationError):
        BearerTokenBackendAuthenticator(token=token)


def test_authenticator_rejects_invalid_key() -> None:
    authenticator = create_authenticator()

    with pytest.raises(BackendAuthenticationError):
        authenticator.build_headers(
            body=b"{}",
            idempotency_key="bad\nkey",
            correlation_id=uuid4(),
        )


async def test_sink_posts_authenticated_event() -> None:
    captured_request: httpx.Request | None = None

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal captured_request

        captured_request = request

        return httpx.Response(
            status_code=202,
            request=request,
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        sink = BackendIncidentEventSink(
            config=create_config(),
            authenticator=create_authenticator(),
            client=client,
        )

        event = create_event()

        await sink.publish(event)

    assert captured_request is not None

    assert captured_request.headers["Authorization"] == "Bearer service-secret-token"

    assert captured_request.headers["X-Correlation-ID"] == str(event.correlation_id)

    idempotency_key = captured_request.headers["Idempotency-Key"]

    assert len(idempotency_key) == 64

    payload = json.loads(captured_request.content.decode("utf-8"))

    assert payload["event_id"] == str(event.correlation_id)
    assert payload["camera_id"] == "camera-001"
    assert payload["frame"]["sequence_number"] == 42


@pytest.mark.parametrize(
    "status_code",
    [
        408,
        425,
        429,
        500,
        502,
        503,
        504,
    ],
)
async def test_retryable_status_is_classified(
    status_code: int,
) -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            request=request,
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        sink = BackendIncidentEventSink(
            config=create_config(),
            authenticator=create_authenticator(),
            client=client,
        )

        with pytest.raises(RetryableBackendRequestError):
            await sink.publish(create_event())


@pytest.mark.parametrize(
    "status_code",
    [
        400,
        401,
        403,
        404,
        409,
        413,
        422,
    ],
)
async def test_permanent_status_is_classified(
    status_code: int,
) -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            request=request,
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        sink = BackendIncidentEventSink(
            config=create_config(),
            authenticator=create_authenticator(),
            client=client,
        )

        with pytest.raises(PermanentBackendRequestError):
            await sink.publish(create_event())


async def test_transport_failure_is_retryable() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        sink = BackendIncidentEventSink(
            config=create_config(),
            authenticator=create_authenticator(),
            client=client,
        )

        with pytest.raises(RetryableBackendRequestError):
            await sink.publish(create_event())


async def test_timeout_is_retryable() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ReadTimeout(
            "read timed out",
            request=request,
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as client:
        sink = BackendIncidentEventSink(
            config=create_config(),
            authenticator=create_authenticator(),
            client=client,
        )

        with pytest.raises(RetryableBackendRequestError):
            await sink.publish(create_event())


@pytest.mark.parametrize(
    "endpoint_url",
    [
        "",
        "backend.test/events",
        "ftp://backend.test/events",
        "https://user:password@backend.test/events",
        "https://backend.test/events?token=secret",
        "https://backend.test/events#fragment",
        "http://backend.test/events",
    ],
)
def test_config_rejects_unsafe_endpoint(
    endpoint_url: str,
) -> None:
    with pytest.raises(BackendConfigurationError):
        BackendIncidentSinkConfig(endpoint_url=endpoint_url)


def test_config_can_explicitly_allow_http() -> None:
    config = BackendIncidentSinkConfig(
        endpoint_url=("http://127.0.0.1:3000/internal/v1/ai/detection-events"),
        allow_insecure_http=True,
        verify_tls=False,
    )

    assert config.endpoint_url.startswith("http://")


async def test_shutdown_is_idempotent() -> None:
    sink = BackendIncidentEventSink(
        config=create_config(),
        authenticator=create_authenticator(),
    )

    await sink.shutdown()
    await sink.shutdown()

    assert sink.closed is True

    with pytest.raises(PermanentBackendRequestError):
        await sink.publish(create_event())
