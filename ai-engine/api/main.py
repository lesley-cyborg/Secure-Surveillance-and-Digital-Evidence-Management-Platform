from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from api.composition.backend_sink import (
    build_backend_incident_sink,
)
from api.composition.stream_dispatcher import (
    build_detection_event_dispatcher,
)
from api.composition.streams import (
    build_stream_worker_factory,
)
from api.error_handlers import (
    install_safe_validation_error_handler,
)
from api.errors import register_exception_handlers
from api.router import router
from api.routes.streams import router as streams_router
from config.settings import Settings, get_settings
from detection.frame_decoder import FrameDecoder
from detection.frame_processor import FrameProcessor
from detection.inference_gate import InferenceGate
from detection.model_registry import ModelRegistry
from models.factory import create_production_detector
from models.lifecycle import ModelLifecycleManager
from streaming.event_sink import (
    ManagedStreamDetectionEventSink,
    StreamDetectionEventSink,
)
from streaming.factory import StreamWorkerFactory
from streaming.manager import StreamManager

logger = structlog.get_logger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    registry: ModelRegistry | None = None,
    lifecycle: ModelLifecycleManager | None = None,
    stream_worker_factory: StreamWorkerFactory | None = None,
    stream_detection_sink: StreamDetectionEventSink | None = None,
    stream_dead_letter_sink: StreamDetectionEventSink | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_registry = registry or ModelRegistry()

    resolved_lifecycle = lifecycle or ModelLifecycleManager(
        enabled=resolved_settings.production_model_enabled,
        registry=resolved_registry,
        detector_factory=lambda: create_production_detector(resolved_settings),
        warmup_runs=resolved_settings.model_warmup_runs,
    )

    decoder = FrameDecoder(
        maximum_bytes=resolved_settings.maximum_upload_bytes,
        maximum_width=resolved_settings.maximum_image_width,
        maximum_height=resolved_settings.maximum_image_height,
        maximum_pixels=resolved_settings.maximum_image_pixels,
    )

    inference_gate = InferenceGate(
        maximum_concurrent=(resolved_settings.maximum_concurrent_inferences),
        queue_timeout_seconds=(resolved_settings.inference_queue_timeout_seconds),
    )

    processor = FrameProcessor(
        registry=resolved_registry,
        decoder=decoder,
        inference_gate=inference_gate,
    )

    resolved_stream_detection_sink = (
        stream_detection_sink
        if stream_detection_sink is not None
        else build_backend_incident_sink(settings=resolved_settings)
    )

    stream_detection_dispatcher = build_detection_event_dispatcher(
        settings=resolved_settings,
        destination=(resolved_stream_detection_sink),
        dead_letter_sink=(stream_dead_letter_sink),
    )

    resolved_stream_worker_factory = (
        stream_worker_factory
        if stream_worker_factory is not None
        else build_stream_worker_factory(
            processor=processor,
            settings=resolved_settings,
            event_sink=(stream_detection_dispatcher),
        )
    )

    stream_manager = StreamManager()

    @asynccontextmanager
    async def lifespan(
        application: FastAPI,
    ) -> AsyncIterator[None]:
        del application

        logger.info("application_startup_started")

        try:
            await resolved_lifecycle.startup()
            await stream_detection_dispatcher.start()

            logger.info(
                "application_startup_finished",
                lifecycle_state=(resolved_lifecycle.state.value),
            )

            yield

        except Exception:
            logger.exception(
                "application_lifecycle_failed",
                lifecycle_state=(resolved_lifecycle.state.value),
                lifecycle_error=(resolved_lifecycle.last_error),
            )
            raise

        finally:
            logger.info(
                "application_shutdown_started",
                lifecycle_state=(resolved_lifecycle.state.value),
            )

            try:
                await stream_manager.shutdown()
            finally:
                try:
                    await stream_detection_dispatcher.shutdown()
                finally:
                    try:
                        if isinstance(
                            resolved_stream_detection_sink,
                            ManagedStreamDetectionEventSink,
                        ):
                            await resolved_stream_detection_sink.shutdown()
                    finally:
                        await resolved_lifecycle.shutdown()

            logger.info(
                "application_shutdown_finished",
                lifecycle_state=(resolved_lifecycle.state.value),
                lifecycle_error=(resolved_lifecycle.last_error),
            )

    application = FastAPI(
        title="Secure Surveillance AI Engine",
        description=(
            "Model-independent detection service for surveillance image processing."
        ),
        version=resolved_settings.service_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    application.state.settings = resolved_settings
    application.state.model_registry = resolved_registry
    application.state.frame_processor = processor
    application.state.model_lifecycle = resolved_lifecycle
    application.state.inference_gate = inference_gate

    application.state.stream_manager = stream_manager
    application.state.stream_worker_factory = resolved_stream_worker_factory
    application.state.stream_detection_sink = resolved_stream_detection_sink
    application.state.stream_detection_dispatcher = stream_detection_dispatcher

    @application.get(
        "/",
        include_in_schema=False,
    )
    async def root() -> RedirectResponse:
        return RedirectResponse(
            url="/docs",
            status_code=307,
        )

    application.include_router(router)

    application.include_router(
        streams_router,
        prefix="/api/v1",
    )

    register_exception_handlers(application)
    install_safe_validation_error_handler(application)

    return application


app = create_app()
