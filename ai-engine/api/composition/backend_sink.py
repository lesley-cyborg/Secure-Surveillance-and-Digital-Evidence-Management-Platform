from __future__ import annotations

from config.settings import Settings
from integrations.backend.authentication import (
    BearerTokenBackendAuthenticator,
)
from integrations.backend.errors import (
    BackendConfigurationError,
)
from integrations.backend.incident_sink import (
    BackendIncidentEventSink,
    BackendIncidentSinkConfig,
)
from streaming.event_sink import (
    NullStreamDetectionEventSink,
    StreamDetectionEventSink,
)


def build_backend_incident_sink(
    *,
    settings: Settings,
) -> StreamDetectionEventSink:
    """Build the configured backend destination."""

    if not settings.backend_incident_sink_enabled:
        return NullStreamDetectionEventSink()

    endpoint_url = settings.backend_incident_endpoint_url
    service_token = settings.backend_service_token

    if endpoint_url is None or not endpoint_url.strip():
        raise BackendConfigurationError(
            "Backend incident endpoint is required when the sink is enabled"
        )

    if service_token is None:
        raise BackendConfigurationError(
            "Backend service token is required when the sink is enabled"
        )

    token_value = service_token.get_secret_value()

    if not token_value.strip():
        raise BackendConfigurationError("Backend service token cannot be empty")

    return BackendIncidentEventSink(
        config=BackendIncidentSinkConfig(
            endpoint_url=endpoint_url,
            connect_timeout_seconds=(settings.backend_incident_connect_timeout_seconds),
            read_timeout_seconds=(settings.backend_incident_read_timeout_seconds),
            write_timeout_seconds=(settings.backend_incident_write_timeout_seconds),
            pool_timeout_seconds=(settings.backend_incident_pool_timeout_seconds),
            maximum_connections=(settings.backend_incident_maximum_connections),
            maximum_keepalive_connections=(
                settings.backend_incident_maximum_keepalive_connections
            ),
            verify_tls=(settings.backend_incident_verify_tls),
            allow_insecure_http=(settings.backend_incident_allow_insecure_http),
        ),
        authenticator=(BearerTokenBackendAuthenticator(token=token_value)),
    )
