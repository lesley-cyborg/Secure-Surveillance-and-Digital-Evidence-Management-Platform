from __future__ import annotations

from config.settings import Settings
from streaming.detection_dispatcher import (
    DetectionEventDispatcher,
    DetectionEventDispatcherConfig,
    EventQueueOverflowPolicy,
)
from streaming.event_sink import (
    StreamDetectionEventSink,
)


def build_detection_event_dispatcher(
    *,
    settings: Settings,
    destination: StreamDetectionEventSink,
    dead_letter_sink: (StreamDetectionEventSink | None) = None,
) -> DetectionEventDispatcher:
    """Build the application detection-event dispatcher."""

    return DetectionEventDispatcher(
        destination=destination,
        dead_letter_sink=dead_letter_sink,
        config=DetectionEventDispatcherConfig(
            queue_capacity=(settings.stream_event_queue_capacity),
            delivery_workers=(settings.stream_event_delivery_workers),
            delivery_timeout_seconds=(settings.stream_event_delivery_timeout_seconds),
            retry_initial_delay_seconds=(
                settings.stream_event_retry_initial_delay_seconds
            ),
            retry_multiplier=(settings.stream_event_retry_multiplier),
            retry_maximum_delay_seconds=(
                settings.stream_event_retry_maximum_delay_seconds
            ),
            maximum_delivery_attempts=(settings.stream_event_retry_maximum_attempts),
            shutdown_timeout_seconds=(settings.stream_event_shutdown_timeout_seconds),
            overflow_policy=(
                EventQueueOverflowPolicy(settings.stream_event_overflow_policy)
            ),
        ),
    )
