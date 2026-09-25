from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import numpy as np
import pytest

from addons.pipeline import AnalysisPipeline
from addons.schemas import AddonAnalysisResult, BoundingBox, PoseObservation
from api.composition.stream_results import (
    build_stream_detection_event,
    create_stream_result_handler,
)
from config.settings import Settings
from detection.schemas import (
    Detection,
    DetectionResult,
    DeviceType,
    FrameMetadata,
    MediaType,
    ModelIdentity,
    NormalisedBoundingBox,
)
from streaming.detection_events import (
    StreamDetectionEvent,
)
from streaming.domain import StreamFrame
from streaming.event_sink import (
    NullStreamDetectionEventSink,
    StreamDetectionEventSink,
)


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[
            StreamDetectionEvent
        ] = []

    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        self.events.append(event)


class FailingEventSink:
    async def publish(
        self,
        event: StreamDetectionEvent,
    ) -> None:
        del event

        raise RuntimeError(
            "event delivery failed"
        )


def create_frame() -> StreamFrame:
    captured_at = datetime.now(UTC)

    return StreamFrame(
        camera_id="camera-001",
        sequence_number=7,
        captured_at=captured_at,
        received_at=(
            captured_at
            + timedelta(milliseconds=15)
        ),
        image=np.zeros(
            (100, 200, 3),
            dtype=np.uint8,
        ),
    )


def create_result(
    *,
    correlation_id: UUID | None = None,
) -> DetectionResult:
    return DetectionResult(
        correlation_id=(
            correlation_id or uuid4()
        ),
        model=ModelIdentity(
            name="surveillance-yolo",
            version="yolo26n-coco",
            device=DeviceType.CPU,
            labels=("person",),
        ),
        frame=FrameMetadata(
            width=200,
            height=100,
            channels=3,
            media_type=MediaType.JPEG,
            byte_size=1024,
        ),
        detections=(
            Detection(
                class_id=0,
                label="person",
                confidence=0.94,
                bounding_box=(
                    NormalisedBoundingBox(
                        x_min=0.1,
                        y_min=0.2,
                        x_max=0.8,
                        y_max=0.9,
                    )
                ),
            ),
        ),
        inference_duration_ms=8.5,
        processed_at=datetime.now(UTC),
    )


def test_build_event_maps_all_required_fields() -> None:
    frame = create_frame()
    result = create_result()

    event = build_stream_detection_event(
        frame=frame,
        result=result,
    )

    assert (
        event.correlation_id
        == result.correlation_id
    )
    assert event.camera_id == frame.camera_id
    assert (
        event.frame_sequence_number
        == frame.sequence_number
    )
    assert event.captured_at == frame.captured_at
    assert event.received_at == frame.received_at
    assert event.processed_at == result.processed_at

    assert event.model.name == result.model.name
    assert (
        event.model.version
        == result.model.version
    )
    assert event.model.device == "cpu"

    assert event.inference_duration_ms == 8.5
    assert event.detection_count == 1

    detection = event.detections[0]

    assert detection.class_id == 0
    assert detection.label == "person"
    assert detection.confidence == 0.94
    assert detection.bounding_box.x_min == 0.1
    assert detection.bounding_box.y_min == 0.2
    assert detection.bounding_box.x_max == 0.8
    assert detection.bounding_box.y_max == 0.9


async def test_result_handler_publishes_event() -> None:
    sink = RecordingEventSink()

    assert isinstance(
        sink,
        StreamDetectionEventSink,
    )

    handler = create_stream_result_handler(
        sink=sink,
    )

    frame = create_frame()
    result = create_result()

    await handler(
        frame,
        result,
    )

    assert len(sink.events) == 1

    event = sink.events[0]

    assert event.camera_id == "camera-001"
    assert event.frame_sequence_number == 7
    assert (
        event.correlation_id
        == result.correlation_id
    )


async def test_result_handler_passes_camera_sequence_to_addon_and_emits_v11() -> None:
    class ConfirmingPipeline(AnalysisPipeline):
        def __init__(self) -> None:
            self.context: tuple[str | None, int | None] | None = None

        async def analyze(
            self,
            frame: np.ndarray,
            *,
            detections: tuple[tuple[str, float], ...],
            camera_id: str | None = None,
            sequence_number: int | None = None,
        ) -> AddonAnalysisResult:
            del frame, detections
            self.context = (camera_id, sequence_number)
            return AddonAnalysisResult(
                poses=(
                    PoseObservation(
                        posture="person",
                        confidence=0.9,
                        bounding_box=BoundingBox(
                            x_min=0.1,
                            y_min=0.1,
                            x_max=0.5,
                            y_max=0.8,
                        ),
                        confirmed=True,
                    ),
                ),
            )

    sink = RecordingEventSink()
    pipeline = ConfirmingPipeline()
    settings = Settings(
        _env_file=None,
        addon_enabled=True,
        addon_event_v11_enabled=True,
    )
    handler = create_stream_result_handler(
        sink=sink,
        settings=settings,
        addon_pipeline=pipeline,
    )
    frame = create_frame()

    await handler(frame, create_result())

    assert pipeline.context == (frame.camera_id, frame.sequence_number)
    assert sink.events[0].schema_version == "1.1"
    assert sink.events[0].analysis is not None
    analysis = sink.events[0].analysis
    assert analysis is not None
    poses = analysis["poses"]
    assert isinstance(poses, list)
    assert poses[0]["confirmed"] is True


async def test_result_handler_rejects_unknown_result() -> None:
    handler = create_stream_result_handler(
        sink=NullStreamDetectionEventSink(),
    )

    with pytest.raises(
        TypeError,
        match="unsupported result type",
    ):
        await handler(
            create_frame(),
            object(),
        )


async def test_sink_failure_propagates() -> None:
    handler = create_stream_result_handler(
        sink=FailingEventSink(),
    )

    with pytest.raises(
        RuntimeError,
        match="event delivery failed",
    ):
        await handler(
            create_frame(),
            create_result(),
        )


async def test_null_sink_accepts_event() -> None:
    sink = NullStreamDetectionEventSink()

    event = build_stream_detection_event(
        frame=create_frame(),
        result=create_result(),
    )

    await sink.publish(event)