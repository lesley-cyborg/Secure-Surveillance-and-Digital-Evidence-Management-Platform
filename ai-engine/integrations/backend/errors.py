from __future__ import annotations

from streaming.event_sink import (
    PermanentStreamDetectionEventDeliveryError,
    StreamDetectionEventDeliveryError,
)


class BackendIntegrationError(Exception):
    """Base exception for backend integrations."""


class BackendConfigurationError(BackendIntegrationError):
    """Raised for invalid backend configuration."""


class BackendAuthenticationError(BackendIntegrationError):
    """Raised when authentication cannot be built."""


class BackendRequestError(
    BackendIntegrationError,
    StreamDetectionEventDeliveryError,
):
    """Base exception for backend requests."""


class RetryableBackendRequestError(BackendRequestError):
    """A transient backend failure."""


class PermanentBackendRequestError(
    BackendRequestError,
    PermanentStreamDetectionEventDeliveryError,
):
    """A request failure that must not be retried."""
