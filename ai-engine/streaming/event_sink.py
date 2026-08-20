from __future__ import annotations

from typing import Protocol, runtime_checkable

from streaming.detection_events import StreamDetectionEvent


class StreamDetectionEventDeliveryError(Exception):
    """Base exception for event-delivery failures."""


class PermanentStreamDetectionEventDeliveryError(StreamDetectionEventDeliveryError):
    """A delivery failure that must not be retried."""


@runtime_checkable
class StreamDetectionEventSink(Protocol):
    """Destination for camera detection events."""

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None: ...


@runtime_checkable
class ManagedStreamDetectionEventSink(
    StreamDetectionEventSink,
    Protocol,
):
    """Event sink with application lifecycle cleanup."""

    async def shutdown(self) -> None: ...


class NullStreamDetectionEventSink:
    """Destination that intentionally discards events."""

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        del event

    async def shutdown(self) -> None:
        """Perform no-op lifecycle cleanup."""
