from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from app.core.config import Settings


class AIServiceSecurityError(Exception):
    """Base exception for AI service authentication."""


class AIServiceAuthenticationError(AIServiceSecurityError):
    """Raised when service credentials are invalid."""


class AIServiceUnavailableError(AIServiceSecurityError):
    """Raised when ingestion is disabled."""


class AIServiceConfigurationError(AIServiceSecurityError):
    """Raised when service authentication is misconfigured."""


@dataclass(
    frozen=True,
    slots=True,
)
class AIServicePrincipal:
    service_name: str


def _secret_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def authenticate_ai_service(
    *,
    authorization_header: str | None,
    settings: Settings,
) -> AIServicePrincipal:
    if not settings.ai_ingestion_enabled:
        raise AIServiceUnavailableError("AI ingestion is disabled")

    configured_token = settings.ai_ingestion_service_token

    if configured_token is None:
        raise AIServiceConfigurationError("AI ingestion service token is missing")

    if authorization_header is None:
        raise AIServiceAuthenticationError("Service credentials are required")

    scheme, separator, credentials = authorization_header.partition(" ")

    if not separator or scheme.casefold() != "bearer" or not credentials.strip():
        raise AIServiceAuthenticationError("Service credentials are invalid")

    expected_token = configured_token.get_secret_value()

    provided_digest = _secret_digest(credentials.strip())
    expected_digest = _secret_digest(expected_token)

    if not hmac.compare_digest(
        provided_digest,
        expected_digest,
    ):
        raise AIServiceAuthenticationError("Service credentials are invalid")

    return AIServicePrincipal(service_name="secure-surveillance-ai-engine")
