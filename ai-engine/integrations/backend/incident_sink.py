from __future__ import annotations

import math
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from integrations.backend.authentication import (
    BackendRequestAuthenticator,
)
from integrations.backend.errors import (
    BackendConfigurationError,
    PermanentBackendRequestError,
    RetryableBackendRequestError,
)
from streaming.detection_events import StreamDetectionEvent
from streaming.event_serialization import (
    create_event_idempotency_key,
    serialize_stream_detection_event,
)

_RETRYABLE_STATUS_CODES = frozenset(
    {
        408,
        425,
        429,
    }
)


@dataclass(
    frozen=True,
    slots=True,
)
class BackendIncidentSinkConfig:
    """Configuration for backend event ingestion."""

    endpoint_url: str

    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    write_timeout_seconds: float = 10.0
    pool_timeout_seconds: float = 5.0

    maximum_connections: int = 20
    maximum_keepalive_connections: int = 10

    verify_tls: bool = True
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        endpoint_url = self.endpoint_url.strip()

        if not endpoint_url:
            raise BackendConfigurationError("Backend incident endpoint cannot be empty")

        parsed_url = urlsplit(endpoint_url)

        if parsed_url.scheme not in {
            "http",
            "https",
        }:
            raise BackendConfigurationError(
                "Backend incident endpoint must use HTTP or HTTPS"
            )

        if not parsed_url.netloc:
            raise BackendConfigurationError(
                "Backend incident endpoint must include a hostname"
            )

        if parsed_url.username is not None or parsed_url.password is not None:
            raise BackendConfigurationError(
                "Backend incident endpoint must not contain credentials"
            )

        if parsed_url.query:
            raise BackendConfigurationError(
                "Backend incident endpoint must not contain query parameters"
            )

        if parsed_url.fragment:
            raise BackendConfigurationError(
                "Backend incident endpoint must not contain a fragment"
            )

        if parsed_url.scheme == "http" and not self.allow_insecure_http:
            raise BackendConfigurationError(
                "Insecure HTTP backend endpoints are disabled"
            )

        object.__setattr__(
            self,
            "endpoint_url",
            endpoint_url,
        )

        timeout_values = {
            "connect_timeout_seconds": (self.connect_timeout_seconds),
            "read_timeout_seconds": (self.read_timeout_seconds),
            "write_timeout_seconds": (self.write_timeout_seconds),
            "pool_timeout_seconds": (self.pool_timeout_seconds),
        }

        for field_name, value in timeout_values.items():
            if not math.isfinite(value):
                raise BackendConfigurationError(f"{field_name} must be finite")

            if value <= 0:
                raise BackendConfigurationError(f"{field_name} must be positive")

        if self.maximum_connections < 1:
            raise BackendConfigurationError("maximum_connections must be at least 1")

        if self.maximum_keepalive_connections < 0:
            raise BackendConfigurationError(
                "maximum_keepalive_connections cannot be negative"
            )

        if self.maximum_keepalive_connections > self.maximum_connections:
            raise BackendConfigurationError(
                "maximum_keepalive_connections cannot exceed maximum_connections"
            )


class BackendIncidentEventSink:
    """Authenticated HTTP destination for detection events."""

    def __init__(
        self,
        *,
        config: BackendIncidentSinkConfig,
        authenticator: BackendRequestAuthenticator,
        client: httpx.AsyncClient | None = None,
        close_client_on_shutdown: bool = False,
    ) -> None:
        self._config = config
        self._authenticator = authenticator

        self._close_client_on_shutdown = client is None or close_client_on_shutdown
        self._closed = False

        self._client = (
            client
            if client is not None
            else httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=(config.connect_timeout_seconds),
                    read=config.read_timeout_seconds,
                    write=config.write_timeout_seconds,
                    pool=config.pool_timeout_seconds,
                ),
                limits=httpx.Limits(
                    max_connections=(config.maximum_connections),
                    max_keepalive_connections=(config.maximum_keepalive_connections),
                ),
                verify=config.verify_tls,
                follow_redirects=False,
            )
        )

    @property
    def config(self) -> BackendIncidentSinkConfig:
        return self._config

    @property
    def closed(self) -> bool:
        return self._closed

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        if self._closed:
            raise PermanentBackendRequestError("Backend incident sink is closed")

        body = serialize_stream_detection_event(event)
        idempotency_key = create_event_idempotency_key(event)

        headers = dict(
            self._authenticator.build_headers(
                body=body,
                idempotency_key=idempotency_key,
                correlation_id=(event.correlation_id),
            )
        )

        try:
            response = await self._client.post(
                self._config.endpoint_url,
                content=body,
                headers=headers,
            )
        except httpx.TimeoutException as exception:
            raise RetryableBackendRequestError(
                "Backend incident request timed out"
            ) from exception
        except httpx.RequestError as exception:
            raise RetryableBackendRequestError(
                "Backend incident request transport failed"
            ) from exception

        status_code = response.status_code

        if 200 <= status_code < 300:
            return

        if status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code < 600:
            raise RetryableBackendRequestError(
                f"Backend incident endpoint returned retryable status {status_code}"
            )

        raise PermanentBackendRequestError(
            f"Backend incident endpoint returned permanent status {status_code}"
        )

    async def shutdown(self) -> None:
        if self._closed:
            return

        self._closed = True

        if self._close_client_on_shutdown:
            await self._client.aclose()
