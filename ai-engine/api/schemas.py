from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from detection.schemas import (
    ApiModel,
    ModelStatus,
)


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class HealthResponse(ApiModel):
    service: str
    version: str
    environment: str
    status: HealthStatus
    registered_models: int
    ready_models: int


class ModelListResponse(ApiModel):
    items: tuple[ModelStatus, ...]
    total: int


class ErrorResponse(ApiModel):
    error_code: str
    message: str
    correlation_id: UUID | None = None


class LivenessResponse(ApiModel):
    service: str
    version: str
    status: str = "alive"


class ReadinessResponse(ApiModel):
    service: str
    version: str
    ready: bool
    lifecycle_state: str
    lifecycle_error: str | None
    registered_models: int
    ready_models: int
    maximum_concurrent_inferences: int
    active_inferences: int
    queued_inferences: int
