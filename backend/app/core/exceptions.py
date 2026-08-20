from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class AppError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


async def app_error_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    if not isinstance(exception, AppError):
        raise exception

    return JSONResponse(
        status_code=exception.status_code,
        content={
            "error": {
                "code": exception.code,
                "message": exception.message,
                "details": exception.details,
                "correlationId": getattr(
                    request.state,
                    "correlation_id",
                    None,
                ),
            }
        },
    )
