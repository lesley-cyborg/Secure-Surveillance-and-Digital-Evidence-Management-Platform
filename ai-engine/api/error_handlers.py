from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT


def install_safe_validation_error_handler(
    app: FastAPI,
) -> None:
    """Install a validation handler that never echoes request input."""

    @app.exception_handler(RequestValidationError)
    async def safe_validation_handler(
        _: Request,
        exception: RequestValidationError,
    ) -> JSONResponse:
        safe_errors: list[dict[str, object]] = []

        for error in exception.errors():
            safe_errors.append(
                {
                    "type": error.get(
                        "type",
                        "validation_error",
                    ),
                    "loc": error.get(
                        "loc",
                        (),
                    ),
                    "msg": error.get(
                        "msg",
                        "Invalid request value",
                    ),
                }
            )

        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": safe_errors,
            },
        )
