from __future__ import annotations

from typing import Protocol, runtime_checkable

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
)


@runtime_checkable
class StreamSource(Protocol):
    """Contract implemented by camera-stream adapters."""

    @property
    def config(self) -> CameraStreamConfig:
        """Return immutable source configuration."""

    @property
    def is_open(self) -> bool:
        """Return whether the source is currently open."""

    def open(self) -> None:
        """Open the underlying camera stream."""

    def read(self) -> StreamFrame:
        """Read and decode the next frame."""

    def close(self) -> None:
        """Release the underlying camera stream."""
