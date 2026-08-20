from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class CoreResponseModel(BaseModel):
    """Base configuration for core API response schemas.

    Extra fields are temporarily allowed because the original schemas
    could not be recovered. This preserves compatibility with the
    existing health and model endpoints while the exact contract is
    verified through tests.
    """

    model_config = ConfigDict(
        extra="allow",
        validate_default=True,
    )


class HealthStatus(StrEnum):
    """Possible service-health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

    # Compatibility states used by some health implementations.
    OK = "ok"
    ALIVE = "alive"
    READY = "ready"
    NOT_READY = "not_ready"


class ErrorResponse(CoreResponseModel):
    """Standard safe API error response."""

    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    detail: str | dict[str, object] | list[dict[str, object]] | None = None

    correlation_id: str | None = None

    # Supports existing handlers that return:
    # {"error": {"code": "...", "message": "..."}}
    error: dict[str, object] | None = None


class LivenessResponse(CoreResponseModel):
    """Process-level liveness response.

    Liveness only confirms that the API process is running. It does not
    guarantee that the model is loaded or ready to perform inference.
    """

    service: str = "Secure Surveillance AI Engine"
    version: str | None = None
    status: HealthStatus = HealthStatus.ALIVE


class ReadinessResponse(CoreResponseModel):
    """Dependency and inference-readiness response."""

    status: HealthStatus = HealthStatus.HEALTHY
    ready: bool = True

    service: str = "Secure Surveillance AI Engine"
    version: str | None = None

    lifecycle_state: str | None = None
    model_loaded: bool = False
    active_model: str | None = None

    registry_generation: int = Field(
        default=0,
        ge=0,
    )

    checks: dict[str, object] = Field(
        default_factory=dict,
    )

    timestamp: datetime = Field(
        default_factory=utc_now,
    )


class HealthResponse(CoreResponseModel):
    """Combined health information for the AI engine."""

    status: HealthStatus = HealthStatus.HEALTHY

    service: str = "Secure Surveillance AI Engine"
    version: str | None = None
    environment: str | None = None

    alive: bool = True
    ready: bool = True

    lifecycle_state: str | None = None
    model_loaded: bool = False
    active_model: str | None = None

    uptime_seconds: float | None = Field(
        default=None,
        ge=0,
    )

    registry_generation: int = Field(
        default=0,
        ge=0,
    )

    checks: dict[str, object] = Field(
        default_factory=dict,
    )

    timestamp: datetime = Field(
        default_factory=utc_now,
    )


class ModelListResponse(CoreResponseModel):
    """Response containing registered model information."""

    models: list[object] = Field(
        default_factory=list,
    )

    count: int | None = Field(
        default=None,
        ge=0,
    )

    active_model: str | None = None
    lifecycle_state: str | None = None

    registry_generation: int = Field(
        default=0,
        ge=0,
    )

    timestamp: datetime = Field(
        default_factory=utc_now,
    )

    @model_validator(mode="after")
    def populate_count(self) -> Self:
        """Derive count when it was not provided explicitly."""

        if self.count is None:
            self.count = len(self.models)

        return self
