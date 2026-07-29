from __future__ import annotations

from uuid import UUID


class DetectionEngineError(Exception):
    """Base exception for detection-engine failures."""

    def __init__(
        self,
        message: str,
        *,
        correlation_id: UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id


class InvalidFrameError(DetectionEngineError):
    """Raised when submitted frame data cannot be decoded."""


class EmptyFrameError(InvalidFrameError):
    """Raised when decoded frame data contains no pixels."""


class UnsupportedMediaTypeError(InvalidFrameError):
    """Raised when the submitted media type is unsupported."""


class FrameTooLargeError(InvalidFrameError):
    """Raised when frame dimensions or byte size exceed configured limits."""


class InvalidBoundingBoxError(DetectionEngineError):
    """Raised when bounding-box coordinates are invalid."""


class InvalidConfidenceError(DetectionEngineError):
    """Raised when a confidence score falls outside the valid range."""


class DetectorNotFoundError(DetectionEngineError):
    """Raised when the requested detector is not registered."""


class DetectorAlreadyRegisteredError(DetectionEngineError):
    """Raised when the same model version is registered more than once."""


class DefaultDetectorNotConfiguredError(DetectionEngineError):
    """Raised when no default detector has been configured."""


class DetectorUnavailableError(DetectionEngineError):
    """Raised when a detector is registered but unavailable."""


class DeviceUnavailableError(DetectionEngineError):
    """Raised when the requested inference device is unavailable."""


class InferenceError(DetectionEngineError):
    """Raised when detector inference fails."""


class InferenceOverloadedError(DetectionEngineError):
    """Raised when inference capacity cannot be acquired."""

    def __init__(
        self,
        message: str = ("Inference capacity is currently exhausted"),
        *,
        correlation_id: UUID | None = None,
        retry_after_seconds: int = 1,
    ) -> None:
        super().__init__(
            message,
            correlation_id=correlation_id,
        )
        self.retry_after_seconds = retry_after_seconds


class ModelLoadError(DetectionEngineError):
    """Raised when a production model cannot be loaded."""


class ModelIntegrityError(ModelLoadError):
    """Raised when a model checksum is invalid."""


class ModelLifecycleError(DetectionEngineError):
    """Raised when model startup or shutdown fails."""
