from __future__ import annotations

import asyncio
from typing import Protocol

import cv2

from addons.pipeline import AnalysisPipeline
from api.composition.stream_results import (
    create_stream_result_handler,
)
from config.settings import Settings
from detection.schemas import DetectionResult, MediaType
from integrations.backend.heartbeat_client import HeartbeatClient  # <-- ADDED IMPORT
from streaming.domain import (
    CameraStreamConfig,
    FrameArray,
    StreamFrame,
)
from streaming.event_sink import (
    NullStreamDetectionEventSink,
    StreamDetectionEventSink,
)
from streaming.factory import CallableStreamWorkerFactory
from streaming.frame_queue import LatestFrameQueue
from streaming.frame_sampler import FrameSampler
from streaming.opencv_rtsp_source import OpenCvRtspSource
from streaming.reconnect_policy import (
    ReconnectPolicy,
    ReconnectPolicyConfig,
)
from streaming.worker import (
    ContinuousDetectionWorker,
    FrameProcessingFunction,
)


class StreamImageProcessor(Protocol):
    """Detection interface required by stream composition."""

    async def process_image(
        self,
        *,
        payload: bytes,
        media_type: MediaType | str,
        confidence_threshold: float = 0.5,
    ) -> DetectionResult: ...


def _encode_frame_as_jpeg(
    image: FrameArray,
    *,
    quality: int,
) -> bytes:
    """Encode an OpenCV BGR frame as JPEG bytes."""

    success, encoded_image = cv2.imencode(
        ".jpg",
        image,
        [
            int(cv2.IMWRITE_JPEG_QUALITY),
            quality,
        ],
    )

    if not success:
        raise ValueError("Stream frame could not be encoded as JPEG")

    return encoded_image.tobytes()


def create_stream_frame_processor(
    *,
    processor: StreamImageProcessor,
    jpeg_quality: int,
) -> FrameProcessingFunction:
    """Adapt StreamFrame to FrameProcessor.process_image()."""

    if not 1 <= jpeg_quality <= 100:
        raise ValueError("jpeg_quality must be between 1 and 100")

    async def process_stream_frame(
        frame: StreamFrame,
        confidence_threshold: float,
    ) -> DetectionResult:
        payload = await asyncio.to_thread(
            _encode_frame_as_jpeg,
            frame.image,
            quality=jpeg_quality,
        )

        return await processor.process_image(
            payload=payload,
            media_type=MediaType.JPEG,
            confidence_threshold=confidence_threshold,
        )

    return process_stream_frame


def build_stream_worker_factory(
    *,
    processor: StreamImageProcessor,
    settings: Settings,
    event_sink: StreamDetectionEventSink | None = None,
    addon_pipeline: AnalysisPipeline | None = None,
) -> CallableStreamWorkerFactory:
    """Create the production camera-worker factory."""

    process_frame = create_stream_frame_processor(
        processor=processor,
        jpeg_quality=settings.stream_jpeg_quality,
    )

    resolved_event_sink = (
        event_sink if event_sink is not None else NullStreamDetectionEventSink()
    )

    result_handler = create_stream_result_handler(
        sink=resolved_event_sink,
        settings=settings,
        addon_pipeline=addon_pipeline,
    )

    reconnect_config = ReconnectPolicyConfig(
        initial_delay_seconds=(settings.stream_reconnect_initial_delay_seconds),
        multiplier=(settings.stream_reconnect_multiplier),
        maximum_delay_seconds=(settings.stream_reconnect_maximum_delay_seconds),
        jitter_ratio=(settings.stream_reconnect_jitter_ratio),
        maximum_attempts=(settings.stream_reconnect_maximum_attempts),
    )

    def build_worker(
        config: CameraStreamConfig,
    ) -> ContinuousDetectionWorker:
        
        # --- HEARTBEAT INJECTION START ---
        # Extract the token safely (it's a SecretStr in your settings)
        service_token = (
            settings.backend_service_token.get_secret_value() 
            if settings.backend_service_token else ""
        )
        
        heartbeat_client = HeartbeatClient(
            camera_id=config.camera_id,
            backend_url=settings.backend_base_url,
            service_token=service_token,
        )
        # --- HEARTBEAT INJECTION END ---

        return ContinuousDetectionWorker(
            config=config,
            source=OpenCvRtspSource(
                config=config,
            ),
            sampler=FrameSampler(
                target_fps=config.target_fps,
            ),
            frame_queue=LatestFrameQueue(
                capacity=config.queue_capacity,
            ),
            reconnect_policy=ReconnectPolicy(
                config=reconnect_config,
            ),
            process_frame=process_frame,
            result_handler=result_handler,
            heartbeat_client=heartbeat_client,  # <-- INJECTED HERE
        )

    return CallableStreamWorkerFactory(
        builder=build_worker,
    )