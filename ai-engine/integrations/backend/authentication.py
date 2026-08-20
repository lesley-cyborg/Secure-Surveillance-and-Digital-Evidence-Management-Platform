from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

from integrations.backend.errors import (
    BackendAuthenticationError,
)


def _validate_header_value(
    value: str,
    *,
    field_name: str,
) -> str:
    normalised = value.strip()

    if not normalised:
        raise BackendAuthenticationError(f"{field_name} cannot be empty")

    if "\r" in normalised or "\n" in normalised:
        raise BackendAuthenticationError(f"{field_name} contains invalid characters")

    return normalised


@runtime_checkable
class BackendRequestAuthenticator(Protocol):
    """Adds service authentication to backend requests."""

    def build_headers(
        self,
        *,
        body: bytes,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> Mapping[str, str]: ...


@dataclass(
    frozen=True,
    slots=True,
)
class BearerTokenBackendAuthenticator:
    """Static service bearer-token authentication."""

    token: str = field(repr=False)
    scheme: str = "Bearer"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "token",
            _validate_header_value(
                self.token,
                field_name="token",
            ),
        )

        object.__setattr__(
            self,
            "scheme",
            _validate_header_value(
                self.scheme,
                field_name="scheme",
            ),
        )

    def build_headers(
        self,
        *,
        body: bytes,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> Mapping[str, str]:
        del body

        validated_key = _validate_header_value(
            idempotency_key,
            field_name="idempotency_key",
        )

        return {
            "Accept": "application/json",
            "Authorization": (f"{self.scheme} {self.token}"),
            "Content-Type": "application/json",
            "Idempotency-Key": validated_key,
            "X-Correlation-ID": str(correlation_id),
        }
