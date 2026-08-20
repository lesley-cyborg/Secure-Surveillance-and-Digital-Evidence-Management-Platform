from __future__ import annotations

from app.core.exceptions import AppError


class AIIngestionError(AppError):
    """Base error for persistent AI-event ingestion."""

    __slots__ = ()


class CameraNotFoundError(AIIngestionError):
    __slots__ = ()

    def __init__(self, camera_code: str) -> None:
        super().__init__(
            status_code=404,
            code="AI_INGESTION_CAMERA_NOT_FOUND",
            message="The source camera is not registered.",
            details={"cameraCode": camera_code},
        )


class CameraInactiveError(AIIngestionError):
    __slots__ = ()

    def __init__(self, camera_code: str) -> None:
        super().__init__(
            status_code=422,
            code="AI_INGESTION_CAMERA_INACTIVE",
            message="The source camera is inactive.",
            details={"cameraCode": camera_code},
        )


class AIModelNotFoundError(AIIngestionError):
    __slots__ = ()

    def __init__(self, *, name: str, version: str) -> None:
        super().__init__(
            status_code=404,
            code="AI_INGESTION_MODEL_NOT_FOUND",
            message="The AI model is not registered.",
            details={"modelName": name, "modelVersion": version},
        )


class AIModelInactiveError(AIIngestionError):
    __slots__ = ()

    def __init__(self, *, name: str, version: str) -> None:
        super().__init__(
            status_code=422,
            code="AI_INGESTION_MODEL_INACTIVE",
            message="The AI model is inactive.",
            details={"modelName": name, "modelVersion": version},
        )


class AIModelAmbiguousError(AIIngestionError):
    __slots__ = ()

    def __init__(self, *, name: str, version: str) -> None:
        super().__init__(
            status_code=409,
            code="AI_INGESTION_MODEL_AMBIGUOUS",
            message=("More than one AI model matches the supplied identity."),
            details={"modelName": name, "modelVersion": version},
        )


class DetectionEventConflictError(AIIngestionError):
    __slots__ = ()

    def __init__(self, *, reason: str) -> None:
        super().__init__(
            status_code=409,
            code="AI_INGESTION_EVENT_CONFLICT",
            message=("The event identifier or idempotency key conflicts with an existing event."),
            details={"reason": reason},
        )


class DetectionEventPersistenceError(AIIngestionError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(
            status_code=500,
            code="AI_INGESTION_PERSISTENCE_FAILED",
            message="The detection event could not be persisted.",
            details={},
        )
