from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Response,
    UploadFile,
    status,
)

from api.dependencies import (
    get_frame_processor,
    get_inference_gate,
    get_model_lifecycle,
    get_model_registry,
    get_settings_from_app,
)
from api.dependencies.core import get_vision_analyzer
from api.schemas import (
    ErrorResponse,
    HealthResponse,
    HealthStatus,
    LivenessResponse,
    ModelListResponse,
    ReadinessResponse,
)
from config.settings import Settings
from detection.exceptions import (
    FrameTooLargeError,
    UnsupportedMediaTypeError,
)
from detection.frame_processor import (
    FrameProcessor,
)
from detection.inference_gate import InferenceGate
from detection.model_registry import (
    ModelRegistry,
)
from detection.schemas import (
    DetectionRequest,
    DetectionResult,
    MediaType,
)
from models.lifecycle import (
    ModelLifecycleManager,
    ModelLifecycleState,
)
from vision.analysis import VisionAnalyzer
from vision.schemas import VisionAnalysisResult

router = APIRouter()


@router.post(
    "/api/v1/analyze/image",
    response_model=VisionAnalysisResult,
    tags=["vision"],
)
async def analyze_image(
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG or PNG surveillance frame")],
    processor: Annotated[FrameProcessor, Depends(get_frame_processor)],
    analyzer: Annotated[VisionAnalyzer, Depends(get_vision_analyzer)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    confidence_threshold: Annotated[float, Form(ge=0, le=1)] = 0.5,
    supplied_correlation_id: Annotated[
        UUID | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> VisionAnalysisResult:
    correlation_id = supplied_correlation_id or uuid4()
    response.headers["X-Correlation-ID"] = str(correlation_id)

    try:
        media_type = _resolve_media_type(
            content_type=file.content_type,
            correlation_id=correlation_id,
        )
        payload = await _read_limited_upload(
            file,
            maximum_bytes=settings.maximum_upload_bytes,
            chunk_size=settings.upload_chunk_size,
            correlation_id=correlation_id,
        )
        result = await processor.process_image(
            payload=payload,
            media_type=media_type,
            confidence_threshold=confidence_threshold,
            correlation_id=correlation_id,
        )
        decoded = processor.decoder.decode_image(payload, media_type)
        return await analyzer.analyze(
            decoded.image,
            detections=tuple(
                (detection.label, detection.confidence)
                for detection in result.detections
            ),
        )
    finally:
        await file.close()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
)
def health_check(
    settings: Annotated[
        Settings,
        Depends(get_settings_from_app),
    ],
    registry: Annotated[
        ModelRegistry,
        Depends(get_model_registry),
    ],
) -> HealthResponse:
    models = registry.list_models()

    ready_models = sum(model.is_ready for model in models)

    health_status = (
        HealthStatus.HEALTHY
        if models and ready_models == len(models)
        else HealthStatus.DEGRADED
    )

    return HealthResponse(
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.environment,
        status=health_status,
        registered_models=len(models),
        ready_models=ready_models,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    tags=["health"],
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
        }
    },
)
async def readiness_check(
    response: Response,
    settings: Annotated[
        Settings,
        Depends(get_settings_from_app),
    ],
    registry: Annotated[
        ModelRegistry,
        Depends(get_model_registry),
    ],
    lifecycle: Annotated[
        ModelLifecycleManager,
        Depends(get_model_lifecycle),
    ],
    inference_gate: Annotated[
        InferenceGate,
        Depends(get_inference_gate),
    ],
) -> ReadinessResponse:
    models = registry.list_models()

    ready_models = sum(model.is_ready for model in models)

    model_registry_ready = bool(models) and ready_models == len(models)

    lifecycle_ready = (
        lifecycle.state is ModelLifecycleState.READY
        if settings.production_model_enabled
        else True
    )

    ready = model_registry_ready and lifecycle_ready

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    gate = await inference_gate.snapshot()

    return ReadinessResponse(
        service=settings.service_name,
        version=settings.service_version,
        ready=ready,
        lifecycle_state=(lifecycle.state.value),
        lifecycle_error=(lifecycle.last_error),
        registered_models=len(models),
        ready_models=ready_models,
        maximum_concurrent_inferences=(gate.maximum_concurrent),
        active_inferences=gate.active,
        queued_inferences=gate.waiting,
    )


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    tags=["health"],
)
def liveness_check(
    settings: Annotated[
        Settings,
        Depends(get_settings_from_app),
    ],
) -> LivenessResponse:
    return LivenessResponse(
        service=settings.service_name,
        version=settings.service_version,
    )


@router.get(
    "/api/v1/models",
    response_model=ModelListResponse,
    tags=["models"],
)
def list_models(
    registry: Annotated[
        ModelRegistry,
        Depends(get_model_registry),
    ],
) -> ModelListResponse:
    models = registry.list_models()

    return ModelListResponse(
        items=models,
        total=len(models),
    )


@router.post(
    "/api/v1/detect/image",
    response_model=DetectionResult,
    status_code=status.HTTP_200_OK,
    tags=["detection"],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
        },
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "model": ErrorResponse,
        },
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
        },
    },
)
async def detect_image(
    response: Response,
    file: Annotated[
        UploadFile,
        File(description=("JPEG or PNG surveillance frame")),
    ],
    processor: Annotated[
        FrameProcessor,
        Depends(get_frame_processor),
    ],
    settings: Annotated[
        Settings,
        Depends(get_settings_from_app),
    ],
    model_name: Annotated[
        str | None,
        Form(
            min_length=1,
            max_length=128,
        ),
    ] = None,
    model_version: Annotated[
        str | None,
        Form(
            min_length=1,
            max_length=64,
        ),
    ] = None,
    confidence_threshold: Annotated[
        float,
        Form(ge=0, le=1),
    ] = 0.5,
    supplied_correlation_id: Annotated[
        UUID | None,
        Header(alias="X-Correlation-ID"),
    ] = None,
) -> DetectionResult:
    correlation_id = supplied_correlation_id or uuid4()

    response.headers["X-Correlation-ID"] = str(correlation_id)

    try:
        media_type = _resolve_media_type(
            content_type=file.content_type,
            correlation_id=correlation_id,
        )

        payload = await _read_limited_upload(
            file,
            maximum_bytes=(settings.maximum_upload_bytes),
            chunk_size=(settings.upload_chunk_size),
            correlation_id=correlation_id,
        )
    finally:
        await file.close()

    request_data = DetectionRequest(
        model_name=model_name,
        model_version=model_version,
        confidence_threshold=(confidence_threshold),
    )

    return await processor.process_image(
        payload=payload,
        media_type=media_type,
        confidence_threshold=(request_data.confidence_threshold),
        model_name=request_data.model_name,
        model_version=(request_data.model_version),
        correlation_id=correlation_id,
    )


def _resolve_media_type(
    *,
    content_type: str | None,
    correlation_id: UUID,
) -> MediaType:
    if content_type is None:
        raise UnsupportedMediaTypeError(
            "A Content-Type is required for the uploaded image",
            correlation_id=correlation_id,
        )

    try:
        return MediaType(content_type.casefold())
    except ValueError as exception:
        raise UnsupportedMediaTypeError(
            "Only image/jpeg and image/png uploads are supported",
            correlation_id=correlation_id,
        ) from exception


async def _read_limited_upload(
    upload: UploadFile,
    *,
    maximum_bytes: int,
    chunk_size: int,
    correlation_id: UUID,
) -> bytes:
    payload = bytearray()

    while chunk := await upload.read(chunk_size):
        payload.extend(chunk)

        if len(payload) > maximum_bytes:
            raise FrameTooLargeError(
                "The uploaded image exceeds the maximum permitted size",
                correlation_id=correlation_id,
            )

    return bytes(payload)
