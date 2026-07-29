from __future__ import annotations

from http import HTTPStatus
from typing import Final

import structlog
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from detection.exceptions import (
    DefaultDetectorNotConfiguredError,
    DetectionEngineError,
    DetectorNotFoundError,
    DetectorUnavailableError,
    EmptyFrameError,
    FrameTooLargeError,
    InferenceError,
    InferenceOverloadedError,
    InvalidBoundingBoxError,
    InvalidConfidenceError,
    InvalidFrameError,
    UnsupportedMediaTypeError,
)

logger = structlog.get_logger(__name__)


_ERROR_STATUS_MAP: Final[
    tuple[
        tuple[
            type[DetectionEngineError],
            HTTPStatus,
        ],
        ...,
    ]
] = (
    (
        UnsupportedMediaTypeError,
        HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    ),
    (
        FrameTooLargeError,
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ),
    (
        DetectorNotFoundError,
        HTTPStatus.NOT_FOUND,
    ),
    (
        DefaultDetectorNotConfiguredError,
        HTTPStatus.SERVICE_UNAVAILABLE,
    ),
    (
        DetectorUnavailableError,
        HTTPStatus.SERVICE_UNAVAILABLE,
    ),
    (
        EmptyFrameError,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    ),
    (
        InvalidFrameError,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    ),
    (
        InvalidBoundingBoxError,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    ),
    (
        InvalidConfidenceError,
        HTTPStatus.UNPROCESSABLE_ENTITY,
    ),
    (
        InferenceError,
        HTTPStatus.INTERNAL_SERVER_ERROR,
    ),
    (
        InferenceOverloadedError,
        HTTPStatus.TOO_MANY_REQUESTS,
    ),
)


def _status_for_exception(
    exception: DetectionEngineError,
) -> HTTPStatus:
    for exception_type, status_code in _ERROR_STATUS_MAP:
        if isinstance(
            exception,
            exception_type,
        ):
            return status_code

    return HTTPStatus.INTERNAL_SERVER_ERROR


def register_exception_handlers(
    app: FastAPI,
) -> None:
    @app.exception_handler(DetectionEngineError)
    async def handle_detection_engine_error(
        request: Request,
        exception: DetectionEngineError,
    ) -> JSONResponse:
        status_code = _status_for_exception(exception)

        correlation_id = (
            str(exception.correlation_id)
            if exception.correlation_id is not None
            else None
        )

        logger.warning(
            "detection_api_request_rejected",
            path=request.url.path,
            method=request.method,
            status_code=int(status_code),
            error_type=type(exception).__name__,
            correlation_id=correlation_id,
        )

        headers: dict[str, str] = {}

        if correlation_id is not None:
            headers["X-Correlation-ID"] = correlation_id

        return JSONResponse(
            status_code=int(status_code),
            content={
                "error_code": type(exception).__name__,
                "message": str(exception),
                "correlation_id": (correlation_id),
            },
            headers=headers,
        )
