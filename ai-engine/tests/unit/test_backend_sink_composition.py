from __future__ import annotations

from pydantic import SecretStr

from api.composition.backend_sink import (
    build_backend_incident_sink,
)
from api.main import create_app
from config.settings import Settings, get_settings
from integrations.backend.errors import (
    BackendConfigurationError,
)
from integrations.backend.incident_sink import (
    BackendIncidentEventSink,
)
from streaming.event_sink import (
    NullStreamDetectionEventSink,
)


def create_settings(
    **updates: object,
) -> Settings:
    values: dict[str, object] = {
        "backend_incident_sink_enabled": False,
        "backend_incident_endpoint_url": None,
        "backend_service_token": None,
        "backend_incident_allow_insecure_http": (False),
        "backend_incident_verify_tls": True,
    }

    values.update(updates)

    return get_settings().model_copy(update=values)


def test_disabled_composition_returns_null_sink() -> None:
    settings = create_settings(backend_incident_sink_enabled=False)

    sink = build_backend_incident_sink(settings=settings)

    assert isinstance(
        sink,
        NullStreamDetectionEventSink,
    )


def test_application_exposes_null_sink_when_disabled() -> None:
    application = create_app(
        settings=create_settings(backend_incident_sink_enabled=False)
    )

    assert isinstance(
        application.state.stream_detection_sink,
        NullStreamDetectionEventSink,
    )


async def test_enabled_composition_returns_http_sink() -> None:
    settings = create_settings(
        backend_incident_sink_enabled=True,
        backend_incident_endpoint_url=(
            "https://backend.test/internal/v1/ai/detection-events"
        ),
        backend_service_token=SecretStr("service-secret-token"),
    )

    sink = build_backend_incident_sink(settings=settings)

    assert isinstance(
        sink,
        BackendIncidentEventSink,
    )

    assert sink.config.endpoint_url == (
        "https://backend.test/internal/v1/ai/detection-events"
    )
    assert sink.config.verify_tls is True
    assert sink.config.allow_insecure_http is False

    await sink.shutdown()

    assert sink.closed is True


def test_enabled_sink_requires_endpoint() -> None:
    settings = create_settings(
        backend_incident_sink_enabled=True,
        backend_incident_endpoint_url=None,
        backend_service_token=SecretStr("service-secret-token"),
    )

    try:
        build_backend_incident_sink(settings=settings)
    except BackendConfigurationError as exception:
        assert "endpoint" in str(exception).casefold()
    else:
        raise AssertionError("Expected backend configuration error")


def test_enabled_sink_requires_service_token() -> None:
    settings = create_settings(
        backend_incident_sink_enabled=True,
        backend_incident_endpoint_url=("https://backend.test/events"),
        backend_service_token=None,
    )

    try:
        build_backend_incident_sink(settings=settings)
    except BackendConfigurationError as exception:
        assert "token" in str(exception).casefold()
    else:
        raise AssertionError("Expected backend configuration error")


def test_settings_repr_redacts_service_token() -> None:
    secret_value = "do-not-expose-this-token"

    settings = create_settings(
        backend_incident_sink_enabled=True,
        backend_incident_endpoint_url=("https://backend.test/events"),
        backend_service_token=SecretStr(secret_value),
    )

    representation = repr(settings)

    assert settings.backend_service_token is not None
    assert settings.backend_service_token.get_secret_value() == secret_value

    assert secret_value not in representation
    assert "backend_service_token" not in representation
