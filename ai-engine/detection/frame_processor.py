from __future__ import annotations

import asyncio
from time import perf_counter
from uuid import UUID, uuid4

import structlog

from detection.exceptions import (
    DetectionEngineError,
    DetectorUnavailableError,
    InferenceError,
    InvalidConfidenceError,
)
from detection.frame_decoder import FrameDecoder
from detection.inference_gate import (
    InferenceGate,
)
from detection.model_registry import (
    ModelRegistry,
)
from detection.schemas import (
    Detection,
    DetectionResult,
    MediaType,
)

logger = structlog.get_logger(__name__)


class FrameProcessor:
    def __init__(
        self,
        *,
        registry: ModelRegistry,
        decoder: FrameDecoder,
        inference_gate: InferenceGate | None = None,
    ) -> None:
        self.registry = registry
        self.decoder = decoder
        self.inference_gate = inference_gate or InferenceGate(
            maximum_concurrent=1,
            queue_timeout_seconds=30.0,
        )

    async def process_image(
        self,
        *,
        payload: bytes,
        media_type: MediaType | str,
        confidence_threshold: float = 0.5,
        model_name: str | None = None,
        model_version: str | None = None,
        correlation_id: UUID | None = None,
    ) -> DetectionResult:
        resolved_correlation_id = correlation_id or uuid4()

        bound_logger = logger.bind(
            correlation_id=str(resolved_correlation_id),
            requested_model_name=model_name,
            requested_model_version=(model_version),
        )

        try:
            self._validate_confidence_threshold(confidence_threshold)

            detector = self.registry.resolve(
                name=model_name,
                version=model_version,
            )

            identity = detector.identity

            bound_logger = bound_logger.bind(
                model_name=identity.name,
                model_version=identity.version,
                inference_device=(identity.device.value),
            )

            if not detector.is_ready:
                raise DetectorUnavailableError(
                    "The selected detector is not ready for inference",
                    correlation_id=(resolved_correlation_id),
                )

            decoded = self.decoder.decode_image(
                payload,
                media_type,
            )

            async with self.inference_gate.acquire(
                correlation_id=resolved_correlation_id,
            ):
                started_at = perf_counter()

                raw_detections = await asyncio.to_thread(
                    detector.detect,
                    decoded.image,
                )

                inference_duration_ms = (perf_counter() - started_at) * 1_000

            detections = tuple(
                Detection(
                    class_id=detection.class_id,
                    label=detection.label,
                    confidence=(detection.confidence),
                    bounding_box=(
                        detection.bounding_box.normalise(
                            frame_width=(decoded.metadata.width),
                            frame_height=(decoded.metadata.height),
                        )
                    ),
                )
                for detection in raw_detections
                if detection.confidence >= confidence_threshold
            )

            result = DetectionResult(
                correlation_id=(resolved_correlation_id),
                model=identity,
                frame=decoded.metadata,
                detections=detections,
                inference_duration_ms=(inference_duration_ms),
            )

            bound_logger.info(
                "inference_completed",
                frame_width=(decoded.metadata.width),
                frame_height=(decoded.metadata.height),
                confidence_threshold=(confidence_threshold),
                detection_count=len(detections),
                inference_duration_ms=round(
                    inference_duration_ms,
                    3,
                ),
            )

            return result

        except DetectionEngineError as exc:
            if exc.correlation_id is None:
                exc.correlation_id = resolved_correlation_id

            bound_logger.warning(
                "inference_rejected",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

            raise

        except Exception as exc:
            bound_logger.exception(
                "inference_failed",
                error_type=type(exc).__name__,
            )

            raise InferenceError(
                "Detector inference failed",
                correlation_id=(resolved_correlation_id),
            ) from exc

    @staticmethod
    def _validate_confidence_threshold(
        threshold: float,
    ) -> None:
        if not 0 <= threshold <= 1:
            raise InvalidConfidenceError("Confidence threshold must be between 0 and 1")

 
    
    
