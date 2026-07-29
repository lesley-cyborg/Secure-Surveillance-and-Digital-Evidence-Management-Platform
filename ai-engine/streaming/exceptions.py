from __future__ import annotations


class StreamingError(RuntimeError):
    """Base exception for camera streaming failures."""


class StreamSourceError(StreamingError):
    """Base exception for stream-source failures."""


class StreamDisabledError(StreamSourceError):
    """Raised when opening a disabled camera source."""


class StreamOpenError(StreamSourceError):
    """Raised when a camera source cannot be opened."""


class StreamNotOpenError(StreamSourceError):
    """Raised when reading from a source that is not open."""


class StreamReadError(StreamSourceError):
    """Raised when a source cannot return a valid frame."""


class FrameQueueError(StreamingError):
    """Base exception for frame queue failures."""


class FrameQueueClosedError(FrameQueueError):
    """Raised when operating on a closed frame queue."""


class FrameQueueTimeoutError(FrameQueueError):
    """Raised when no frame arrives before the timeout."""


class ReconnectionError(StreamingError):
    """Base exception for reconnection-policy failures."""


class ReconnectAttemptsExhaustedError(ReconnectionError):
    """Raised when the configured retry limit has been reached."""


class StreamWorkerError(StreamingError):
    """Base exception for continuous-stream worker failures."""


class StreamWorkerDisposedError(StreamWorkerError):
    """Raised when attempting to restart a disposed worker."""


class StreamManagerError(StreamingError):
    """Base exception for stream-manager failures."""


class StreamManagerClosedError(StreamManagerError):
    """Raised when an operation is attempted after manager shutdown."""


class StreamWorkerAlreadyRegisteredError(StreamManagerError):
    """Raised when a camera ID already has a registered worker."""


class StreamWorkerNotRegisteredError(StreamManagerError):
    """Raised when a camera ID has no registered worker."""


class StreamManagerOperationError(StreamManagerError):
    """Raised when one or more workers fail during a batch operation."""

    def __init__(
        self,
        *,
        operation: str,
        failures: dict[str, BaseException],
    ) -> None:
        self.operation = operation
        self.failures = dict(failures)

        failed_camera_ids = ", ".join(sorted(self.failures))

        super().__init__(
            f"Stream-manager operation {operation!r} failed "
            f"for cameras: {failed_camera_ids}"
        )
