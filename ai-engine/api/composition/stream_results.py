from __future__ import annotations
from typing import TYPE_CHECKING
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
from streaming.event_sink import StreamDetectionEventSink
from streaming.worker import DetectionResultHandler

if TYPE_CHECKING:
    from addons.pipeline import AnalysisPipeline
    from config.settings import Settings


def build_stream_detection_event(
    *,
    frame: StreamFrame,
    result: DetectionResult,
) -> StreamDetectionEvent:
    """Combine camera context with a detection result."""
    
    # 1. Safely get the analysis data (if it was attached by the pipeline)
    analysis_data = getattr(result, "analysis", None)
    
    # 2. Explicitly set schema version based on whether analysis data exists
    schema_ver = "1.1" if analysis_data is not None else "1.0"

    return StreamDetectionEvent(
        correlation_id=result.correlation_id,
        camera_id=frame.camera_id,
        frame_sequence_number=frame.sequence_number,
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
                    x_min=detection.bounding_box.x_min,
                    y_min=detection.bounding_box.y_min,
                    x_max=detection.bounding_box.x_max,
                    y_max=detection.bounding_box.y_max,
                ),
            )
            for detection in result.detections
        ),
        inference_duration_ms=result.inference_duration_ms,
        schema_version=schema_ver,  # <-- Explicitly set this to match the data!
        analysis=analysis_data,
    )


def create_stream_result_handler(
    *,
    sink: StreamDetectionEventSink,
    settings: Settings,
    addon_pipeline: AnalysisPipeline | None = None,
) -> DetectionResultHandler:
    """Create the worker callback that publishes detection events."""

    async def handle_result(
        frame: StreamFrame,
        result: object,
    ) -> None:
        if not isinstance(result, DetectionResult):
            raise TypeError("Stream processor returned an unsupported result type")

        # 1. Run the add-on pipeline (threat, plates, pose) if available
        if addon_pipeline is not None:
            # Extract primary detections to pass to the addon pipeline
            primary_detections = [(d.label, d.confidence) for d in result.detections]
            
            # Run the analysis (this triggers weapons.pt, etc.)
            analysis_result = await addon_pipeline.analyze(
                frame=frame.image,
                detections=primary_detections,
                camera_id=frame.camera_id,
                sequence_number=frame.sequence_number,
            )
            
            # 2. Attach the analysis result to the DetectionResult
            if hasattr(result, "model_copy"):
                # If DetectionResult is a Pydantic model
                result = result.model_copy(update={"analysis": analysis_result})
            elif dataclasses.is_dataclass(result):
                # If DetectionResult is a dataclass
                result = dataclasses.replace(result, analysis=analysis_result)
            else:
                # Fallback
                result.analysis = analysis_result

        # 3. Build and publish the event
        event = build_stream_detection_event(frame=frame, result=result)
        await sink.publish(event)

    return handle_result