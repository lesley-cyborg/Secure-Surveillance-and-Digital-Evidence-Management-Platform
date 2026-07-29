from __future__ import annotations

from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)

from streaming.factory import (
    StreamWorkerFactory,
)
from streaming.manager import StreamManager


def get_stream_manager(
    request: Request,
) -> StreamManager:
    manager = getattr(
        request.app.state,
        "stream_manager",
        None,
    )

    if not isinstance(
        manager,
        StreamManager,
    ):
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "STREAM_MANAGER_UNAVAILABLE",
                "message": ("Camera stream management is currently unavailable."),
            },
        )

    return manager


def get_stream_worker_factory(
    request: Request,
) -> StreamWorkerFactory:
    factory = getattr(
        request.app.state,
        "stream_worker_factory",
        None,
    )

    if not isinstance(
        factory,
        StreamWorkerFactory,
    ):
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": "STREAM_FACTORY_UNAVAILABLE",
                "message": ("Camera stream registration is currently unavailable."),
            },
        )

    return factory


type StreamManagerDependency = Annotated[
    StreamManager,
    Depends(get_stream_manager),
]

type StreamWorkerFactoryDependency = Annotated[
    StreamWorkerFactory,
    Depends(get_stream_worker_factory),
]
