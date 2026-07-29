from __future__ import annotations

from typing import NoReturn

import structlog
from fastapi import (
    APIRouter,
    HTTPException,
    Response,
    status,
)

from api.dependencies.streams import (
    StreamManagerDependency,
    StreamWorkerFactoryDependency,
)
from api.schemas.streams import (
    CameraStreamRegistrationRequest,
    CameraStreamStatusResponse,
    StreamManagerStatusResponse,
)
from streaming.exceptions import (
    StreamManagerClosedError,
    StreamManagerOperationError,
    StreamWorkerAlreadyRegisteredError,
    StreamWorkerDisposedError,
    StreamWorkerNotRegisteredError,
)
from streaming.manager import (
    ManagedStreamWorker,
    StreamManager,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/streams",
    tags=["camera-streams"],
)


async def _worker_response(
    worker: ManagedStreamWorker,
) -> CameraStreamStatusResponse:
    snapshot = await worker.snapshot()

    return CameraStreamStatusResponse(
        camera_id=worker.config.camera_id,
        state=snapshot.runtime.state,
        running=snapshot.running,
        disposed=snapshot.disposed,
    )


async def _manager_response(
    manager: StreamManager,
) -> StreamManagerStatusResponse:
    snapshot = await manager.snapshot()

    return StreamManagerStatusResponse(
        closed=snapshot.closed,
        total_workers=(snapshot.total_workers),
        running_workers=(snapshot.running_workers),
        failed_workers=(snapshot.failed_workers),
        disposed_workers=(snapshot.disposed_workers),
        workers=tuple(
            CameraStreamStatusResponse(
                camera_id=worker.camera_id,
                state=worker.state,
                running=worker.running,
                disposed=worker.disposed,
            )
            for worker in snapshot.workers
        ),
    )


async def _dispose_safely(
    worker: ManagedStreamWorker,
) -> None:
    try:
        await worker.dispose()
    except Exception as exception:
        # Never log exception text because a third-party
        # implementation could include a source URI.
        logger.warning(
            "unregistered_stream_cleanup_failed",
            camera_id=(worker.config.camera_id),
            error_type=(type(exception).__name__),
        )


def _raise_known_error(
    exception: BaseException,
) -> NoReturn:
    if isinstance(
        exception,
        StreamWorkerAlreadyRegisteredError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STREAM_ALREADY_REGISTERED",
                "message": ("A stream is already registered for this camera."),
            },
        ) from None

    if isinstance(
        exception,
        StreamWorkerNotRegisteredError,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "STREAM_NOT_FOUND",
                "message": ("The requested camera stream is not registered."),
            },
        ) from None

    if isinstance(
        exception,
        StreamManagerClosedError,
    ):
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "STREAM_MANAGER_CLOSED",
                "message": ("Camera stream management has been shut down."),
            },
        ) from None

    if isinstance(
        exception,
        StreamWorkerDisposedError,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STREAM_WORKER_DISPOSED",
                "message": ("The camera stream worker has already been disposed."),
            },
        ) from None

    if isinstance(
        exception,
        StreamManagerOperationError,
    ):
        failed_camera_ids = sorted(exception.failures)

        logger.warning(
            "stream_batch_operation_failed",
            operation=exception.operation,
            failed_camera_ids=(failed_camera_ids),
            error_types={
                camera_id: type(worker_error).__name__
                for (
                    camera_id,
                    worker_error,
                ) in exception.failures.items()
            },
        )

        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "STREAM_BATCH_OPERATION_FAILED",
                "message": ("One or more camera stream operations failed."),
                "operation": (exception.operation),
                "failed_camera_ids": (failed_camera_ids),
            },
        ) from None

    raise RuntimeError("Unsupported stream API exception")


@router.post(
    "",
    response_model=CameraStreamStatusResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="registerCameraStream",
)
async def register_camera_stream(
    payload: CameraStreamRegistrationRequest,
    manager: StreamManagerDependency,
    factory: StreamWorkerFactoryDependency,
) -> CameraStreamStatusResponse:
    worker: ManagedStreamWorker | None = None

    try:
        config = payload.to_domain()
        worker = factory.create(config)

        await manager.register(worker)

        logger.info(
            "camera_stream_registered",
            camera_id=config.camera_id,
        )

        return await _worker_response(worker)

    except (
        StreamWorkerAlreadyRegisteredError,
        StreamManagerClosedError,
        StreamWorkerDisposedError,
    ) as exception:
        if worker is not None:
            await _dispose_safely(worker)

        _raise_known_error(exception)

    except (TypeError, ValueError) as exception:
        if worker is not None:
            await _dispose_safely(worker)

        logger.warning(
            "camera_stream_configuration_rejected",
            camera_id=payload.camera_id,
            error_type=(type(exception).__name__),
        )

        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
            detail={
                "code": "INVALID_STREAM_CONFIGURATION",
                "message": ("The camera stream configuration is invalid."),
            },
        ) from None

    except Exception as exception:
        if worker is not None:
            await _dispose_safely(worker)

        logger.error(
            "camera_stream_registration_failed",
            camera_id=payload.camera_id,
            error_type=(type(exception).__name__),
        )

        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail={
                "code": "STREAM_REGISTRATION_FAILED",
                "message": ("The camera stream could not be registered."),
            },
        ) from None


@router.get(
    "",
    response_model=StreamManagerStatusResponse,
    operation_id="listCameraStreams",
)
async def list_camera_streams(
    manager: StreamManagerDependency,
) -> StreamManagerStatusResponse:
    return await _manager_response(manager)


@router.get(
    "/{camera_id}",
    response_model=CameraStreamStatusResponse,
    operation_id="getCameraStream",
)
async def get_camera_stream(
    camera_id: str,
    manager: StreamManagerDependency,
) -> CameraStreamStatusResponse:
    try:
        worker = await manager.get(camera_id)
    except StreamWorkerNotRegisteredError as exception:
        _raise_known_error(exception)

    return await _worker_response(worker)


@router.post(
    "/{camera_id}/start",
    response_model=CameraStreamStatusResponse,
    operation_id="startCameraStream",
)
async def start_camera_stream(
    camera_id: str,
    manager: StreamManagerDependency,
) -> CameraStreamStatusResponse:
    try:
        await manager.start(camera_id)
        worker = await manager.get(camera_id)
    except (
        StreamWorkerNotRegisteredError,
        StreamManagerClosedError,
        StreamWorkerDisposedError,
    ) as exception:
        _raise_known_error(exception)
    except Exception as exception:
        logger.error(
            "camera_stream_start_failed",
            camera_id=camera_id,
            error_type=(type(exception).__name__),
        )

        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "STREAM_START_FAILED",
                "message": ("The camera stream could not be started."),
            },
        ) from None

    return await _worker_response(worker)


@router.post(
    "/{camera_id}/stop",
    response_model=CameraStreamStatusResponse,
    operation_id="stopCameraStream",
)
async def stop_camera_stream(
    camera_id: str,
    manager: StreamManagerDependency,
) -> CameraStreamStatusResponse:
    try:
        await manager.stop(camera_id)
        worker = await manager.get(camera_id)
    except (
        StreamWorkerNotRegisteredError,
        StreamManagerClosedError,
    ) as exception:
        _raise_known_error(exception)
    except Exception as exception:
        logger.error(
            "camera_stream_stop_failed",
            camera_id=camera_id,
            error_type=(type(exception).__name__),
        )

        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "STREAM_STOP_FAILED",
                "message": ("The camera stream could not be stopped."),
            },
        ) from None

    return await _worker_response(worker)


@router.delete(
    "/{camera_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="unregisterCameraStream",
)
async def unregister_camera_stream(
    camera_id: str,
    manager: StreamManagerDependency,
) -> Response:
    try:
        await manager.unregister(
            camera_id,
            dispose=True,
        )
    except (
        StreamWorkerNotRegisteredError,
        StreamManagerClosedError,
    ) as exception:
        _raise_known_error(exception)

    logger.info(
        "camera_stream_unregistered",
        camera_id=camera_id,
    )

    return Response(status_code=(status.HTTP_204_NO_CONTENT))


@router.post(
    "/actions/start-all",
    response_model=StreamManagerStatusResponse,
    operation_id="startAllCameraStreams",
)
async def start_all_camera_streams(
    manager: StreamManagerDependency,
) -> StreamManagerStatusResponse:
    try:
        await manager.start_all()
    except (
        StreamManagerClosedError,
        StreamManagerOperationError,
    ) as exception:
        _raise_known_error(exception)

    return await _manager_response(manager)


@router.post(
    "/actions/stop-all",
    response_model=StreamManagerStatusResponse,
    operation_id="stopAllCameraStreams",
)
async def stop_all_camera_streams(
    manager: StreamManagerDependency,
) -> StreamManagerStatusResponse:
    try:
        await manager.stop_all()
    except (
        StreamManagerClosedError,
        StreamManagerOperationError,
    ) as exception:
        _raise_known_error(exception)

    return await _manager_response(manager)
