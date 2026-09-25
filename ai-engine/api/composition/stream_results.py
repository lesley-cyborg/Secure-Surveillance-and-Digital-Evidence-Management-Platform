from __future__ import annotations

from dataclasses import replace

import structlog

from addons.pipeline import AnalysisPipeline
from config.settings import Settings
from detection.schemas import DetectionResult
from streaming.detection_events import (
    StreamBoundingBox,
    StreamDetection,
    StreamDetectionEvent,
    StreamModelIdentity,
)
from streaming.domain import StreamFrame
from streaming.event_sink import (
    StreamDetectionEventSink,
)
from streaming.worker import DetectionResultHandler

logger = structlog.get_logger(__name__)


def build_stream_detection_event(
    *,
    frame: StreamFrame,
    result: DetectionResult,
) -> StreamDetectionEvent:
    """Combine camera context with a detection result."""

    return StreamDetectionEvent(
        correlation_id=result.correlation_id,
        camera_id=frame.camera_id,
        frame_sequence_number=(frame.sequence_number),
        captured_at=frame.captured_at,
        received_at=frame.received_at,
        processed_at=result.processed_at,
        model=StreamModelIdentity(
            name=result.model.name,
            version=result.model.version,
            device=result.model.device.value,
        ),
        detections=tuple(
            StreamDetection(
                class_id=detection.class_id,
                label=detection.label,
                confidence=detection.confidence,
                bounding_box=StreamBoundingBox(
                    x_min=(detection.bounding_box.x_min),
                    y_min=(detection.bounding_box.y_min),
                    x_max=(detection.bounding_box.x_max),
                    y_max=(detection.bounding_box.y_max),
                ),
            )
            for detection in result.detections
        ),
        inference_duration_ms=(result.inference_duration_ms),
    )


def create_stream_result_handler(
    *,
    sink: StreamDetectionEventSink,
    settings: Settings | None = None,
    addon_pipeline: AnalysisPipeline | None = None,
) -> DetectionResultHandler:
    """Create the worker callback that publishes events."""

    async def handle_result(
        frame: StreamFrame,
        result: object,
    ) -> None:
        if not isinstance(
            result,
            DetectionResult,
        ):
            raise TypeError("Stream processor returned an unsupported result type")

        event = build_stream_detection_event(
            frame=frame,
            result=result,
        )
        if (
            settings is not None
            and settings.addon_enabled
            and addon_pipeline is not None
        ):
            analysis = await addon_pipeline.analyze(
                frame.image,
                detections=tuple(
                    (detection.label, detection.confidence)
                    for detection in result.detections
                ),
                camera_id=frame.camera_id,
                sequence_number=frame.sequence_number,
            )
            logger.info(
                "addon_analysis_completed",
                camera_id=frame.camera_id,
                sequence_number=frame.sequence_number,
                threat_count=len(analysis.threat_signals),
                plate_count=len(analysis.plates),
                pose_count=len(analysis.poses),
                confirmed_pose_count=sum(pose.confirmed for pose in analysis.poses),
                degraded_capabilities=analysis.degraded_capabilities,
            )
            if settings.addon_event_v11_enabled:
                event = replace(
                    event,
                    schema_version="1.1",
                    analysis=analysis.model_dump(mode="json"),
                )

        await sink.publish(event)

    return handle_result
